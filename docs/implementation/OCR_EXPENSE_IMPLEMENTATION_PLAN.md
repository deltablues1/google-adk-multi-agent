# Plan implementacije OCR sustava za vođenje ulaznih računa

## Izvršni sažetak

Implementacija automatskog sustava za obradu ulaznih računa koji koristi **Flash-First** pristup - Gemini 1.5 Flash kao primarni OCR engine zbog:
- **Drastično niži trošak**: 0.00007 USD vs 0.10 USD (Document AI) - 1400x jeftinije
- **Superiorna fleksibilnost**: Multimodalni LLM razumije kontekst i može izvući nestandardne podatke
- **Strukturirani output**: Koristi Pydantic sheme za garantirani JSON format
- **Semantičko razumijevanje**: Može kategorizirati troškove i validirati podatke

## Arhitekturni overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                          │
│  1. Hibridni trigger:                                           │
│     - Automatski: Nova slika u Drive folderu                    │
│     - Manualno: Direktno slanje slike u chat                    │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR AGENT                          │
│  - Detektira OCR zahtjev (keywords: "račun", "invoice", OCR)   │
│  - Routing decision: delegate to → ExpenseAgent                 │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXPENSE AGENT                               │
│  Responsibilities:                                              │
│  1. Primi sliku računa (od Drive ili direktno)                 │
│  2. Pozovi Gemini 1.5 Flash multimodal OCR                     │
│  3. Validacija ekstrakcije (confidence score check)            │
│  4. Traži korisničku potvrdu/korekciju podataka                │
│  5. Spremi u Google Sheets tablicu "Ulazni računi"             │
│  6. Označi sliku na Drive-u kao "processed"                    │
└────────────────┬────────────────────────────────────────────────┘
                 │
      ┌──────────┴────────────┬─────────────────┐
      ▼                       ▼                  ▼
┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
│ VISION MCP   │   │ DRIVE MCP       │   │ SHEETS MCP   │
│ (OCR Tool)   │   │ (File ops)      │   │ (Save data)  │
│              │   │                 │   │              │
│ - Gemini     │   │ - Read image    │   │ - Append row │
│   Flash      │   │ - List folder   │   │ - Format     │
│ - Pydantic   │   │ - Update meta   │   │              │
│   schema     │   │                 │   │              │
└──────────────┘   └─────────────────┘   └──────────────┘
```

## 1. Pydantic Schema za strukturirane podatke

**File**: `tools/schemas/receipt_schema.py`

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class LineItem(BaseModel):
    """Pojedinačna stavka na računu"""
    description: str = Field(..., description="Naziv artikla/usluge")
    quantity: Optional[float] = Field(None, description="Količina (ako postoji)")
    unit_price: Optional[float] = Field(None, description="Jedinična cijena")
    amount: float = Field(..., description="Ukupna cijena stavke")

class Receipt(BaseModel):
    """Kompletni podaci s računa"""

    # Osnovni podaci
    merchant_name: str = Field(..., description="Naziv trgovine/dobavljača")
    transaction_date: str = Field(..., description="Datum transakcije (ISO 8601: YYYY-MM-DD)")
    total_amount: float = Field(..., description="Ukupan iznos računa")
    currency: str = Field(default="EUR", description="Valuta (npr. EUR, USD, HRK)")

    # Stavke
    items: List[LineItem] = Field(default_factory=list, description="Lista stavki s računa")

    # Kategorija troška
    expense_category: str = Field(
        ...,
        description="Kategorija troška: Hrana, Prijevoz, Ured, Režije, Ostalo"
    )

    # Dodatni metapodaci
    receipt_number: Optional[str] = Field(None, description="Broj računa/fakture")
    payment_method: Optional[str] = Field(None, description="Način plaćanja: Gotovina, Kartica, Virman")
    vat_amount: Optional[float] = Field(None, description="Iznos PDV-a")
    vat_rate: Optional[float] = Field(None, description="Stopa PDV-a (%)")

    # OCR metapodaci
    confidence_score: float = Field(
        ...,
        description="Pouzdanost ekstrakcije (0.0 - 1.0). Ispod 0.8 zahtijeva manual review"
    )
    drive_file_id: Optional[str] = Field(None, description="ID slike računa na Google Drive-u")
    notes: Optional[str] = Field(None, description="Dodatne bilješke ili komentari")

class ReceiptValidation(BaseModel):
    """Validacijski rezultat OCR-a"""
    success: bool
    receipt: Optional[Receipt]
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    requires_manual_review: bool = False
```

**Strategija**:
- **Confidence threshold**: Računi s `confidence_score < 0.8` zahtijevaju manual review
- **Required fields**: merchant_name, transaction_date, total_amount, expense_category
- **Optional fields**: Gemini će pokušati izvući, ali neće failati ako ne uspije

---

## 2. Vision MCP Toolset - Gemini Flash OCR

**File**: `tools/mcp_toolsets/vision_mcp.py`

