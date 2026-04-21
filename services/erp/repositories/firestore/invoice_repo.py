"""
Firestore Invoice Repository
=============================
Handles multi-collection invoice queries (b2c/b2b/b2g/eu/int).
Business services use InvoiceReference.invoice_type to identify the collection —
the mapping lives here, not in services.
"""

import asyncio
import logging
from decimal import Decimal
from itertools import chain
from typing import Optional, List

from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

from ..base import InvoiceReference
from ...request_context import ERPRequestContext
from ...base_erp_service import get_firestore_db, serialize_doc

logger = logging.getLogger(__name__)

# Firestore collection name mapping — ONLY this file knows the storage layout
INVOICE_TYPE_TO_COLLECTION: dict[str, str] = {
    "b2c": "invoices_b2c",
    "b2b": "invoices_b2b",
    "b2g": "invoices_b2g",
    "eu":  "invoices_eu",
    "int": "invoices_int",
}

ALL_INVOICE_TYPES = list(INVOICE_TYPE_TO_COLLECTION.keys())


class FirestoreInvoiceRepository:
    """
    Repository for outgoing invoices across all 5 type-specific collections.

    Note: The existing fiscal collections are not migrated. This repo adds
    ERP payment tracking fields (erp_payment_status, erp_amount_paid, erp_amount_due, due_date)
    as additive fields on existing documents.
    """

    def __init__(self, db: Optional[AsyncClient] = None):
        self._db = db or get_firestore_db()

    def _collection_for_type(self, invoice_type: str) -> str:
        col = INVOICE_TYPE_TO_COLLECTION.get(invoice_type)
        if col is None:
            raise ValueError(f"Unknown invoice_type: {invoice_type!r}. "
                             f"Valid: {list(INVOICE_TYPE_TO_COLLECTION)}")
        return col

    async def get(self, invoice_ref: InvoiceReference, ctx: ERPRequestContext) -> Optional[dict]:
        """Fetch a single invoice by InvoiceReference, scoped to company_id."""
        col = self._collection_for_type(invoice_ref.invoice_type)
        snap = await self._db.collection(col).document(invoice_ref.invoice_id).get()
        if not snap.exists:
            return None
        doc = snap.to_dict()
        # Tenant isolation check
        if doc.get("company_id") and doc["company_id"] != ctx.company_id:
            return None
        doc["_id"] = snap.id
        doc["invoice_type"] = invoice_ref.invoice_type
        return self._enrich(doc)

    async def get_by_display_id(self, display_id: str, ctx: ERPRequestContext) -> Optional[dict]:
        """Find invoice by its human-readable display_id across all collections."""
        for inv_type, col in INVOICE_TYPE_TO_COLLECTION.items():
            query = (
                self._db.collection(col)
                .where(filter=FieldFilter("company_id", "==", ctx.company_id))
                .where(filter=FieldFilter("display_id", "==", display_id))
                .limit(1)
            )
            docs = [s async for s in query.stream()]
            if docs:
                doc = docs[0].to_dict()
                doc["_id"] = docs[0].id
                doc["invoice_type"] = inv_type
                return self._enrich(doc)
        return None

    async def list_by_type(
        self,
        invoice_type: str,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """List invoices from a single type collection."""
        col = self._collection_for_type(invoice_type)
        return await self._query_collection(invoice_type, col, ctx, filters or {}, limit, offset)

    async def list_all(
        self,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """
        Unified list across all 5 collections — parallel async queries.
        Returns merged + date-sorted results.
        """
        f = filters or {}
        # If a specific type is requested, query only that collection
        if "invoice_type" in f:
            inv_type = f["invoice_type"]
            return await self.list_by_type(inv_type, ctx, f, limit * 2, 0)

        # When date filters are active, Python-side filtering runs after the Firestore fetch.
        # Use a large safety cap so we don't silently miss documents.
        # For a Croatian SME (< 5000 invoices/collection/company lifetime), 5000 is safe.
        fetch_limit = 5000 if (f.get("date_from") or f.get("date_to")) else limit * 2
        tasks = [
            self._query_collection(t, col, ctx, f, fetch_limit, 0)
            for t, col in INVOICE_TYPE_TO_COLLECTION.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"[InvoiceRepo] Collection query error: {r}")
            else:
                merged.extend(r)

        merged.sort(key=lambda x: x.get("date", ""), reverse=True)
        return merged[offset: offset + limit]

    async def list_open_receivables(
        self, ctx: ERPRequestContext, as_of_date: Optional[str] = None
    ) -> List[dict]:
        """Return all invoices with erp_payment_status != 'paid'."""
        f = {"payment_status_ne": "paid"}
        return await self.list_all(ctx, f, limit=500)

    async def update_payment_tracking(
        self,
        invoice_ref: InvoiceReference,
        amount_paid: Decimal,
        amount_due: Decimal,
        payment_status: str,
    ) -> None:
        """
        Update ERP payment tracking fields on an existing invoice document.
        Called inside a Firestore batch by InvoiceService.record_payment().
        """
        col = self._collection_for_type(invoice_ref.invoice_type)
        await self._db.collection(col).document(invoice_ref.invoice_id).update({
            "erp_amount_paid": float(amount_paid),
            "erp_amount_due": float(amount_due),
            "erp_payment_status": payment_status,
        })

    async def get_payment_tracking(self, invoice_ref: InvoiceReference) -> dict:
        """Read just the ERP payment tracking fields from an invoice."""
        col = self._collection_for_type(invoice_ref.invoice_type)
        snap = await self._db.collection(col).document(invoice_ref.invoice_id).get(
            field_paths=["erp_amount_paid", "erp_amount_due", "erp_payment_status",
                         "grand_total", "total_gross", "due_date", "invoice_number",
                         "company_id", "customer_id", "customer_name",
                         "buyer_name", "buyer_oib"]
        )
        if not snap.exists:
            return {}
        return snap.to_dict() or {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _query_collection(
        self,
        inv_type: str,
        collection: str,
        ctx: ERPRequestContext,
        filters: dict,
        limit: int,
        offset: int,
    ) -> List[dict]:
        """Build and execute a Firestore query for one collection."""
        try:
            query = self._db.collection(collection).where(filter=FieldFilter("company_id", "==", ctx.company_id))

            if filters.get("payment_status"):
                query = query.where(filter=FieldFilter("erp_payment_status", "==", filters["payment_status"]))
            if filters.get("payment_status_ne") == "paid":
                # Firestore doesn't support !=; we query partial + unpaid separately
                pass  # handled in post-filter below
            if filters.get("customer_id"):
                query = query.where(filter=FieldFilter("customer_id", "==", filters["customer_id"]))
            # Date filters applied in Python after _enrich() normalises "date" from "issue_date".
            # Firestore-side date filtering is skipped here because different collections
            # use different field names ("date" vs "issue_date"); Python-side is safe for the
            # typical batch sizes queried here (limit * 2 docs per collection).

            query = query.limit(limit)
            docs = []
            date_from = filters.get("date_from", "")
            date_to   = filters.get("date_to", "")
            async for snap in query.stream():
                doc = snap.to_dict() or {}
                doc["_id"] = snap.id
                doc["invoice_type"] = inv_type
                doc = self._enrich(doc)   # sets doc["date"] from issue_date if needed

                # Post-filter: date range (Python-side, collection-agnostic)
                doc_date = doc.get("date", "")
                if date_from and doc_date < date_from:
                    continue
                if date_to and doc_date > date_to:
                    continue

                # Post-filter for payment_status_ne (Firestore != workaround)
                if filters.get("payment_status_ne") == "paid":
                    if doc.get("erp_payment_status") == "paid":
                        continue

                docs.append(doc)

            return docs
        except Exception as exc:
            logger.warning(f"[InvoiceRepo] Error querying {collection}: {exc}")
            return []

    def _enrich(self, doc: dict) -> dict:
        """Add computed fields and normalize ERP tracking fields."""
        # Normalize date field — outbound B2B/B2G write "issue_date"; older collections write "date".
        # Ensure every doc exposes a canonical "date" key for sorting and Python-side filtering.
        if not doc.get("date"):
            doc["date"] = doc.get("issue_date", "")

        # Default ERP payment fields if not yet set
        if "erp_amount_paid" not in doc:
            doc["erp_amount_paid"] = 0.0
        if "erp_payment_status" not in doc:
            doc["erp_payment_status"] = "unpaid"
        # Use grand_total or total_gross
        total = doc.get("grand_total") or doc.get("total_gross") or 0.0
        if "erp_amount_due" not in doc:
            doc["erp_amount_due"] = total
        doc["_total_gross"] = total
        return doc
