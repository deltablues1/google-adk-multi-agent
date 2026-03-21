"""
ERP Quote Service (Ponude)
==========================
Manages quotes with state machine enforcement and invoice conversion.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit
)
from .errors import ValidationError, NotFoundError, DuplicateError
from .request_context import ERPRequestContext
from .state_machines import QUOTE_DOC_TRANSITIONS, validate_transition
from .repositories.firestore.quote_repo import FirestoreQuoteRepository

logger = logging.getLogger(__name__)


class QuoteService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreQuoteRepository] = None

    def _get_repo(self) -> FirestoreQuoteRepository:
        if self._repo is None:
            self._repo = FirestoreQuoteRepository(db=self._get_db())
        return self._repo

    async def get_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:read")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ponuda '{quote_id}' nije pronađena."
            )
        return doc

    async def list_quotes(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 50, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "quote:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def create_quote(self, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:create")

        if not data.get("customer_id"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="customer_id je obavezan.",
                field="customer_id",
            )
        items = data.get("items", [])
        if not items:
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Ponuda mora imati barem jednu stavku.",
                field="items",
            )
        if not data.get("valid_until"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Rok valjanosti (valid_until) je obavezan.",
                field="valid_until",
            )

        # Compute totals from items
        subtotal_net = 0.0
        vat_total = 0.0
        for item in items:
            qty = float(item.get("quantity", 1))
            price = float(item.get("unit_price", 0))
            vat_rate = float(item.get("vat_rate", 25))
            line_net = round(qty * price, 2)
            line_vat = round(line_net * vat_rate / 100, 2)
            item["line_net"] = line_net
            item["line_vat"] = line_vat
            item["line_gross"] = round(line_net + line_vat, 2)
            subtotal_net += line_net
            vat_total += line_vat

        total_gross = round(subtotal_net + vat_total, 2)

        display_id = await generate_display_id(ctx.company_id, "PON", self._get_db())

        doc_data = {
            "display_id": display_id,
            "customer_id": data["customer_id"],
            "customer_name": data.get("customer_name", ""),
            "customer_oib": data.get("customer_oib", ""),
            "issue_date": data.get("issue_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "valid_until": data["valid_until"],
            "currency": data.get("currency", "EUR"),
            "document_status": "draft",
            "items": items,
            "subtotal_net": subtotal_net,
            "vat_total": vat_total,
            "total_gross": total_gross,
            "notes": data.get("notes", ""),
            "source": data.get("source", "manual"),
            "converted_invoice_id": "",
            "converted_invoice_type": "",
            "converted_at": "",
            "accepted_at": "",
            "rejected_at": "",
            "sent_at": "",
            "created_by": ctx.user_id,
        }

        doc = await self._get_repo().create(doc_data, ctx)
        await write_audit(
            "quote_created", "quote", doc["quote_id"],
            display_id, ctx, db=self._get_db()
        )
        return doc

    async def update_quote(self, quote_id: str, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        if doc["document_status"] != "draft":
            raise ValidationError(
                code="WRONG_STATUS",
                message="Uređivanje je moguće samo za ponude u statusu 'draft'.",
            )

        # Allowed editable fields
        editable = {
            "customer_id", "customer_name", "customer_oib",
            "valid_until", "currency", "items", "notes",
        }
        update_data = {k: v for k, v in data.items() if k in editable}

        # Recompute totals if items changed
        if "items" in update_data:
            items = update_data["items"]
            subtotal_net = 0.0
            vat_total = 0.0
            for item in items:
                qty = float(item.get("quantity", 1))
                price = float(item.get("unit_price", 0))
                vat_rate = float(item.get("vat_rate", 25))
                line_net = round(qty * price, 2)
                line_vat = round(line_net * vat_rate / 100, 2)
                item["line_net"] = line_net
                item["line_vat"] = line_vat
                item["line_gross"] = round(line_net + line_vat, 2)
                subtotal_net += line_net
                vat_total += line_vat
            update_data["subtotal_net"] = subtotal_net
            update_data["vat_total"] = vat_total
            update_data["total_gross"] = round(subtotal_net + vat_total, 2)

        updated = await self._get_repo().update(quote_id, ctx, update_data)
        await write_audit(
            "quote_updated", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def mark_sent(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:send")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "sent", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "sent",
            "sent_at": now,
        })
        await write_audit(
            "quote_sent", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def accept_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "accepted", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "accepted",
            "accepted_at": now,
        })
        await write_audit(
            "quote_accepted", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def reject_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "rejected", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "rejected",
            "rejected_at": now,
        })
        await write_audit(
            "quote_rejected", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def expire_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "expired", QUOTE_DOC_TRANSITIONS)
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "expired",
        })
        await write_audit(
            "quote_expired", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def convert_to_invoice(self, quote_id: str, invoice_type: str, ctx: ERPRequestContext) -> dict:
        """
        Convert an accepted quote to an outgoing invoice.
        Idempotent: if already converted, returns existing invoice reference.
        """
        check_permission(ctx, "quote:convert")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")

        # Idempotency: already converted
        if doc["document_status"] == "converted" and doc.get("converted_invoice_id"):
            return {
                "quote_id": quote_id,
                "invoice_id": doc["converted_invoice_id"],
                "invoice_type": doc["converted_invoice_type"],
                "already_converted": True,
            }

        validate_transition(doc["document_status"], "converted", QUOTE_DOC_TRANSITIONS)

        if invoice_type not in ("b2c", "b2b", "b2g", "eu", "int"):
            raise ValidationError(
                code="INVALID_INVOICE_TYPE",
                message=f"Nepoznat tip računa: {invoice_type}. Dozvoljeni: b2c, b2b, b2g, eu, int.",
            )

        # Build invoice document from quote data
        from .base_erp_service import get_firestore_db
        db = self._get_db()

        invoice_id = str(uuid4())
        invoice_display_id = await generate_display_id(ctx.company_id, "RA", db)

        INVOICE_TYPE_TO_COLLECTION = {
            "b2c": "invoices_b2c", "b2b": "invoices_b2b",
            "b2g": "invoices_b2g", "eu": "invoices_eu", "int": "invoices_int",
        }
        collection = INVOICE_TYPE_TO_COLLECTION[invoice_type]

        now = datetime.now(timezone.utc).isoformat()
        invoice_doc = {
            "invoice_id": invoice_id,
            "display_id": invoice_display_id,
            "invoice_number": invoice_display_id,
            "company_id": ctx.company_id,
            "customer_id": doc.get("customer_id", ""),
            "customer_name": doc.get("customer_name", ""),
            "customer_oib": doc.get("customer_oib", ""),
            "buyer_name": doc.get("customer_name", ""),
            "buyer_oib": doc.get("customer_oib", ""),
            "issue_date": now[:10],
            "currency": doc.get("currency", "EUR"),
            "document_status": "draft",
            "erp_payment_status": "unpaid",
            "erp_amount_paid": 0.0,
            "erp_amount_due": doc.get("total_gross", 0),
            "items": doc.get("items", []),
            "subtotal_net": doc.get("subtotal_net", 0),
            "vat_total": doc.get("vat_total", 0),
            "grand_total": doc.get("total_gross", 0),
            "total_gross": doc.get("total_gross", 0),
            "notes": f"Kreirano iz ponude {doc.get('display_id', quote_id)}.",
            "source_quote_id": quote_id,
            "source_quote_display_id": doc.get("display_id", ""),
            "created_at": now,
            "created_by": ctx.user_id,
            "deleted": False,
        }

        batch = db.batch()
        batch.set(db.collection(collection).document(invoice_id), invoice_doc)
        batch.update(db.collection("quotes").document(quote_id), {
            "document_status": "converted",
            "converted_invoice_id": invoice_id,
            "converted_invoice_type": invoice_type,
            "converted_at": now,
            "updated_at": now,
        })
        await batch.commit()

        await write_audit(
            "quote_converted", "quote", quote_id,
            doc.get("display_id"), ctx,
            {"invoice_id": invoice_id, "invoice_display_id": invoice_display_id, "invoice_type": invoice_type},
            db,
        )
        return {
            "quote_id": quote_id,
            "invoice_id": invoice_id,
            "invoice_type": invoice_type,
            "invoice_display_id": invoice_display_id,
            "already_converted": False,
        }


_quote_service_instance: Optional[QuoteService] = None


def get_quote_service() -> QuoteService:
    global _quote_service_instance
    if _quote_service_instance is None:
        _quote_service_instance = QuoteService()
    return _quote_service_instance
