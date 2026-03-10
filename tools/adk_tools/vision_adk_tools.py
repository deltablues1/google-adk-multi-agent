"""
Vision ADK Tools

ADK-compatible wrappers for Vision/OCR operations using Gemini Flash.
"""

from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# AUTHENTICATION HELPER
# ============================================================================

def _get_credentials():
    """Get OAuth credentials from token file"""
    try:
        from auth.oauth_manager import get_oauth_manager
        oauth_manager = get_oauth_manager()
        creds = oauth_manager.get_credentials()
        if creds and creds.valid:
            return creds
        logger.warning("No valid credentials available for Vision operations")
        return None
    except Exception as e:
        logger.error(f"Failed to get credentials: {e}")
        return None


# ============================================================================
# VISION/OCR TOOLS
# ============================================================================

async def extract_receipt_data(
    image_data: str,
    mime_type: str = "image/jpeg"
) -> dict:
    """
    Extract structured data from a receipt image using Gemini Flash OCR.

    This function uses Gemini 2.0 Flash multimodal OCR to extract:
    - Merchant name
    - Transaction date (YYYY-MM-DD)
    - Total amount and currency
    - Individual line items (if visible)
    - Expense category (Hrana, Prijevoz, Ured, Režije, Ostalo)
    - Payment method, VAT, receipt number (if available)
    - Confidence score (0.0 - 1.0)

    Confidence thresholds:
    - < 0.5: Very low confidence - Manual review required
    - 0.5-0.79: Low confidence - User confirmation recommended
    - ≥ 0.8: High confidence - Auto-save allowed

    Args:
        image_data: Base64 encoded image data OR Google Drive File ID
        mime_type: MIME type of the image (default: "image/jpeg")
                  Common types: "image/jpeg", "image/png", "image/bmp"

    Returns:
        Dictionary containing:
            - merchant_name: Name of merchant/vendor
            - transaction_date: Date in YYYY-MM-DD format
            - total_amount: Total amount as float
            - currency: Currency code (EUR, USD, HRK, etc.)
            - expense_category: Category (Hrana, Prijevoz, Ured, Režije, Ostalo)
            - items: List of line items with description and amount
            - receipt_number: Receipt/invoice number (optional)
            - payment_method: Payment method (optional)
            - vat_amount: VAT amount (optional)
            - confidence_score: Confidence score (0.0 - 1.0)
            - extraction_notes: Any notes about the extraction

    Example:
        result = await extract_receipt_data(
            image_data="base64_encoded_image_here",
            mime_type="image/jpeg"
        )
        # Returns: {"merchant_name": "Konzum", "total_amount": 125.50, ...}
    """
    creds = _get_credentials()

    try:
        from tools.handlers.vision_handler import VisionHandler
        handler = VisionHandler()

        # Call OCR extraction
        receipt_data = await handler.extract_receipt_data(
            image_data=image_data,
            mime_type=mime_type,
            credentials=creds
        )

        logger.info(
            f"Receipt OCR completed: {receipt_data.get('merchant_name', 'Unknown')}, "
            f"{receipt_data.get('total_amount', 0)} {receipt_data.get('currency', 'EUR')}, "
            f"confidence={receipt_data.get('confidence_score', 0):.2f}"
        )

        # Wrap in status envelope for consistent response format
        return {
            "status": "success",
            "data": receipt_data
        }

    except Exception as e:
        logger.error(f"extract_receipt_data failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "message": "OCR extraction failed. Image may be too blurry or unreadable."
        }


async def categorize_expense(
    merchant: str,
    items: Optional[List[str]] = None,
    total_amount: float = 0.0
) -> dict:
    """
    Automatically categorize an expense based on merchant name and items.

    Uses Gemini Flash to intelligently categorize expenses into one of:
    - Hrana (Food): Restaurants, groceries, cafes, food delivery
    - Prijevoz (Transport): Fuel, parking, public transport, taxi
    - Ured (Office): Office supplies, electronics, software
    - Režije (Utilities): Electricity, gas, water, internet, mobile
    - Ostalo (Other): Everything else

    Args:
        merchant: Name of the merchant/vendor
        items: Optional list of item descriptions
        total_amount: Optional total amount (helps with categorization)

    Returns:
        Dictionary containing:
            - category: Expense category (one of the 5 categories above)
            - confidence: Confidence in categorization
            - reasoning: Brief explanation of why this category was chosen

    Example:
        result = await categorize_expense(
            merchant="Konzum",
            items=["Mlijeko", "Kruh", "Voće"]
        )
        # Returns: {"category": "Hrana", "confidence": 0.95, "reasoning": "Grocery store"}
    """
    creds = _get_credentials()

    try:
        from tools.handlers.vision_handler import VisionHandler
        handler = VisionHandler()

        # Call categorization
        category = await handler.categorize_expense(
            merchant=merchant,
            items=items or [],
            total_amount=total_amount,
            credentials=creds
        )

        logger.info(f"Expense categorized: {merchant} → {category}")

        return {
            "category": category,
            "merchant": merchant,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"categorize_expense failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "category": "Ostalo"  # Default fallback
        }
