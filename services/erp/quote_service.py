"""
ERP Quote Service (Ponude)
==========================
Manages quotes with state machine enforcement and invoice conversion.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from uuid import uuid4

from .base_erp_service import (
    BaseERPService, check_permission, generate_display_id, write_audit
)
from .errors import ValidationError, NotFoundError, DuplicateError
from .request_context import ERPRequestContext
from .state_machines import QUOTE_DOC_TRANSITIONS, validate_transition
from .repositories.firestore.quote_repo import FirestoreQuoteRepository

logger = logging.getLogger(__name__)


class QuoteService(BaseERPService):

    def __init__(self, project_id: Optional[str] = None):
        super().__init__(project_id)
        self._repo: Optional[FirestoreQuoteRepository] = None

    def _get_repo(self) -> FirestoreQuoteRepository:
        if self._repo is None:
            self._repo = FirestoreQuoteRepository(db=self._get_db())
        return self._repo

    @staticmethod
    def _compute_item_totals(items: list) -> tuple:
        """Compute line totals and return (items, subtotal_net, vat_total, total_gross) using Decimal."""
        _Q = Decimal("0.01")
        subtotal_net = Decimal("0")
        vat_total = Decimal("0")
        for item in items:
            qty = Decimal(str(item.get("quantity", 1)))
            price = Decimal(str(item.get("unit_price", 0)))
            vat_rate = Decimal(str(item.get("vat_rate", 25)))
            line_net = (qty * price).quantize(_Q, ROUND_HALF_UP)
            line_vat = (line_net * vat_rate / Decimal("100")).quantize(_Q, ROUND_HALF_UP)
            line_gross = line_net + line_vat
            item["line_net"] = float(line_net)
            item["line_vat"] = float(line_vat)
            item["line_gross"] = float(line_gross)
            subtotal_net += line_net
            vat_total += line_vat
        total_gross = subtotal_net + vat_total
        return items, float(subtotal_net), float(vat_total), float(total_gross)

    async def get_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:read")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ponuda '{quote_id}' nije pronađena."
            )
        return doc

    async def list_quotes(
        self, ctx: ERPRequestContext, filters: Optional[dict] = None,
        limit: int = 50, offset: int = 0
    ) -> List[dict]:
        check_permission(ctx, "quote:read")
        f = dict(filters or {})
        customer_name_q = f.pop("customer_name", "").strip().lower()
        if customer_name_q:
            # Firestore has no substring search — fetch more, filter in service
            repo_limit = min(limit * 5, 500)
        else:
            repo_limit = limit
        docs = await self._get_repo().list(ctx, f, repo_limit, offset if not customer_name_q else 0)
        if customer_name_q:
            docs = [d for d in docs if customer_name_q in (d.get("customer_name") or "").lower()]
            docs = docs[offset:offset + limit]
        return docs

    async def create_quote(self, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:create")

        if not data.get("customer_id"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="customer_id je obavezan.",
                field="customer_id",
            )
        items = data.get("items", [])
        if not items:
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Ponuda mora imati barem jednu stavku.",
                field="items",
            )
        if not data.get("valid_until"):
            raise ValidationError(
                code="REQUIRED_FIELD",
                message="Rok valjanosti (valid_until) je obavezan.",
                field="valid_until",
            )
        # valid_until must not be in the past
        try:
            vu = datetime.strptime(str(data["valid_until"])[:10], "%Y-%m-%d").date()
            if vu < datetime.now(timezone.utc).date():
                raise ValidationError(
                    code="INVALID_DATE",
                    message="Rok valjanosti ne može biti u prošlosti.",
                    field="valid_until",
                )
        except ValueError:
            raise ValidationError(
                code="INVALID_DATE",
                message="Neispravan format datuma za valid_until (očekivan YYYY-MM-DD).",
                field="valid_until",
            )

        # Compute totals from items (Decimal precision)
        items, subtotal_net, vat_total, total_gross = self._compute_item_totals(items)

        display_id = await generate_display_id(ctx.company_id, "PON", self._get_db())

        doc_data = {
            "display_id": display_id,
            "customer_id": data["customer_id"],
            "customer_name": data.get("customer_name", ""),
            "customer_oib": data.get("customer_oib", ""),
            "issue_date": data.get("issue_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "valid_until": data["valid_until"],
            "currency": data.get("currency", "EUR"),
            "document_status": "draft",
            "items": items,
            "subtotal_net": subtotal_net,
            "vat_total": vat_total,
            "total_gross": total_gross,
            "notes": data.get("notes", ""),
            "source": data.get("source", "manual"),
            "converted_invoice_id": "",
            "converted_invoice_type": "",
            "converted_at": "",
            "accepted_at": "",
            "rejected_at": "",
            "sent_at": "",
            "cancelled_at": "",
            "created_by": ctx.user_id,
        }

        doc = await self._get_repo().create(doc_data, ctx)
        await write_audit(
            "quote_created", "quote", doc["quote_id"],
            display_id, ctx, db=self._get_db()
        )
        return doc

    async def update_quote(self, quote_id: str, data: dict, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        if doc["document_status"] != "draft":
            raise ValidationError(
                code="WRONG_STATUS",
                message="Uređivanje je moguće samo za ponude u statusu 'draft'.",
            )

        # Allowed editable fields
        editable = {
            "customer_id", "customer_name", "customer_oib",
            "valid_until", "currency", "items", "notes",
        }
        update_data = {k: v for k, v in data.items() if k in editable}

        # Recompute totals if items changed (Decimal precision)
        if "items" in update_data:
            items, sn, vt, tg = self._compute_item_totals(update_data["items"])
            update_data["items"] = items
            update_data["subtotal_net"] = sn
            update_data["vat_total"] = vt
            update_data["total_gross"] = tg

        updated = await self._get_repo().update(quote_id, ctx, update_data)
        await write_audit(
            "quote_updated", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def mark_sent(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:send")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "sent", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "sent",
            "sent_at": now,
        })
        await write_audit(
            "quote_sent", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def accept_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "accepted", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "accepted",
            "accepted_at": now,
        })
        await write_audit(
            "quote_accepted", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def reject_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "rejected", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "rejected",
            "rejected_at": now,
        })
        await write_audit(
            "quote_rejected", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def cancel_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "cancelled", QUOTE_DOC_TRANSITIONS)
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "cancelled",
            "cancelled_at": now,
        })
        await write_audit(
            "quote_cancelled", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def expire_quote(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        check_permission(ctx, "quote:update")
        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")
        validate_transition(doc["document_status"], "expired", QUOTE_DOC_TRANSITIONS)
        updated = await self._get_repo().update(quote_id, ctx, {
            "document_status": "expired",
        })
        await write_audit(
            "quote_expired", "quote", quote_id,
            doc.get("display_id"), ctx, db=self._get_db()
        )
        return updated

    async def convert_to_invoice(self, quote_id: str, invoice_type: str, ctx: ERPRequestContext) -> dict:
        """
        Convert an accepted quote to an outgoing invoice.
        Idempotent: if already converted, returns existing invoice reference.

        For invoice_type="b2b", delegates to create_outbound_b2b_from_quote() so that
        the invoice is created through the full OutboundB2BService pipeline (display_id
        counter, archive tracking fields, dispatch fields, idempotency, etc.).
        """
        check_permission(ctx, "quote:convert")

        if invoice_type not in ("b2c", "b2b", "b2g", "eu", "int"):
            raise ValidationError(
                code="INVALID_INVOICE_TYPE",
                message=f"Nepoznat tip računa: {invoice_type}. Dozvoljeni: b2c, b2b, b2g, eu, int.",
            )

        # Domestic B2B: delegate to canonical outbound B2B pipeline.
        if invoice_type == "b2b":
            return await self._convert_to_outbound_b2b(quote_id, ctx)

        # Public-sector B2G: delegate to canonical outbound B2G pipeline.
        if invoice_type == "b2g":
            return await self._convert_to_outbound_b2g(quote_id, ctx)

        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")

        # Idempotency: already converted
        if doc["document_status"] == "converted" and doc.get("converted_invoice_id"):
            return {
                "quote_id": quote_id,
                "invoice_id": doc["converted_invoice_id"],
                "invoice_type": doc["converted_invoice_type"],
                "already_converted": True,
            }

        validate_transition(doc["document_status"], "converted", QUOTE_DOC_TRANSITIONS)

        # Build invoice document from quote data
        from .base_erp_service import get_firestore_db
        db = self._get_db()

        invoice_id = str(uuid4())
        invoice_display_id = await generate_display_id(ctx.company_id, "RA", db)

        INVOICE_TYPE_TO_COLLECTION = {
            "b2c": "invoices_b2c", "b2b": "invoices_b2b",
            "b2g": "invoices_b2g", "eu": "invoices_eu", "int": "invoices_int",
        }
        collection = INVOICE_TYPE_TO_COLLECTION[invoice_type]

        # Resolve seller identity from company_settings (Sprint C0.2)
        _seller: dict = {}
        try:
            from services.erp.company_service import get_company_settings as _get_cs
            _cs = await _get_cs(ctx.company_id) or {}
            _seller = {
                "seller_name":    _cs.get("name", ""),
                "seller_oib":     _cs.get("oib", ""),
                "seller_iban":    _cs.get("iban", ""),
                "seller_address": _cs.get("address", ""),
                "seller_city":    _cs.get("city", ""),
                "seller_country": _cs.get("country", "HR"),
            }
        except Exception as _cs_exc:
            logger.warning(
                f"[QuoteService] company_settings lookup failed for "
                f"{ctx.company_id}: {_cs_exc}. Seller fields will be empty."
            )

        now = datetime.now(timezone.utc).isoformat()
        invoice_doc = {
            "invoice_id": invoice_id,
            "display_id": invoice_display_id,
            "invoice_number": invoice_display_id,
            "company_id": ctx.company_id,
            # Seller identity (Sprint C0.2: from company_settings when available)
            "seller_name":    _seller.get("seller_name", ""),
            "seller_oib":     _seller.get("seller_oib", ""),
            "seller_iban":    _seller.get("seller_iban", ""),
            "seller_address": _seller.get("seller_address", ""),
            "seller_city":    _seller.get("seller_city", ""),
            "seller_country": _seller.get("seller_country", "HR"),
            "customer_id": doc.get("customer_id", ""),
            "customer_name": doc.get("customer_name", ""),
            "customer_oib": doc.get("customer_oib", ""),
            "buyer_name": doc.get("customer_name", ""),
            "buyer_oib": doc.get("customer_oib", ""),
            # "date" is the canonical sort/filter field used by invoice_repo + reporting_service.
            "issue_date": now[:10],
            "date":       now[:10],
            "currency": doc.get("currency", "EUR"),
            "document_status": "draft",
            "erp_payment_status": "unpaid",
            "erp_amount_paid": 0.0,
            "erp_amount_due": doc.get("total_gross", 0),
            "items": doc.get("items", []),
            "subtotal_net": doc.get("subtotal_net", 0),
            "vat_total": doc.get("vat_total", 0),
            "grand_total": doc.get("total_gross", 0),
            "total_gross": doc.get("total_gross", 0),
            "notes": f"Kreirano iz ponude {doc.get('display_id', quote_id)}.",
            "source_quote_id": quote_id,
            "source_quote_display_id": doc.get("display_id", ""),
            "created_at": now,
            "created_by": ctx.user_id,
            "deleted": False,
            # Fiscalization tracking (Sprint C1 bridge) — populated after CIS call
            "fiscalization_status":  "pending" if invoice_type == "b2c" else "not_required",
            "fiscalized_at":         None,
            "jir":                   None,
            "zki":                   None,
            "verification_url":      None,
            "qr_code_base64":        None,
            "fiscalization_error":   None,
            # Fiscal invoice number fields (Sprint C1.2)
            # fiscal_invoice_number is the FINA-required XXX/PP/NU format.
            # It is distinct from display_id (RA-...) which is the internal ERP number.
            # Populated at fiscalization time (POST /invoices/b2c/{id}/fiscalize).
            "fiscal_invoice_number": None,
            "business_unit":         None,  # vu_code from company_settings
            "device_number":         None,  # nu_code from company_settings
        }

        batch = db.batch()
        batch.set(db.collection(collection).document(invoice_id), invoice_doc)
        batch.update(db.collection("quotes").document(quote_id), {
            "document_status": "converted",
            "converted_invoice_id": invoice_id,
            "converted_invoice_type": invoice_type,
            "converted_at": now,
            "updated_at": now,
        })
        await batch.commit()

        await write_audit(
            "quote_converted", "quote", quote_id,
            doc.get("display_id"), ctx,
            {"invoice_id": invoice_id, "invoice_display_id": invoice_display_id, "invoice_type": invoice_type},
            db,
        )
        return {
            "quote_id": quote_id,
            "invoice_id": invoice_id,
            "invoice_type": invoice_type,
            "invoice_display_id": invoice_display_id,
            "already_converted": False,
        }

    # ------------------------------------------------------------------
    # Sprint B: convert_to_invoice("b2b") canonical delegation
    # ------------------------------------------------------------------

    async def _convert_to_outbound_b2b(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        """
        Canonical handler for convert_to_invoice(invoice_type="b2b").

        Delegates creation to create_outbound_b2b_from_quote() so the invoice goes
        through the full OutboundB2BService pipeline.  After creation, marks the
        quote as "converted" and writes converted_invoice_id for the idempotency
        path on the next call to convert_to_invoice().

        Returns the same thin summary dict as the generic convert_to_invoice()
        so the /quotes/{id}/convert route is backward-compatible.
        """
        check_permission(ctx, "quote:convert")

        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")

        if doc.get("converted_invoice_id"):
            return {
                "quote_id":           quote_id,
                "invoice_id":         doc["converted_invoice_id"],
                "invoice_type":       "b2b",
                "invoice_display_id": doc.get("converted_invoice_display_id", ""),
                "already_converted":  True,
            }

        invoice = await self.create_outbound_b2b_from_quote(quote_id, ctx)
        already_existed = invoice.pop("_already_exists", False)

        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._get_db().collection("quotes").document(quote_id).update({
                "document_status":               "converted",
                "converted_invoice_id":          invoice["invoice_id"],
                "converted_invoice_display_id":  invoice.get("display_id", ""),
                "converted_invoice_type":        "b2b",
                "linked_outbound_invoice_type":  "b2b",
                "converted_at":                  now,
                "updated_at":                    now,
            })
        except Exception as exc:
            logger.warning(
                f"[QuoteService] convert_to_invoice: failed to mark quote {quote_id} "
                f"as converted (invoice already created: {invoice['invoice_id']}): {exc}"
            )

        return {
            "quote_id":           quote_id,
            "invoice_id":         invoice["invoice_id"],
            "invoice_type":       "b2b",
            "invoice_display_id": invoice.get("display_id", ""),
            "already_converted":  already_existed,
        }

    # ------------------------------------------------------------------
    # Faza 2E: quote → outbound B2B invoice
    # ------------------------------------------------------------------

    async def _find_existing_outbound_invoice(
        self,
        quote_id: str,
        linked_id: Optional[str],
        ctx: ERPRequestContext,
        *,
        col: str = "invoices_b2b",
        svc_getter=None,
    ) -> Optional[dict]:
        """
        Robust idempotency lookup for create_outbound_*_from_quote().

        Two-stage strategy:
          1. If linked_id is set, try to fetch that invoice by ID directly via svc_getter().
          2. If fetch fails (deleted, wrong company, etc.) OR linked_id is missing,
             fall back to a Firestore query on source_quote_id in ``col``.
             This catches the "link-back write failed" scenario.

        Args:
            col:        Firestore collection name (e.g. "invoices_b2b", "invoices_b2g").
            svc_getter: Callable returning the appropriate outbound service instance.
                        Defaults to get_outbound_b2b_service.

        Returns the invoice doc if found, None otherwise.
        """
        from .outbound_b2b_service import get_outbound_b2b_service
        from google.cloud.firestore_v1.base_query import FieldFilter

        if svc_getter is None:
            svc_getter = get_outbound_b2b_service

        # Stage 1: fast path via stored linked_id
        if linked_id:
            try:
                return await svc_getter().get(linked_id, ctx)
            except (NotFoundError, Exception) as exc:
                logger.warning(
                    f"[QuoteService] linked_outbound_invoice_id={linked_id!r} fetch failed "
                    f"({type(exc).__name__}); falling back to source_quote_id query in {col!r}."
                )

        # Stage 2: query by source_quote_id — catches link-back failures.
        # If this query itself fails we MUST NOT return None (which would let create()
        # proceed and risk producing a duplicate). Raise instead so the caller aborts.
        try:
            db = self._get_db()
            query = (
                db.collection(col)
                .where(filter=FieldFilter("company_id",      "==", ctx.company_id))
                .where(filter=FieldFilter("source_quote_id", "==", quote_id))
                .where(filter=FieldFilter("deleted",          "==", False))
                .limit(1)
            )
            async for snap in query.stream():
                inv = snap.to_dict() or {}
                inv["_id"] = snap.id
                logger.info(
                    f"[QuoteService] Found existing invoice {inv.get('display_id')} "
                    f"via source_quote_id fallback for quote {quote_id} in {col!r}."
                )
                return inv
        except (ValidationError, NotFoundError):
            raise  # propagate our own errors unchanged
        except Exception as exc:
            # Cannot verify uniqueness → refuse to create rather than risk a duplicate.
            logger.error(
                f"[QuoteService] source_quote_id fallback query failed for {quote_id} "
                f"in {col!r}: {exc}. Aborting create to avoid duplicate invoice."
            )
            raise ValidationError(
                code="IDEMPOTENCY_CHECK_FAILED",
                message=(
                    "Provjera duplikata nije uspjela zbog privremene greške baze podataka. "
                    "Pokušajte ponovo za nekoliko trenutaka."
                ),
            )

        return None

    def _check_cross_type_link(self, doc: dict, target_type: str) -> None:
        """
        Guard: raise if the quote is already linked to an outbound invoice of a *different* type.

        This prevents a B2B-linked quote from silently producing a B2G invoice (and vice versa).
        Old documents without linked_outbound_invoice_type are not blocked.
        """
        existing_type = (doc.get("linked_outbound_invoice_type") or "").strip()
        if existing_type and existing_type != target_type:
            raise ValidationError(
                code="QUOTE_ALREADY_LINKED_TO_OTHER_OUTBOUND_TYPE",
                message=(
                    f"Ponuda je već povezana s izlaznim računom tipa '{existing_type}'. "
                    f"Nije moguće kreirati račun tipa '{target_type}' za istu ponudu. "
                    f"Jedan tip izlaznog računa po ponudi."
                ),
                field="invoice_type",
            )

    async def create_outbound_b2b_from_quote(
        self,
        quote_id: str,
        ctx: ERPRequestContext,
        overrides: Optional[dict] = None,
    ) -> dict:
        """
        Create a fully-structured outbound B2B invoice from an accepted quote,
        using OutboundB2BService.create() so all tracking fields are initialised.

        The quote must be in 'accepted' status.

        Idempotency (2E.1 hardened):
          - If quote.linked_outbound_invoice_id is set: fetch that invoice by ID.
          - If that fetch fails: fall back to querying invoices_b2b by source_quote_id.
          - Only if both lookups return nothing: create a new invoice.
        This ensures link-back write failures never produce duplicates.

        Returns the invoice doc. Callers can inspect _already_exists=True to decide
        whether to respond with HTTP 200 (existing) or 201 (created).

        Args:
            quote_id:  Firestore document ID of the quote.
            ctx:       Request context (must have outbound:create permission).
            overrides: Optional dict with seller_name, seller_oib, seller_iban,
                       seller_address, seller_city, due_date, notes.
        """
        check_permission(ctx, "outbound:create")

        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ponuda '{quote_id}' nije pronađena.",
            )

        # Cross-type guard: ensure quote isn't linked to a different outbound type
        self._check_cross_type_link(doc, "b2b")

        # Robust idempotency check (Stage 1 + Stage 2 fallback)
        existing = await self._find_existing_outbound_invoice(
            quote_id, doc.get("linked_outbound_invoice_id"), ctx,
            col="invoices_b2b",
        )
        if existing is not None:
            existing["_already_exists"] = True
            return existing

        # Status guard — only after idempotency check so repeat calls on
        # already-created invoices work regardless of current quote status.
        if doc["document_status"] != "accepted":
            raise ValidationError(
                code="QUOTE_NOT_ACCEPTED",
                message=(
                    f"Ponuda mora biti u statusu 'accepted' za kreiranje računa "
                    f"(trenutni status: {doc['document_status']!r})."
                ),
                field="document_status",
            )

        overrides = overrides or {}

        items = [
            {
                "name":        item.get("name") or item.get("description") or "",
                "description": item.get("description") or item.get("name") or "",
                "quantity":    float(item.get("quantity", 1)),
                "unit":        item.get("unit", "kom"),
                "unit_price":  float(item.get("unit_price", 0)),
                "vat_rate":    float(item.get("vat_rate", 25)),
            }
            for item in doc.get("items", [])
        ]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        payment_terms = int(doc.get("payment_terms", 30))

        if overrides.get("due_date"):
            due_date_str = str(overrides["due_date"])[:10]
        else:
            from datetime import timedelta
            due_date_str = (
                datetime.now(timezone.utc).date() + timedelta(days=payment_terms)
            ).isoformat()

        # Seller identity: overrides > company_settings (resolved inside create())
        # We pass override keys into payload; _resolve_seller() in OutboundB2BService
        # will fill in any blanks from company_settings automatically.
        payload = {
            "customer_id":       doc.get("customer_id", ""),
            "customer_name":     doc["customer_name"],
            "customer_oib":      doc.get("customer_oib", ""),
            "customer_address":  doc.get("customer_address", ""),
            "customer_city":     doc.get("customer_city", ""),
            "customer_country":  doc.get("customer_country", "HR"),
            "seller_name":       overrides.get("seller_name", ""),
            "seller_oib":        overrides.get("seller_oib", ""),
            "seller_iban":       overrides.get("seller_iban", ""),
            "seller_address":    overrides.get("seller_address", ""),
            "seller_city":       overrides.get("seller_city", ""),
            "issue_date":        today,
            "due_date":          due_date_str,
            "payment_terms":     payment_terms,
            "currency":          doc.get("currency", "EUR"),
            "items":             items,
            "notes":             overrides.get("notes")
                                 or f"Kreirano iz ponude {doc.get('display_id', quote_id)}.",
            "source_quote_id":   quote_id,
        }
        # Sprint C0.2: seller fields intentionally left empty/overridden above.
        # OutboundB2BService.create() will call _resolve_seller() which fills
        # missing seller fields from company_settings automatically.

        from .outbound_b2b_service import get_outbound_b2b_service
        invoice = await get_outbound_b2b_service().create(payload, ctx)

        # Link back to quote — if this fails, the next call will find the invoice
        # via the source_quote_id fallback query in _find_existing_outbound_invoice().
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._get_db().collection("quotes").document(quote_id).update({
                "linked_outbound_invoice_id":         invoice["invoice_id"],
                "linked_outbound_invoice_display_id": invoice.get("display_id", ""),
                "linked_outbound_invoice_type":       "b2b",
                "updated_at":                         now,
            })
        except Exception as exc:
            logger.warning(
                f"[QuoteService] Link-back write failed for quote {quote_id} → "
                f"invoice {invoice['invoice_id']}: {exc}. "
                f"Next call will recover via source_quote_id query."
            )

        await write_audit(
            "quote_outbound_invoice_created", "quote", quote_id,
            doc.get("display_id"), ctx,
            data={"invoice_id": invoice["invoice_id"],
                  "invoice_display_id": invoice.get("display_id")},
            db=self._get_db(),
        )
        return invoice

    # ------------------------------------------------------------------
    # Faza 2E / D1: quote → outbound B2G invoice
    # ------------------------------------------------------------------

    async def create_outbound_b2g_from_quote(
        self,
        quote_id: str,
        ctx: ERPRequestContext,
        overrides: Optional[dict] = None,
    ) -> dict:
        """
        Create a fully-structured outbound B2G invoice from an accepted quote,
        using OutboundB2GService.create() so all tracking fields are initialised.

        The quote must be in 'accepted' status.

        Idempotency: same two-stage strategy as the B2B path, but queries invoices_b2g.

        B2G-specific overrides (beyond the standard seller/due_date/notes):
            buyer_reference    — contract/procurement reference (EN 16931 BT-10)
            customer_peppol_id — buyer Peppol participant ID; pre-fills delivery_target

        Returns the invoice doc.  _already_exists=True when idempotency path was taken.
        """
        check_permission(ctx, "outbound:create")

        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(
                code="NOT_FOUND",
                message=f"Ponuda '{quote_id}' nije pronađena.",
            )

        # Cross-type guard
        self._check_cross_type_link(doc, "b2g")

        # Robust idempotency check
        from .outbound_b2g_service import get_outbound_b2g_service
        existing = await self._find_existing_outbound_invoice(
            quote_id, doc.get("linked_outbound_invoice_id"), ctx,
            col="invoices_b2g",
            svc_getter=get_outbound_b2g_service,
        )
        if existing is not None:
            existing["_already_exists"] = True
            return existing

        # Status guard — after idempotency so repeat calls on already-created invoices work
        if doc["document_status"] != "accepted":
            raise ValidationError(
                code="QUOTE_NOT_ACCEPTED",
                message=(
                    f"Ponuda mora biti u statusu 'accepted' za kreiranje računa "
                    f"(trenutni status: {doc['document_status']!r})."
                ),
                field="document_status",
            )

        overrides = overrides or {}

        items = [
            {
                "name":        item.get("name") or item.get("description") or "",
                "description": item.get("description") or item.get("name") or "",
                "quantity":    float(item.get("quantity", 1)),
                "unit":        item.get("unit", "kom"),
                "unit_price":  float(item.get("unit_price", 0)),
                "vat_rate":    float(item.get("vat_rate", 25)),
            }
            for item in doc.get("items", [])
        ]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        payment_terms = int(doc.get("payment_terms", 30))

        if overrides.get("due_date"):
            due_date_str = str(overrides["due_date"])[:10]
        else:
            from datetime import timedelta
            due_date_str = (
                datetime.now(timezone.utc).date() + timedelta(days=payment_terms)
            ).isoformat()

        payload = {
            "customer_id":          doc.get("customer_id", ""),
            "customer_name":        doc["customer_name"],
            "customer_oib":         doc.get("customer_oib", ""),
            "customer_address":     doc.get("customer_address", ""),
            "customer_city":        doc.get("customer_city", ""),
            "customer_country":     doc.get("customer_country", "HR"),
            "seller_name":          overrides.get("seller_name", ""),
            "seller_oib":           overrides.get("seller_oib", ""),
            "seller_iban":          overrides.get("seller_iban", ""),
            "seller_address":       overrides.get("seller_address", ""),
            "seller_city":          overrides.get("seller_city", ""),
            "issue_date":           today,
            "due_date":             due_date_str,
            "payment_terms":        payment_terms,
            "currency":             doc.get("currency", "EUR"),
            "items":                items,
            "notes":                overrides.get("notes")
                                    or f"Kreirano iz ponude {doc.get('display_id', quote_id)}.",
            "source_quote_id":      quote_id,
            # B2G-specific fields — from overrides; empty string if not provided
            "buyer_reference":      overrides.get("buyer_reference") or "",
            "customer_peppol_id":   overrides.get("customer_peppol_id") or "",
        }

        invoice = await get_outbound_b2g_service().create(payload, ctx)

        # Link back to quote
        try:
            now = datetime.now(timezone.utc).isoformat()
            await self._get_db().collection("quotes").document(quote_id).update({
                "linked_outbound_invoice_id":         invoice["invoice_id"],
                "linked_outbound_invoice_display_id": invoice.get("display_id", ""),
                "linked_outbound_invoice_type":       "b2g",
                "updated_at":                         now,
            })
        except Exception as exc:
            logger.warning(
                f"[QuoteService] B2G link-back write failed for quote {quote_id} → "
                f"invoice {invoice['invoice_id']}: {exc}. "
                f"Next call will recover via source_quote_id query."
            )

        await write_audit(
            "quote_outbound_b2g_invoice_created", "quote", quote_id,
            doc.get("display_id"), ctx,
            data={"invoice_id": invoice["invoice_id"],
                  "invoice_display_id": invoice.get("display_id")},
            db=self._get_db(),
        )
        return invoice

    async def _convert_to_outbound_b2g(self, quote_id: str, ctx: ERPRequestContext) -> dict:
        """
        Canonical handler for convert_to_invoice(invoice_type="b2g").

        Delegates creation to create_outbound_b2g_from_quote() so the invoice goes
        through the full OutboundB2GService pipeline.  After creation, marks the
        quote as "converted" and writes converted_invoice_id for the idempotency
        path on the next call to convert_to_invoice().

        Returns the same thin summary dict as the generic convert_to_invoice()
        so the /quotes/{id}/convert route is backward-compatible.
        """
        check_permission(ctx, "quote:convert")

        doc = await self._get_repo().get(quote_id, ctx)
        if doc is None:
            raise NotFoundError(code="NOT_FOUND", message=f"Ponuda '{quote_id}' nije pronađena.")

        if doc.get("converted_invoice_id") and doc.get("converted_invoice_type") == "b2g":
            return {
                "quote_id":           quote_id,
                "invoice_id":         doc["converted_invoice_id"],
                "invoice_type":       "b2g",
                "invoice_display_id": doc.get("converted_invoice_display_id", ""),
                "already_converted":  True,
            }

        invoice = await self.create_outbound_b2g_from_quote(quote_id, ctx)
        already_existed = invoice.pop("_already_exists", False)

        now = datetime.now(timezone.utc).isoformat()
        try:
            await self._get_db().collection("quotes").document(quote_id).update({
                "document_status":               "converted",
                "converted_invoice_id":          invoice["invoice_id"],
                "converted_invoice_display_id":  invoice.get("display_id", ""),
                "converted_invoice_type":        "b2g",
                "converted_at":                  now,
                "updated_at":                    now,
            })
        except Exception as exc:
            logger.warning(
                f"[QuoteService] _convert_to_outbound_b2g: failed to mark quote {quote_id} "
                f"as converted (invoice already created: {invoice['invoice_id']}): {exc}"
            )

        return {
            "quote_id":           quote_id,
            "invoice_id":         invoice["invoice_id"],
            "invoice_type":       "b2g",
            "invoice_display_id": invoice.get("display_id", ""),
            "already_converted":  already_existed,
        }


_quote_service_instance: Optional[QuoteService] = None


def get_quote_service() -> QuoteService:
    global _quote_service_instance
    if _quote_service_instance is None:
        _quote_service_instance = QuoteService()
    return _quote_service_instance