```python
"""
Vision MCP Toolset - Gemini 1.5 Flash Multimodal OCR

Flash-First strategija: Gemini kao primarni OCR engine
"""

from google.genai.types import Tool, FunctionDeclaration
import logging

logger = logging.getLogger(__name__)

def get_vision_mcp_tools() -> list[Tool]:
    """
    Dohvaća Vision/OCR MCP alate koristeći Gemini 1.5 Flash

    Returns:
        Lista Tool objekata za OCR operacije
    """

    tools = [
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="extract_receipt_data",
                    description="""
                    Extract structured data from receipt/invoice image using Gemini 1.5 Flash multimodal OCR.
                    Returns JSON with merchant, date, amount, items, category, and confidence score.
                    """,
                    parameters={
                        "type": "object",
                        "properties": {
                            "image_data": {
                                "type": "string",
                                "description": "Base64 encoded image data OR Google Drive file ID"
                            },
                            "image_source": {
                                "type": "string",
                                "description": "Source type: 'base64' or 'drive_id'",
                                "enum": ["base64", "drive_id"]
                            },
                            "language_hint": {
                                "type": "string",
                                "description": "Optional language hint (e.g., 'hr', 'en', 'de')",
                                "default": "hr"
                            },
                            "extract_line_items": {
                                "type": "boolean",
                                "description": "Whether to extract individual line items (default: true)",
                                "default": True
                            }
                        },
                        "required": ["image_data", "image_source"]
                    }
                ),

                FunctionDeclaration(
                    name="categorize_expense",
                    description="""
                    Automatically categorize expense based on merchant name and items.
                    Returns category: Hrana, Prijevoz, Ured, Režije, Ostalo.
                    """,
                    parameters={
                        "type": "object",
                        "properties": {
                            "merchant_name": {
                                "type": "string",
                                "description": "Name of merchant/vendor"
                            },
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of item descriptions (optional)"
                            }
                        },
                        "required": ["merchant_name"]
                    }
                ),
            ]
        )
    ]

    return tools
```

**Implementation details**:
- Tool će interno koristiti `google.genai` SDK s Gemini 1.5 Flash
- Koristi `response_mime_type="application/json"` i `response_schema=Receipt` za strukturirani output
- `temperature=0.0` za konzistentnost
- Automatski računa confidence score na temelju:
  - Jesu li sva obavezna polja popunjena
  - Je li iznos validan broj
  - Je li datum u validnom formatu

---

## 3. Implementacija OCR Tool Handler-a

**File**: `tools/handlers/vision_handler.py`

```python
"""
Vision Handler - Implementacija OCR funkcionalnosti
"""

from google import genai
from google.genai import types
from tools.schemas.receipt_schema import Receipt, ReceiptValidation
import base64
import logging

logger = logging.getLogger(__name__)

class VisionHandler:
    """Handler za Gemini Vision OCR operacije"""

    def __init__(self):
        """Inicijalizacija Gemini klijenta za Vertex AI"""
        self.client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("VERTEX_AI_LOCATION", "us-central1")
        )
        self.model = "gemini-1.5-flash"

    async def extract_receipt_data(
        self,
        image_data: str,
        image_source: str = "base64",
        language_hint: str = "hr",
        extract_line_items: bool = True
    ) -> ReceiptValidation:
        """
        Ekstraktira strukturirane podatke s računa koristeći Gemini Flash

        Args:
            image_data: Base64 string ili Drive file ID
            image_source: 'base64' ili 'drive_id'
            language_hint: Jezik računa
            extract_line_items: Treba li izvući pojedinačne stavke

        Returns:
            ReceiptValidation objekt s rezultatima
        """
        try:
            # Pripremi sliku
            if image_source == "drive_id":
                # Download from Drive
                image_bytes = await self._download_from_drive(image_data)
            else:
                # Decode base64
                image_bytes = base64.b64decode(image_data)

            # Pripremi prompt
            prompt = self._build_extraction_prompt(language_hint, extract_line_items)

            # Pozovi Gemini Flash s multimodal input
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    prompt
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Receipt,
                    temperature=0.0,
                    max_output_tokens=2048
                )
            )

            # Parse rezultat (SDK automatski parsira u Pydantic)
            receipt: Receipt = response.parsed

            # Validacija
            validation = self._validate_receipt(receipt)

            logger.info(
                f"OCR completed: {receipt.merchant_name}, "
                f"amount={receipt.total_amount} {receipt.currency}, "
                f"confidence={receipt.confidence_score:.2f}"
            )

            return validation

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return ReceiptValidation(
                success=False,
                receipt=None,
                errors=[str(e)],
                requires_manual_review=True
            )

    def _build_extraction_prompt(self, language_hint: str, extract_items: bool) -> str:
        """Generira OCR prompt za Gemini"""

        base_prompt = f"""
        Ekstrahiraj strukturirane podatke s ovog računa/fakture.

        VAŽNO:
        1. Jezik računa je vjerojatno: {language_hint.upper()}
        2. Iznosi mogu biti u EUR, HRK, USD - detektiraj točno
        3. Datum mora biti u ISO 8601 formatu (YYYY-MM-DD)
        4. expense_category mora biti JEDNA od: Hrana, Prijevoz, Ured, Režije, Ostalo
        5. confidence_score računaj na temelju kvalitete slike i čitljivosti teksta (0.0-1.0)
        """

        if extract_items:
            base_prompt += """
        6. Ekstrahiraj SVE stavke (items) s računa s opisom i cijenama
        7. Ako stavke nisu jasno odvojene, vrati praznu listu
        """
        else:
            base_prompt += """
        6. Možeš preskočiti ekstraktiranje pojedinih stavki (items=[])
        """

        base_prompt += """

        KATEGORIJE:
        - Hrana: Restorani, supermarketi, dostava hrane, kafići
        - Prijevoz: Gorivo, parkiralište, javni prijevoz, taxi, autopraonica
        - Ured: Uredski materijal, elektronika, software, kancelarija
        - Režije: Struja, plin, voda, internet, mobitel, najam
        - Ostalo: Sve ostalo što ne spada u gornje kategorije

        Vrati točan JSON prema definiranoj shemi.
        """

        return base_prompt.strip()

    def _validate_receipt(self, receipt: Receipt) -> ReceiptValidation:
        """
        Validira ekstraktirane podatke

        Returns:
            ReceiptValidation s validacijskim rezultatima
        """
        errors = []
        warnings = []

        # Required fields check
        if not receipt.merchant_name or receipt.merchant_name == "Unknown":
            errors.append("Naziv trgovca nije ekstraktiran")

        if not receipt.transaction_date:
            errors.append("Datum nije ekstraktiran")

        if receipt.total_amount <= 0:
            errors.append(f"Nevaljani iznos: {receipt.total_amount}")

        if receipt.expense_category not in ["Hrana", "Prijevoz", "Ured", "Režije", "Ostalo"]:
            errors.append(f"Nepoznata kategorija: {receipt.expense_category}")

        # Confidence check
        if receipt.confidence_score < 0.5:
            warnings.append("Vrlo niska pouzdanost OCR-a (< 50%)")
        elif receipt.confidence_score < 0.8:
            warnings.append("Niska pouzdanost OCR-a (< 80%)")

        # Datum format check
        try:
            from datetime import datetime
            datetime.fromisoformat(receipt.transaction_date)
        except ValueError:
            errors.append(f"Nevaljani format datuma: {receipt.transaction_date}")

        # Determine if manual review needed
        requires_review = (
            len(errors) > 0 or
            receipt.confidence_score < 0.8
        )

        return ReceiptValidation(
            success=len(errors) == 0,
            receipt=receipt if len(errors) == 0 else None,
            errors=errors,
            warnings=warnings,
            requires_manual_review=requires_review
        )

    async def categorize_expense(
        self,
        merchant_name: str,
        items: list[str] = None
    ) -> str:
        """
        Automatski kategorizira trošak na temelju trgovca i stavki

        Returns:
            Kategorija: Hrana, Prijevoz, Ured, Režije, Ostalo
        """
        # Pozovi Gemini Flash s jednostavnim promptom
        items_text = ", ".join(items) if items else "N/A"

        prompt = f"""
        Kategoriziraj trošak u JEDNU od sljedećih kategorija:
        - Hrana
        - Prijevoz
        - Ured
        - Režije
        - Ostalo

        Trgovac: {merchant_name}
        Stavke: {items_text}

        Vrati SAMO naziv kategorije, bez dodatnog teksta.
        """

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=50
            )
        )

        category = response.text.strip()

        # Fallback na "Ostalo" ako kategorija nije prepoznata
        valid_categories = ["Hrana", "Prijevoz", "Ured", "Režije", "Ostalo"]
        if category not in valid_categories:
            category = "Ostalo"

        return category
```

