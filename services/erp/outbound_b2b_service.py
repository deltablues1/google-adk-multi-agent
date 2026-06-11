"""
Outbound B2B Invoice Service (IRA — Izlazni eRačuni)
=====================================================
Manages the full lifecycle of domestic B2B outgoing invoices:

    draft → approved → issued → eracun_sent → delivered → accepted/rejected

State machine: OUTGOING_B2B_DOC_TRANSITIONS (services/erp/state_machines.py)

Key operations
--------------
  create()          — create invoice doc in Firestore (invoices_b2b collection)
  approve()         — validate + transition draft → approved
  issue()           — generate UBL 2.1 XML + transition approved → issued
  send()            — record delivery intent + transition issued → eracun_sent
  mark_delivered()  — transition eracun_sent → delivered
  accept()          — buyer confirmed receipt → delivered → accepted
  reject()          — buyer rejected           → eracun_sent/delivered → rejected
  archive_outbound()— move UBL file to Invoices_Archive/OUT/b2b/YYYY/MM/

UBL XML is stored inline on the Firestore doc (truncated at 1 MB).
Separate Drive archive is optional (post-issue).
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, date
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit,
)
from .errors import ValidationError, NotFoundError
from .request_context import ERPRequestContext
from .state_machines import OUTGOING_B2B_DOC_TRANSITIONS, validate_transition

logger = logging.getLogger(__name__)

_COL = "invoices_b2b"
_DISPLAY_PREFIX = "B2B"
_MAX_UBL_BYTES = 1_000_000   # 1 MB Firestore field limit


def get_outbound_b2b_service() -> "OutboundB2BService":
    """Singleton factory — import-safe (no module-level Firestore init)."""
    return OutboundB2BService()


class OutboundB2BService(BaseERPService):
    """Service for outgoing B2B invoice lifecycle."""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "outbound:read")
        snap = await self._get_db().collection(_COL).document(invoice_id).get()
        if not snap.exists:
            raise NotFoundError(code="NOT_FOUND",
                                message=f"Izlazni B2B račun '{invoice_id}' nije pronađen.")
        doc = snap.to_dict() or {}
        if doc.get("company_id") != ctx.company_id or doc.get("deleted"):
            raise NotFoundError(code="NOT_FOUND",
                                message=f"Izlazni B2B račun '{invoice_id}' nije pronađen.")
        doc["_id"] = snap.id
        return doc

    async def list(
        self,
        ctx: ERPRequestContext,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        check_permission(ctx, "outbound:read")
        from google.cloud.firestore_v1.base_query import FieldFilter
        # invoice_type filter intentionally absent — all docs in invoices_b2b are b2b.
        # Adding it would require a composite index with no practical benefit.
        query = (
            self._get_db().collection(_COL)
            .where(filter=FieldFilter("company_id", "==", ctx.company_id))
            .where(filter=FieldFilter("deleted",    "==", False))
        )
        f = filters or {}
        if f.get("document_status"):
            query = query.where(filter=FieldFilter("document_status", "==", f["document_status"]))
        if f.get("customer_id"):
            query = query.where(filter=FieldFilter("customer_id", "==", f["customer_id"]))
        if f.get("date_from") and not f.get("date_to"):
            # Single-sided range + order_by is fine
            query = query.where(filter=FieldFilter("issue_date", ">=", f["date_from"]))

        # Use offset-based limit to avoid composite index on issue_date DESCENDING.
        # Sort in Python to avoid additional Firestore composite index requirements.
        query = query.limit(limit + offset + 50)
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            doc["_id"] = snap.id
            # Post-filter date_to and date_from in Python
            issue = doc.get("issue_date", "")
            if f.get("date_from") and issue < f["date_from"]:
                continue
            if f.get("date_to") and issue > f["date_to"]:
                continue
            # Strip heavy UBL XML from list responses
            doc.pop("ubl_xml", None)
            docs.append(doc)
        # Sort descending by issue_date in Python
        docs.sort(key=lambda d: d.get("issue_date", ""), reverse=True)
        return docs[offset: offset + limit]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        data: dict,
        ctx: ERPRequestContext,
        invoice_id: Optional[str] = None,
        fail_if_exists: bool = False,
    ) -> dict:
        """Create a draft outbound B2B invoice.

        Args:
            invoice_id:     Optional explicit document ID. Callers that need
                            idempotent creation (e.g. quote→invoice) pass a
                            deterministic ID here.
            fail_if_exists: When True, uses Firestore's create() precondition —
                            raises google.api_core.exceptions.AlreadyExists if a
                            document with that ID already exists. This makes
                            concurrent duplicate creation impossible.
        """
        check_permission(ctx, "outbound:create")

        # Required field validation
        missing = [f for f in ("customer_name", "customer_oib", "issue_date")
                   if not data.get(f)]
        if missing:
            raise ValidationError(
                code="MISSING_FIELDS",
                message=f"Obavezna polja nedostaju: {missing}",
            )
        if not data.get("items"):
            raise ValidationError(
                code="MISSING_ITEMS",
                message="Račun mora imati barem jednu stavku.",
            )

        # Compute totals from items
        items, subtotal_net, vat_amount, total_gross = self._compute_totals(data["items"])

        # Honour explicitly provided totals if no items compute differs
        if data.get("total_gross") and not data.get("items"):
            total_gross = Decimal(str(data["total_gross"]))

        invoice_id  = invoice_id or str(uuid4())
        display_id  = await generate_display_id(ctx.company_id, _DISPLAY_PREFIX, self._get_db())
        now_iso     = datetime.now(timezone.utc).isoformat()

        # invoice_number = user-supplied or default to display_id
        invoice_number = data.get("invoice_number") or display_id

        doc = {
            "invoice_id":       invoice_id,
            "company_id":       ctx.company_id,
            "invoice_type":     "b2b",
            "display_id":       display_id,
            "invoice_number":   invoice_number,
            "deleted":          False,
            "document_status":  "draft",

            # Parties
            "seller_name":      data.get("seller_name", ""),
            "seller_oib":       data.get("seller_oib", ""),
            "seller_iban":      data.get("seller_iban", ""),
            "seller_address":   data.get("seller_address", ""),
            "seller_city":      data.get("seller_city", ""),
            "seller_country":   data.get("seller_country", "HR"),
            "customer_id":      data.get("customer_id", ""),
            "customer_name":    data["customer_name"],
            "customer_oib":     data["customer_oib"],
            "customer_address": data.get("customer_address", ""),
            "customer_city":    data.get("customer_city", ""),
            "customer_country": data.get("customer_country", "HR"),

            # Dates / terms
            "issue_date":     str(data["issue_date"])[:10],
            "due_date":       str(data["due_date"])[:10] if data.get("due_date") else None,
            "payment_terms":  int(data.get("payment_terms", 30)),
            "currency":       data.get("currency", "EUR"),

            # Financials
            "items":          items,
            "subtotal_net":   float(subtotal_net),
            "vat_amount":     float(vat_amount),
            "total_gross":    float(total_gross),
            "grand_total":    float(total_gross),   # InvoiceService compat

            # ERP payment tracking (InvoiceService compat)
            "erp_payment_status": "unpaid",
            "erp_amount_paid":    0.0,
            "erp_amount_due":     float(total_gross),

            # UBL / delivery
            "ubl_xml":           None,
            "ubl_generated_at":  None,
            "delivery_method":   None,
            "delivery_target":   None,
            "delivery_ref":      None,
            "sent_at":           None,
            "delivered_at":      None,
            "accepted_at":       None,
            "rejected_at":       None,
            "rejection_reason":  None,
            # Dispatch tracking (Faza 2B)
            "send_attempts":              0,
            "last_send_attempt_at":       None,
            "last_send_error":            None,
            "external_submission_id":     None,
            "external_status":            None,
            "external_status_updated_at": None,
            "next_retry_at":              None,

            # Source traceability (Faza 2E)
            "source_quote_id":   data.get("source_quote_id"),
            "source_order_id":   data.get("source_order_id"),

            # Dispatch capability snapshot (Faza 2D) — set at send() time
            "delivery_capabilities": None,

            # Archive (Faza 2C)
            "archive_status":          "not_archived",
            "archive_drive_file_id":   None,
            "archive_folder_id":       None,
            "archived_at":             None,
            "archive_error":           None,
            "archive_attempts":        0,
            "last_archive_attempt_at": None,
            "archive_ubl_file_id":     None,
            "archive_meta_file_id":    None,
            "archive_pdf_file_id":     None,

            "notes":       data.get("notes", ""),
            "created_at":  now_iso,
            "updated_at":  now_iso,
            "created_by":  ctx.user_id,
        }

        ref = self._get_db().collection(_COL).document(invoice_id)
        if fail_if_exists:
            await ref.create(doc)  # atomic — raises AlreadyExists on duplicate
        else:
            await ref.set(doc)
        await write_audit("outbound_b2b.created", "outbound_b2b", invoice_id, display_id, ctx,
                          data={"total_gross": float(total_gross)}, db=self._get_db())
        doc["_id"] = invoice_id
        return doc

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    async def approve(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "outbound:approve")
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "approved", OUTGOING_B2B_DOC_TRANSITIONS)
        return await self._transition(invoice_id, ctx, "approved",
                                      {"approved_at": datetime.now(timezone.utc).isoformat(),
                                       "approved_by": ctx.user_id})

    async def issue(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        """
        Transition approved → issued.
        Validates mandatory UBL fields, generates UBL 2.1 XML, stores inline.

        Pre-issue checks (HR-FISK 2.0 mandatory fields):
          - seller_name  — required for AccountingSupplierParty/PartyName
          - seller_oib   — required for PartyTaxScheme/CompanyID (HRXXXXXXXXXXX)
          - customer_oib — required for AccountingCustomerParty/PartyTaxScheme
          - invoice_number — defaults to display_id, but must not be blank
        """
        check_permission(ctx, "outbound:issue")
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "issued", OUTGOING_B2B_DOC_TRANSITIONS)

        # --- HR-FISK mandatory field checks before attempting UBL generation ---
        errors = []
        if not (doc.get("seller_name") or "").strip():
            errors.append("seller_name (naziv prodavatelja)")
        if not (doc.get("seller_oib") or "").strip():
            errors.append("seller_oib (OIB prodavatelja)")
        if not (doc.get("customer_oib") or "").strip():
            errors.append("customer_oib (OIB kupca)")
        if not (doc.get("items")):
            errors.append("items (stavke računa)")
        if errors:
            raise ValidationError(
                code="UBL_MISSING_FIELDS",
                message=(
                    "Račun nema sve obavezne HR-FISK podatke za UBL generaciju: "
                    + ", ".join(errors)
                    + ". Ažurirajte račun prije izdavanja."
                ),
            )

        # Generate UBL
        try:
            from .ubl_outbound_builder import build_ubl_b2b
            ubl_xml = build_ubl_b2b(doc)
        except ValueError as exc:
            raise ValidationError(code="UBL_BUILD_FAILED",
                                  message=f"UBL generacija nije uspjela: {exc}")

        # Truncate if over Firestore field limit
        ubl_bytes = ubl_xml.encode("utf-8")
        if len(ubl_bytes) > _MAX_UBL_BYTES:
            logger.warning(
                f"[OutboundB2B] UBL XML for {invoice_id} is {len(ubl_bytes)} bytes — "
                f"truncating to {_MAX_UBL_BYTES}"
            )
            ubl_xml = ubl_bytes[:_MAX_UBL_BYTES].decode("utf-8", errors="ignore")

        now = datetime.now(timezone.utc).isoformat()
        return await self._transition(invoice_id, ctx, "issued",
                                      {"ubl_xml": ubl_xml,
                                       "ubl_generated_at": now,
                                       "issued_at": now,
                                       "issued_by": ctx.user_id})

    async def send(
        self,
        invoice_id: str,
        ctx: ERPRequestContext,
        delivery_method: str,
        delivery_target: str,
        delivery_ref: str = "",
    ) -> dict:
        """
        Dispatch invoice to buyer via real transport adapter, then transition issued → eracun_sent.

        delivery_method: "email" | "peppol" | "manual"
        delivery_target: email address, Peppol participant ID, or blank for manual
        delivery_ref:    AP confirmation ref or note (optional)

        On success: records external_submission_id, clears last_send_error.
        On failure: records last_send_error, increments send_attempts, sets next_retry_at.
                    Does NOT transition status — retry via resend().
        """
        check_permission(ctx, "outbound:send")
        if delivery_method not in ("email", "peppol", "manual"):
            raise ValidationError(
                code="INVALID_DELIVERY_METHOD",
                message="Dozvoljene metode: email | peppol | manual",
                field="delivery_method",
            )
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "eracun_sent", OUTGOING_B2B_DOC_TRANSITIONS)

        from .outbound_dispatch_service import dispatch_invoice
        now = datetime.now(timezone.utc).isoformat()
        attempts = int(doc.get("send_attempts") or 0) + 1

        result = await dispatch_invoice(doc, delivery_method, delivery_target, delivery_ref)

        if result.get("ok"):
            from .outbound_capabilities import get_capabilities
            return await self._transition(invoice_id, ctx, "eracun_sent", {
                "delivery_method":            delivery_method,
                "delivery_target":            delivery_target,
                "delivery_ref":               delivery_ref,
                "sent_at":                    result.get("sent_at", now),
                "sent_by":                    ctx.user_id,
                "send_attempts":              attempts,
                "last_send_attempt_at":       now,
                "last_send_error":            None,
                "external_submission_id":     result.get("external_submission_id"),
                "next_retry_at":              None,
                "delivery_capabilities":      get_capabilities(delivery_method),
            })
        else:
            # Dispatch failed — record error, schedule retry in 30 min, do NOT change status
            from datetime import timedelta
            next_retry = (
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ).isoformat()
            await self._get_db().collection(_COL).document(invoice_id).update({
                "send_attempts":        attempts,
                "last_send_attempt_at": now,
                "last_send_error":      result.get("error", "unknown"),
                "next_retry_at":        next_retry,
                "delivery_method":      delivery_method,
                "delivery_target":      delivery_target,
                "delivery_ref":         delivery_ref,
                "updated_at":           now,
            })
            raise ValidationError(
                code="SEND_FAILED",
                message=f"Slanje nije uspjelo: {result.get('error')}. Retry scheduled.",
            )

    async def mark_delivered(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "outbound:send")
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "delivered", OUTGOING_B2B_DOC_TRANSITIONS)
        return await self._transition(invoice_id, ctx, "delivered",
                                      {"delivered_at": datetime.now(timezone.utc).isoformat()})

    async def accept(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Buyer confirmed receipt — delivered → accepted."""
        check_permission(ctx, "outbound:approve")
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "accepted", OUTGOING_B2B_DOC_TRANSITIONS)
        return await self._transition(invoice_id, ctx, "accepted",
                                      {"accepted_at": datetime.now(timezone.utc).isoformat()})

    async def reject(
        self, invoice_id: str, ctx: ERPRequestContext, rejection_reason: str
    ) -> dict:
        """Buyer rejected — eracun_sent/delivered → rejected."""
        check_permission(ctx, "outbound:approve")
        if not (rejection_reason or "").strip():
            raise ValidationError(
                code="REJECTION_REASON_REQUIRED",
                message="rejection_reason je obavezan.",
                field="rejection_reason",
            )
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "rejected", OUTGOING_B2B_DOC_TRANSITIONS)
        return await self._transition(invoice_id, ctx, "rejected", {
            "rejected_at":      datetime.now(timezone.utc).isoformat(),
            "rejection_reason": rejection_reason.strip(),
        })

    async def cancel(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        """Cancel a draft/approved/issued/eracun_sent invoice."""
        check_permission(ctx, "outbound:approve")
        doc = await self.get(invoice_id, ctx)
        validate_transition(doc["document_status"], "cancelled", OUTGOING_B2B_DOC_TRANSITIONS)
        return await self._transition(invoice_id, ctx, "cancelled",
                                      {"cancelled_at": datetime.now(timezone.utc).isoformat(),
                                       "cancelled_by": ctx.user_id})

    # ------------------------------------------------------------------
    # Dispatch / retry (Faza 2B)
    # ------------------------------------------------------------------

    async def resend(
        self,
        invoice_id: str,
        ctx: ERPRequestContext,
        delivery_method: Optional[str] = None,
        delivery_target: Optional[str] = None,
    ) -> dict:
        """
        Retry dispatch for an issued invoice that previously failed to send,
        OR re-send an already-sent invoice (e.g. buyer claims they didn't receive it).

        If delivery_method/target are omitted, uses the values already on the doc.
        Clears last_send_error and next_retry_at on success.
        """
        check_permission(ctx, "outbound:send")
        doc = await self.get(invoice_id, ctx)

        if doc["document_status"] not in ("issued", "eracun_sent"):
            raise ValidationError(
                code="INVALID_STATE_FOR_RESEND",
                message=(
                    f"Resend je moguć samo u statusu 'issued' ili 'eracun_sent', "
                    f"trenutni status: {doc['document_status']!r}"
                ),
            )
        if not doc.get("ubl_xml"):
            raise ValidationError(code="UBL_NOT_GENERATED",
                                  message="UBL XML nije generiran — pozovite /issue.")

        method = delivery_method or doc.get("delivery_method") or "manual"
        target = delivery_target or doc.get("delivery_target") or ""
        ref    = doc.get("delivery_ref") or ""

        if method not in ("email", "peppol", "manual"):
            raise ValidationError(
                code="INVALID_DELIVERY_METHOD",
                message="Dozvoljene metode: email | peppol | manual",
                field="delivery_method",
            )

        from .outbound_dispatch_service import dispatch_invoice
        now      = datetime.now(timezone.utc).isoformat()
        attempts = int(doc.get("send_attempts") or 0) + 1

        result = await dispatch_invoice(doc, method, target, ref)

        if result.get("ok"):
            from .outbound_capabilities import get_capabilities
            update = {
                "delivery_method":            method,
                "delivery_target":            target,
                "send_attempts":              attempts,
                "last_send_attempt_at":       now,
                "last_send_error":            None,
                "external_submission_id":     result.get("external_submission_id"),
                "next_retry_at":              None,
                "delivery_capabilities":      get_capabilities(method),
                "updated_at":                 now,
            }
            # If currently issued, transition to eracun_sent
            if doc["document_status"] == "issued":
                update["document_status"] = "eracun_sent"
                update["sent_at"] = result.get("sent_at", now)
                update["sent_by"] = ctx.user_id
            else:
                # Re-sent from eracun_sent — update sent_at
                update["sent_at"] = result.get("sent_at", now)
            await self._get_db().collection(_COL).document(invoice_id).update(update)
            await write_audit("outbound_b2b.resent", "outbound_b2b", invoice_id,
                              doc.get("display_id", invoice_id), ctx,
                              data={"method": method, "attempt": attempts}, db=self._get_db())
            return await self.get(invoice_id, ctx)
        else:
            from datetime import timedelta
            next_retry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            await self._get_db().collection(_COL).document(invoice_id).update({
                "send_attempts":        attempts,
                "last_send_attempt_at": now,
                "last_send_error":      result.get("error", "unknown"),
                "next_retry_at":        next_retry,
                "updated_at":           now,
            })
            raise ValidationError(
                code="SEND_FAILED",
                message=f"Resend nije uspio: {result.get('error')}. Retry scheduled.",
            )

    async def sync_external_status(
        self, invoice_id: str, ctx: ERPRequestContext,
        external_status: str, external_ref: str = ""
    ) -> dict:
        """
        Record an externally-sourced delivery/acknowledgement status update.

        Called by:
          - webhook callbacks from AP (Peppol, email delivery receipt)
          - manual operator sync
          - polling scheduler

        external_status values:
          "delivered"   → mark_delivered() automatically
          "accepted"    → accept() automatically
          "rejected"    → requires rejection_reason; use reject() directly
          "pending"     → just records the external status, no SM transition
          "failed"      → records error, no SM transition
        """
        check_permission(ctx, "outbound:send")
        doc = await self.get(invoice_id, ctx)
        now = datetime.now(timezone.utc).isoformat()

        update = {
            "external_status":            external_status,
            "external_status_updated_at": now,
            "updated_at":                 now,
        }
        if external_ref:
            update["external_submission_id"] = external_ref

        # For "failed" statuses: populate failure-tracking fields so the doc
        # enters list_send_failures() / retry_send_failures() flow.
        if external_status == "failed":
            from datetime import timedelta
            next_retry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            update["last_send_error"] = (
                f"External AP reported failure. ref={external_ref or 'none'}"
            )
            update["next_retry_at"]  = next_retry
            update["send_attempts"]  = int(doc.get("send_attempts") or 0) + 1

        await self._get_db().collection(_COL).document(invoice_id).update(update)

        # Auto-transition for unambiguous statuses
        if external_status == "delivered" and doc["document_status"] == "eracun_sent":
            return await self.mark_delivered(invoice_id, ctx)
        elif external_status == "accepted" and doc["document_status"] == "delivered":
            return await self.accept(invoice_id, ctx)

        return await self.get(invoice_id, ctx)

    async def list_pending_ack(self, ctx: ERPRequestContext) -> List[dict]:
        """
        Return invoices in eracun_sent or delivered status that have not yet been
        accepted/rejected by the buyer — i.e., awaiting buyer acknowledgement.

        Each doc is enriched with:
          days_waiting     — calendar days since sent_at
          ack_deadline     — ISO date: sent_at + 5 business days
          is_ack_overdue   — True when today > ack_deadline
        """
        check_permission(ctx, "outbound:read")
        from google.cloud.firestore_v1.base_query import FieldFilter
        from datetime import timedelta

        today = date.today()

        def _ack_deadline(sent_at_iso: str) -> date:
            """5 business days from sent_at (Mon-Fri only)."""
            try:
                sent_date = date.fromisoformat(sent_at_iso[:10])
            except (ValueError, TypeError):
                return today
            deadline = sent_date
            bdays = 0
            while bdays < 5:
                deadline += timedelta(days=1)
                if deadline.weekday() < 5:
                    bdays += 1
            return deadline

        from .outbound_capabilities import ack_expected as _ack_expected

        docs = []
        for status in ("eracun_sent", "delivered"):
            query = (
                self._get_db().collection(_COL)
                .where(filter=FieldFilter("company_id", "==", ctx.company_id))
                .where(filter=FieldFilter("deleted",    "==", False))
                .where(filter=FieldFilter("document_status", "==", status))
                .limit(200)
            )
            async for snap in query.stream():
                doc = snap.to_dict() or {}
                # Only include adapters where ack is expected (e.g. manual skipped)
                if not _ack_expected(doc.get("delivery_method") or "manual"):
                    continue
                doc["_id"] = snap.id
                doc.pop("ubl_xml", None)

                sent_at = doc.get("sent_at") or ""
                if sent_at:
                    try:
                        sent_date   = date.fromisoformat(sent_at[:10])
                        days_waiting = (today - sent_date).days
                    except (ValueError, TypeError):
                        days_waiting = None

                    deadline         = _ack_deadline(sent_at)
                    doc["days_waiting"]   = days_waiting
                    doc["ack_deadline"]   = deadline.isoformat()
                    doc["is_ack_overdue"] = today > deadline
                else:
                    doc["days_waiting"]   = None
                    doc["ack_deadline"]   = None
                    doc["is_ack_overdue"] = False

                docs.append(doc)

        docs.sort(key=lambda d: d.get("sent_at") or "", reverse=True)
        return docs

    async def list_send_failures(self, ctx: ERPRequestContext) -> List[dict]:
        """
        Return issued invoices with a non-null last_send_error
        (i.e. dispatch attempted at least once but failed, still in 'issued' status).
        """
        check_permission(ctx, "outbound:read")
        from google.cloud.firestore_v1.base_query import FieldFilter
        query = (
            self._get_db().collection(_COL)
            .where(filter=FieldFilter("company_id",     "==", ctx.company_id))
            .where(filter=FieldFilter("deleted",        "==", False))
            .where(filter=FieldFilter("document_status", "==", "issued"))
            .limit(200)
        )
        docs = []
        async for snap in query.stream():
            doc = snap.to_dict() or {}
            if doc.get("last_send_error"):   # Python filter — avoids composite index
                doc["_id"] = snap.id
                doc.pop("ubl_xml", None)
                docs.append(doc)
        docs.sort(key=lambda d: d.get("last_send_attempt_at") or "", reverse=True)
        return docs

    async def retry_send_failures(
        self, ctx: ERPRequestContext, max_attempts: int = 5
    ) -> dict:
        """
        Scheduler-called: retry all issued invoices with send failures
        where send_attempts < max_attempts and next_retry_at <= now.

        Returns: {"attempted": N, "succeeded": N, "failed": N, "skipped": N}
        """
        check_permission(ctx, "outbound:send")
        candidates = await self.list_send_failures(ctx)
        now_iso = datetime.now(timezone.utc).isoformat()

        attempted = succeeded = failed = skipped = 0
        for doc in candidates:
            if int(doc.get("send_attempts") or 0) >= max_attempts:
                skipped += 1
                continue
            next_retry = doc.get("next_retry_at") or ""
            if next_retry and next_retry > now_iso:
                skipped += 1
                continue

            attempted += 1
            try:
                await self.resend(doc["invoice_id"], ctx)
                succeeded += 1
            except Exception as exc:
                failed += 1
                logger.warning(f"[OutboundB2B] retry_send_failures: {doc.get('display_id')} failed: {exc}")

        return {"attempted": attempted, "succeeded": succeeded, "failed": failed, "skipped": skipped}

    # ------------------------------------------------------------------
    # Drive archive
    # ------------------------------------------------------------------

    async def archive_outbound(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        """
        Upload UBL XML + meta JSON to Drive (Invoices_Archive/OUT/b2b/YYYY/MM/).
        Delegates to outbound_archive_service.archive_outbound_document().
        Idempotent: if already archived, returns current doc state.
        """
        from .outbound_archive_service import archive_outbound_document
        return await archive_outbound_document(invoice_id, ctx)

    async def list_pending_archive(self, ctx: ERPRequestContext) -> List[dict]:
        """Return issued/sent/delivered/accepted/rejected invoices not yet archived."""
        from .outbound_archive_service import list_pending_outbound_archive
        return await list_pending_outbound_archive(ctx)

    async def retry_archive(
        self, ctx: ERPRequestContext, max_attempts: int = 3
    ) -> dict:
        """Retry archiving for all pending-archive invoices. Returns summary dict."""
        from .outbound_archive_service import retry_outbound_archive
        return await retry_outbound_archive(ctx, max_attempts=max_attempts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _transition(
        self, invoice_id: str, ctx: ERPRequestContext, new_status: str, extra: dict
    ) -> dict:
        """Write status transition + extra fields atomically."""
        now = datetime.now(timezone.utc).isoformat()
        update = {"document_status": new_status, "updated_at": now, **extra}
        await self._get_db().collection(_COL).document(invoice_id).update(update)
        await write_audit(f"outbound_b2b.{new_status}", "outbound_b2b", invoice_id, invoice_id,
                          ctx, data={"new_status": new_status}, db=self._get_db())
        return await self.get(invoice_id, ctx)

    @staticmethod
    def _compute_totals(items: list) -> tuple:
        """
        Compute (items_with_totals, subtotal_net, vat_amount, total_gross).
        Mutates item dicts by adding computed line total fields.
        """
        subtotal_net = Decimal("0")
        vat_amount   = Decimal("0")
        enriched = []
        for item in items:
            qty      = Decimal(str(item.get("quantity", 1)))
            price    = Decimal(str(item.get("unit_price", 0)))
            rate     = Decimal(str(item.get("vat_rate", 25)))
            line_net = (qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line_vat = (line_net * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line_gross = line_net + line_vat
            subtotal_net += line_net
            vat_amount   += line_vat
            enriched.append({
                **item,
                "line_total_net":   float(line_net),
                "vat_amount":       float(line_vat),
                "line_total_gross": float(line_gross),
            })
        total_gross = subtotal_net + vat_amount
        return enriched, subtotal_net, vat_amount, total_gross


