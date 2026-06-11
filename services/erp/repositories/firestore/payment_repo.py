"""Firestore Payment Repository."""

import logging
from typing import Optional, List
from uuid import uuid4

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_PAYMENTS_COL = "payments"
_ALLOCATIONS_COL = "payment_allocations"


class FirestorePaymentRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def key_exists(self, idempotency_key: str, company_id: str) -> bool:
        """Check if an idempotency key already exists in this company's payments."""
        query = (
            self._db.collection(_PAYMENTS_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("idempotency_key", "==", idempotency_key))
            .limit(1)
        )
        docs = [s async for s in query.stream()]
        return len(docs) > 0

    async def create(self, payment_data: dict, ctx: ERPRequestContext) -> dict:
        """Write a new payment document. Returns the full document."""
        payment_id = payment_data.get("payment_id") or str(uuid4())
        payment_data["payment_id"] = payment_id
        payment_data["company_id"] = ctx.company_id
        await self._db.collection(_PAYMENTS_COL).document(payment_id).set(payment_data)
        return payment_data

    async def create_allocation(self, allocation_data: dict, ctx: ERPRequestContext) -> dict:
        """Write a payment_allocations document."""
        alloc_id = str(uuid4())
        allocation_data["allocation_id"] = alloc_id
        allocation_data["company_id"] = ctx.company_id
        await self._db.collection(_ALLOCATIONS_COL).document(alloc_id).set(allocation_data)
        return allocation_data

    async def get(self, payment_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        snap = await self._db.collection(_PAYMENTS_COL).document(payment_id).get()
        if not snap.exists:
            return None
        doc = snap.to_dict()
        if doc.get("company_id") != ctx.company_id:
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
        query = self._db.collection(_PAYMENTS_COL).where(filter=FieldFilter("company_id", "==", ctx.company_id))
        f = filters or {}
        if f.get("type"):
            query = query.where(filter=FieldFilter("type", "==", f["type"]))
        if f.get("party_id"):
            query = query.where(filter=FieldFilter("party_id", "==", f["party_id"]))
        if f.get("status"):
            query = query.where(filter=FieldFilter("status", "==", f["status"]))
        if f.get("date_from"):
            query = query.where(filter=FieldFilter("payment_date", ">=", f["date_from"]))
        if f.get("date_to"):
            query = query.where(filter=FieldFilter("payment_date", "<=", f["date_to"]))
        query = query.order_by("payment_date", direction="DESCENDING").limit(limit)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs[offset:]

    async def get_allocations_for_invoice(
        self, invoice_id: str, company_id: str
    ) -> List[dict]:
        """All payment allocations for a given invoice_id."""
        query = (
            self._db.collection(_ALLOCATIONS_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("invoice_id", "==", invoice_id))
        )
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs

    async def get_allocations_for_payment(
        self, payment_id: str, company_id: str
    ) -> List[dict]:
        """All payment allocations for a given payment_id."""
        query = (
            self._db.collection(_ALLOCATIONS_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("payment_id", "==", payment_id))
        )
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs

    async def get_cashflow(
        self, company_id: str, date_from: str, date_to: str
    ) -> dict:
        """Aggregate incoming vs outgoing payments for a date range."""
        query = (
            self._db.collection(_PAYMENTS_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("payment_date", ">=", date_from))
            .where(filter=FieldFilter("payment_date", "<=", date_to))
            .where(filter=FieldFilter("status", "==", "confirmed"))
        )
        # Use Decimal to avoid float accumulation errors on monetary sums.
        from decimal import Decimal, ROUND_HALF_UP

        def _q(d: Decimal) -> float:
            return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        incoming = Decimal("0")
        outgoing = Decimal("0")
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            amount = Decimal(str(doc.get("amount", 0) or 0))
            if doc.get("type") == "incoming":
                incoming += amount
            else:
                outgoing += amount
        return {
            "incoming": _q(incoming),
            "outgoing": _q(outgoing),
            "net": _q(incoming - outgoing),
            "date_from": date_from,
            "date_to": date_to,
        }