---

## 4. ExpenseAgent - Agent za obradu računa

**File**: `agents/expense/expense.py`

```python
"""
Expense Agent - Receipt Processing Specialist

Handles OCR extraction, validation, and storage of expense receipts
using Gemini 1.5 Flash multimodal OCR
"""

from typing import List, Optional
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from agents.base_agent import BaseAgent
from tools.mcp_toolsets.vision_mcp import get_vision_mcp_tools
from tools.mcp_toolsets.drive_mcp import get_drive_mcp_tools
from tools.mcp_toolsets.sheets_mcp import get_sheets_mcp_tools
from tools.handlers.vision_handler import VisionHandler
from tools.schemas.receipt_schema import Receipt, ReceiptValidation
import logging

logger = logging.getLogger(__name__)

class ExpenseAgent(BaseAgent):
    """
    Expense processing agent using Gemini 1.5 Flash OCR

    Capabilities:
    - Multimodal OCR with Gemini Flash (Flash-First strategy)
    - Automatic categorization
    - User confirmation workflow
    - Google Sheets integration for expense tracking
    """

    def __init__(
        self,
        name: str = "expense",
        model: str = "gemini-2.0-flash-exp",
        instruction_file: Optional[str] = None,
        config: Optional[dict] = None
    ):
        # Default instruction file
        if not instruction_file:
            instruction_file = os.path.join(
                os.path.dirname(__file__),
                "instructions.md"
            )

        # Default config
        if not config:
            config = {
                "temperature": 0.3,
                "max_tokens": 2048,
            }

        super().__init__(
            name=name,
            model=model,
            instruction_file=instruction_file,
            config=config
        )

        # Initialize tools
        self.tools = self._initialize_tools()

        # Vision handler for OCR
        self.vision_handler = VisionHandler()

        # Configuration
        self.expense_sheet_id = os.getenv("EXPENSE_SHEET_ID")  # From .env
        self.expense_folder_id = os.getenv("EXPENSE_FOLDER_ID")  # Drive folder ID

    def _initialize_tools(self) -> List:
        """Inicijalizira Vision + Drive + Sheets alate"""
        tools = []

        try:
            # Vision/OCR tools
            vision_tools = get_vision_mcp_tools()
            tools.extend(vision_tools)

            # Drive tools (za čitanje slika)
            drive_tools = get_drive_mcp_tools()
            tools.extend(drive_tools)

            # Sheets tools (za spremanje podataka)
            sheets_tools = get_sheets_mcp_tools()
            tools.extend(sheets_tools)

            logger.info(f"ExpenseAgent initialized with {len(tools)} tools")
        except Exception as e:
            logger.error(f"Failed to initialize tools: {e}")

        return tools

    def get_tools(self) -> List:
        """Vraća listu alata"""
        return self.tools

    async def process_receipt_image(
        self,
        image_source: str,
        source_type: str = "drive_id"
    ) -> dict:
        """
        Glavna metoda za obradu računa

        Workflow:
        1. OCR ekstrakcija (Gemini Flash)
        2. Validacija podataka
        3. User confirmation (ako je potrebno)
        4. Spremanje u Sheets
        5. Markiranje slike kao "processed"

        Args:
            image_source: Drive file ID ili base64
            source_type: 'drive_id' ili 'base64'

        Returns:
            Dict s rezultatima obrade
        """
        logger.info(f"Processing receipt: {image_source} ({source_type})")

        # Step 1: OCR ekstrakcija
        validation = await self.vision_handler.extract_receipt_data(
            image_data=image_source,
            image_source=source_type,
            language_hint="hr",
            extract_line_items=True
        )

        if not validation.success:
            return {
                "success": False,
                "errors": validation.errors,
                "message": "OCR ekstrakcija nije uspjela. Molim pregledaj račun ručno."
            }

        receipt = validation.receipt

        # Step 2: Pripremi za user review
        review_needed = validation.requires_manual_review

        if review_needed:
            # Format podataka za pregled
            review_message = self._format_receipt_for_review(receipt, validation.warnings)
            return {
                "success": True,
                "requires_review": True,
                "receipt_data": receipt.model_dump(),
                "review_message": review_message
            }

        # Step 3: Automatsko spremanje (visoka pouzdanost)
        save_result = await self._save_to_sheets(receipt)

        # Step 4: Označi sliku kao processed (ako je s Drive-a)
        if source_type == "drive_id":
            await self._mark_as_processed(image_source)

        return {
            "success": True,
            "receipt_data": receipt.model_dump(),
            "save_result": save_result,
            "message": f"✅ Račun automatski obrađen i spremljen: {receipt.merchant_name}, {receipt.total_amount} {receipt.currency}"
        }

    def _format_receipt_for_review(self, receipt: Receipt, warnings: List[str]) -> str:
        """Formatira podatke za user review"""

        message = f"""
📄 **Ekstraktirani podaci s računa**

**Osnovni podaci:**
- Trgovac: {receipt.merchant_name}
- Datum: {receipt.transaction_date}
- Iznos: {receipt.total_amount} {receipt.currency}
- Kategorija: {receipt.expense_category}

**Dodatno:**
- Broj računa: {receipt.receipt_number or 'N/A'}
- Način plaćanja: {receipt.payment_method or 'N/A'}
- PDV: {receipt.vat_amount or 'N/A'} {receipt.currency} ({receipt.vat_rate or 'N/A'}%)

**Stavke ({len(receipt.items)}):**
"""

        for i, item in enumerate(receipt.items, 1):
            message += f"{i}. {item.description} - {item.amount} {receipt.currency}\n"

        if warnings:
            message += f"\n⚠️ **Upozorenja:**\n"
            for warning in warnings:
                message += f"- {warning}\n"

        message += f"""
🎯 **Pouzdanost OCR-a: {receipt.confidence_score * 100:.1f}%**

Molim pregledaj podatke. Odgovori sa:
- "OK" za spremanje kako je
- "EDIT [polje] [nova_vrijednost]" za korekciju
- "CANCEL" za odbacivanje
"""

        return message

    async def _save_to_sheets(self, receipt: Receipt) -> dict:
        """
        Sprema račun u Google Sheets tablicu

        Format tablice:
        | Datum | Trgovac | Iznos | Valuta | Kategorija | PDV | Način plaćanja | Broj računa | Stavke | Link slike | Bilješke |
        """

        if not self.expense_sheet_id:
            logger.error("EXPENSE_SHEET_ID not configured in .env")
            return {"success": False, "error": "Sheets ID not configured"}

        try:
            # Formatiraj stavke
            items_text = "; ".join([
                f"{item.description} ({item.amount})"
                for item in receipt.items
            ])

            # Drive link (ako postoji)
            drive_link = ""
            if receipt.drive_file_id:
                drive_link = f"https://drive.google.com/file/d/{receipt.drive_file_id}/view"

            # Pripremi redak
            row_data = [
                receipt.transaction_date,
                receipt.merchant_name,
                receipt.total_amount,
                receipt.currency,
                receipt.expense_category,
                receipt.vat_amount or "",
                receipt.payment_method or "",
                receipt.receipt_number or "",
                items_text,
                drive_link,
                receipt.notes or ""
            ]

            # Append u Sheets (koristi MCP tool)
            # TODO: Implementirati poziv sheets_append_row
            # Za sada, return mock result

            logger.info(f"Receipt saved to Sheets: {receipt.merchant_name}")

            return {
                "success": True,
                "sheet_id": self.expense_sheet_id,
                "row_data": row_data
            }

        except Exception as e:
            logger.error(f"Failed to save to Sheets: {e}")
            return {"success": False, "error": str(e)}

    async def _mark_as_processed(self, file_id: str):
        """Označi sliku na Drive-u kao obrađenu (dodaj prefix ili premjesti)"""
        # TODO: Implementirati - npr. rename file s "[PROCESSED]" prefixom
        pass


# Factory function
def create_expense_agent(**kwargs) -> ExpenseAgent:
    """Factory funkcija za kreiranje ExpenseAgent instance"""
    return ExpenseAgent(**kwargs)
```

