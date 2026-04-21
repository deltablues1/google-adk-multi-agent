"""
Outbound B2G Invoice Service (IRA — Izlazni eRačuni prema javnoj nabavi)
========================================================================
Manages the full lifecycle of domestic B2G outgoing invoices sent to the
Croatian public sector via FINA Peppol network.

State machine: same as B2B — draft → approved → issued → eracun_sent → delivered → accepted/rejected

Key differences from B2B
-------------------------
  - Collection       : invoices_b2g
  - Display prefix   : B2G-
  - Archive folder   : Invoices_Archive/OUT/b2g/YYYY/MM/ (alias: archive_out_b2g)
  - Fiscalization    : not_required (same as B2B — B2G uses CTC dual-reporting, not SOZU/CIS)
  - Delivery channel : Peppol (FINA network) mandatory for production;
                       email/manual permitted for staging/testing
  - Extra metadata   : buyer_reference (contract/procurement reference, BT-10 in EN 16931)
                       Optional but strongly recommended for public-sector compliance.

All lifecycle logic is inherited from OutboundB2BService.  Only the three
collection-level constants (_col, _display_prefix, _invoice_type, _archive_alias)
and the create() override differ.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .outbound_b2b_service import OutboundB2BService
from .base_erp_service import check_permission, generate_display_id, write_audit
from .errors import ValidationError
from .request_context import ERPRequestContext
from .state_machines import OUTGOING_B2B_DOC_TRANSITIONS, validate_transition

logger = logging.getLogger(__name__)


def get_outbound_b2g_service() -> "OutboundB2GService":
    """Singleton factory — import-safe."""
    return OutboundB2GService()


class OutboundB2GService(OutboundB2BService):
    """
    Service for outgoing B2G invoice lifecycle.
    Inherits all lifecycle methods from OutboundB2BService.
    Overrides collection, display prefix, and create() for B2G specifics.
    """

    _col            = "invoices_b2g"
    _display_prefix = "B2G"
    _invoice_type   = "b2g"
    _archive_alias  = "archive_out_b2g"

    async def create(self, data: dict, ctx: ERPRequestContext) -> dict:
        """
        Create a B2G invoice draft.

        Required fields (same as B2B):
          customer_name, customer_oib, issue_date, items

        B2G-specific optional fields:
          buyer_reference — contract/procurement reference number (EN 16931 BT-10).
                            Strongly recommended for FINA Peppol compliance.
          customer_peppol_id — buyer's Peppol participant ID (e.g. "0190:12345678901").
                               If provided, delivery_target defaults to this value.
        """
        check_permission(ctx, "outbound:create")

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

        items, subtotal_net, vat_amount, total_gross = self._compute_totals(data["items"])

        seller = await self._resolve_seller(data, ctx)

        invoice_id = str(__import__("uuid").uuid4())
        display_id = await generate_display_id(ctx.company_id, self._display_prefix, self._get_db())
        now_iso    = datetime.now(timezone.utc).isoformat()

        invoice_number = data.get("invoice_number") or display_id

        doc = {
            "invoice_id":       invoice_id,
            "company_id":       ctx.company_id,
            "invoice_type":     self._invoice_type,
            "display_id":       display_id,
            "invoice_number":   invoice_number,
            "deleted":          False,
            "document_status":  "draft",

            # Parties
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

            # B2G-specific
            "buyer_reference":   data.get("buyer_reference", ""),   # EN 16931 BT-10
            "customer_peppol_id": data.get("customer_peppol_id", ""),

            # Dates / terms
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
            "grand_total":    float(total_gross),

            # ERP payment tracking
            "erp_payment_status": "unpaid",
            "erp_amount_paid":    0.0,
            "erp_amount_due":     float(total_gross),

            # UBL / delivery
            "ubl_xml":           None,
            "ubl_generated_at":  None,
            "delivery_method":   None,
            "delivery_target":   data.get("customer_peppol_id") or None,
            "delivery_ref":      None,
            "sent_at":           None,
            "delivered_at":      None,
            "accepted_at":       None,
            "rejected_at":       None,
            "rejection_reason":  None,
            "send_attempts":              0,
            "last_send_attempt_at":       None,
            "last_send_error":            None,
            "external_submission_id":     None,
            "external_status":            None,
            "external_status_updated_at": None,
            "next_retry_at":              None,

            # Source traceability
            "source_quote_id":   data.get("source_quote_id"),
            "source_order_id":   data.get("source_order_id"),
            "delivery_capabilities": None,

            # Archive
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

        await self._get_db().collection(self._col).document(invoice_id).set(doc)
        await write_audit(
            f"outbound_{self._invoice_type}.created",
            f"outbound_{self._invoice_type}",
            invoice_id, display_id, ctx,
            data={"total_gross": float(total_gross)},
            db=self._get_db(),
        )
        doc["_id"] = invoice_id
        return doc
