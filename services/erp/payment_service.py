"""
ERP Payment Service
====================
Manages payment records, allocations, and cashflow aggregation.
"""

import logging
from typing import Optional, List
from decimal import Decimal

from .base_erp_service import BaseERPService, check_permission, write_audit
from .errors import NotFoundError
from .request_context import ERPRequestContext
from .repositories.firestore.payment_repo import FirestorePaymentRepository

logger = logging.getLogger(__name__)


class PaymentService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestorePaymentRepository] = None

    def _get_repo(self) -> FirestorePaymentRepository:
        if self._repo is None:
            self._repo = FirestorePaymentRepository(db=self._get_db())
        return self._repo

    async def get_payment(self, payment_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "invoice:read")
        doc = await self._get_repo().get(payment_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Uplata '{payment_id}' nije pronađena.")
        return doc

    async def list_payments(
        self,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        check_permission(ctx, "invoice:read")
        return await self._get_repo().list(ctx, filters, limit, offset)

    async def get_allocations_for_invoice(
        self, invoice_id: str, ctx: ERPRequestContext
    ) -> List[dict]:
        check_permission(ctx, "invoice:read")
        return await self._get_repo().get_allocations_for_invoice(invoice_id, ctx.company_id)

    async def get_allocations_for_payment(
        self, payment_id: str, ctx: ERPRequestContext
    ) -> List[dict]:
        check_permission(ctx, "invoice:read")
        return await self._get_repo().get_allocations_for_payment(payment_id, ctx.company_id)

    async def get_cashflow_summary(
        self, ctx: ERPRequestContext, date_from: str, date_to: str
    ) -> dict:
        """
        Pure Decimal arithmetic aggregation of incoming vs outgoing payments.
        No LLM, no writes.
        """
        check_permission(ctx, "report:read")
        return await self._get_repo().get_cashflow(ctx.company_id, date_from, date_to)


# Singleton factory
_payment_service_instance: Optional[PaymentService] = None


def get_payment_service() -> PaymentService:
    global _payment_service_instance
    if _payment_service_instance is None:
        _payment_service_instance = PaymentService()
    return _payment_service_instance
