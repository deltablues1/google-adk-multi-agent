"""ERP Product Service — product catalog and stock adjustments."""

import logging
from decimal import Decimal
from typing import Optional, List
from datetime import datetime, timezone
from uuid import uuid4

from .base_erp_service import BaseERPService, check_permission, write_audit
from .errors import NotFoundError, ValidationError
from .request_context import ERPRequestContext
from .repositories.firestore.product_repo import FirestoreProductRepository
from .repositories.firestore.inventory_repo import FirestoreInventoryRepository

logger = logging.getLogger(__name__)


class ProductService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreProductRepository] = None
        self._inventory_repo: Optional[FirestoreInventoryRepository] = None

    def _get_repo(self) -> FirestoreProductRepository:
        if self._repo is None:
            self._repo = FirestoreProductRepository(db=self._get_db())
        return self._repo

    def _get_inventory_repo(self) -> FirestoreInventoryRepository:
        if self._inventory_repo is None:
            self._inventory_repo = FirestoreInventoryRepository(db=self._get_db())
        return self._inventory_repo

    async def get_product(self, product_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "product:read")
        doc = await self._get_repo().get(product_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Proizvod '{product_id}' nije pronađen.")
        return doc

    async def list_products(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 100, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "product:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def get_stock_levels(self, ctx: ERPRequestContext) -> List[dict]:
        """Return all products with stock status."""
        check_permission(ctx, "product:read")
        return await self._get_repo().list(ctx, limit=500)

    async def create_product(self, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "product:write")
        if not data.get("name"):
            raise ValidationError(code="REQUIRED_FIELD", message="Naziv proizvoda je obavezan.", field="name")
        doc = await self._get_repo().create(data, ctx)
        await write_audit("product_created", "product", doc["_id"],
                          data.get("name"), ctx, db=self._get_db())
        return doc

    async def update_product(self, product_id: str, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "product:write")
        existing = await self._get_repo().get(product_id, ctx)
        if existing is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Proizvod '{product_id}' nije pronađen.")
        return await self._get_repo().update(product_id, ctx, data)

    async def adjust_stock(
        self,
        product_id: str,
        new_quantity: Decimal,
        reason: str,
        ctx: ERPRequestContext,
    ) -> dict:
        """Adjust stock quantity with audit trail. Records an inventory movement."""
        check_permission(ctx, "stock:adjust")
        if len(reason.strip()) < 5:
            raise ValidationError(
                code="REASON_TOO_SHORT",
                message="Razlog usklađivanja mora imati minimalno 5 znakova.",
                field="reason",
            )
        product = await self._get_repo().get(product_id, ctx)
        if product is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Proizvod '{product_id}' nije pronađen.")

        old_quantity = float(product.get("stock_quantity") or 0)
        qty_after = float(new_quantity)
        delta = qty_after - old_quantity

        await self._get_repo().update_stock(product_id, qty_after)

        await self._get_inventory_repo().create_movement(
            company_id=ctx.company_id,
            product_id=product_id,
            product_sku=product.get("sku", ""),
            movement_type="manual_adjust",
            quantity_delta=delta,
            quantity_after=qty_after,
            reason=reason,
            created_by=ctx.user_id,
        )

        await write_audit(
            "stock_adjusted", "product", product_id, product.get("name"), ctx,
            {"old_quantity": old_quantity, "new_quantity": qty_after, "reason": reason},
            self._get_db(),
        )
        return {
            "product_id": product_id,
            "product_name": product.get("name"),
            "old_quantity": old_quantity,
            "new_quantity": qty_after,
            "delta": delta,
        }


    async def get_stock_movements(
        self, product_id: str, ctx: ERPRequestContext, limit: int = 100
    ) -> List[dict]:
        check_permission(ctx, "product:read")
        product = await self._get_repo().get(product_id, ctx)
        if product is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Proizvod '{product_id}' nije pronađen.")
        return await self._get_inventory_repo().list_for_product(product_id, ctx.company_id, limit)


_product_service_instance: Optional[ProductService] = None


def get_product_service() -> ProductService:
    global _product_service_instance
    if _product_service_instance is None:
        _product_service_instance = ProductService()
    return _product_service_instance
