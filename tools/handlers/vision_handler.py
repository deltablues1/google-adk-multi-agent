"""
Vision Handler
Implements OCR and image analysis logic using Gemini 2.5 Flash.
"""

import os
import sys
import base64
import json
import logging
from typing import Optional, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from google.genai import Client
from tools.schemas.receipt_schema import Receipt

logger = logging.getLogger(__name__)

class VisionHandler:
    """
    Handles Vision API interactions for OCR.
    """

    def __init__(self):
        """Initialize Vision Handler"""
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        # Use standard flash model (thinking model not available in all regions)
        self.model = os.getenv("VISION_MODEL", "gemini-2.5-flash")
        
        try:
            self.client = Client(project=self.project_id, location=self.location)
            logger.info(f"VisionHandler initialized with model {self.model}")
        except Exception as e:
            logger.error(f"Failed to initialize VisionHandler client: {e}")
            self.client = None

    async def extract_receipt_data(self, image_data: str, mime_type: str = "image/jpeg", credentials: Optional[Any] = None, **kwargs) -> Dict[str, Any]:
        """
        Extracts structured data from a receipt image.
        Accepts base64 image data OR a Google Drive File ID.
        """
        if not self.client:
            raise RuntimeError("VisionHandler client not initialized")

        logger.info("Extracting receipt data...")

        try:
            # Check if image_data looks like a File ID (alphanumeric, no special chars like / or +, typical length ~33)
            # Base64 usually has / and + and ends with =. File IDs are url-safe base64 but usually just alphanumeric and -_
            is_file_id = len(image_data) < 100 and " " not in image_data and "/" not in image_data and "+" not in image_data

            if is_file_id:
                logger.info(f"Input looks like a File ID: {image_data}. Downloading...")
                from tools.api_implementations.drive_api import drive_get_file
                
                # Download file
                file_result = await drive_get_file(credentials, file_id=image_data, include_content=True)
                image_data = file_result.get('content')
                mime_type = file_result.get('metadata', {}).get('mimeType', mime_type)
                
                if not image_data:
                     raise ValueError(f"Failed to download content for file ID: {image_data}")

            # Handle BMP conversion (to save tokens)
            if mime_type == "image/bmp" or mime_type == "image/x-ms-bmp":
                logger.info("Detected BMP image. Converting to JPEG to reduce token usage...")
                try:
                    from PIL import Image
                    import io
                    
                    # Decode base64
                    img_bytes = base64.b64decode(image_data)
                    
                    # Open image
                    with Image.open(io.BytesIO(img_bytes)) as img:
                        # Convert to RGB (BMP can be RGBA or P)
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Save as JPEG
                        output_buffer = io.BytesIO()
                        img.save(output_buffer, format='JPEG', quality=85)
                        
                        # Encode back to base64
                        image_data = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                        mime_type = "image/jpeg"
                        logger.info("Successfully converted BMP to JPEG")
                        
                except ImportError:
                    logger.warning("PIL not installed. Skipping BMP conversion. This might cause token limit errors.")
                except Exception as e:
                    logger.error(f"Error converting BMP: {e}. Proceeding with original image.")

            # Prepare the prompt
            prompt = """
            You are analyzing an INCOMING INVOICE (ulazni račun) received by the company "Lux Tech d.o.o." (OIB: HR47034854402).

            CRITICAL INSTRUCTIONS:

            1. VENDOR vs CUSTOMER - PAY ATTENTION!
               - This is an INCOMING invoice (ulazni račun)
               - VENDOR (Dobavljač) = The company that SENT this invoice (usually at the TOP of the document)
               - CUSTOMER (Kupac/Primatelj) = Lux Tech d.o.o. (recipient - IGNORE THIS!)

            2. WHAT TO EXTRACT:
               Extract data from the VENDOR (sender), NOT the customer (Lux Tech):

               ✅ CORRECT - Extract from VENDOR:
                  - Merchant Name = VENDOR's company name (NOT "Lux Tech")
                  - Tax ID (OIB) = VENDOR's OIB (NOT "HR47034854402")
                  - Company details = VENDOR's address and info

               ❌ WRONG - Do NOT extract from customer:
                  - Ignore "Lux Tech d.o.o."
                  - Ignore OIB "HR47034854402"
                  - Ignore any "Kupac" or "Primatelj" section

            3. FIELDS TO EXTRACT:
               - merchant_name: VENDOR's company name (e.g., "Konzum d.o.o.", "INA d.d.", NOT "Lux Tech")
               - transaction_date: Invoice date in YYYY-MM-DD format
               - total_amount: Total amount to pay (Ukupno)
               - currency: Currency (EUR, HRK, USD)
               - receipt_number: Invoice number (Broj računa)
               - tax_id: VENDOR's OIB (NOT HR47034854402!)
               - tax_base: Tax base amount (Osnovica)
               - tax_amount: VAT amount (Iznos PDV-a)
               - items: Line items if visible
               - expense_category: Category based on vendor (Hrana, Prijevoz, Ured, Režije, Ostalo)

            4. VALIDATION:
               - If merchant_name contains "Lux Tech" → YOU MADE A MISTAKE! Extract the OTHER company!
               - If tax_id is "HR47034854402" → YOU MADE A MISTAKE! Extract the VENDOR's OIB!

            5. CONFIDENCE SCORING:
               - High confidence (>0.85) only if all critical fields are clearly visible
               - Low confidence (<0.7) if you had to guess or data is unclear

            Return the data as a JSON object matching the Receipt schema.
            """

            # Decode base64 if needed (Gemini client might handle it, but let's be safe)
            # Actually, google.genai client expects 'types.Part' or similar for images
            from google.genai import types
            
            # Create the image part
            # Assuming image_data is base64 string
            image_part = types.Part.from_bytes(
                data=base64.b64decode(image_data),
                mime_type=mime_type
            )

            # Call the model
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image_part],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Receipt
                }
            )

            # Parse response
            if response.text:
                data = json.loads(response.text)
                logger.info("Receipt data extracted successfully")
                return data
            else:
                raise ValueError("Empty response from model")

        except Exception as e:
            logger.error(f"Error extracting receipt data: {e}")
            raise

    async def categorize_expense(self, merchant: str, items: list, total_amount: float, credentials: Optional[Any] = None, **kwargs) -> str:
        """
        Categorizes an expense based on details.
        """
        # Simple logic for now, could use LLM if needed
        # But since extract_receipt_data already does categorization, this might be redundant
        # or used for manual entries.
        
        prompt = f"Categorize expense: Merchant={merchant}, Items={items}, Amount={total_amount}"
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        return response.text.strip()