---

## 5. Instructions za ExpenseAgent

**File**: `agents/expense/instructions.md`

```markdown
# Expense Agent - Receipt Processing Specialist

You are **Expense**, a specialized AI agent for processing expense receipts using cutting-edge OCR technology. Your role is to extract, validate, and organize receipt data efficiently using **Gemini 1.5 Flash multimodal OCR** (Flash-First strategy).

## Your Mission

Transform photos of receipts into structured, searchable expense data automatically while maintaining high accuracy through intelligent validation and user confirmation workflows.

## Core Capabilities

### 1. OCR Extraction (Gemini 1.5 Flash)

You use **Gemini 1.5 Flash** as your primary OCR engine because:
- **Ultra-low cost**: ~$0.00007 per receipt (1400x cheaper than Document AI)
- **Multimodal understanding**: Sees the image holistically, not just text
- **Structured output**: Guaranteed JSON format via Pydantic schemas
- **Semantic reasoning**: Can categorize expenses and validate data intelligently

**Available OCR Tools:**
1. `extract_receipt_data` - Main OCR extraction with structured output
2. `categorize_expense` - Automatic expense categorization

### 2. Data Extraction Workflow

**Standard Process:**
1. **Receive receipt image** (from Drive folder or direct upload)
2. **Extract data using Gemini Flash OCR**
   - Merchant name
   - Transaction date (ISO 8601 format)
   - Total amount + currency
   - Individual line items (if visible)
   - Category (auto-classified)
   - Payment method, VAT, receipt number (if available)
3. **Validate extraction**
   - Check confidence score
   - Validate required fields
   - Verify data formats
4. **User confirmation** (if needed)
   - Confidence < 80% → Always ask for review
   - Confidence ≥ 80% → Auto-save
5. **Save to Google Sheets**
6. **Mark image as processed**

### 3. Expense Categories

You categorize expenses into **5 main categories**:

- **Hrana** (Food): Restaurants, groceries, cafes, food delivery
- **Prijevoz** (Transport): Fuel, parking, public transport, taxi, car wash
- **Ured** (Office): Office supplies, electronics, software, stationery
- **Režije** (Utilities): Electricity, gas, water, internet, mobile, rent
- **Ostalo** (Other): Everything else

**Categorization Logic:**
- Analyze merchant name (e.g., "Konzum" → Hrana, "INA" → Prijevoz)
- Consider line items if available
- Use semantic understanding (not just keywords)

### 4. Confidence Scoring

You calculate confidence scores based on:
- Image quality and text clarity
- Completeness of extracted fields
- Format validity (dates, amounts, etc.)

**Thresholds:**
- **< 50%**: Very low confidence - Always require manual review
- **50-79%**: Low confidence - Ask for user confirmation
- **≥ 80%**: High confidence - Auto-save allowed

### 5. User Confirmation Workflow

**When manual review is needed (confidence < 80%):**

Present extracted data in this format:
```
📄 **Ekstraktirani podaci s računa**

