"""
Human-in-the-Loop (HITL) Confirmation Service for Fiskalizacija

Provides structured confirmation dialogs before critical operations:
1. Invoice fiscalization - review before sending to FINA
2. NKD activity validation warnings
3. Amount verification
4. Povratna naknada handling

This ensures human oversight to prevent errors and LLM hallucinations.
"""

import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConfirmationStatus(Enum):
    """Status of confirmation request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    EXPIRED = "expired"


class WarningLevel(Enum):
    """Warning severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ConfirmationWarning:
    """A warning or notice in confirmation dialog."""
    level: WarningLevel
    code: str
    message: str
    field: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "suggestion": self.suggestion
        }


@dataclass
class InvoiceLineConfirmation:
    """Single invoice line for confirmation."""
    index: int
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    line_total: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    nkd_code: Optional[str] = None
    nkd_name: Optional[str] = None
    nkd_registered: bool = True
    warnings: List[ConfirmationWarning] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "description": self.description,
            "quantity": str(self.quantity),
            "unit": self.unit,
            "unit_price": str(self.unit_price),
            "line_total": str(self.line_total),
            "vat_rate": str(self.vat_rate),
            "vat_amount": str(self.vat_amount),
            "nkd_code": self.nkd_code,
            "nkd_name": self.nkd_name,
            "nkd_registered": self.nkd_registered,
            "warnings": [w.to_dict() for w in self.warnings]
        }


@dataclass
class DepositRefundConfirmation:
    """Povratna naknada (deposit refund) for confirmation."""
    unit_count: int
    unit_amount: Decimal
    total_amount: Decimal
    is_pass_through: bool = True  # Not subject to VAT

    def to_dict(self) -> dict:
        return {
            "unit_count": self.unit_count,
            "unit_amount": str(self.unit_amount),
            "total_amount": str(self.total_amount),
            "is_pass_through": self.is_pass_through,
            "note": "Prolazna stavka - ne podliježe PDV-u, ide FZOEU"
        }


