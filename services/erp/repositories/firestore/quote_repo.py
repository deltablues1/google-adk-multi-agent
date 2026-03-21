"""Firestore Quote (Ponuda) Repository."""

import logging
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient

from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_COL = "quotes"


class FirestoreQuoteRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def get(self, quote_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        snap = await self._db.collection(_COL).document(quote_id).get()
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
            .where("company_id", "==", ctx.company_id)
            .where("deleted", "==", False)
        )
        f = filters or {}
        if f.get("document_status"):
            query = query.where("document_status", "==", f["document_status"])
        if f.get("customer_id"):
            query = query.where("customer_id", "==", f["customer_id"])
        query = query.order_by("created_at", direction="DESCENDING").limit(limit)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs[offset:]

    async def create(self, data: dict, ctx: ERPRequestContext) -> dict:
        quote_id = str(uuid4())
        data["quote_id"] = quote_id
        data["company_id"] = ctx.company_id
        data["deleted"] = False
        data.setdefault("document_status", "draft")
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = data["created_at"]
        await self._db.collection(_COL).document(quote_id).set(data)
        data["_id"] = quote_id
        return data

    async def update(self, quote_id: str, ctx: ERPRequestContext, data: dict) -> dict:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._db.collection(_COL).document(quote_id).update(data)
        return await self.get(quote_id, ctx) or {}

    async def soft_delete(self, quote_id: str, ctx: ERPRequestContext) -> None:
        doc = await self.get(quote_id, ctx)
        if doc and doc.get("document_status") not in ("draft",):
            from ...errors import ValidationError
            raise ValidationError(
                code="CANNOT_DELETE",
                message="Možete brisati samo ponude u statusu 'draft'.",
            )
        await self._db.collection(_COL).document(quote_id).update({
            "deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": ctx.user_id,
        })