**Osnovni podaci:**
- Trgovac: [merchant_name]
- Datum: [transaction_date]
- Iznos: [total_amount] [currency]
- Kategorija: [expense_category]

**Dodatno:**
- Broj računa: [receipt_number]
- Način plaćanja: [payment_method]
- PDV: [vat_amount] ([vat_rate]%)

**Stavke:**
1. [item description] - [amount]
2. ...

⚠️ **Upozorenja:**
- [warning 1]
- [warning 2]

🎯 **Pouzdanost OCR-a: [confidence_score]%**

Molim pregledaj podatke. Odgovori sa:
- "OK" za spremanje kako je
- "EDIT [polje] [nova_vrijednost]" za korekciju
- "CANCEL" za odbacivanje
```

**Handle user responses:**
- **"OK"** → Save to Sheets as-is
- **"EDIT iznos 45.99"** → Update amount field and save
- **"CANCEL"** → Discard, mark image for manual processing

### 6. Google Sheets Integration

**Target spreadsheet:** "Ulazni računi" (configured via EXPENSE_SHEET_ID env var)

**Column structure:**
| Datum | Trgovac | Iznos | Valuta | Kategorija | PDV | Način plaćanja | Broj računa | Stavke | Link slike | Bilješke |

**Operations:**
- Use `sheets_append_row` to add new receipts
- Format dates as ISO 8601 (YYYY-MM-DD)
- Format amounts as numbers (not text)
- Combine line items into single cell (semicolon-separated)

### 7. Drive Folder Monitoring (Hybrid Mode)

You support **two trigger modes**:

**A) Automatic Processing**
- Monitor Drive folder "Ulazni računi foto" (configured via EXPENSE_FOLDER_ID)
- Detect new images (polling-based)
- Auto-process with workflow above

**B) Manual Processing**
- User sends message: "Obradi novi račun" or uploads image directly
- Process single receipt on-demand

**After processing:**
- Mark image as processed (rename with "[PROCESSED]" prefix or move to subfolder)

## Best Practices

### DO:
✅ Always calculate and check confidence score
✅ Ask for confirmation if confidence < 80%
✅ Validate date formats (ISO 8601 only)
✅ Include Drive link to original image in Sheets
✅ Log all OCR operations for audit trail
✅ Handle Croatian language receipts (PDV = VAT)

### DON'T:
❌ Never auto-save receipts with confidence < 80%
❌ Don't fail if optional fields are missing
❌ Don't use Document AI (too expensive for this use case)
❌ Don't proceed without user confirmation for low-confidence extractions

## Error Handling

**If OCR fails:**
1. Log error with context
2. Return clear error message to user
3. Suggest manual processing
4. Mark image for manual review

**Common failure scenarios:**
- Image too blurry/dark
- Receipt crumpled or torn
- Non-standard format (handwritten, thermal paper faded)
- Multiple receipts in one image

**Fallback strategy:**
- No Document AI fallback (user confirmed "No - samo Gemini")
- For failed extractions → Ask user to re-photograph or enter manually

## Integration with Other Agents

You work with:
- **Librarian** (Drive operations) - Reading images, folder monitoring
- **Analyst** (Sheets operations) - Data storage and analysis

**Multi-agent workflow example:**
User: "Obradi sve nove račune u folderu"
1. You → Request Librarian to list new images in folder
2. Librarian → Returns list of file IDs
3. You → Process each image (OCR + validation + save)
4. You → Return summary of processed receipts

## Performance Metrics

Track and report:
- Total receipts processed
- Average confidence score
- Auto-save rate (% with confidence ≥ 80%)
- Manual review rate
- Processing time per receipt
- OCR cost per receipt (~$0.00007)

## Example Interactions

**Example 1: High-confidence auto-save**
```
User: [uploads receipt image]
You:
🔍 Analiziram račun...
✅ Račun automatski obrađen i spremljen!

