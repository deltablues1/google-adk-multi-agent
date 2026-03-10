"""
Fiskalizacija 2.0 - Pydantic Models

Data models for Croatian electronic invoicing (e-Invoice) according to:
- UBL 2.1 standard
- EN 16931 European e-Invoice norm
- HR-FISK 2.0 Croatian extension

These models ensure type safety and validation throughout the fiscalization pipeline.
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from typing import List, Optional
from enum import Enum
import re


# ============================================================================
# ENUMS
# ============================================================================

class VATRate(str, Enum):
    """Croatian VAT rates as of 2024"""
    STANDARD = "25"       # Standard rate
    REDUCED_13 = "13"     # Reduced rate (food service, newspapers)
    REDUCED_5 = "5"       # Super-reduced rate (bread, milk, books)
    ZERO = "0"            # Zero rate (exports, certain services)


class ValidationStatus(str, Enum):
    """Invoice validation status"""
    READY = "READY"              # Ready for signing and submission
    NEEDS_REVIEW = "NEEDS_REVIEW"  # Requires human review
    INVALID = "INVALID"          # Failed validation


class FiskalizacijaStatus(str, Enum):
    """Fiscalization execution status"""
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    QUEUED = "QUEUED"
    PENDING = "PENDING"


class InvoiceTypeCode(str, Enum):
    """UBL Invoice Type Codes"""
    INVOICE = "380"              # Commercial invoice
    CREDIT_NOTE = "381"          # Credit note
    DEBIT_NOTE = "383"           # Debit note
    CORRECTED_INVOICE = "384"    # Corrected invoice
    PREPAYMENT_INVOICE = "386"   # Prepayment invoice


# ============================================================================
# UN/ECE RECOMMENDATION 20 - UNIT CODES
# ============================================================================

UNIT_CODE_MAP = {
    # Croatian → UN/ECE Rec 20
    "kom": "H87",
    "komad": "H87",
    "pcs": "H87",
    "piece": "H87",
    "sat": "HUR",
    "h": "HUR",
    "hour": "HUR",
    "dan": "DAY",
    "day": "DAY",
    "mjesec": "MON",
    "month": "MON",
    "godina": "ANN",
    "year": "ANN",
    "kg": "KGM",
    "kilogram": "KGM",
    "g": "GRM",
    "gram": "GRM",
    "t": "TNE",
    "tona": "TNE",
    "m": "MTR",
    "metar": "MTR",
    "metre": "MTR",
    "meter": "MTR",
    "m2": "MTK",
    "m²": "MTK",
    "m3": "MTQ",
    "m³": "MTQ",
    "l": "LTR",
    "litra": "LTR",
    "litre": "LTR",
    "liter": "LTR",
    "kwh": "KWH",
    "kWh": "KWH",
    "paket": "PK",
    "package": "PK",
    "kutija": "BX",
    "box": "BX",
}


def normalize_unit_code(unit: str) -> str:
    """Convert various unit representations to UN/ECE Rec 20 code"""
    if not unit:
        return "H87"  # Default to piece

    unit_lower = unit.lower().strip()
    return UNIT_CODE_MAP.get(unit_lower, unit.upper())


# ============================================================================
# OIB VALIDATION (Module 11 Algorithm)
# ============================================================================

def validate_oib_checksum(oib: str) -> bool:
    """
    Validate Croatian OIB using Module 11 algorithm.

    The OIB (Osobni Identifikacijski Broj) is an 11-digit number where
    the last digit is a check digit calculated using Module 11 algorithm.

    Algorithm:
    1. Start with initial value 10
    2. For each of the first 10 digits:
       a. Add digit to current value
       b. Take modulo 10 (if result is 0, use 10)
       c. Multiply by 2
       d. Take modulo 11
    3. Final check digit = 11 - result (if 11, use 0)
    """
    if not oib or len(oib) != 11:
        return False

    if not oib.isdigit():
        return False

    # Module 11 algorithm
    remainder = 10
    for i in range(10):
        digit = int(oib[i])
        remainder = (remainder + digit) % 10
        if remainder == 0:
            remainder = 10
        remainder = (remainder * 2) % 11

    check_digit = 11 - remainder
    if check_digit == 11:
        check_digit = 0

    return check_digit == int(oib[10])


# ============================================================================
# BASE MODELS
# ============================================================================

class OIBResult(BaseModel):
    """Result of OIB validation"""
    valid: bool
    oib: str
    error_message: Optional[str] = None


class VIESResult(BaseModel):
    """Result of VIES VAT number lookup"""
    valid: bool
    vat_number: str
    company_name: Optional[str] = None
    address: Optional[str] = None
    vat_active: bool = False
    country_code: Optional[str] = None
    error_message: Optional[str] = None


class KPDMatch(BaseModel):
    """Single KPD code match from search"""
    code: str = Field(..., description="KPD 2025 code (e.g., '62.02.10')")
    name_hr: str = Field(..., description="Croatian name")
    name_en: Optional[str] = Field(None, description="English name")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence")
    parent_code: Optional[str] = Field(None, description="Parent category code")
    default_vat_rate: VATRate = Field(VATRate.STANDARD, description="Default VAT rate")


class KPDSearchResult(BaseModel):
    """Result of KPD code search"""
    query: str
    matches: List[KPDMatch]
    best_match: Optional[KPDMatch] = None
    needs_review: bool = False  # True if best match confidence < 95%


# ============================================================================
# TAX CALCULATION MODELS
# ============================================================================

class TaxItem(BaseModel):
    """Single item for tax calculation"""
    net_amount: Decimal = Field(..., description="Net amount before tax")
    vat_rate: VATRate = Field(..., description="VAT rate to apply")
    description: Optional[str] = Field(None, description="Item description")

    @field_validator('net_amount', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class TaxSubtotal(BaseModel):
    """Tax subtotal for a specific VAT rate"""
    vat_rate: VATRate
    taxable_amount: Decimal = Field(..., description="Base amount for this rate")
    tax_amount: Decimal = Field(..., description="Calculated tax amount")

    @field_validator('taxable_amount', 'tax_amount', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v


class TaxBreakdown(BaseModel):
    """Complete tax calculation breakdown"""
    subtotals: List[TaxSubtotal] = Field(default_factory=list)
    total_net: Decimal = Field(..., description="Sum of all net amounts")
    total_tax: Decimal = Field(..., description="Sum of all tax amounts")
    total_gross: Decimal = Field(..., description="Net + Tax = Gross")

    @field_validator('total_net', 'total_tax', 'total_gross', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    @model_validator(mode='after')
    def validate_totals(self):
        """Ensure gross = net + tax"""
        expected_gross = self.total_net + self.total_tax
        if abs(self.total_gross - expected_gross) > Decimal('0.01'):
            raise ValueError(
                f"Gross total mismatch: {self.total_gross} != "
                f"{self.total_net} + {self.total_tax}"
            )
        return self


# ============================================================================
# INVOICE PARTY MODELS
# ============================================================================

class Party(BaseModel):
    """Business party (supplier or customer)"""
    name: str = Field(..., min_length=1, description="Company or person name")
    oib: str = Field(..., pattern=r'^\d{11}$', description="Croatian OIB (11 digits)")
    address: str = Field(..., min_length=1, description="Street address")
    city: str = Field(..., min_length=1, description="City name")
    postal_code: str = Field(..., min_length=1, description="Postal/ZIP code")
    country_code: str = Field("HR", pattern=r'^[A-Z]{2}$', description="ISO 3166-1 alpha-2")
    vat_number: Optional[str] = Field(None, description="VAT number with country prefix")
    email: Optional[str] = Field(None, description="Contact email")
    phone: Optional[str] = Field(None, description="Contact phone")

    @field_validator('oib')
    @classmethod
    def validate_oib(cls, v):
        if not validate_oib_checksum(v):
            raise ValueError(f"Invalid OIB checksum: {v}")
        return v

    @field_validator('vat_number')
    @classmethod
    def validate_vat_number(cls, v, info):
        if v is None:
            return v
        # VAT number should be country code + OIB for Croatian companies
        if not re.match(r'^[A-Z]{2}\d+$', v):
            raise ValueError(f"Invalid VAT number format: {v}")
        return v


# ============================================================================
# INVOICE LINE ITEM MODEL
# ============================================================================

class InvoiceItem(BaseModel):
    """Single invoice line item"""
    description: str = Field(..., min_length=1, description="Item/service description")
    quantity: Decimal = Field(..., gt=0, description="Quantity")
    unit_code: str = Field("H87", description="UN/ECE Rec 20 unit code")
    unit_price: Decimal = Field(..., ge=0, description="Price per unit (net)")
    kpd_code: str = Field(..., description="KPD 2025 classification code")
    kpd_confidence: float = Field(..., ge=0.0, le=1.0, description="KPD classification confidence")
    vat_rate: VATRate = Field(..., description="VAT rate")
    needs_review: bool = Field(False, description="Flag for human review")
    line_extension_amount: Optional[Decimal] = Field(None, description="Calculated: qty * price")

    @field_validator('quantity', 'unit_price', 'line_extension_amount', mode='before')
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return v
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    @model_validator(mode='after')
    def calculate_line_amount(self):
        """Auto-calculate line extension amount if not provided"""
        if self.line_extension_amount is None:
            self.line_extension_amount = (
                self.quantity * self.unit_price
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return self

    @field_validator('kpd_code')
    @classmethod
    def validate_kpd_format(cls, v):
        # KPD format: XX.XX.XX (e.g., 62.02.10)
        if not re.match(r'^\d{2}\.\d{2}\.\d{2}$', v):
            raise ValueError(f"Invalid KPD code format: {v}. Expected: XX.XX.XX")
        return v


# ============================================================================
# MAIN INVOICE MODEL
# ============================================================================

class FiskalniPodaci(BaseModel):
    """
    Complete invoice data for fiscalization.

    This is the main data structure passed through the fiscalization pipeline:
    Pripremac → Validator → Executor
    """
    # Invoice identification
    invoice_number: str = Field(..., description="Format: XXX/PP/NU")
    invoice_type: InvoiceTypeCode = Field(InvoiceTypeCode.INVOICE, description="Invoice type code")

    # Dates
    issue_date: date = Field(..., description="Invoice issue date")
    due_date: date = Field(..., description="Payment due date")

    # Parties
    supplier: Party = Field(..., description="Seller/supplier information")
    customer: Party = Field(..., description="Buyer/customer information")

    # Line items
    items: List[InvoiceItem] = Field(..., min_length=1, description="Invoice line items")

    # Payment
    currency: str = Field("EUR", pattern=r'^[A-Z]{3}$', description="ISO 4217 currency code")
    payment_means_code: str = Field("30", description="UNCL 4461 payment means code")
    bank_account: Optional[str] = Field(None, description="Supplier bank account (IBAN)")
    payment_reference: Optional[str] = Field(None, description="Payment reference number")

    # Optional fields
    note: Optional[str] = Field(None, description="Invoice note")
    order_reference: Optional[str] = Field(None, description="Reference to purchase order")
    contract_reference: Optional[str] = Field(None, description="Reference to contract")

    # Calculated totals (populated by calculate_tax)
    tax_breakdown: Optional[TaxBreakdown] = Field(None, description="Calculated tax breakdown")

    # Validation status
    validation_status: ValidationStatus = Field(
        ValidationStatus.READY,
        description="Current validation status"
    )
    review_items: List[str] = Field(default_factory=list, description="Items flagged for review")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors")

    @field_validator('invoice_number')
    @classmethod
    def validate_invoice_number_format(cls, v):
        # Croatian format: XXX/PP/NU
        # XXX = sequential number, PP = business premises, NU = cash register
        if not re.match(r'^\d{1,}/.+/\d+$', v):
            raise ValueError(
                f"Invalid invoice number format: {v}. "
                f"Expected: XXX/PP/NU (e.g., 001/URED/1)"
            )
        return v

    @model_validator(mode='after')
    def validate_dates(self):
        """Ensure due_date >= issue_date"""
        if self.due_date < self.issue_date:
            raise ValueError(
                f"Due date ({self.due_date}) cannot be before issue date ({self.issue_date})"
            )
        return self

    @model_validator(mode='after')
    def check_review_items(self):
        """Update validation status based on review items"""
        review_needed = [
            item.description for item in self.items
            if item.needs_review or item.kpd_confidence < 0.95
        ]
        if review_needed:
            self.review_items = review_needed
            if self.validation_status == ValidationStatus.READY:
                self.validation_status = ValidationStatus.NEEDS_REVIEW
        return self


# ============================================================================
# FISCALIZATION RESULT MODELS
# ============================================================================

class FINAError(BaseModel):
    """Error from FINA service"""
    code: str = Field(..., description="FINA error code (e.g., S001, V001)")
    message: str = Field(..., description="Error message")
    field: Optional[str] = Field(None, description="Field that caused error")
    severity: str = Field("critical", description="Error severity")


class FiskalizacijaResult(BaseModel):
    """Result of fiscalization attempt"""
    status: FiskalizacijaStatus
    invoice_number: str
    jir: Optional[str] = Field(None, description="Jedinstveni Identifikator Racuna")
    zki: Optional[str] = Field(None, description="Zastitni Kod Izdavatelja")
    qr_code_url: Optional[str] = Field(None, description="URL to QR code image")
    verification_url: Optional[str] = Field(None, description="URL for verification on Porezna")
    timestamp: Optional[datetime] = Field(None, description="Fiscalization timestamp")
    signed_xml: Optional[str] = Field(None, description="Signed XML document")
    errors: List[FINAError] = Field(default_factory=list)
    message: str = Field(..., description="Human-readable status message")

    # For queued items
    queue_position: Optional[int] = Field(None, description="Position in retry queue")
    next_retry: Optional[datetime] = Field(None, description="Next retry attempt time")

    # For error recovery
    forward_to: Optional[str] = Field(None, description="Next agent to handle")
    action_required: Optional[str] = Field(None, description="Required user action")
    retry_possible: bool = Field(True, description="Can be retried")


class InvoiceLedgerEntry(BaseModel):
    """Entry in the invoice ledger for idempotency"""
    invoice_number: str
    supplier_oib: str
    jir: str
    zki: Optional[str] = None
    timestamp: datetime
    signed_xml: str
    fina_response: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetryQueueEntry(BaseModel):
    """Entry in the retry queue for failed fiscalizations"""
    invoice_id: str
    supplier_oib: str
    signed_xml: str
    attempts: int = Field(0, ge=0)
    max_attempts: int = Field(10, ge=1)
    next_retry: datetime
    last_error: Optional[str] = None
    created_at: datetime
    deadline: datetime  # 48h limit by Croatian law

    @model_validator(mode='after')
    def validate_deadline(self):
        """Ensure deadline is within 48 hours of creation"""
        max_deadline = self.created_at + timedelta(hours=48)
        if self.deadline > max_deadline:
            self.deadline = max_deadline
        return self


# Import for deadline calculation
from datetime import timedelta


# ============================================================================
# VALIDATION RESULT MODELS
# ============================================================================

class ValidationCheck(BaseModel):
    """Single validation check result"""
    step: str = Field(..., description="Validation step (e.g., '1.1', '2.3')")
    description: str = Field(..., description="What was checked")
    passed: bool = Field(..., description="Check passed or failed")
    severity: str = Field("critical", description="critical, warning, info")
    message: Optional[str] = Field(None, description="Error or warning message")
    field: Optional[str] = Field(None, description="Field that was checked")
    expected: Optional[str] = Field(None, description="Expected value")
    actual: Optional[str] = Field(None, description="Actual value")


class ValidationResult(BaseModel):
    """Complete validation result from Validator agent"""
    status: ValidationStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    checks_passed: int = Field(..., ge=0)
    checks_total: int = Field(..., ge=0)
    checks: List[ValidationCheck] = Field(default_factory=list)
    errors: List[ValidationCheck] = Field(default_factory=list)
    warnings: List[ValidationCheck] = Field(default_factory=list)
    forward_to: str = Field(..., description="Next handler")
    remediation: Optional[str] = Field(None, description="How to fix issues")


# ============================================================================
# XSD VALIDATION RESULT
# ============================================================================

class XSDError(BaseModel):
    """XSD schema validation error"""
    line: int = Field(..., description="Line number in XML")
    column: int = Field(..., description="Column number")
    message: str = Field(..., description="Error message")
    element: Optional[str] = Field(None, description="Element that failed")


class XSDValidationResult(BaseModel):
    """Result of XSD schema validation"""
    valid: bool
    errors: List[XSDError] = Field(default_factory=list)
    schema_version: str = Field(..., description="Schema version used")
