"""
ERP Reporting Service
======================
Pure read-only aggregation. No LLM, no writes.

TODO: When volumes exceed ~10k documents per company, consider BigQuery streaming
export or a Postgres read replica for reporting aggregations.
"""

import asyncio
import logging
from decimal import Decimal
from datetime import date
from typing import Optional, List
from itertools import chain

from google.cloud.firestore_v1.base_query import FieldFilter

from .base_erp_service import BaseERPService, check_permission
from .request_context import ERPRequestContext
from .repositories.firestore.invoice_repo import (
    FirestoreInvoiceRepository, INVOICE_TYPE_TO_COLLECTION
)
from .repositories.firestore.vendor_invoice_repo import FirestoreVendorInvoiceRepository

logger = logging.getLogger(__name__)


class ReportingService(BaseERPService):
    """All methods are read-only. Returns serializable dicts."""

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._invoice_repo: Optional[FirestoreInvoiceRepository] = None
        self._vendor_repo: Optional[FirestoreVendorInvoiceRepository] = None

    def _get_invoice_repo(self) -> FirestoreInvoiceRepository:
        if self._invoice_repo is None:
            self._invoice_repo = FirestoreInvoiceRepository(db=self._get_db())
        return self._invoice_repo

    def _get_vendor_repo(self) -> FirestoreVendorInvoiceRepository:
        if self._vendor_repo is None:
            self._vendor_repo = FirestoreVendorInvoiceRepository(db=self._get_db())
        return self._vendor_repo

    # ------------------------------------------------------------------
    # VAT Summary (PDV sažetak)
    # ------------------------------------------------------------------

    async def get_vat_summary(
        self, ctx: ERPRequestContext, year: int, month: int
    ) -> dict:
        """
        Output + input VAT by rate for a given month.
        Used for PDV obrazac preparation.
        """
        check_permission(ctx, "report:read")
        date_from = f"{year}-{month:02d}-01"
        if month == 12:
            date_to = f"{year}-12-31"
        else:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            date_to = f"{year}-{month:02d}-{last_day}"

        # Output VAT — parallel query across all outgoing invoice collections
        output_tasks = [
            self._query_vat_for_collection(col, ctx.company_id, date_from, date_to, "date")
            for col in INVOICE_TYPE_TO_COLLECTION.values()
        ]
        output_results = await asyncio.gather(*output_tasks, return_exceptions=True)
        output_vat = self._aggregate_vat(
            chain.from_iterable(r for r in output_results if not isinstance(r, Exception))
        )

        # Input VAT — vendor invoices
        input_vat_docs = await self._get_vendor_repo().list(
            ctx, {"date_from": date_from, "date_to": date_to}, limit=500
        )
        input_vat = self._aggregate_vendor_vat(input_vat_docs)

        net_vat = {
            rate: round(output_vat.get(rate, {}).get("vat_amount", 0) -
                        input_vat.get(rate, {}).get("vat_amount", 0), 2)
            for rate in set(list(output_vat.keys()) + list(input_vat.keys()))
        }

        return {
            "period": f"{year}-{month:02d}",
            "output_vat": output_vat,
            "input_vat": input_vat,
            "net_vat_payable": net_vat,
            "total_output_vat": round(sum(v.get("vat_amount", 0) for v in output_vat.values()), 2),
            "total_input_vat": round(sum(v.get("vat_amount", 0) for v in input_vat.values()), 2),
        }

    # ------------------------------------------------------------------
    # Receivables Aging
    # ------------------------------------------------------------------

    async def get_receivables_aging(
        self, ctx: ERPRequestContext, as_of_date: Optional[str] = None
    ) -> dict:
        """Open receivables bucketed by days overdue."""
        check_permission(ctx, "report:read")
        from .invoice_service import get_invoice_service
        service = get_invoice_service()
        return await service.get_open_receivables(ctx, as_of_date)

    # ------------------------------------------------------------------
    # Payables Aging
    # ------------------------------------------------------------------

    async def get_payables_aging(
        self, ctx: ERPRequestContext, as_of_date: Optional[str] = None
    ) -> dict:
        """Open payables bucketed by days overdue."""
        check_permission(ctx, "report:read")
        from .vendor_invoice_service import get_vendor_invoice_service
        service = get_vendor_invoice_service()
        return await service.get_open_payables(ctx)

    # ------------------------------------------------------------------
    # Financial Summary
    # ------------------------------------------------------------------

    async def get_financial_summary(
        self, ctx: ERPRequestContext, date_from: str, date_to: str
    ) -> dict:
        """Revenue vs expenses, gross margin."""
        check_permission(ctx, "report:read")

        # Revenue: sum of outgoing invoices (grand_total) in period
        revenue_tasks = [
            self._query_revenue_for_collection(col, ctx.company_id, date_from, date_to)
            for col in INVOICE_TYPE_TO_COLLECTION.values()
        ]
        revenue_results = await asyncio.gather(*revenue_tasks, return_exceptions=True)
        total_revenue = sum(
            r[0] for r in revenue_results if isinstance(r, tuple)
        )

        # Expenses: sum of vendor invoices in period
        vendor_docs = await self._get_vendor_repo().list(
            ctx, {"date_from": date_from, "date_to": date_to}, limit=1000
        )
        total_expenses = sum(float(d.get("total_gross") or 0) for d in vendor_docs)
        expenses_by_category = {}
        for d in vendor_docs:
            cat = d.get("category", "other")
            expenses_by_category[cat] = round(
                expenses_by_category.get(cat, 0) + float(d.get("total_gross") or 0), 2
            )

        gross_margin = total_revenue - total_expenses
        margin_pct = round(gross_margin / total_revenue * 100, 1) if total_revenue > 0 else 0

        return {
            "date_from": date_from,
            "date_to": date_to,
            "revenue_eur": round(total_revenue, 2),
            "expenses_eur": round(total_expenses, 2),
            "gross_margin_eur": round(gross_margin, 2),
            "gross_margin_pct": margin_pct,
            "expenses_by_category": expenses_by_category,
            "invoice_count": sum(
                r[1] for r in revenue_results if isinstance(r, tuple)
            ),
            "vendor_invoice_count": len(vendor_docs),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _query_vat_for_collection(
        self, collection: str, company_id: str, date_from: str, date_to: str, date_field: str
    ) -> List[dict]:
        """Query VAT breakdown from a single invoice collection."""
        try:
            query = (
                self._get_db().collection(collection)
                .where(filter=FieldFilter("company_id", "==", company_id))
                .where(filter=FieldFilter(date_field, ">=", date_from))
                .where(filter=FieldFilter(date_field, "<=", date_to))
                .limit(1000)
            )
            docs = []
            async for snap in query.stream():
                d = snap.to_dict() or {}
                docs.append(d)
            return docs
        except Exception as e:
            logger.warning(f"[Reporting] VAT query error for {collection}: {e}")
            return []

    async def _query_revenue_for_collection(
        self, collection: str, company_id: str, date_from: str, date_to: str
    ) -> tuple:
        try:
            query = (
                self._get_db().collection(collection)
                .where(filter=FieldFilter("company_id", "==", company_id))
                .where(filter=FieldFilter("date", ">=", date_from))
                .where(filter=FieldFilter("date", "<=", date_to))
                .limit(1000)
            )
            total = 0.0
            count = 0
            async for snap in query.stream():
                d = snap.to_dict() or {}
                total += float(d.get("grand_total") or d.get("total_gross") or 0)
                count += 1
            return total, count
        except Exception as e:
            logger.warning(f"[Reporting] Revenue query error for {collection}: {e}")
            return 0.0, 0

    def _aggregate_vat(self, docs) -> dict:
        """Aggregate VAT amounts by rate from outgoing invoice documents."""
        result: dict[str, dict] = {}
        for doc in docs:
            vat_breakdown = doc.get("vat_breakdown") or {}
            for rate, breakdown in vat_breakdown.items():
                rate_key = str(rate)
                if rate_key not in result:
                    result[rate_key] = {"rate": rate_key, "taxable_amount": 0.0, "vat_amount": 0.0}
                if isinstance(breakdown, dict):
                    result[rate_key]["taxable_amount"] = round(
                        result[rate_key]["taxable_amount"] + float(breakdown.get("base", 0) or breakdown.get("taxable_amount", 0)), 2
                    )
                    result[rate_key]["vat_amount"] = round(
                        result[rate_key]["vat_amount"] + float(breakdown.get("amount", 0) or breakdown.get("tax_amount", 0)), 2
                    )
        return result

    def _aggregate_vendor_vat(self, docs: List[dict]) -> dict:
        """Aggregate input VAT from vendor invoice documents."""
        result: dict[str, dict] = {}
        for doc in docs:
            vat_amount = float(doc.get("vat_amount") or 0)
            total_gross = float(doc.get("total_gross") or 0)
            taxable = total_gross - vat_amount
            # Vendor invoices store total VAT, not broken down by rate
            rate_key = "input"
            if rate_key not in result:
                result[rate_key] = {"rate": "input", "taxable_amount": 0.0, "vat_amount": 0.0}
            result[rate_key]["taxable_amount"] = round(result[rate_key]["taxable_amount"] + taxable, 2)
            result[rate_key]["vat_amount"] = round(result[rate_key]["vat_amount"] + vat_amount, 2)
        return result


_reporting_service_instance: Optional[ReportingService] = None


def get_reporting_service() -> ReportingService:
    global _reporting_service_instance
    if _reporting_service_instance is None:
        _reporting_service_instance = ReportingService()
    return _reporting_service_instance
