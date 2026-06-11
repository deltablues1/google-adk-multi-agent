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
from .peppol_status_service import fetch_submission_status, needs_poll

logger = logging.getLogger(__name__)

_COL = "invoices_b2b"
_DISPLAY_PREFIX = "B2B"
_MAX_UBL_BYTES = 1_000_000   # 1 MB Firestore field limit


def get_outbound_b2b_service() -> "OutboundB2BService":
    """Singleton factory — import-safe (no module-level Firestore init)."""
    return OutboundB2BService()


class OutboundB2BService(BaseERPService):
    """Service for outgoing B2B invoice lifecycle."""

    # Subclass-override points — change these to get a B2G (or other) service:
    _col            = "invoices_b2b"
    _display_prefix = "B2B"
    _invoice_type   = "b2b"
    _archive_alias  = "archive_out_b2b"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, invoice_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "outbound:read")
        snap = await self._get_db().collection(self._col).document(invoice_id).get()
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
            self._get_db().collection(self._col)
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

    async def _resolve_seller(
        self,
        data: dict,
        ctx: ERPRequestContext,
    ) -> dict:
        """
        Resolve seller identity with three-level precedence (Sprint C0.2):

          1. Explicit override in `data` (non-empty string wins)
          2. Firestore `company_settings` for ctx.company_id
          3. Empty string (never raises — downstream validation may catch it)

        Returns a dict with keys: seller_name, seller_oib, seller_iban,
        seller_address, seller_city, seller_country.
        """
        # Try company_settings when ANY seller field is missing/empty
        cs: dict = {}
        needs_cs = any(
            not data.get(k)
            for k in ("seller_name", "seller_oib", "seller_iban",
                       "seller_address", "seller_city")
        )
        if needs_cs:
            try:
                from services.erp.company_service import get_company_settings
                cs = await get_company_settings(ctx.company_id) or {}
            except Exception as exc:
                logger.warning(
                    f"[OutboundB2B] company_settings lookup failed for "
                    f"{ctx.company_id}: {exc}. Seller fields may be empty."
                )

        def _pick(field: str, cs_field: str | None = None) -> str:
            """data override > company_settings > empty string."""
            v = (data.get(field) or "").strip()
            if v:
                return v
            cs_key = cs_field or field.replace("seller_", "")
            return (cs.get(cs_key) or "").strip()

        return {
            "seller_name":    _pick("seller_name",    "name"),
            "seller_oib":     _pick("seller_oib",     "oib"),
            "seller_iban":    _pick("seller_iban",     "iban"),
            "seller_address": _pick("seller_address",  "address"),
            "seller_city":    _pick("seller_city",     "city"),
            "seller_country": _pick("seller_country",  "country") or "HR",
        }

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

        # Resolve seller identity — override > company_settings > ""
        seller = await self._resolve_seller(data, ctx)

        invoice_id  = invoice_id or str(uuid4())
        display_id  = await generate_display_id(ctx.company_id, self._display_prefix, self._get_db())
        now_iso     = datetime.now(timezone.utc).isoformat()

        # invoice_number = user-supplied or default to display_id
        invoice_number = data.get("invoice_number") or display_id

        doc = {
            "invoice_id":       invoice_id,
            "company_id":       ctx.company_id,
            "invoice_type":     self._invoice_type,
            "display_id":       display_id,
            "invoice_number":   invoice_number,
            "deleted":          False,
            "document_status":  "draft",

            # Parties (Sprint C0.2: seller resolved from company_settings when not given)
            "seller_name":      seller["seller_name"],
            "seller_oib":       seller["seller_oib"],
            "seller_iban":      seller["seller_iban"],
            "seller_address":   seller["seller_address"],
            "seller_city":      seller["seller_city"],
            "seller_country":   seller["seller_country"],
            "customer_id":      data.get("customer_id", ""),
            "customer_name":    data["customer_name"],
            "customer_oib":     data["customer_oib"],
            "customer_address": data.get("customer_address", ""),
            "customer_city":    data.get("customer_city", ""),
            "customer_country": data.get("customer_country", "HR"),

            # Dates / terms
            # "date" is the canonical sort/filter field used by invoice_repo and reporting_service.
            # Write both to ensure Firestore-side date queries work alongside issue_date consumers.
            "issue_date":     str(data["issue_date"])[:10],
            "date":           str(data["issue_date"])[:10],
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

        ref = self._get_db().collection(self._col).document(invoice_id)
        if fail_if_exists:
            await ref.create(doc)  # atomic — raises AlreadyExists on duplicate
        else:
            await ref.set(doc)
        await write_audit(f"outbound_{self._invoice_type}.created", f"outbound_{self._invoice_type}", invoice_id, display_id, ctx,
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

        # Fallback: if delivery_target is blank, use the value already on the doc
        # (set at create time from customer_peppol_id for B2G, or from a previous send attempt).
        if not delivery_target:
            delivery_target = doc.get("delivery_target") or doc.get("customer_peppol_id") or ""

        from .outbound_dispatch_service import dispatch_invoice
        now = datetime.now(timezone.utc).isoformat()
        attempts = int(doc.get("send_attempts") or 0) + 1

        result = await dispatch_invoice(doc, delivery_method, delivery_target, delivery_ref)

        if result.get("ok"):
            from .outbound_capabilities import get_capabilities
            # ap_submission_id — verbatim ID from AP; NEVER mutated.
            # Used for: AP status polling, webhook lookup, AP cross-reference.
            ap_sid = result.get("external_submission_id") or None

            # external_submission_key — local unique lookup key.
            # Normally equals ap_submission_id, but gets a suffix when AP recycles IDs
            # so that Firestore equality queries remain unambiguous within this company.
            # The KEY is used for local Firestore queries; the AP_SID is used for AP calls.
            ext_key = ap_sid

            if (
                ap_sid
                and not str(ap_sid).startswith("PEPPOL-STUB-")
                and delivery_method == "peppol"
            ):
                from google.cloud.firestore_v1.base_query import FieldFilter as _FF
                # Check both ap_submission_id (new) and external_submission_id (legacy)
                # to catch collisions with docs created before C2.2.3
                collision_found = False
                for check_field in ("ap_submission_id", "external_submission_id"):
                    if collision_found:
                        break
                    conflict_query = (
                        self._get_db().collection(self._col)
                        .where(filter=_FF("company_id", "==", ctx.company_id))
                        .where(filter=_FF("deleted",    "==", False))
                        .where(filter=_FF(check_field,  "==", ap_sid))
                        .limit(1)
                    )
                    async for snap in conflict_query.stream():
                        existing = snap.to_dict() or {}
                        if existing.get("invoice_id") != invoice_id:
                            logger.warning(
                                f"[OutboundB2B] ap_submission_id={ap_sid!r} already assigned "
                                f"to {existing.get('invoice_id')} (via {check_field}) — "
                                f"AP may have recycled the ID. "
                                f"external_submission_key will be suffixed; ap_submission_id stays verbatim."
                            )
                            ext_key = f"{ap_sid}#{invoice_id[:8]}"
                            collision_found = True
                        break

            return await self._transition(invoice_id, ctx, "eracun_sent", {
                "delivery_method":            delivery_method,
                "delivery_target":            delivery_target,
                "delivery_ref":               delivery_ref,
                "sent_at":                    result.get("sent_at", now),
                "sent_by":                    ctx.user_id,
                "send_attempts":              attempts,
                "last_send_attempt_at":       now,
                "last_send_error":            None,
                # Two-field AP identity model (C2.2.3):
                "ap_submission_id":           ap_sid,        # verbatim from AP — use for AP calls
                "external_submission_key":    ext_key,       # local unique key — use for Firestore lookups
                "external_submission_id":     ext_key,       # keep for backward compat (old queries/tests)
                "next_retry_at":              None,
                "delivery_capabilities":      get_capabilities(delivery_method),
            })
        else:
            # Dispatch failed — record error, schedule retry in 30 min, do NOT change status
            from datetime import timedelta
            next_retry = (
                datetime.now(timezone.utc) + timedelta(minutes=30)
            ).isoformat()
            await self._get_db().collection(self._col).document(invoice_id).update({
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
            # Two-field AP identity model (C2.2.3) — same logic as send()
            ap_sid  = result.get("external_submission_id") or None
            ext_key = ap_sid

            if (
                ap_sid
                and not str(ap_sid).startswith("PEPPOL-STUB-")
                and method == "peppol"
            ):
                from google.cloud.firestore_v1.base_query import FieldFilter as _FF
                collision_found = False
                for check_field in ("ap_submission_id", "external_submission_id"):
                    if collision_found:
                        break
                    conflict_query = (
                        self._get_db().collection(self._col)
                        .where(filter=_FF("company_id", "==", ctx.company_id))
                        .where(filter=_FF("deleted",    "==", False))
                        .where(filter=_FF(check_field,  "==", ap_sid))
                        .limit(1)
                    )
                    async for snap in conflict_query.stream():
                        existing = snap.to_dict() or {}
                        if existing.get("invoice_id") != invoice_id:
                            logger.warning(
                                f"[OutboundB2B/resend] ap_submission_id={ap_sid!r} already "
                                f"assigned to {existing.get('invoice_id')} (via {check_field}) — "
                                f"AP may have recycled the ID on resend. "
                                f"external_submission_key will be suffixed; ap_submission_id stays verbatim."
                            )
                            ext_key = f"{ap_sid}#{invoice_id[:8]}"
                            collision_found = True
                        break

            update = {
                "delivery_method":            method,
                "delivery_target":            target,
                "send_attempts":              attempts,
                "last_send_attempt_at":       now,
                "last_send_error":            None,
                "ap_submission_id":           ap_sid,
                "external_submission_key":    ext_key,
                "external_submission_id":     ext_key,
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
            await self._get_db().collection(self._col).document(invoice_id).update(update)
            await write_audit(f"outbound_{self._invoice_type}.resent", f"outbound_{self._invoice_type}", invoice_id,
                              doc.get("display_id", invoice_id), ctx,
                              data={"method": method, "attempt": attempts}, db=self._get_db())
            return await self.get(invoice_id, ctx)
        else:
            from datetime import timedelta
            next_retry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            await self._get_db().collection(self._col).document(invoice_id).update({
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

        await self._get_db().collection(self._col).document(invoice_id).update(update)

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
                self._get_db().collection(self._col)
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
            self._get_db().collection(self._col)
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
        Upload UBL XML + meta JSON to Drive (Invoices_Archive/OUT/{type}/YYYY/MM/).
        Delegates to outbound_archive_service.archive_outbound_document().
        Idempotent: if already archived, returns current doc state.
        """
        from .outbound_archive_service import archive_outbound_document
        return await archive_outbound_document(
            invoice_id, ctx, col=self._col, archive_alias=self._archive_alias,
            invoice_type=self._invoice_type,
        )

    async def list_pending_archive(self, ctx: ERPRequestContext) -> List[dict]:
        """Return issued/sent/delivered/accepted/rejected invoices not yet archived."""
        from .outbound_archive_service import list_pending_outbound_archive
        return await list_pending_outbound_archive(ctx, col=self._col)

    async def retry_archive(
        self, ctx: ERPRequestContext, max_attempts: int = 3
    ) -> dict:
        """Retry archiving for all pending-archive invoices. Returns summary dict."""
        from .outbound_archive_service import retry_outbound_archive
        return await retry_outbound_archive(
            ctx, max_attempts=max_attempts, col=self._col,
            archive_alias=self._archive_alias, invoice_type=self._invoice_type,
        )

    # ------------------------------------------------------------------
    # Peppol status feedback loop (Sprint C2.2)
    # ------------------------------------------------------------------

    async def get_by_submission_id(
        self, submission_id: str, ctx: ERPRequestContext
    ) -> dict:
        """
        Find an outbound B2B invoice by AP submission_id, scoped to ctx.company_id.

        Queries ``ap_submission_id`` first (C2.2.3 field), falls back to legacy
        ``external_submission_id`` for documents created before C2.2.3.

        Used by the status poller (which always has a company context).
        For webhook callbacks use get_by_submission_id_global().
        """
        check_permission(ctx, "outbound:read")
        from google.cloud.firestore_v1.base_query import FieldFilter
        db = self._get_db()

        # Primary: ap_submission_id (new canonical field)
        for field in ("ap_submission_id", "external_submission_id"):
            query = (
                db.collection(self._col)
                .where(filter=FieldFilter("company_id", "==", ctx.company_id))
                .where(filter=FieldFilter("deleted",    "==", False))
                .where(filter=FieldFilter(field,        "==", submission_id))
                .limit(1)
            )
            async for snap in query.stream():
                doc = snap.to_dict() or {}
                doc["_id"] = snap.id
                return doc

        raise NotFoundError(
            code="NOT_FOUND",
            message=f"Nema outbound B2B računa s ap_submission_id='{submission_id}'.",
        )

    async def get_by_submission_id_global(
        self,
        submission_id: str,
        *,
        receiver_participant_id: Optional[str] = None,
        sender_participant_id: Optional[str] = None,
    ) -> dict:
        """
        Find an outbound B2B invoice by AP submission_id across ALL companies.

        Used exclusively by the AP webhook handler (no user/company context).

        Lookup strategy (C2.2.3):
          1. Query ``ap_submission_id`` — the verbatim AP-issued ID (new canonical field)
          2. Fallback: ``external_submission_id`` — legacy field for docs pre-C2.2.3

        Disambiguation (when AP recycled the same ID for multiple docs):
          1. receiver_participant_id matches doc.delivery_target  (strongest signal)
          2. sender_participant_id matches doc's company peppol_participant_id
          3. First found + WARNING (last resort)

        Raises NotFoundError if no doc is found at all.
        """
        from google.cloud.firestore_v1.base_query import FieldFilter
        db = self._get_db()

        candidates: list[dict] = []
        seen_ids: set[str] = set()

        for field in ("ap_submission_id", "external_submission_id"):
            query = (
                db.collection(self._col)
                .where(filter=FieldFilter("deleted", "==", False))
                .where(filter=FieldFilter(field,     "==", submission_id))
                .limit(10)
            )
            async for snap in query.stream():
                if snap.id not in seen_ids:
                    doc = snap.to_dict() or {}
                    doc["_id"] = snap.id
                    candidates.append(doc)
                    seen_ids.add(snap.id)

        if not candidates:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Nema outbound B2B računa s ap_submission_id='{submission_id}'.",
            )

        if len(candidates) == 1:
            return candidates[0]

        # Multiple matches — recycled AP submission_id
        logger.warning(
            f"[OutboundB2B] ap_submission_id={submission_id!r} matched {len(candidates)} docs — "
            f"AP may have recycled this ID. Attempting disambiguation."
        )

        # 1. Match on receiver (delivery_target) — most reliable
        if receiver_participant_id:
            for doc in candidates:
                if doc.get("delivery_target") == receiver_participant_id:
                    logger.info(f"[OutboundB2B] Disambiguated {submission_id!r} via receiver match")
                    return doc

        # 2. Match on sender via company_settings.peppol_participant_id
        if sender_participant_id:
            for doc in candidates:
                company_id = doc.get("company_id") or ""
                if company_id:
                    try:
                        from services.erp.company_service import get_company_settings
                        cs = await get_company_settings(company_id) or {}
                        peppol_id = cs.get("peppol_participant_id") or ""
                        if not peppol_id and cs.get("oib"):
                            peppol_id = f"{cs.get('peppol_scheme','0190')}:{cs['oib']}"
                        if peppol_id and peppol_id == sender_participant_id:
                            logger.info(f"[OutboundB2B] Disambiguated {submission_id!r} via sender match")
                            return doc
                    except Exception:
                        pass

        # 3. Last resort: first found
        logger.warning(
            f"[OutboundB2B] Could not disambiguate {submission_id!r} — "
            f"using first match ({candidates[0].get('invoice_id')}). Manual review recommended."
        )
        return candidates[0]

    def _make_system_ctx(self, company_id: str) -> ERPRequestContext:
        """Return a minimal owner-level context for system-to-system operations."""
        from uuid import uuid4 as _uuid4
        return ERPRequestContext(
            user_id="peppol-ap-callback",
            company_id=company_id,
            role="owner",
            grants=set(),
            denies=set(),
            request_id=str(_uuid4()),
        )

    async def apply_peppol_status(
        self,
        submission_id: str,
        ctx: ERPRequestContext,
        *,
        status: str,
        raw_status: str = "",
        buyer_message: str = "",
    ) -> dict:
        """
        Apply a normalised Peppol status update (from poller) to the matching doc.
        Uses company-scoped lookup via ctx.  For webhook use apply_peppol_status_from_webhook().
        """
        doc = await self.get_by_submission_id(submission_id, ctx)
        return await self._apply_peppol_status_to_doc(doc, ctx, status, raw_status, buyer_message, submission_id)

    async def apply_peppol_status_from_webhook(
        self,
        submission_id: str,
        *,
        status: str,
        raw_status: str = "",
        buyer_message: str = "",
        receiver_participant_id: str = "",
        sender_participant_id: str = "",
    ) -> dict:
        """
        Apply a Peppol status update arriving from the AP webhook.

        Does NOT require a user identity — uses global cross-tenant lookup by
        submission_id, then derives a system context from the doc's company_id.

        receiver_participant_id / sender_participant_id are disambiguation hints
        used when an AP recycles submission IDs across multiple documents.

        Returns the updated invoice doc.
        """
        doc = await self.get_by_submission_id_global(
            submission_id,
            receiver_participant_id=receiver_participant_id or None,
            sender_participant_id=sender_participant_id or None,
        )
        company_id = doc.get("company_id") or ""
        if not company_id:
            raise ValidationError(
                code="MISSING_COMPANY_ID",
                message=f"Doc for submission {submission_id} has no company_id",
            )
        ctx = self._make_system_ctx(company_id)
        return await self._apply_peppol_status_to_doc(doc, ctx, status, raw_status, buyer_message, submission_id)

    async def _apply_peppol_status_to_doc(
        self,
        doc: dict,
        ctx: ERPRequestContext,
        status: str,
        raw_status: str,
        buyer_message: str,
        submission_id: str,
    ) -> dict:
        """Shared implementation for both webhook and poller paths."""
        invoice_id = doc["_id"]
        now = datetime.now(timezone.utc).isoformat()
        await self._get_db().collection(self._col).document(invoice_id).update({
            "peppol_raw_status":        raw_status or status,
            "peppol_status_updated_at": now,
            "updated_at":               now,
        })

        if status == "rejected":
            return await self.reject(
                invoice_id, ctx,
                rejection_reason=buyer_message or f"AP reported rejected (raw: {raw_status})",
            )

        return await self.sync_external_status(
            invoice_id, ctx,
            external_status=status,
            external_ref=submission_id,
        )

    async def poll_pending_peppol_status(
        self,
        ctx: ERPRequestContext,
        *,
        max_invoices: int = 50,
    ) -> dict:
        """
        Scheduler-called: poll the AP for status of all outbound Peppol invoices
        that are still in eracun_sent or delivered state.

        Returns::

            {
                "polled": N,
                "updated": N,   # status changed
                "errors":  N,   # AP call failed
                "skipped": N,   # terminal / no submission_id
                "_stub":   True/False
            }
        """
        check_permission(ctx, "outbound:send")

        from google.cloud.firestore_v1.base_query import FieldFilter

        # Collect Peppol docs in non-terminal states
        candidates = []
        for status in ("eracun_sent", "delivered"):
            query = (
                self._get_db().collection(self._col)
                .where(filter=FieldFilter("company_id",      "==", ctx.company_id))
                .where(filter=FieldFilter("deleted",         "==", False))
                .where(filter=FieldFilter("document_status", "==", status))
                .where(filter=FieldFilter("delivery_method", "==", "peppol"))
                .limit(max_invoices)
            )
            async for snap in query.stream():
                doc = snap.to_dict() or {}
                doc["_id"] = snap.id
                candidates.append(doc)

        polled = updated = errors = skipped = 0
        stub_mode = False

        for doc in candidates:
            # ap_submission_id is the verbatim AP ID — use it for AP calls.
            # Fall back to external_submission_id for docs created before C2.2.3.
            ap_sid = (
                doc.get("ap_submission_id")
                or doc.get("external_submission_id")
                or ""
            )
            if not ap_sid or ap_sid.startswith("PEPPOL-STUB-"):
                skipped += 1
                continue
            if not needs_poll(doc.get("external_status") or "pending"):
                skipped += 1
                continue

            polled += 1
            try:
                result = await fetch_submission_status(ap_sid, company_id=ctx.company_id)
                if result.get("_stub"):
                    stub_mode = True
                    skipped += 1
                    polled -= 1
                    continue

                new_status = result["status"]
                old_status = doc.get("external_status") or "pending"
                if new_status != old_status:
                    await self.apply_peppol_status(
                        ap_sid, ctx,
                        status=new_status,
                        raw_status=result.get("raw_status", ""),
                    )
                    updated += 1
                else:
                    # Still same status — just update checked_at
                    await self._get_db().collection(self._col).document(doc["_id"]).update({
                        "peppol_status_updated_at": result["checked_at"],
                        "updated_at":               result["checked_at"],
                    })
            except Exception as exc:
                errors += 1
                logger.warning(
                    f"[OutboundB2B/poll] {doc.get('display_id')}: {exc}"
                )

        result = {"polled": polled, "updated": updated, "errors": errors, "skipped": skipped}
        if stub_mode:
            result["_stub"] = True
        return result

    async def list_pending_peppol_sync(
        self,
        ctx: ERPRequestContext,
        *,
        cutoff_minutes: int = 30,
    ) -> dict:
        """
        Return all outbound Peppol invoices in eracun_sent or delivered state
        whose last AP status check is older than cutoff_minutes (or never checked).

        PEPPOL-STUB-* submission IDs are excluded.
        Works across B2B and B2G via self._col.

        Returns: {"count": N, "invoices": [...]}
        """
        check_permission(ctx, "outbound:read")
        from google.cloud.firestore_v1.base_query import FieldFilter
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=cutoff_minutes)).isoformat()
        docs = []
        for status in ("eracun_sent", "delivered"):
            query = (
                self._get_db().collection(self._col)
                .where(filter=FieldFilter("company_id",      "==", ctx.company_id))
                .where(filter=FieldFilter("deleted",         "==", False))
                .where(filter=FieldFilter("document_status", "==", status))
                .where(filter=FieldFilter("delivery_method", "==", "peppol"))
                .limit(100)
            )
            async for snap in query.stream():
                doc = snap.to_dict() or {}
                sid = doc.get("ap_submission_id") or doc.get("external_submission_id") or ""
                if sid.startswith("PEPPOL-STUB-"):
                    continue
                checked = doc.get("peppol_status_updated_at") or ""
                if not checked or checked < cutoff:
                    doc["_id"] = snap.id
                    doc.pop("ubl_xml", None)
                    docs.append(doc)
        docs.sort(key=lambda d: d.get("sent_at") or "", reverse=True)
        return {"count": len(docs), "invoices": docs}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _transition(
        self, invoice_id: str, ctx: ERPRequestContext, new_status: str, extra: dict
    ) -> dict:
        """Write status transition + extra fields atomically."""
        now = datetime.now(timezone.utc).isoformat()
        update = {"document_status": new_status, "updated_at": now, **extra}
        await self._get_db().collection(self._col).document(invoice_id).update(update)
        await write_audit(f"outbound_{self._invoice_type}.{new_status}", f"outbound_{self._invoice_type}", invoice_id, invoice_id,
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


