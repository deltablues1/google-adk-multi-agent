"""Firestore Product Repository."""

import logging
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_COL = "products"


class FirestoreProductRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def get(self, product_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        snap = await self._db.collection(_COL).document(product_id).get()
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
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        query = (
            self._db.collection(_COL)
            .where(filter=FieldFilter("company_id", "==", ctx.company_id))
            .where(filter=FieldFilter("deleted", "==", False))
        )
        f = filters or {}
        if f.get("active") is not None:
            query = query.where(filter=FieldFilter("active", "==", f["active"]))
        query = query.order_by("name").limit(limit)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            # Compute low_stock flag
            stock = float(doc.get("stock_quantity", 0) or 0)
            min_s = float(doc.get("min_stock") or 0)
            doc["low_stock"] = (min_s > 0 and stock < min_s)
            docs.append(doc)
        if f.get("low_stock_only"):
            docs = [d for d in docs if d.get("low_stock")]
        if f.get("search"):
            term = f["search"].lower()
            docs = [d for d in docs if term in d.get("name", "").lower()
                    or term in d.get("sku", "").lower()]
        return docs[offset: offset + limit]

    async def create(self, data: dict, ctx: ERPRequestContext) -> dict:
        product_id = str(uuid4())
        data["_id"] = product_id
        data["company_id"] = ctx.company_id
        data["deleted"] = False
        data.setdefault("active", True)
        data.setdefault("stock_quantity", 0)
        data["created_at"] = datetime.now(timezone.utc).isoformat()
        data["updated_at"] = data["created_at"]
        await self._db.collection(_COL).document(product_id).set(data)
        return data

    async def update(self, product_id: str, ctx: ERPRequestContext, data: dict) -> dict:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._db.collection(_COL).document(product_id).update(data)
        return await self.get(product_id, ctx) or {}

    async def update_stock(self, product_id: str, new_quantity: float) -> None:
        """Direct stock quantity update — called from InventoryService inside a transaction."""
        await self._db.collection(_COL).document(product_id).update({
            "stock_quantity": new_quantity,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    async def soft_delete(self, product_id: str, ctx: ERPRequestContext) -> None:
        await self._db.collection(_COL).document(product_id).update({
            "deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": ctx.user_id,
        })