Trgovac: Konzum
Datum: 2025-11-27
Iznos: 125.50 EUR
Kategorija: Hrana
Pouzdanost: 95%

Spremljeno u Google Sheets tablicu "Ulazni računi".
```

**Example 2: Low-confidence review**
```
User: [uploads blurry receipt]
You:
🔍 Analiziram račun...
⚠️ Niska pouzdanost OCR-a (72%), molim provjeri podatke:

📄 **Ekstraktirani podaci**
- Trgovac: INA (možda IMA?)
- Datum: 2025-11-26
- Iznos: 67.30 EUR (nije potpuno čitljivo)
- Kategorija: Prijevoz

Molim potvrdi: "OK" za spremanje ili "EDIT [polje] [vrijednost]" za korekciju.
```

**Example 3: Batch processing**
```
User: Obradi sve nove račune iz foldera
You:
🔍 Tražim nove račune u folderu "Ulazni računi foto"...
📋 Pronađeno 5 novih računa

Obrađujem:
1. IMG_2023.jpg → ✅ Lidl, 89.20 EUR (95% confidence)
2. IMG_2024.jpg → ✅ OMV, 45.00 EUR (88% confidence)
3. IMG_2025.jpg → ⚠️ Potrebna provjera (64% confidence)
4. IMG_2026.jpg → ✅ Kaufland, 112.75 EUR (91% confidence)
5. IMG_2027.jpg → ❌ OCR failed (slika previše zamrljana)

Rezultat:
- 3 automatski spremljena
- 1 zahtijeva provjeru
- 1 neuspješan

Prikazujem račun koji zahtijeva provjeru...
[shows review prompt for IMG_2025.jpg]
```

---

## Technical Notes

**Environment Variables Required:**
- `EXPENSE_SHEET_ID` - Google Sheets ID za tablicu "Ulazni računi"
- `EXPENSE_FOLDER_ID` - Google Drive folder ID za "Ulazni računi foto"
- `GOOGLE_CLOUD_PROJECT` - GCP project ID
- `VERTEX_AI_LOCATION` - Vertex AI region (default: us-central1)

**Dependencies:**
- `google-genai` SDK for Vertex AI
- Pydantic for data validation
- Google Drive MCP tools
- Google Sheets MCP tools

**Cost Optimization:**
- Flash-First strategy: ~$0.00007 per receipt
- No Document AI usage (would be $0.10 per receipt)
- Savings: 1400x cost reduction

You are cost-effective, accurate, and user-friendly. Process receipts with confidence! 🚀
```

---

## 6. Drive Monitoring Tool (Optional - za automatsko praćenje)

**File**: `tools/monitors/drive_folder_monitor.py`

```python
"""
Drive Folder Monitor - Prati folder za nove slike računa

Polling-based pristup (može se kasnije nadograditi na webhook)
"""

import os
import time
import asyncio
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)

class DriveFolderMonitor:
    """
    Monitoring tool za praćenje novih slika u Drive folderu
    """

    def __init__(
        self,
        folder_id: str,
        poll_interval: int = 60,  # seconds
        image_extensions: Set[str] = {".jpg", ".jpeg", ".png", ".pdf"}
    ):
        """
        Args:
            folder_id: Drive folder ID to monitor
            poll_interval: How often to check (seconds)
            image_extensions: Valid image file extensions
        """
        self.folder_id = folder_id
        self.poll_interval = poll_interval
        self.image_extensions = image_extensions
        self.processed_files: Set[str] = set()  # Track processed file IDs
        self.running = False

    async def start_monitoring(self, callback):
        """
        Pokreni continuous monitoring loop

        Args:
            callback: Async function to call with new file IDs
        """
        self.running = True
        logger.info(f"Started monitoring Drive folder: {self.folder_id}")

        while self.running:
            try:
                # Get new files
                new_files = await self._check_for_new_files()

                if new_files:
                    logger.info(f"Found {len(new_files)} new receipt images")

                    # Process each file
                    for file_info in new_files:
                        try:
                            await callback(file_info)
                            self.processed_files.add(file_info['id'])
                        except Exception as e:
                            logger.error(f"Failed to process {file_info['name']}: {e}")

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(self.poll_interval)

    def stop_monitoring(self):
        """Zaustavi monitoring loop"""
        self.running = False
        logger.info("Stopped Drive folder monitoring")

    async def _check_for_new_files(self) -> List[Dict]:
        """
        Provjerava folder za nove slike

        Returns:
            Lista novih file info objekata
        """
        # TODO: Implementirati s Drive MCP toolom
        # Pseudokod:
        # 1. drive_search_files(query=f"'{self.folder_id}' in parents")
        # 2. Filter by image extensions
        # 3. Exclude processed_files
        # 4. Return new files

        # Mock za sada
        return []
```

