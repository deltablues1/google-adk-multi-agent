"""Firestore Vendor Invoice (URA — ulazni računi) Repository."""

import hashlib
import logging
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_COL = "vendor_invoices"


class FirestoreVendorInvoiceRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def get(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        snap = await self._db.collection(_COL).document(vendor_invoice_id).get()
        if not snap.exists:
            return None
        doc = snap.to_dict() or {}
        if doc.get("company_id") != ctx.company_id:
            return None
        if doc.get("deleted"):
            return None
        doc["_id"] = snap.id
        return doc

    async def list(
        self,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", ctx.company_id))
            .where(filter=FieldFilter("deleted", "==", False))
        )
        f = filters or {}
        if f.get("document_status"):
            query = query.where(filter=FieldFilter("document_status", "==", f["document_status"]))
        if f.get("payment_status"):
            query = query.where(filter=FieldFilter("payment_status", "==", f["payment_status"]))
        if f.get("vendor_id"):
            query = query.where(filter=FieldFilter("vendor_id", "==", f["vendor_id"]))
        if f.get("date_from"):
            query = query.where(filter=FieldFilter("issue_date", ">=", f["date_from"]))
        if f.get("date_to"):
            query = query.where(filter=FieldFilter("issue_date", "<=", f["date_to"]))
        query = query.order_by("issue_date", direction="DESCENDING").limit(limit)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs[offset:]

    async def list_open_payables(self, ctx: ERPRequestContext) -> List[dict]:
        """All vendor invoices with payment_status != paid."""
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", ctx.company_id))
            .where(filter=FieldFilter("deleted", "==", False))
            .where(filter=FieldFilter("payment_status", "in", ["unpaid", "partial"]))
            .limit(500)
        )
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs

    async def create(self, data: dict, ctx: ERPRequestContext) -> dict:
        vendor_invoice_id = str(uuid4())
        data["vendor_invoice_id"] = vendor_invoice_id
        data["company_id"] = ctx.company_id
        data["deleted"] = False
        data.setdefault("document_status", "draft")
        data.setdefault("payment_status", "unpaid")
        data.setdefault("amount_paid", 0.0)
        data.setdefault("amount_due", float(data.get("total_gross", 0)))
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = data["created_at"]
        await self._db.collection(_COL).document(vendor_invoice_id).set(data)
        data["_id"] = vendor_invoice_id
        return data

    async def update(self, vendor_invoice_id: str, ctx: ERPRequestContext, data: dict) -> dict:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._db.collection(_COL).document(vendor_invoice_id).update(data)
        return await self.get(vendor_invoice_id, ctx) or {}

    @staticmethod
    def compute_dedup_hash(company_id: str, vendor_oib: str, vendor_invoice_no: str,
                           issue_date: str, total_gross: float) -> str:
        key = f"{company_id}:{vendor_oib}:{vendor_invoice_no}:{issue_date}:{round(total_gross, 2)}"
        return hashlib.sha256(key.encode()).hexdigest()

    async def find_by_dedup_hash(self, dedup_hash: str, company_id: str) -> Optional[dict]:
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("_dedup_hash", "==", dedup_hash))
            .where(filter=FieldFilter("deleted", "==", False))
            .limit(1)
        )
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            return doc
        return None

    async def soft_delete(self, vendor_invoice_id: str, ctx: ERPRequestContext) -> None:
        doc = await self.get(vendor_invoice_id, ctx)
        if doc and doc.get("document_status") not in ("draft", "received"):
            from ...errors import ValidationError
            raise ValidationError(
                code="CANNOT_DELETE",
                message="Možete brisati samo ulazne račune u statusu 'draft' ili 'received'.",
            )
        await self._db.collection(_COL).document(vendor_invoice_id).update({
            "deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": ctx.user_id,
        })
