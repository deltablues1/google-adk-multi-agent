"""Firestore Inventory Movements Repository."""

import logging
from typing import Optional, List
from uuid import uuid4
from datetime import datetime, timezone

from google.cloud.firestore_v1.async_client import AsyncClient

from ...base_erp_service import get_firestore_db

logger = logging.getLogger(__name__)

_COL = "inventory_movements"

MOVEMENT_TYPES = frozenset({"manual_adjust", "purchase", "sale", "write_off"})


class FirestoreInventoryRepository:

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    async def create_movement(
        self,
        company_id: str,
        product_id: str,
        product_sku: str,
        movement_type: str,
        quantity_delta: float,
        quantity_after: float,
        reason: str,
        created_by: str,
        reference_id: str = "",
    ) -> dict:
        movement_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "movement_id": movement_id,
            "company_id": company_id,
            "product_id": product_id,
            "product_sku": product_sku,
            "movement_type": movement_type,
            "quantity_delta": quantity_delta,
            "quantity_after": quantity_after,
            "reference_id": reference_id,
            "reason": reason,
            "created_at": now,
            "created_by": created_by,
        }
        await self._db.collection(_COL).document(movement_id).set(doc)
        doc["_id"] = movement_id
        return doc

    async def list_for_product(
        self, product_id: str, company_id: str, limit: int = 100
    ) -> List[dict]:
        query = (
            self._db.collection(_COL)
            .where("company_id", "==", company_id)
            .where("product_id", "==", product_id)
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
        )
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            docs.append(doc)
        return docs
