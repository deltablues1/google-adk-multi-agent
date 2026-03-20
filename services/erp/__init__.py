"""ERP Service Layer — deterministic business logic, no LLM."""

from .errors import (
    BusinessError, ValidationError, InvalidStateTransitionError,
    DuplicateError, NotFoundError, InsufficientPermissionError,
)
from .request_context import ERPRequestContext, build_context, build_system_context
from .state_machines import (
    OUTGOING_INVOICE_DOC_TRANSITIONS,
    VENDOR_INVOICE_DOC_TRANSITIONS,
    validate_transition,
    compute_payment_status,
    is_overdue,
)
from .invoice_service import InvoiceService
from .payment_service import PaymentService
from .customer_service import CustomerService
from .product_service import ProductService
from .vendor_invoice_service import VendorInvoiceService
from .reporting_service import ReportingService

__all__ = [
    "BusinessError", "ValidationError", "InvalidStateTransitionError",
    "DuplicateError", "NotFoundError", "InsufficientPermissionError",
    "ERPRequestContext", "build_context", "build_system_context",
    "OUTGOING_INVOICE_DOC_TRANSITIONS", "VENDOR_INVOICE_DOC_TRANSITIONS",
    "validate_transition", "compute_payment_status", "is_overdue",
    "InvoiceService", "PaymentService", "CustomerService",
    "ProductService", "VendorInvoiceService", "ReportingService",
]