@dataclass
class FiscalizationConfirmation:
    """
    Complete confirmation request for fiscalization.

    This is the main structure shown to user before fiscalization.
    """
    # Identification
    confirmation_id: str
    created_at: datetime
    status: ConfirmationStatus = ConfirmationStatus.PENDING

    # Invoice details
    invoice_number: str = ""
    invoice_date: str = ""
    invoice_time: str = ""

    # Parties
    supplier_name: str = ""
    supplier_oib: str = ""
    supplier_address: str = ""
    customer_name: str = ""
    customer_oib: str = ""
    customer_address: str = ""

    # Business context
    business_unit: str = ""  # Poslovni prostor
    device_number: str = ""  # Naplatni uređaj

    # Lines
    lines: List[InvoiceLineConfirmation] = field(default_factory=list)

    # Deposit refund (povratna naknada)
    deposit_refund: Optional[DepositRefundConfirmation] = None

    # Totals
    subtotal: Decimal = Decimal("0")
    total_vat: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")

    # VAT breakdown
    vat_breakdown: Dict[str, Dict[str, Decimal]] = field(default_factory=dict)

    # Warnings and validation
    warnings: List[ConfirmationWarning] = field(default_factory=list)
    has_critical_warnings: bool = False
    has_unregistered_activities: bool = False

    # Calculated fields
    zki_preview: Optional[str] = None

    # User response
    user_notes: str = ""
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "confirmation_id": self.confirmation_id,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "invoice": {
                "number": self.invoice_number,
                "date": self.invoice_date,
                "time": self.invoice_time
            },
            "supplier": {
                "name": self.supplier_name,
                "oib": self.supplier_oib,
                "address": self.supplier_address
            },
            "customer": {
                "name": self.customer_name,
                "oib": self.customer_oib,
                "address": self.customer_address
            },
            "business_context": {
                "business_unit": self.business_unit,
                "device_number": self.device_number
            },
            "lines": [line.to_dict() for line in self.lines],
            "deposit_refund": self.deposit_refund.to_dict() if self.deposit_refund else None,
            "totals": {
                "subtotal": str(self.subtotal),
                "total_vat": str(self.total_vat),
                "total_amount": str(self.total_amount)
            },
            "vat_breakdown": {
                rate: {
                    "base": str(values.get("base", Decimal("0"))),
                    "amount": str(values.get("amount", Decimal("0")))
                }
                for rate, values in self.vat_breakdown.items()
            },
            "warnings": [w.to_dict() for w in self.warnings],
            "has_critical_warnings": self.has_critical_warnings,
            "has_unregistered_activities": self.has_unregistered_activities,
            "zki_preview": self.zki_preview,
            "user_notes": self.user_notes,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by
        }

    def to_display_text(self) -> str:
        """
        Generate human-readable confirmation text.

        This is what the user sees for review.
        """
        lines = []
        sep = "=" * 60

        # Header
        lines.append(sep)
        lines.append("  FISKALIZACIJA - PROVJERA PRIJE SLANJA")
        lines.append(sep)
        lines.append("")

        # Invoice info
        lines.append(f"Račun: {self.invoice_number}")
        lines.append(f"Datum: {self.invoice_date} {self.invoice_time}")
        lines.append("")

        # Parties
        lines.append(f"Izdavatelj: {self.supplier_name}")
        lines.append(f"OIB: {self.supplier_oib}")
        if self.supplier_address:
            lines.append(f"Adresa: {self.supplier_address}")
        lines.append("")

        lines.append(f"Kupac: {self.customer_name}")
        lines.append(f"OIB: {self.customer_oib}")
        if self.customer_address:
            lines.append(f"Adresa: {self.customer_address}")
        lines.append("")

        # Business context
        lines.append(f"Poslovni prostor: {self.business_unit}")
        lines.append(f"Naplatni uređaj: {self.device_number}")
        lines.append("")

        # Lines
        lines.append("-" * 60)
        lines.append("STAVKE:")
        lines.append("-" * 60)

        for line in self.lines:
            # Main line info
            nkd_info = f"[{line.nkd_code}]" if line.nkd_code else "[NKD nije određen]"
            status = "[OK]" if line.nkd_registered else "[!]"

            lines.append(f"{line.index + 1}. {line.description}")
            lines.append(f"   {line.quantity} {line.unit} x {line.unit_price} EUR = {line.line_total} EUR")
            lines.append(f"   PDV {line.vat_rate}%: {line.vat_amount} EUR")
            lines.append(f"   NKD: {nkd_info} {status}")

            if line.nkd_name:
                lines.append(f"   Djelatnost: {line.nkd_name}")

            # Line warnings
            for warning in line.warnings:
                prefix = "!!!" if warning.level == WarningLevel.ERROR else "!"
                lines.append(f"   {prefix} {warning.message}")

            lines.append("")

        # Deposit refund
        if self.deposit_refund:
            lines.append("-" * 60)
            lines.append("POVRATNA NAKNADA (prolazna stavka):")
            lines.append(f"   {self.deposit_refund.unit_count} x {self.deposit_refund.unit_amount} EUR = {self.deposit_refund.total_amount} EUR")
            lines.append("   Napomena: Ne podliježe PDV-u, ide Fondu za zaštitu okoliša")
            lines.append("")

        # Totals
        lines.append("-" * 60)
        lines.append("UKUPNO:")
        lines.append(f"   Osnovica: {self.subtotal} EUR")

        for rate, values in self.vat_breakdown.items():
            lines.append(f"   PDV {rate}%: {values.get('amount', 0)} EUR (na {values.get('base', 0)} EUR)")

        lines.append(f"   UKUPNO ZA PLATITI: {self.total_amount} EUR")

        if self.deposit_refund:
            total_with_deposit = self.total_amount + self.deposit_refund.total_amount
            lines.append(f"   (s povratnom naknadom: {total_with_deposit} EUR)")

        lines.append("")

        # Warnings
        if self.warnings:
            lines.append("-" * 60)
            lines.append("UPOZORENJA:")
            for warning in self.warnings:
                if warning.level == WarningLevel.CRITICAL:
                    prefix = "[!!!]"
                elif warning.level == WarningLevel.ERROR:
                    prefix = "[!!]"
                elif warning.level == WarningLevel.WARNING:
                    prefix = "[!]"
                else:
                    prefix = "[i]"

                lines.append(f"   {prefix} {warning.message}")
                if warning.suggestion:
                    lines.append(f"       Prijedlog: {warning.suggestion}")
            lines.append("")

        # ZKI preview
        if self.zki_preview:
            lines.append(f"ZKI (preview): {self.zki_preview[:20]}...")
            lines.append("")

        # Footer
        lines.append(sep)

        if self.has_critical_warnings:
            lines.append("!!! KRITIČNA UPOZORENJA - preporučuje se ispravak prije fiskalizacije")
        elif self.has_unregistered_activities:
            lines.append("! Postoje neregistrirane djelatnosti - provjerite prije potvrde")
        else:
            lines.append("Sve provjere uspješne - račun spreman za fiskalizaciju")

        lines.append(sep)

        return "\n".join(lines)


