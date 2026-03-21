"""Firestore Customer Repository."""

import logging
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_COL = "customers"


class FirestoreCustomerRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def get(self, customer_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        snap = await self._db.collection(_COL).document(customer_id).get()
        if not snap.exists:
            return None
        doc = snap.to_dict() or {}
        if doc.get("company_id") and doc["company_id"] != ctx.company_id:
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
        if f.get("party_type"):
            query = query.where(filter=FieldFilter("party_type", "==", f["party_type"]))
        if f.get("category"):
            query = query.where(filter=FieldFilter("category", "==", f["category"]))
        if f.get("active") is not None:
            query = query.where(filter=FieldFilter("active", "==", f["active"]))
        query = query.order_by("name").limit(limit)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        # Text search post-filter (Firestore doesn't support ILIKE)
        if f.get("search"):
            term = f["search"].lower()
            docs = [d for d in docs if term in d.get("name", "").lower()
                    or term in d.get("oib", "")]
        return docs[offset: offset + limit]

    async def create(self, data: dict, ctx: ERPRequestContext) -> dict:
        customer_id = str(uuid4())
        data["_id"] = customer_id
        data["company_id"] = ctx.company_id
        data["deleted"] = False
        data.setdefault("active", True)
        data.setdefault("party_type", "customer")
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = data["created_at"]
        await self._db.collection(_COL).document(customer_id).set(data)
        return data

    async def update(self, customer_id: str, ctx: ERPRequestContext, data: dict) -> dict:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._db.collection(_COL).document(customer_id).update(data)
        return await self.get(customer_id, ctx) or {}

    async def soft_delete(self, customer_id: str, ctx: ERPRequestContext) -> None:
        await self._db.collection(_COL).document(customer_id).update({
            "deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": ctx.user_id,
        })

    async def search(self, query_text: str, ctx: ERPRequestContext, limit: int = 20) -> List[dict]:
        """Simple name/OIB search."""
        return await self.list(ctx, filters={"search": query_text}, limit=limit)

    async def find_by_oib(self, oib: str, company_id: str) -> Optional[dict]:
        """Exact OIB match for vendor/supplier lookup. Returns first match or None."""
        if not oib:
            return None
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("oib", "==", oib))
            .where(filter=FieldFilter("deleted", "==", False))
            .limit(1)
        )
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            return doc
        return None

    async def find_by_name_fuzzy(self, name: str, company_id: str, limit: int = 200) -> Optional[dict]:
        """Case-insensitive contains match on customer name. Returns best (first) match or None."""
        if not name:
            return None
        needle = name.lower().strip()
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", company_id))
            .where(filter=FieldFilter("deleted", "==", False))
            .limit(limit)
        )
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            if needle in (doc.get("name") or "").lower():
                doc["_id"] = snap.id
                return doc
        return None
