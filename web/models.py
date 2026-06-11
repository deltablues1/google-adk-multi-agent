"""Pydantic models for Web API request/response."""

from decimal import Decimal
from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import uuid4


class FileAttachment(BaseModel):
    file_id: str
    mime_type: str
    base64: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    user_id: str = Field(default="web-user")
    session_id: Optional[str] = None
    route_hint: Optional[str] = None
    response_mode: Optional[str] = None
    attachments: Optional[List[FileAttachment]] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    timestamp: float


class SessionInfo(BaseModel):
    user_id: str
    session_id: str
    message_count: int
    last_activity: Optional[float]
    active: bool = False


class AgentInfo(BaseModel):
    name: str
    model: str
    description: str
    tools: List[str]


class TraceEvent(BaseModel):
    type: str
    name: str
    author: str
    timestamp: float
    args: Optional[str] = None
    result: Optional[str] = None


# ---------------------------------------------------------------------------
# ERP Models
# ---------------------------------------------------------------------------

class PaymentRequest(BaseModel):
    """Record a payment against an invoice."""
    amount: Decimal = Field(..., gt=0, description="Payment amount in EUR")
    payment_date: date
    payment_method: str = Field(
        ..., pattern="^(transfer|cash|card|direct_debit)$",
        description="transfer | cash | card | direct_debit"
    )
    reference: str = Field(default="", description="Poziv na broj / bank reference")
    notes: str = Field(default="")
    idempotency_key: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique key to prevent duplicate payment submissions"
    )


class VendorInvoiceCreate(BaseModel):
    """Create a new vendor invoice (URA — ulazni račun)."""
    vendor_id: str = Field(default="", description="FK → customers (party_type=supplier|both)")
    vendor_name: str = Field(default="", description="Vendor name (denormalized, required if vendor_id is empty)")
    vendor_oib: str = Field(default="", description="Vendor OIB")
    vendor_invoice_no: str = Field(default="", description="Supplier's own invoice number")
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    received_date: Optional[date] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_gross: Decimal = Field(..., gt=0, description="Total gross amount including VAT")
    vat_amount: Decimal = Field(..., ge=0, description="Total VAT amount")
    subtotal_net: Optional[Decimal] = None
    category: str = Field(
        default="services",
        description="materials | services | utilities | equipment | other"
    )
    vat_deductible: bool = Field(default=True, description="Can we reclaim input VAT?")
    notes: str = Field(default="")
    from_ocr: bool = Field(default=False, description="If True, vendor_id is optional (OCR/UBL import)")
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()))


class StockAdjustRequest(BaseModel):
    """Manual stock quantity adjustment."""
    new_quantity: Decimal = Field(..., ge=0, description="New absolute stock quantity")
    reason: str = Field(..., min_length=5, description="Reason for adjustment (min 5 chars)")


class CustomerCreate(BaseModel):
    """Create a new customer/vendor."""
    name: str = Field(..., min_length=1)
    oib: str = Field(default="", description="Croatian OIB (11 digits)")
    party_type: str = Field(
        default="customer",
        pattern="^(customer|supplier|both)$"
    )
    category: str = Field(
        default="B2B",
        description="B2B | B2C | B2G | EU | INT"
    )
    email: str = Field(default="")
    phone: str = Field(default="")
    address: str = Field(default="")
    city: str = Field(default="")
    postal_code: str = Field(default="")
    country: str = Field(default="HR")
    iban: str = Field(default="")
    payment_terms: int = Field(default=30, description="Payment terms in days")
    credit_limit: Optional[Decimal] = None
    notes: str = Field(default="")


class QuoteItemCreate(BaseModel):
    """A single line item on a quote."""
    description: str = Field(..., min_length=1)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(..., ge=0)
    vat_rate: int = Field(default=25, description="VAT rate: 0, 5, 13, or 25")


class QuoteCreate(BaseModel):
    """Create a new quote (ponuda)."""
    customer_id: str = Field(..., min_length=1)
    customer_name: str = Field(default="")
    customer_oib: str = Field(default="")
    valid_until: date
    currency: str = Field(default="EUR")
    items: List[QuoteItemCreate] = Field(..., min_length=1)
    notes: str = Field(default="")


class QuoteUpdate(BaseModel):
    """Update a draft quote."""
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_oib: Optional[str] = None
    valid_until: Optional[date] = None
    currency: Optional[str] = None
    items: Optional[List[QuoteItemCreate]] = None
    notes: Optional[str] = None


class QuoteConvertRequest(BaseModel):
    """Convert a quote to an invoice."""
    invoice_type: str = Field(
        default="b2c",
        pattern="^(b2c|b2b|b2g|eu|int)$",
        description="Target invoice type: b2c | b2b | b2g | eu | int"
    )