class HITLConfirmationService:
    """
    Service for managing Human-in-the-Loop confirmations.

    Handles:
    - Creating confirmation requests from invoice data
    - Validating and adding warnings
    - Storing pending confirmations
    - Processing user responses
    """

    def __init__(self):
        """Initialize HITL service."""
        self._pending_confirmations: Dict[str, FiscalizationConfirmation] = {}
        self._confirmation_history: List[FiscalizationConfirmation] = []

    def create_confirmation(
        self,
        invoice_data: Dict[str, Any],
        nkd_service=None,
        calculate_zki_preview: bool = False
    ) -> FiscalizationConfirmation:
        """
        Create a confirmation request from invoice data.

        Args:
            invoice_data: Invoice data dictionary
            nkd_service: Optional NKD service for activity validation
            calculate_zki_preview: Whether to calculate ZKI preview

        Returns:
            FiscalizationConfirmation ready for user review
        """
        import uuid
        from datetime import datetime

        confirmation = FiscalizationConfirmation(
            confirmation_id=str(uuid.uuid4())[:8],
            created_at=datetime.now()
        )

        # Extract invoice details
        confirmation.invoice_number = invoice_data.get("invoice_number", "")
        confirmation.invoice_date = invoice_data.get("invoice_date", "")
        confirmation.invoice_time = invoice_data.get("invoice_time", "")

        # Supplier
        supplier = invoice_data.get("supplier", {})
        confirmation.supplier_name = supplier.get("name", "")
        confirmation.supplier_oib = supplier.get("oib", "")
        confirmation.supplier_address = supplier.get("address", "")

        # Customer
        customer = invoice_data.get("customer", {})
        confirmation.customer_name = customer.get("name", "")
        confirmation.customer_oib = customer.get("oib", "")
        confirmation.customer_address = customer.get("address", "")

        # Business context
        confirmation.business_unit = invoice_data.get("business_unit", "")
        confirmation.device_number = invoice_data.get("device_number", "")

        # Process lines (accept both "lines" and "items" keys)
        lines_data = invoice_data.get("lines") or invoice_data.get("items", [])
        subtotal = Decimal("0")
        total_vat = Decimal("0")
        vat_breakdown = {}

        for i, line_data in enumerate(lines_data):
            line = self._create_line_confirmation(i, line_data, nkd_service)
            confirmation.lines.append(line)

            # Accumulate totals
            subtotal += line.line_total
            total_vat += line.vat_amount

            # VAT breakdown
            rate_key = str(line.vat_rate)
            if rate_key not in vat_breakdown:
                vat_breakdown[rate_key] = {"base": Decimal("0"), "amount": Decimal("0")}
            vat_breakdown[rate_key]["base"] += line.line_total
            vat_breakdown[rate_key]["amount"] += line.vat_amount

            # Check for unregistered activities
            if not line.nkd_registered:
                confirmation.has_unregistered_activities = True

        confirmation.subtotal = subtotal
        confirmation.total_vat = total_vat
        confirmation.total_amount = subtotal + total_vat
        confirmation.vat_breakdown = vat_breakdown

        # Process deposit refund (povratna naknada)
        deposit_data = invoice_data.get("deposit_refund")
        if deposit_data:
            confirmation.deposit_refund = DepositRefundConfirmation(
                unit_count=deposit_data.get("unit_count", 0),
                unit_amount=Decimal(str(deposit_data.get("unit_amount", "0.10"))),
                total_amount=Decimal(str(deposit_data.get("total_amount", "0")))
            )

        # Add general validations
        self._add_validations(confirmation)

        # Store in pending
        self._pending_confirmations[confirmation.confirmation_id] = confirmation

        return confirmation

    def _create_line_confirmation(
        self,
        index: int,
        line_data: dict,
        nkd_service=None
    ) -> InvoiceLineConfirmation:
        """Create line confirmation with validations."""
        line = InvoiceLineConfirmation(
            index=index,
            description=line_data.get("description", ""),
            quantity=Decimal(str(line_data.get("quantity", "0"))),
            unit=line_data.get("unit", "kom"),
            unit_price=Decimal(str(line_data.get("unit_price", "0"))),
            line_total=Decimal(str(line_data.get("line_total", "0"))),
            vat_rate=Decimal(str(line_data.get("vat_rate", "25"))),
            vat_amount=Decimal(str(line_data.get("vat_amount", "0"))),
            nkd_code=line_data.get("nkd_code"),
            nkd_name=line_data.get("nkd_name")
        )

        # Validate NKD if service available
        if nkd_service and line.nkd_code:
            is_registered, warning = nkd_service.is_activity_registered(line.nkd_code)
            line.nkd_registered = is_registered

            if not is_registered:
                line.warnings.append(ConfirmationWarning(
                    level=WarningLevel.WARNING,
                    code="NKD_NOT_REGISTERED",
                    message=warning or f"NKD {line.nkd_code} nije registrirana djelatnost",
                    field="nkd_code",
                    suggestion="Registrirajte djelatnost ili odaberite drugu NKD šifru"
                ))

        # Validate line total
        expected_total = line.quantity * line.unit_price
        if abs(expected_total - line.line_total) > Decimal("0.01"):
            line.warnings.append(ConfirmationWarning(
                level=WarningLevel.ERROR,
                code="TOTAL_MISMATCH",
                message=f"Iznos stavke ({line.line_total}) ne odgovara izračunu ({expected_total})",
                field="line_total"
            ))

        return line

    def _add_validations(self, confirmation: FiscalizationConfirmation):
        """Add general validations and warnings."""
        # OIB validation
        if not self._validate_oib(confirmation.supplier_oib):
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.CRITICAL,
                code="INVALID_SUPPLIER_OIB",
                message=f"Neispravan OIB izdavatelja: {confirmation.supplier_oib}",
                field="supplier_oib"
            ))
            confirmation.has_critical_warnings = True

        if confirmation.customer_oib and not self._validate_oib(confirmation.customer_oib):
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.WARNING,
                code="INVALID_CUSTOMER_OIB",
                message=f"Neispravan OIB kupca: {confirmation.customer_oib}",
                field="customer_oib"
            ))

        # Invoice number format
        if not confirmation.invoice_number:
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.CRITICAL,
                code="MISSING_INVOICE_NUMBER",
                message="Nedostaje broj računa",
                field="invoice_number"
            ))
            confirmation.has_critical_warnings = True

        # Business context
        if not confirmation.business_unit:
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.CRITICAL,
                code="MISSING_BUSINESS_UNIT",
                message="Nedostaje oznaka poslovnog prostora",
                field="business_unit"
            ))
            confirmation.has_critical_warnings = True

        if not confirmation.device_number:
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.CRITICAL,
                code="MISSING_DEVICE_NUMBER",
                message="Nedostaje oznaka naplatnog uređaja",
                field="device_number"
            ))
            confirmation.has_critical_warnings = True

        # Empty invoice
        if not confirmation.lines:
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.CRITICAL,
                code="NO_LINES",
                message="Račun nema stavki",
                field="lines"
            ))
            confirmation.has_critical_warnings = True

        # Amount validations
        if confirmation.total_amount <= Decimal("0"):
            confirmation.warnings.append(ConfirmationWarning(
                level=WarningLevel.WARNING,
                code="ZERO_AMOUNT",
                message="Ukupni iznos računa je 0 ili negativan",
                field="total_amount"
            ))

    def _validate_oib(self, oib: str) -> bool:
        """Validate Croatian OIB."""
        if not oib or len(oib) != 11:
            return False

        try:
            # ISO 7064, MOD 11-10 check
            remainder = 10
            for digit in oib[:10]:
                remainder = (remainder + int(digit)) % 10
                if remainder == 0:
                    remainder = 10
                remainder = (remainder * 2) % 11

            check_digit = (11 - remainder) % 10
            return check_digit == int(oib[10])
        except (ValueError, IndexError):
            return False

    def get_pending(self, confirmation_id: str) -> Optional[FiscalizationConfirmation]:
        """Get pending confirmation by ID."""
        return self._pending_confirmations.get(confirmation_id)

    def approve(
        self,
        confirmation_id: str,
        approved_by: str = "user",
        notes: str = ""
    ) -> Optional[FiscalizationConfirmation]:
        """
        Approve a pending confirmation.

        Args:
            confirmation_id: Confirmation ID
            approved_by: Who approved
            notes: Optional notes

        Returns:
            Approved confirmation or None if not found
        """
        confirmation = self._pending_confirmations.get(confirmation_id)
        if not confirmation:
            return None

        confirmation.status = ConfirmationStatus.APPROVED
        confirmation.approved_at = datetime.now()
        confirmation.approved_by = approved_by
        confirmation.user_notes = notes

        # Move to history
        self._confirmation_history.append(confirmation)
        del self._pending_confirmations[confirmation_id]

        logger.info(f"Confirmation {confirmation_id} approved by {approved_by}")
        return confirmation

    def reject(
        self,
        confirmation_id: str,
        reason: str = ""
    ) -> Optional[FiscalizationConfirmation]:
        """
        Reject a pending confirmation.

        Args:
            confirmation_id: Confirmation ID
            reason: Rejection reason

        Returns:
            Rejected confirmation or None if not found
        """
        confirmation = self._pending_confirmations.get(confirmation_id)
        if not confirmation:
            return None

        confirmation.status = ConfirmationStatus.REJECTED
        confirmation.user_notes = reason

        # Move to history
        self._confirmation_history.append(confirmation)
        del self._pending_confirmations[confirmation_id]

        logger.info(f"Confirmation {confirmation_id} rejected: {reason}")
        return confirmation

    def list_pending(self) -> List[FiscalizationConfirmation]:
        """Get all pending confirmations."""
        return list(self._pending_confirmations.values())


