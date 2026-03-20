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
    vendor_invoice_no: str = Field(default="", description="Supplier's own invoice number")
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_gross: Decimal = Field(..., gt=0, description="Total gross amount including VAT")
    vat_amount: Decimal = Field(..., ge=0, description="Total VAT amount")
    category: str = Field(
        default="services",
        description="materials | services | utilities | equipment | other"
    )
    vat_deductible: bool = Field(default=True, description="Can we reclaim input VAT?")
    notes: str = Field(default="")
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
