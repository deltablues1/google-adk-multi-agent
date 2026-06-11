"""
Inbound eRačun Transport Service  (Sprint Inbound A / A.1 / B)
==============================================================
Canonical orchestrator for inbound UBL/XML e-račun intake.

Architecture
------------
``_process_inbound_ubl()``  — the single private core that does all the real work:
  - calls vendor_invoice_service.create_from_ubl()  (dedup/parse/validate)
  - writes source metadata to the vendor invoice doc
  - archives original XML bytes via drive_archive_service.archive_inbound_bytes()
  - writes audit events

``InboundEracunTransportService``  — public façade with two thin adapters:
  - ``process_gmail_ubl_attachment()``   → Gmail path (Sprint A)
  - ``process_peppol_ubl_document()``    → AP/Peppol inbound path (Sprint B)
    (delegates to InboundPeppolTransportService internally but lives here for symmetry)

No domain logic lives here.  All parser / dedup / validation logic stays in:
  - services/erp/ubl_inbound_parser.py
  - services/erp/vendor_invoice_service.py
  - services/erp/repositories/firestore/vendor_invoice_repo.py

Result codes
------------
  "imported"   — vendor invoice draft created, original archived
  "duplicate"  — already exists (idempotent skip, no invoice created)
  "failed"     — parse error or unexpected exception (logged, not raised)

Source metadata fields recorded on vendor invoice
-------------------------------------------------
  source_type                   — "gmail_attachment" | "peppol_inbound"
  source_email_message_id       — (Gmail only)
  source_email_thread_id        — (Gmail only)
  source_email_from             — (Gmail only)
  source_email_subject          — (Gmail only)
  source_email_received_at      — (Gmail only)
  source_email_attachment_name  — (Gmail only)
  source_ap_submission_id       — (Peppol only)
  source_ap_document_id         — (Peppol only)
  source_sender_participant_id  — (Peppol only)
  source_receiver_participant_id— (Peppol only)
  source_received_at            — (Peppol only)
  source_filename               — (Peppol only, if AP provides filename)

Idempotency (Gmail — A.1)
--------------------------
Labels applied at **message** granularity (not thread).
Label IDs resolved once per poll cycle via _LabelCache.

Credentials (A.1 hardening)
----------------------------
Credentials forwarded all the way to Drive archive so Gmail and Drive
share the same OAuth identity.  Falls back to create_api_client_auto()
when credentials is None.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Gmail idempotency label names (A.1)
_LABEL_IMPORTED  = "ERP_IMPORTED"
_LABEL_DUPLICATE = "ERP_DUPLICATE"
_LABEL_FAILED    = "ERP_IMPORT_FAILED"

_OUTCOME_TO_LABEL = {
    "imported":  _LABEL_IMPORTED,
    "duplicate": _LABEL_DUPLICATE,
    "failed":    _LABEL_FAILED,
}


class _LabelCache:
    """
    Resolve label names to Gmail label IDs once per poll cycle.
    Gmail messages.modify() requires IDs, not names, for user labels.
    """

    def __init__(self, credentials):
        self._credentials = credentials
        self._cache: Dict[str, str] = {}

    async def get(self, label_name: str) -> str:
        if label_name not in self._cache:
            from tools.api_implementations.gmail_api import gmail_get_or_create_label
            self._cache[label_name] = await gmail_get_or_create_label(
                self._credentials, label_name
            )
        return self._cache[label_name]


# ---------------------------------------------------------------------------
# Canonical core (private)
# ---------------------------------------------------------------------------

async def _process_inbound_ubl(
    source_type: str,
    source_meta: dict,
    xml_bytes: bytes,
    ctx,
    *,
    credentials=None,
    archive: bool = True,
    filename: str = "",
) -> dict:
    """
    Single canonical core for all inbound UBL intake paths.

    Steps:
      1. create_from_ubl() — parse + validate + dedup + vendor match
      2. Write source_meta fields to vendor invoice doc
      3. Archive XML bytes to Drive (if archive=True and credentials given)
      4. Audit trail

    Returns dict with keys:
      status, vendor_invoice_id, display_id, archive_status, drive_file_id, error
    """
    from services.erp.vendor_invoice_service import VendorInvoiceService
    from services.erp.errors import DuplicateError, ValidationError
    from services.erp.base_erp_service import get_firestore_db

    svc = VendorInvoiceService()

    # ── Step 1: Create vendor invoice ──────────────────────────────────────
    try:
        invoice = await svc.create_from_ubl(xml_bytes, ctx)
        vendor_invoice_id = invoice["vendor_invoice_id"]
        display_id        = invoice.get("display_id", vendor_invoice_id)
    except DuplicateError as exc:
        logger.info(
            f"[InboundTransport/{source_type}] Duplicate UBL skipped: {exc.message} "
            f"(filename={filename!r})"
        )
        await _write_inbound_audit(
            f"vendor_invoice_inbound_{source_type}_duplicate",
            ctx,
            data={**source_meta, "duplicate_message": exc.message},
        )
        return {
            "status":         "duplicate",
            "archive_status": "skipped",
        }
    except (ValidationError, Exception) as exc:
        error_msg = getattr(exc, "message", None) or str(exc)
        logger.error(
            f"[InboundTransport/{source_type}] Failed to create vendor invoice: {error_msg} "
            f"(filename={filename!r})"
        )
        await _write_inbound_audit(
            f"vendor_invoice_inbound_{source_type}_failed",
            ctx,
            data={**source_meta, "error": error_msg[:500]},
        )
        return {
            "status":         "failed",
            "archive_status": "skipped",
            "error":          error_msg,
        }

    # ── Step 2: Write source metadata ──────────────────────────────────────
    db = get_firestore_db()
    try:
        await db.collection("vendor_invoices").document(vendor_invoice_id).update(source_meta)
    except Exception as exc:
        logger.warning(
            f"[InboundTransport/{source_type}] Could not write source metadata "
            f"to {vendor_invoice_id}: {exc}"
        )

    # ── Step 3: Archive XML bytes ───────────────────────────────────────────
    # archive_inbound_bytes() falls back to create_api_client_auto() when
    # credentials is None, so we attempt archiving regardless of caller context.
    archive_status = "skipped"
    drive_file_id  = ""
    if archive:
        archive_result = await _archive_xml_bytes(
            credentials,
            xml_bytes,
            filename or "eracun.xml",
            issue_date=invoice.get("issue_date", ""),
        )
        if archive_result["ok"]:
            archive_status = "archived"
            drive_file_id  = archive_result.get("drive_file_id", "")
            try:
                await db.collection("vendor_invoices").document(vendor_invoice_id).update({
                    "archive_status":         "archived",
                    "archived_at":            archive_result["archived_at"],
                    "drive_folder_id":        archive_result["drive_folder_id"],
                    "drive_original_file_id": drive_file_id,
                })
            except Exception as exc:
                logger.warning(
                    f"[InboundTransport/{source_type}] Could not backpatch archive fields "
                    f"on {vendor_invoice_id}: {exc}"
                )
        else:
            archive_status = "not_archived"
            logger.warning(
                f"[InboundTransport/{source_type}] Drive archive failed for {filename!r}: "
                f"{archive_result.get('error')}"
            )

    # ── Step 4: Audit trail ─────────────────────────────────────────────────
    await _write_inbound_audit(
        f"vendor_invoice_inbound_{source_type}_imported",
        ctx,
        data={
            **source_meta,
            "vendor_invoice_id": vendor_invoice_id,
            "display_id":        display_id,
            "archive_status":    archive_status,
        },
    )

    logger.info(
        f"[InboundTransport/{source_type}] Imported {filename!r} → {display_id} "
        f"(archive={archive_status})"
    )
    return {
        "status":            "imported",
        "vendor_invoice_id": vendor_invoice_id,
        "display_id":        display_id,
        "archive_status":    archive_status,
        "drive_file_id":     drive_file_id,
    }


# ---------------------------------------------------------------------------
# Public façade
# ---------------------------------------------------------------------------

class InboundEracunTransportService:

    # ------------------------------------------------------------------
    # Gmail adapter (Sprint A)
    # ------------------------------------------------------------------

    async def process_gmail_ubl_attachment(
        self,
        credentials,
        message_meta: dict,
        attachment_name: str,
        xml_bytes: bytes,
        ctx,
        *,
        archive: bool = True,
    ) -> dict:
        """
        Process a single UBL/XML attachment received via Gmail.

        Args:
            credentials:     Google OAuth2 credentials forwarded to Drive archive.
            message_meta:    Dict: message_id, thread_id, from, subject, received_at
            attachment_name: Filename of the attachment (e.g. "eracun.xml").
            xml_bytes:       Raw XML bytes of the UBL document.
            ctx:             ERPRequestContext.
            archive:         If False, skip Drive archive (useful in tests).

        Returns:
            {status, vendor_invoice_id, display_id, message_id, attachment_name,
             archive_status, drive_file_id, error}
        """
        message_id  = message_meta.get("message_id", "")
        thread_id   = message_meta.get("thread_id", "")
        from_addr   = message_meta.get("from", "")
        subject     = message_meta.get("subject", "")
        received_at = message_meta.get("received_at", "")

        source_meta = {
            "source_type":                    "gmail_attachment",
            "source_email_message_id":        message_id,
            "source_email_thread_id":         thread_id,
            "source_email_from":              from_addr,
            "source_email_subject":           subject,
            "source_email_received_at":       received_at,
            "source_email_attachment_name":   attachment_name,
        }

        result = await _process_inbound_ubl(
            "gmail_attachment",
            source_meta,
            xml_bytes,
            ctx,
            credentials=credentials,
            archive=archive,
            filename=attachment_name,
        )
        # Add Gmail-specific fields to response
        result["message_id"]      = message_id
        result["attachment_name"] = attachment_name
        return result

    # ------------------------------------------------------------------
    # Batch Gmail poll (Sprint A / A.1)
    # ------------------------------------------------------------------

    async def poll_gmail_inbound(
        self,
        credentials,
        ctx,
        *,
        query: str = (
            "has:attachment "
            "-label:ERP_IMPORTED "
            "-label:ERP_DUPLICATE "
            "-label:ERP_IMPORT_FAILED"
        ),
        max_messages: int = 50,
    ) -> dict:
        """
        Poll Gmail for new UBL/XML attachments and process each one.

        Idempotency (A.1): labels applied at **message** granularity, not thread.
        Label IDs resolved once per poll cycle via _LabelCache.

        Returns summary: imported, duplicate, failed, skipped, total_messages.
        """
        from tools.api_implementations.gmail_api import (
            gmail_list_messages_with_attachments,
            gmail_get_message_full,
            gmail_download_attachment,
            gmail_modify_message,
        )

        summary = {"imported": 0, "duplicate": 0, "failed": 0, "skipped": 0, "total_messages": 0}
        label_cache = _LabelCache(credentials)

        list_result = await gmail_list_messages_with_attachments(
            credentials, query=query, max_results=max_messages
        )
        messages = list_result.get("messages", [])
        summary["total_messages"] = len(messages)

        for msg_stub in messages:
            message_id = msg_stub["id"]
            thread_id  = msg_stub.get("thread_id", "")

            try:
                full = await gmail_get_message_full(credentials, message_id)
            except Exception as exc:
                logger.error(f"[InboundTransport/poll] Failed to fetch message {message_id}: {exc}")
                summary["failed"] += 1
                continue

            message_meta = {
                "message_id":  message_id,
                "thread_id":   thread_id,
                "from":        full.get("from", ""),
                "subject":     full.get("subject", ""),
                "received_at": full.get("received_at", ""),
            }

            xml_attachments = [att for att in full.get("attachments", []) if _is_ubl_attachment(att)]
            if not xml_attachments:
                summary["skipped"] += 1
                continue

            msg_outcome = "imported"
            for att in xml_attachments:
                try:
                    raw = await gmail_download_attachment(credentials, message_id, att["attachment_id"])
                except Exception as exc:
                    logger.error(
                        f"[InboundTransport/poll] Download failed for {att['filename']} "
                        f"in {message_id}: {exc}"
                    )
                    msg_outcome = "failed"
                    summary["failed"] += 1
                    continue

                result = await self.process_gmail_ubl_attachment(
                    credentials, message_meta, att["filename"], raw, ctx
                )
                status = result["status"]
                summary[status] += 1
                if status == "failed":
                    msg_outcome = "failed"
                elif status == "duplicate" and msg_outcome == "imported":
                    msg_outcome = "duplicate"

            # Apply idempotency label to the **message** (not the thread)
            label_name = _OUTCOME_TO_LABEL.get(msg_outcome, _LABEL_FAILED)
            try:
                label_id = await label_cache.get(label_name)
                await gmail_modify_message(credentials, message_id, add_label_ids=[label_id])
            except Exception as exc:
                logger.warning(
                    f"[InboundTransport/poll] Could not apply label {label_name!r} "
                    f"to message {message_id}: {exc}"
                )

        return summary

    # ------------------------------------------------------------------
    # Peppol AP inbound adapter (Sprint B)
    # ------------------------------------------------------------------

    async def process_peppol_ubl_document(
        self,
        xml_bytes: bytes,
        peppol_meta: dict,
        ctx,
        *,
        credentials=None,
        archive: bool = True,
    ) -> dict:
        """
        Process a single UBL/XML document received from a Peppol AP webhook.

        Args:
            xml_bytes:    Raw UBL XML bytes from the AP.
            peppol_meta:  Dict with AP metadata:
                            ap_submission_id, ap_document_id,
                            sender_participant_id, receiver_participant_id,
                            received_at, filename (optional)
            ctx:          ERPRequestContext derived from receiver_participant_id lookup.
            credentials:  Google OAuth2 credentials for Drive archive (optional).
            archive:      If False, skip Drive archive (useful in tests).

        Returns:
            {status, vendor_invoice_id, display_id, archive_status, drive_file_id,
             ap_submission_id, error}
        """
        ap_submission_id         = peppol_meta.get("ap_submission_id", "")
        ap_document_id           = peppol_meta.get("ap_document_id", "")
        sender_participant_id    = peppol_meta.get("sender_participant_id", "")
        receiver_participant_id  = peppol_meta.get("receiver_participant_id", "")
        received_at              = peppol_meta.get("received_at", "")
        filename                 = peppol_meta.get("filename", "") or "peppol_eracun.xml"

        source_meta = {
            "source_type":                    "peppol_inbound",
            "source_ap_submission_id":        ap_submission_id,
            "source_ap_document_id":          ap_document_id,
            "source_sender_participant_id":   sender_participant_id,
            "source_receiver_participant_id": receiver_participant_id,
            "source_received_at":             received_at,
            "source_filename":                filename,
        }

        result = await _process_inbound_ubl(
            "peppol_inbound",
            source_meta,
            xml_bytes,
            ctx,
            credentials=credentials,
            archive=archive,
            filename=filename,
        )
        result["ap_submission_id"] = ap_submission_id
        return result


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _is_ubl_attachment(att: dict) -> bool:
    """Return True if the attachment looks like a UBL/XML document."""
    filename  = (att.get("filename") or "").lower()
    mime_type = (att.get("mime_type") or "").lower()
    return (
        filename.endswith(".xml")
        or filename.endswith(".ubl")
        or "xml" in mime_type
    )


async def _archive_xml_bytes(
    credentials,
    xml_bytes: bytes,
    filename: str,
    issue_date: str = "",
) -> dict:
    """
    Upload XML bytes to Invoices_Archive/IN/YYYY/MM/.
    Forwards credentials so Drive uses the same identity as the caller.
    """
    from services.erp.drive_archive_service import archive_inbound_bytes
    return await archive_inbound_bytes(
        content=xml_bytes,
        filename=filename,
        issue_date=issue_date,
        mime_type="application/xml",
        credentials=credentials,
    )


async def _write_inbound_audit(event_type: str, ctx, data: dict) -> None:
    """Write an audit record; swallows exceptions so intake is never blocked."""
    try:
        from services.erp.base_erp_service import write_audit, get_firestore_db
        await write_audit(
            event_type, "vendor_invoice", "", "", ctx,
            data=data, db=get_firestore_db()
        )
    except Exception as exc:
        logger.warning(f"[InboundTransport] Audit write failed ({event_type}): {exc}")
