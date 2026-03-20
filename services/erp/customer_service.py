"""ERP Customer Service — customer/vendor master data CRUD."""

import logging
from typing import Optional, List

from .base_erp_service import BaseERPService, check_permission, write_audit
from .errors import NotFoundError, ValidationError
from .request_context import ERPRequestContext
from .repositories.firestore.customer_repo import FirestoreCustomerRepository

logger = logging.getLogger(__name__)


class CustomerService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreCustomerRepository] = None

    def _get_repo(self) -> FirestoreCustomerRepository:
        if self._repo is None:
            self._repo = FirestoreCustomerRepository(db=self._get_db())
        return self._repo

    async def get_customer(self, customer_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "customer:read")
        doc = await self._get_repo().get(customer_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Kupac '{customer_id}' nije pronađen.")
        return doc

    async def search_customers(
        self, query: str, ctx: ERPRequestContext,
        party_type: Optional[str] = None, limit: int = 20
    ) -> List[dict]:
        check_permission(ctx, "customer:read")
        filters = {"search": query}
        if party_type:
            filters["party_type"] = party_type
        return await self._get_repo().list(ctx, filters, limit=limit)

    async def list_customers(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 50, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "customer:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def create_customer(self, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "customer:create")
        if not data.get("name"):
            raise ValidationError(code="REQUIRED_FIELD", message="Ime kupca je obavezno.", field="name")
        doc = await self._get_repo().create(data, ctx)
        await write_audit("customer_created", "customer", doc["_id"],
                          data.get("name"), ctx, data, self._get_db())
        return doc

    async def update_customer(self, customer_id: str, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "customer:update")
        existing = await self._get_repo().get(customer_id, ctx)
        if existing is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Kupac '{customer_id}' nije pronađen.")
        doc = await self._get_repo().update(customer_id, ctx, data)
        await write_audit("customer_updated", "customer", customer_id,
                          existing.get("name"), ctx, data, self._get_db())
        return doc

    async def delete_customer(self, customer_id: str, ctx: ERPRequestContext) -> None:
        check_permission(ctx, "customer:update")
        existing = await self._get_repo().get(customer_id, ctx)
        if existing is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Kupac '{customer_id}' nije pronađen.")
        # TODO: check for open invoices before allowing delete
        await self._get_repo().soft_delete(customer_id, ctx)
        await write_audit("customer_deleted", "customer", customer_id,
                          existing.get("name"), ctx, db=self._get_db())

    async def get_customer_balance(self, customer_id: str, ctx: ERPRequestContext) -> dict:
        """Return open receivable balance for a customer."""
        check_permission(ctx, "invoice:read")
        from .invoice_service import get_invoice_service
        service = get_invoice_service()
        receivables = await service.list_invoices(
            ctx, filters={"customer_id": customer_id, "payment_status_ne": "paid"}
        )
        total_due = sum(float(r.get("erp_amount_due", 0)) for r in receivables)
        return {
            "customer_id": customer_id,
            "open_invoices": len(receivables),
            "total_due_eur": round(total_due, 2),
            "invoices": receivables,
        }


_customer_service_instance: Optional[CustomerService] = None


def get_customer_service() -> CustomerService:
    global _customer_service_instance
    if _customer_service_instance is None:
        _customer_service_instance = CustomerService()
    return _customer_service_instance