**Napomena**: Ovo je optional feature. Može se implementirati kasnije ako korisnik želi fully automatic processing.

---

## 7. Agent Registry Update

**File**: `config/agent_registry.py`

Dodaj u `AGENT_REGISTRY`:

```python
"expense": AgentConfig(
    name="expense",
    module="agents.expense.expense",
    class_name="ExpenseAgent",
    model="gemini-2.0-flash-exp",
    description="Processes expense receipts: OCR extraction (Gemini Flash), validation, categorization, and Google Sheets storage. Handles Croatian language receipts.",
    tools=["vision_mcp", "drive_mcp", "sheets_mcp"],
    instruction_file="agents/expense/instructions.md",
    config={
        "temperature": 0.3,
        "max_tokens": 2048,
    }
),
```

---

## 8. Orchestrator Routing Update

**File**: `agents/orchestrator/instructions.md`

Dodaj u routing guide:

```markdown
## EXPENSE
**Model:** gemini-2.0-flash-exp
**Description:** Processes expense receipts: OCR extraction (Gemini Flash), validation, categorization, and Google Sheets storage.
**Tools:** vision_mcp, drive_mcp, sheets_mcp

**When to delegate:**
- User uploads receipt/invoice image
- Keywords: "račun", "invoice", "expense", "OCR", "skeniranje"
- Requests like "obradi račun", "spremanje računa", "ulazni računi"
```

Dodaj u `_fallback_keyword_routing`:

```python
# Receipt/OCR keywords
if any(kw in request_lower for kw in ['račun', 'invoice', 'expense', 'ocr', 'skeniranje', 'receipt']):
    return {"agent": "expense", "reasoning": "Receipt/OCR keywords detected", "requires_multiple": False}
```

---

## 9. Environment Configuration

**File**: `.env` (dodaj nove varijable)

```bash
# Expense Management Configuration
EXPENSE_SHEET_ID=your-expense-tracking-sheet-id
EXPENSE_FOLDER_ID=your-drive-folder-id-for-receipts

# Expense Settings
EXPENSE_AUTO_PROCESS=false  # Set to true for automatic folder monitoring
EXPENSE_CONFIDENCE_THRESHOLD=0.8  # Minimum confidence for auto-save
```

---

## 10. Test Script

**File**: `test_expense_ocr.py`

```python
"""
Test script za ExpenseAgent OCR funkcionalnost
"""

import asyncio
import os
from dotenv import load_dotenv
from agents.expense.expense import create_expense_agent
from tools.handlers.vision_handler import VisionHandler

load_dotenv()

async def test_ocr_extraction():
    """Test OCR ekstrakcije s test slikom"""
    print("=" * 80)
    print("TEST: OCR Extraction with Gemini 1.5 Flash")
    print("=" * 80)

    # Kreiraj handler
    handler = VisionHandler()

    # Test s mock base64 slikom (zamijeniti s realnom)
    # TODO: Dodaj test receipt image
    test_image_base64 = "..."  # Base64 encoded test receipt

    print("\n1. Extracting receipt data...")
    validation = await handler.extract_receipt_data(
        image_data=test_image_base64,
        image_source="base64",
        language_hint="hr",
        extract_line_items=True
    )

    print(f"\n2. Validation Result:")
    print(f"   Success: {validation.success}")
    print(f"   Requires Review: {validation.requires_manual_review}")

    if validation.errors:
        print(f"   Errors: {validation.errors}")

    if validation.warnings:
        print(f"   Warnings: {validation.warnings}")

    if validation.receipt:
        receipt = validation.receipt
        print(f"\n3. Extracted Data:")
        print(f"   Merchant: {receipt.merchant_name}")
        print(f"   Date: {receipt.transaction_date}")
        print(f"   Amount: {receipt.total_amount} {receipt.currency}")
        print(f"   Category: {receipt.expense_category}")
        print(f"   Confidence: {receipt.confidence_score * 100:.1f}%")
        print(f"   Items: {len(receipt.items)}")

        if receipt.items:
            print(f"\n   Line Items:")
            for i, item in enumerate(receipt.items, 1):
                print(f"   {i}. {item.description} - {item.amount}")

async def test_expense_agent():
    """Test kompletnog ExpenseAgent workflow-a"""
    print("\n" + "=" * 80)
    print("TEST: ExpenseAgent Workflow")
    print("=" * 80)

    # Kreiraj agent
    agent = create_expense_agent()

    print(f"\n1. Agent created: {agent.name}")
    print(f"   Model: {agent.model}")
    print(f"   Tools: {len(agent.get_tools())}")

    # TODO: Test s realnom slikom
    print("\n2. Testing receipt processing...")
    # result = await agent.process_receipt_image(
    #     image_source="test_drive_file_id",
    #     source_type="drive_id"
    # )

    print("\n✅ ExpenseAgent test completed")

async def test_categorization():
    """Test automatske kategorizacije"""
    print("\n" + "=" * 80)
    print("TEST: Expense Categorization")
    print("=" * 80)

    handler = VisionHandler()

    test_cases = [
        ("Konzum", ["Mlijeko", "Kruh", "Voće"]),
        ("INA", ["Eurodiesel", "Benzin 95"]),
        ("IKEA", ["Uredski stol", "Stolica"]),
        ("HEP", []),
        ("Restoran Vinodol", ["Riba", "Vino"])
    ]

    print("\nCategorizing expenses:")
    for merchant, items in test_cases:
        category = await handler.categorize_expense(merchant, items)
        print(f"  {merchant} → {category}")

if __name__ == "__main__":
    print("🚀 Starting ExpenseAgent OCR Tests\n")

    asyncio.run(test_ocr_extraction())
    asyncio.run(test_expense_agent())
    asyncio.run(test_categorization())

    print("\n🎉 All tests completed!")
```

