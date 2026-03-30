"""
ERP Vendor Invoice Service (Ulazni računi — URA)
=================================================
Manages incoming invoices from vendors with state machine enforcement.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit
)
from .errors import ValidationError, NotFoundError, DuplicateError
from .request_context import ERPRequestContext
from .state_machines import VENDOR_INVOICE_DOC_TRANSITIONS, validate_transition, compute_payment_status
from .repositories.firestore.vendor_invoice_repo import FirestoreVendorInvoiceRepository
from .repositories.firestore.payment_repo import FirestorePaymentRepository
from .repositories.firestore.customer_repo import FirestoreCustomerRepository

logger = logging.getLogger(__name__)


class VendorInvoiceService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreVendorInvoiceRepository] = None
        self._payment_repo: Optional[FirestorePaymentRepository] = None

    def _get_repo(self) -> FirestoreVendorInvoiceRepository:
        if self._repo is None:
            self._repo = FirestoreVendorInvoiceRepository(db=self._get_db())
        return self._repo

    def _get_payment_repo(self) -> FirestorePaymentRepository:
        if self._payment_repo is None:
            self._payment_repo = FirestorePaymentRepository(db=self._get_db())
        return self._payment_repo

    async def _try_match_vendor(self, vendor_oib: str, vendor_name: str, company_id: str) -> Optional[dict]:
        """Return customer doc if vendor can be matched by OIB (exact) or name (fuzzy)."""
        repo = FirestoreCustomerRepository(db=self._get_db())
        match = await repo.find_by_oib(vendor_oib, company_id)
        if match:
            return match
        return await repo.find_by_name_fuzzy(vendor_name, company_id)

    async def get_vendor_invoice(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "vendor_invoice:read")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ulazni račun '{vendor_invoice_id}' nije pronađen."
            )
        return doc

    async def list_vendor_invoices(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 50, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "vendor_invoice:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def get_open_payables(self, ctx: ERPRequestContext) -> dict:
        """Open payables with aging."""
        from datetime import date
        check_permission(ctx, "vendor_invoice:read")
        docs = await self._get_repo().list_open_payables(ctx)
        today = date.today()
        buckets = {"current": [], "1_30": [], "31_60": [], "61_90": [], "over_90": []}
        total_due = Decimal("0")

        for doc in docs:
            amount_due = Decimal(str(doc.get("amount_due") or 0))
            total_due += amount_due
            due_str = doc.get("due_date")
            if not due_str:
                buckets["current"].append(doc)
                continue
            try:
                dd = date.fromisoformat(str(due_str)[:10])
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
            "total_due_eur": float(total_due),
            "total_count": len(docs),
            "buckets": {k: {"invoices": v, "total": float(sum(
                Decimal(str(d.get("amount_due") or 0)) for d in v
            ))} for k, v in buckets.items()},
        }

    async def update_vendor_invoice(
        self, vendor_invoice_id: str, ctx: ERPRequestContext, update_data: dict
    ) -> dict:
        """Update safe fields on a vendor invoice."""
        check_permission(ctx, "vendor_invoice:create")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ulazni racun '{vendor_invoice_id}' nije pronaden."
            )
        return await self._get_repo().update(vendor_invoice_id, ctx, update_data)

    async def create_vendor_invoice(self, data: dict, ctx: ERPRequestContext) -> dict:
        """Create a new vendor invoice (manual entry or from OCR)."""
        check_permission(ctx, "vendor_invoice:create")
        # vendor_id is optional for OCR drafts — accountant assigns it via UI
        if not data.get("from_ocr") and not data.get("vendor_id"):
            raise ValidationError(code="REQUIRED_FIELD", message="vendor_id je obavezan.", field="vendor_id")
        if not data.get("total_gross") or float(data["total_gross"]) <= 0:
            raise ValidationError(code="REQUIRED_FIELD", message="total_gross mora biti > 0.", field="total_gross")

        # Dedup check: block exact duplicate invoices (same vendor + invoice_no + date + amount)
        vendor_oib = data.get("vendor_oib", "")
        vendor_invoice_no = data.get("vendor_invoice_no", "")
        if vendor_oib and vendor_invoice_no:
            dedup_hash = self._get_repo().compute_dedup_hash(
                ctx.company_id, vendor_oib, vendor_invoice_no,
                data.get("issue_date", ""), float(data.get("total_gross", 0))
            )
            existing = await self._get_repo().find_by_dedup_hash(dedup_hash, ctx.company_id)
            if existing:
                raise DuplicateError(
                    code="DUPLICATE_VENDOR_INVOICE",
                    message=(
                        f"Ulazni račun '{vendor_invoice_no}' od dobavljača OIB {vendor_oib} "
                        f"već postoji (ID: {existing['_id']})."
                    ),
                )
            data["_dedup_hash"] = dedup_hash

        display_id = await generate_display_id(ctx.company_id, "URA", self._get_db())
        data["display_id"] = display_id
        data["created_by"] = ctx.user_id

        doc = await self._get_repo().create(data, ctx)
        await write_audit("vendor_invoice_created", "vendor_invoice", doc["vendor_invoice_id"],
                          display_id, ctx, db=self._get_db())
        return doc

    async def create_from_ocr(
        self, ocr_data: dict, scan_file_id: str, ctx: ERPRequestContext
    ) -> dict:
        """
        Create a DRAFT vendor invoice from OCR output.
        AI populates fields, human confirms via UI.
        """
        check_permission(ctx, "vendor_invoice:create")
        # Map OCR category to ERP category
        cat_map = {
            "Hrana": "materials", "Prijevoz": "services",
            "Ured": "services", "Režije": "utilities", "Ostalo": "other",
        }
        erp_category = cat_map.get(ocr_data.get("expense_category", ""), "other")
        vat_raw = ocr_data.get("vat_amount") or ocr_data.get("tax_amount") or 0
        gross = float(ocr_data.get("total_amount", 0))
        vat = float(vat_raw)
        net = round(gross - vat, 2)

        vendor_oib = ocr_data.get("tax_id") or ocr_data.get("vendor_oib", "")
        vendor_name_ocr = ocr_data.get("merchant_name", "")

        # Auto-match vendor from customers collection (OIB exact → name fuzzy)
        matched = await self._try_match_vendor(vendor_oib, vendor_name_ocr, ctx.company_id)
        vendor_id = matched["_id"] if matched else ""
        vendor_name = (matched.get("name") if matched else None) or vendor_name_ocr
        vendor_match_status = "matched" if matched else "no_match"

        notes_base = (
            f"Kreirano automatski iz OCR skeniranja "
            f"(pouzdanost: {ocr_data.get('confidence_score', 0):.0%}). "
        )
        if matched:
            notes_base += f"Dobavljač automatski prepoznat: {vendor_name}."
        else:
            notes_base += "Molimo provjerite i dodijelite dobavljača."

        data = {
            "from_ocr": True,
            "document_status": "draft",
            "scan_file_id": scan_file_id,
            "ocr_data": {**ocr_data, "vendor_match": vendor_match_status},
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "vendor_oib": vendor_oib,
            "vendor_invoice_no": ocr_data.get("invoice_number") or ocr_data.get("receipt_number", ""),
            "issue_date": ocr_data.get("transaction_date", ""),
            "total_gross": gross,
            "vat_amount": vat,
            "subtotal_net": net,
            "category": erp_category,
            "due_date": ocr_data.get("due_date", ""),
            "items": ocr_data.get("items", []),
            "notes": notes_base,
        }
        return await self.create_vendor_invoice(data, ctx)

    async def mark_received(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Transition vendor invoice from 'draft' to 'received'."""
        check_permission(ctx, "vendor_invoice:create")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")
        validate_transition(doc["document_status"], "received", VENDOR_INVOICE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        await self._get_repo()._db.collection("vendor_invoices").document(vendor_invoice_id).update({
            "document_status": "received",
            "received_date": now,
            "updated_at": now,
        })
        await write_audit("vendor_invoice_received", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id", ""), ctx, db=self._get_db())
        doc["document_status"] = "received"
        return doc

    async def approve_vendor_invoice(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Transition vendor invoice from 'received' to 'approved'."""
        check_permission(ctx, "vendor_invoice:approve")
        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"URA '{vendor_invoice_id}' nije pronađen.")

        validate_transition(
            doc["document_status"], "approved", VENDOR_INVOICE_DOC_TRANSITIONS
        )
        # Required fields for approval
        if not doc.get("due_date"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Datum dospijeća (due_date) mora biti postavljen prije odobravanja.",
                field="due_date"
            )

        updated = await self._get_repo().update(vendor_invoice_id, ctx, {
            "document_status": "approved",
            "approved_by": ctx.user_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        })
        await write_audit("vendor_invoice_approved", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, db=self._get_db())
        return updated

    async def record_payment(
        self,
        vendor_invoice_id: str,
        amount: Decimal,
        payment_date: str,
        payment_method: str,
        reference: str,
        ctx: ERPRequestContext,
        idempotency_key: Optional[str] = None,
        notes: str = "",
    ) -> dict:
        """Record outgoing payment for a vendor invoice."""
        check_permission(ctx, "payment:record")

        idem_key = idempotency_key or str(uuid4())
        payment_repo = self._get_payment_repo()

        if await payment_repo.key_exists(idem_key, ctx.company_id):
            raise DuplicateError(code="DUPLICATE", message="Duplikat uplate odbijen.")

        doc = await self._get_repo().get(vendor_invoice_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message="URA nije pronađen.")
        if doc["document_status"] not in ("approved", "partial_paid"):
            raise ValidationError(
                code="WRONG_STATUS",
                message=f"Plaćanje moguće samo za odobren račun. Trenutni status: {doc['document_status']}.",
            )

        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        amount_due = Decimal(str(doc.get("amount_due") or 0))
        if amount > amount_due:
            raise ValidationError(
                code="OVERPAYMENT",
                message=f"Iznos {amount} EUR premašuje dugovanje {amount_due:.2f} EUR.",
                field="amount",
            )

        total_gross = Decimal(str(doc.get("total_gross") or 0))
        new_amount_paid = Decimal(str(doc.get("amount_paid") or 0)) + amount
        new_amount_due = total_gross - new_amount_paid
        new_payment_status = compute_payment_status(new_amount_paid, total_gross)

        payment_id = str(uuid4())
        from .base_erp_service import generate_display_id
        display_id = await generate_display_id(ctx.company_id, "PAY", self._get_db())

        db = self._get_db()
        batch = db.batch()

        payment_doc = {
            "payment_id": payment_id, "display_id": display_id,
            "company_id": ctx.company_id, "type": "outgoing",
            "party_id": doc.get("vendor_id", ""),
            "party_name": doc.get("vendor_name", ""),
            "invoice_ref_id": vendor_invoice_id,
            "invoice_ref_type": "vendor",
            "invoice_ref_display": doc.get("display_id", ""),
            "amount": float(amount), "currency": "EUR",
            "payment_date": payment_date, "payment_method": payment_method,
            "reference": reference, "status": "confirmed", "notes": notes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": ctx.user_id, "reconciled": False, "reconciled_at": None,
            "idempotency_key": idem_key,
        }
        batch.set(db.collection("payments").document(payment_id), payment_doc)

        alloc_id = str(uuid4())
        batch.set(db.collection("payment_allocations").document(alloc_id), {
            "allocation_id": alloc_id, "company_id": ctx.company_id,
            "payment_id": payment_id, "invoice_id": vendor_invoice_id,
            "invoice_type": "vendor", "display_id": doc.get("display_id", ""),
            "amount": float(amount),
            "allocated_at": datetime.now(timezone.utc).isoformat(),
            "allocated_by": ctx.user_id,
        })

        batch.update(db.collection("vendor_invoices").document(vendor_invoice_id), {
            "amount_paid": float(new_amount_paid),
            "amount_due": float(new_amount_due),
            "payment_status": new_payment_status,
        })
        await batch.commit()

        await write_audit("vendor_payment_recorded", "vendor_invoice", vendor_invoice_id,
                          doc.get("display_id"), ctx, {"amount": float(amount)}, db)
        return {
            "payment_id": payment_id, "display_id": display_id,
            "amount": float(amount), "new_payment_status": new_payment_status,
            "amount_due_after": float(new_amount_due),
        }


_vendor_invoice_service_instance: Optional[VendorInvoiceService] = None


def get_vendor_invoice_service() -> VendorInvoiceService:
    global _vendor_invoice_service_instance
    if _vendor_invoice_service_instance is None:
        _vendor_invoice_service_instance = VendorInvoiceService()
    return _vendor_invoice_service_instance
