"""
ERP Invoice Service
====================
Manages outgoing invoice payment tracking and unified queries across all 5 invoice types.
Does NOT create invoices — that belongs to the fiscalization flow.
Adds ERP payment tracking fields to existing fiscalized invoice documents.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, date
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit, serialize_doc
)
from .errors import ValidationError, NotFoundError, DuplicateError
from .request_context import ERPRequestContext
from .state_machines import compute_payment_status, is_overdue
from .repositories.base import InvoiceReference
from .repositories.firestore.invoice_repo import FirestoreInvoiceRepository
from .repositories.firestore.payment_repo import FirestorePaymentRepository

logger = logging.getLogger(__name__)


class InvoiceService(BaseERPService):
    """
    Service for outgoing invoice ERP operations.

    Responsibilities:
    - Unified invoice listing across all 5 type collections
    - Payment recording (atomic: payment + allocation + invoice update)
    - Open receivables and aging
    """

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._invoice_repo: Optional[FirestoreInvoiceRepository] = None
        self._payment_repo: Optional[FirestorePaymentRepository] = None

    def _get_invoice_repo(self) -> FirestoreInvoiceRepository:
        if self._invoice_repo is None:
            self._invoice_repo = FirestoreInvoiceRepository(db=self._get_db())
        return self._invoice_repo

    def _get_payment_repo(self) -> FirestorePaymentRepository:
        if self._payment_repo is None:
            self._payment_repo = FirestorePaymentRepository(db=self._get_db())
        return self._payment_repo

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_invoice(
        self, invoice_ref: InvoiceReference, ctx: ERPRequestContext
    ) -> dict:
        """
        Fetch a single invoice by InvoiceReference.
        Returns the full document enriched with computed ERP fields.
        """
        check_permission(ctx, "invoice:read")
        doc = await self._get_invoice_repo().get(invoice_ref, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Račun '{invoice_ref.display_id}' nije pronađen.",
            )
        return self._add_computed_fields(doc)

    async def list_invoices(
        self,
        ctx: ERPRequestContext,
        invoice_type: Optional[str] = None,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """Unified list across all or a single invoice type collection."""
        check_permission(ctx, "invoice:read")
        f = dict(filters or {})
        if invoice_type:
            f["invoice_type"] = invoice_type
        docs = await self._get_invoice_repo().list_all(ctx, f, limit, offset)
        return [self._add_computed_fields(d) for d in docs]

    async def get_open_receivables(
        self,
        ctx: ERPRequestContext,
        as_of_date: Optional[str] = None,
    ) -> dict:
        """
        Return all open (unpaid/partial) invoices with aging computed.
        Groups by customer and computes days overdue.
        """
        check_permission(ctx, "invoice:read")
        docs = await self._get_invoice_repo().list_open_receivables(ctx)
        today = date.fromisoformat(as_of_date) if as_of_date else date.today()

        # Buckets: current, 1-30, 31-60, 61-90, 90+
        buckets = {"current": [], "1_30": [], "31_60": [], "61_90": [], "over_90": []}
        total_open = Decimal("0")

        for doc in docs:
            doc = self._add_computed_fields(doc, as_of=today)
            due_date_str = doc.get("due_date") or doc.get("erp_due_date")
            amount_due = Decimal(str(doc.get("erp_amount_due") or 0))
            total_open += amount_due

            if not due_date_str:
                buckets["current"].append(doc)
                continue

            try:
                dd = date.fromisoformat(str(due_date_str)[:10])
                days = (today - dd).days
                if days <= 0:
                    buckets["current"].append(doc)
                elif days <= 30:
                    buckets["1_30"].append(doc)
                elif days <= 60:
                    buckets["31_60"].append(doc)
                elif days <= 90:
                    buckets["61_90"].append(doc)
                else:
                    buckets["over_90"].append(doc)
            except (ValueError, TypeError):
                buckets["current"].append(doc)

        return {
            "as_of_date": today.isoformat(),
            "total_open_eur": float(total_open),
            "total_count": len(docs),
            "buckets": {k: {"invoices": v, "total": float(sum(
                Decimal(str(d.get("erp_amount_due") or 0)) for d in v
            ))} for k, v in buckets.items()},
        }

    # ------------------------------------------------------------------
    # Payment recording
    # ------------------------------------------------------------------

    async def record_payment(
        self,
        invoice_ref: InvoiceReference,
        amount: Decimal,
        payment_date: str,
        payment_method: str,
        reference: str,
        ctx: ERPRequestContext,
        idempotency_key: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """
        Record a payment against an invoice.

        Atomic operation:
          1. Permission check
          2. Idempotency check
          3. Fetch invoice + validate amount
          4. Batch write: payment doc + allocation doc + invoice update
          5. Audit log

        Returns: {"payment_id", "display_id", "new_payment_status", "amount_due_after"}
        """
        check_permission(ctx, "payment:record")

        idem_key = idempotency_key or str(uuid4())

        # 1. Idempotency check
        payment_repo = self._get_payment_repo()
        if await payment_repo.key_exists(idem_key, ctx.company_id):
            raise DuplicateError(
                code="DUPLICATE",
                message="Uplata s ovim idempotency_key već postoji. Duplikat je odbijen.",
            )

        # 2. Fetch current invoice payment state
        tracking = await self._get_invoice_repo().get_payment_tracking(invoice_ref)
        if not tracking:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Račun '{invoice_ref.display_id}' nije pronađen.",
            )

        current_amount_paid = Decimal(str(tracking.get("erp_amount_paid") or "0"))
        total_gross = Decimal(str(
            tracking.get("grand_total") or tracking.get("total_gross") or "0"
        ))
        current_amount_due = total_gross - current_amount_paid

        # 3. Overpayment guard
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount <= Decimal("0"):
            raise ValidationError(
                code="INVALID_AMOUNT", message="Iznos uplate mora biti > 0.", field="amount"
            )
        if amount > current_amount_due:
            raise ValidationError(
                code="OVERPAYMENT",
                message=(
                    f"Iznos {amount} EUR premašuje dugovanje {current_amount_due:.2f} EUR. "
                    "Preplata nije dozvoljena."
                ),
                field="amount",
            )

        # 4. Compute new state
        new_amount_paid = (current_amount_paid + amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        new_amount_due = (total_gross - new_amount_paid).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        new_payment_status = compute_payment_status(new_amount_paid, total_gross)

        # 5. Generate display ID
        payment_id = str(uuid4())
        display_id = await generate_display_id(ctx.company_id, "PAY", self._get_db())

        # 6. Batch write
        db = self._get_db()
        batch = db.batch()

        payment_doc = {
            "payment_id": payment_id,
            "display_id": display_id,
            "company_id": ctx.company_id,
            "type": "incoming",
            "party_id": tracking.get("customer_id") or tracking.get("buyer_oib", ""),
            "party_name": tracking.get("customer_name") or tracking.get("buyer_name", ""),
            "invoice_ref_id": invoice_ref.invoice_id,
            "invoice_ref_type": invoice_ref.invoice_type,
            "invoice_ref_display": invoice_ref.display_id,
            "amount": float(amount),
            "currency": "EUR",
            "payment_date": payment_date,
            "payment_method": payment_method,
            "reference": reference,
            "status": "confirmed",
            "notes": notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": ctx.user_id,
            "reconciled": False,
            "reconciled_at": None,
            "idempotency_key": idem_key,
        }
        batch.set(db.collection("payments").document(payment_id), payment_doc)

        alloc_id = str(uuid4())
        alloc_doc = {
            "allocation_id": alloc_id,
            "company_id": ctx.company_id,
            "payment_id": payment_id,
            "invoice_id": invoice_ref.invoice_id,
            "invoice_type": invoice_ref.invoice_type,
            "display_id": invoice_ref.display_id,
            "amount": float(amount),
            "allocated_at": datetime.now(timezone.utc).isoformat(),
            "allocated_by": ctx.user_id,
        }
        batch.set(db.collection("payment_allocations").document(alloc_id), alloc_doc)

        from .repositories.firestore.invoice_repo import INVOICE_TYPE_TO_COLLECTION
        col_name = INVOICE_TYPE_TO_COLLECTION[invoice_ref.invoice_type]
        invoice_update = {
            "erp_amount_paid": float(new_amount_paid),
            "erp_amount_due": float(new_amount_due),
            "erp_payment_status": new_payment_status,
        }
        batch.update(
            db.collection(col_name).document(invoice_ref.invoice_id),
            invoice_update
        )

        await batch.commit()

        # 7. Audit
        await write_audit(
            action="payment_recorded",
            entity_type="invoice",
            entity_id=invoice_ref.invoice_id,
            display_id=invoice_ref.display_id,
            ctx=ctx,
            data={"payment_id": payment_id, "amount": float(amount),
                  "new_status": new_payment_status},
            db=db,
        )

        return {
            "payment_id": payment_id,
            "display_id": display_id,
            "amount": float(amount),
            "new_payment_status": new_payment_status,
            "amount_due_after": float(new_amount_due),
            "invoice_ref": invoice_ref.to_dict(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_computed_fields(self, doc: dict, as_of: Optional[date] = None) -> dict:
        """Add computed is_overdue field and normalize amounts."""
        due_date_str = doc.get("due_date") or doc.get("erp_due_date")
        due_date = None
        if due_date_str:
            try:
                due_date = date.fromisoformat(str(due_date_str)[:10])
            except (ValueError, TypeError):
                pass

        payment_status = doc.get("erp_payment_status", "unpaid")
        doc_status = doc.get("document_status", doc.get("fiscalization_status", ""))

        doc["is_overdue"] = is_overdue(due_date, payment_status, doc_status, as_of)
        doc["erp_payment_status"] = payment_status
        doc["erp_amount_paid"] = float(doc.get("erp_amount_paid") or 0)
        total = float(doc.get("grand_total") or doc.get("total_gross") or 0)
        doc["erp_amount_due"] = float(doc.get("erp_amount_due") or total)
        doc["_total_gross"] = total
        return doc


# Singleton factory
_invoice_service_instance: Optional[InvoiceService] = None


def get_invoice_service() -> InvoiceService:
    global _invoice_service_instance
    if _invoice_service_instance is None:
        _invoice_service_instance = InvoiceService()
    return _invoice_service_instance