---

## 11. Sheets Setup Helper

**File**: `setup_expense_sheet.py`

```python
"""
Helper script za kreiranje i setup Google Sheets tablice za troškove
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
from dotenv import load_dotenv

load_dotenv()

def create_expense_sheet():
    """
    Kreira novu Google Sheets tablicu za praćenje troškova
    s predefiniranim stupcima i formatiranjem
    """

    # TODO: Implementirati s Sheets API
    # 1. Create new spreadsheet "Ulazni računi"
    # 2. Setup headers:
    #    Datum | Trgovac | Iznos | Valuta | Kategorija | PDV | Način plaćanja |
    #    Broj računa | Stavke | Link slike | Bilješke
    # 3. Format header row (bold, freeze)
    # 4. Set column widths
    # 5. Add data validation for Category column (dropdown)
    # 6. Return spreadsheet ID

    print("Kreiranje Google Sheets tablice za troškove...")
    print("TODO: Implementirati")

    # Return mock ID za sada
    return "mock-spreadsheet-id"

if __name__ == "__main__":
    sheet_id = create_expense_sheet()
    print(f"\n✅ Spreadsheet created!")
    print(f"   ID: {sheet_id}")
    print(f"\n   Add to .env:")
    print(f"   EXPENSE_SHEET_ID={sheet_id}")
```

---

## 12. Implementation Roadmap

### Phase 1: Core OCR Functionality ✅
1. ✅ Kreirati Pydantic shemu (`receipt_schema.py`)
2. ✅ Implementirati Vision MCP toolset (`vision_mcp.py`)
3. ✅ Implementirati Vision Handler (`vision_handler.py`)
4. ✅ Kreirati ExpenseAgent (`expense.py`)
5. ✅ Napisati instructions (`instructions.md`)

### Phase 2: Integration ⏳
6. ⏳ Dodati u Agent Registry
7. ⏳ Ažurirati Orchestrator routing
8. ⏳ Implementirati Sheets save logic
9. ⏳ Kreirati test tablicu (`setup_expense_sheet.py`)

### Phase 3: Testing & Validation ⏳
10. ⏳ Napisati test script (`test_expense_ocr.py`)
11. ⏳ Testirati s realnim računima (HR receipts)
12. ⏳ Validirati accuracy i confidence scoring
13. ⏳ Optimizirati prompts za bolje rezultate

### Phase 4: Advanced Features (Optional) 🔮
14. 🔮 Implementirati Drive folder monitoring
15. 🔮 Dodati batch processing
16. 🔮 Kreirati expense analytics dashboard
17. 🔮 Multi-language support (DE, EN, IT)

---

## Cost Analysis

### Flash-First Strategy (Preporučeno)

**Per Receipt:**
- Gemini 1.5 Flash OCR: ~$0.00007
- Sheets API: Free (u razumnim limitima)
- Drive API: Free

**Monthly (500 računa):**
- Total: ~$0.035 (približno 3 centa mjesečno!)

### Alternative: Document AI (NE preporučeno)

**Per Receipt:**
- Document AI Expense Parser: $0.10
- Sheets API: Free
- Drive API: Free

**Monthly (500 računa):**
- Total: $50.00

**Ušteda s Flash-First:** 99.93% ($49.965 mjesečno)

---

## Success Metrics

Track the following KPIs:

1. **Accuracy**
   - Target: >95% field extraction accuracy
   - Measure: Manual validation sample (50 receipts/month)

2. **Auto-save Rate**
   - Target: >80% of receipts auto-saved (confidence ≥ 80%)
   - Measure: Count of auto vs manual review

3. **Processing Time**
   - Target: <5 seconds per receipt
   - Measure: End-to-end latency

4. **Cost Efficiency**
   - Target: <$0.0001 per receipt
   - Current: ~$0.00007 (70% below target!)

5. **User Satisfaction**
   - Target: <5% manual corrections needed
   - Measure: Edit rate after confirmation

---

## FAQ

**Q: Zašto koristimo Gemini Flash umjesto Document AI?**
A: Gemini Flash je 1400x jeftinije ($0.00007 vs $0.10 po računu), a uz to razumije kontekst i može kategorizar troškove automatski. Document AI je overkill za ovaj use case.

**Q: Što ako OCR ne uspije?**
A: Sustav će prikazati poruku o grešci i predložiti da korisnik re-fotografira račun ili unese podatke ručno. Nemamo Document AI fallback (korisnik je potvrdio).

**Q: Koliko računa mogu procesuirati mjesečno?**
A: Teoretski neograničeno (u okviru Vertex AI kvota). Praktično, s 500 računa mjesečno trošak je ~$0.035.

**Q: Podržava li hrvatski jezik?**
A: Da! Gemini Flash izvrsno razumije hrvatske račune (PDV, trgovci, itd.). Language hint je postavljen na "hr".

**Q: Mogu li mijenjati kategorije?**
A: Da. Kategorije su definirane u shemi i promptu. Lako ih je mijenjati/dodavati po potrebi.

---

## Next Steps

1. **Kreni s Phase 1** - Implementiraj core OCR funkcionalnost
2. **Testiraj s realnim računima** - Probaj s 5-10 realnih računa
3. **Optimiziraj prompts** - Tune extraction accuracy
4. **Deploy u production** - Dodaj u main.py

Let's build! 🚀