class QuoteCreateInvoiceRequest(BaseModel):
    """
    Optional overrides when creating an outbound invoice from an accepted quote.
    All fields are optional — quote data is used as the base.

    invoice_type controls the target pipeline:
      "b2b" (default) — domestic B2B eRačun via OutboundB2BService
      "b2g"           — public-sector B2G eRačun via FINA Peppol / OutboundB2GService
    """
    invoice_type:       str            = Field(
        default="b2b",
        pattern="^(b2b|b2g)$",
        description="Target invoice pipeline: b2b (default) | b2g",
    )
    # Seller overrides (both types)
    seller_name:    Optional[str]  = None
    seller_oib:     Optional[str]  = None
    seller_iban:    Optional[str]  = None
    seller_address: Optional[str]  = None
    seller_city:    Optional[str]  = None
    due_date:       Optional[date] = None
    notes:          Optional[str]  = None
    # B2G-specific overrides (ignored for b2b)
    buyer_reference:    Optional[str] = Field(
        default=None,
        description="Contract/procurement reference number (EN 16931 BT-10). B2G only.",
    )
    customer_peppol_id: Optional[str] = Field(
        default=None,
        description="Buyer Peppol participant ID (e.g. '0190:12345678901'). B2G only.",
    )


class ProductCreate(BaseModel):
    """Create a new product/service."""
    sku: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    category: str = Field(default="")
    kpd_code: str = Field(default="", description="Croatian CPA/KPD classification code")
    unit: str = Field(default="kom")
    price: Decimal = Field(..., ge=0, description="Base price (net, without VAT)")
    cost_price: Optional[Decimal] = Field(default=None)
    vat_rate: int = Field(default=25, description="VAT rate: 0, 5, 13, or 25")
    stock_quantity: Decimal = Field(default=Decimal("0"))
    min_stock: Optional[Decimal] = None
    active: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Outbound B2B eRačun models
# ---------------------------------------------------------------------------

class OutboundB2BItemCreate(BaseModel):
    """A single line item on an outbound B2B invoice."""
    description: str = Field(..., min_length=1)
    name: str = Field(default="")
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit: str = Field(default="kom", description="Unit of measure (e.g. kom, sat, kg)")
    unit_price: Decimal = Field(..., ge=0, description="Net unit price (without VAT)")
    vat_rate: int = Field(default=25, description="VAT rate: 0, 5, 13, or 25")


class OutboundB2BCreate(BaseModel):
    """Create a new outgoing domestic B2B invoice (eRačun)."""
    # Buyer
    customer_id: str = Field(default="", description="FK → customers collection")
    customer_name: str = Field(..., min_length=1)
    customer_oib: str = Field(..., min_length=11, max_length=11, description="Buyer OIB (11 digits)")
    customer_address: str = Field(default="")
    customer_city: str = Field(default="")
    customer_country: str = Field(default="HR")

    # Seller info (filled from company profile or request body)
    seller_name: str = Field(default="", description="Seller name — defaults to company profile")
    seller_oib: str = Field(default="", description="Seller OIB")
    seller_iban: str = Field(default="", description="Seller IBAN for payment block in UBL")
    seller_address: str = Field(default="")
    seller_city: str = Field(default="")

    # Invoice header
    invoice_number: str = Field(default="", description="Seller invoice number (auto-generated if empty)")
    issue_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    payment_terms: int = Field(default=30, description="Payment terms in days")
    currency: str = Field(default="EUR")

    # Items (required — at least 1)
    items: List[OutboundB2BItemCreate] = Field(..., min_length=1)

    notes: str = Field(default="")


class OutboundB2GCreate(BaseModel):
    """Create a new outgoing B2G (public-sector) invoice (eRačun via FINA Peppol)."""
    # Buyer (public-sector entity)
    customer_id: str = Field(default="")
    customer_name: str = Field(..., min_length=1)
    customer_oib: str = Field(..., min_length=11, max_length=11, description="Buyer OIB (11 digits)")
    customer_address: str = Field(default="")
    customer_city: str = Field(default="")
    customer_country: str = Field(default="HR")
    customer_peppol_id: str = Field(
        default="",
        description="Buyer Peppol participant ID (e.g. '0190:12345678901'). "
                    "Pre-fills delivery_target for Peppol dispatch.",
    )

    # B2G-specific
    buyer_reference: str = Field(
        default="",
        description="Contract/procurement reference (EN 16931 BT-10 BuyerReference). "
                    "Strongly recommended for public-sector invoices.",
    )

    # Seller (auto-resolved from company profile when empty)
    seller_name: str = Field(default="")
    seller_oib: str = Field(default="")
    seller_iban: str = Field(default="")
    seller_address: str = Field(default="")
    seller_city: str = Field(default="")

    # Invoice header
    invoice_number: str = Field(default="")
    issue_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    payment_terms: int = Field(default=30)
    currency: str = Field(default="EUR")

    items: List[OutboundB2BItemCreate] = Field(..., min_length=1)
    notes: str = Field(default="")


class OutboundB2BSendRequest(BaseModel):
    """Send an issued B2B invoice to the buyer."""
    delivery_method: str = Field(
        ..., pattern="^(email|peppol|manual)$",
        description="email | peppol | manual"
    )
    delivery_target: str = Field(
        default="",
        description="Email address, Peppol participant ID, or blank for manual delivery"
    )
    delivery_ref: str = Field(default="", description="AP confirmation reference (optional)")


class OutboundB2BRejectRequest(BaseModel):
    """Buyer rejection of a sent/delivered B2B invoice."""
    rejection_reason: str = Field(..., min_length=5, description="Mandatory rejection reason")