# ============================================================================
# Module-level singleton and helper functions
# ============================================================================

_hitl_service: Optional[HITLConfirmationService] = None


def get_hitl_service() -> HITLConfirmationService:
    """Get or create HITL service singleton."""
    global _hitl_service
    if _hitl_service is None:
        _hitl_service = HITLConfirmationService()
    return _hitl_service


def create_fiscalization_confirmation(
    invoice_data: Dict[str, Any],
    nkd_service=None
) -> Dict[str, Any]:
    """
    Create confirmation request for fiscalization.

    Args:
        invoice_data: Invoice data dictionary
        nkd_service: Optional NKD service for validation

    Returns:
        Confirmation data with display text
    """
    service = get_hitl_service()
    confirmation = service.create_confirmation(invoice_data, nkd_service)

    return {
        "confirmation_id": confirmation.confirmation_id,
        "status": confirmation.status.value,
        "display_text": confirmation.to_display_text(),
        "data": confirmation.to_dict(),
        "has_critical_warnings": confirmation.has_critical_warnings,
        "has_unregistered_activities": confirmation.has_unregistered_activities,
        "can_proceed": not confirmation.has_critical_warnings
    }


def approve_fiscalization(
    confirmation_id: str,
    approved_by: str = "user"
) -> Dict[str, Any]:
    """
    Approve pending fiscalization.

    Args:
        confirmation_id: Confirmation ID
        approved_by: Approver identifier

    Returns:
        Result with approval status
    """
    service = get_hitl_service()
    confirmation = service.approve(confirmation_id, approved_by)

    if confirmation:
        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "status": "approved",
            "approved_at": confirmation.approved_at.isoformat()
        }
    else:
        return {
            "success": False,
            "error": f"Confirmation {confirmation_id} not found"
        }


def reject_fiscalization(
    confirmation_id: str,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Reject pending fiscalization.

    Args:
        confirmation_id: Confirmation ID
        reason: Rejection reason

    Returns:
        Result with rejection status
    """
    service = get_hitl_service()
    confirmation = service.reject(confirmation_id, reason)

    if confirmation:
        return {
            "success": True,
            "confirmation_id": confirmation_id,
            "status": "rejected",
            "reason": reason
        }
    else:
        return {
            "success": False,
            "error": f"Confirmation {confirmation_id} not found"
        }
