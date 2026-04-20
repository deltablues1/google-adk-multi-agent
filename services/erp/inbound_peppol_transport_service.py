"""
Inbound Peppol Transport Service  (Sprint Inbound B)
=====================================================
Source adapter for Peppol AP inbound e-račun documents.

Responsibilities (this service only):
  - AP webhook signature verification
  - Payload parsing and normalisation (submissionId, documentId, participants, XML bytes)
  - Company resolution from receiver_participant_id
  - Forwarding to InboundEracunTransportService.process_peppol_ubl_document()

What this service does NOT do:
  - UBL parsing  → ubl_inbound_parser
  - Dedup        → vendor_invoice_service / vendor_invoice_repo
  - Drive archive → drive_archive_service
  - Audit        → inbound_eracun_transport_service._write_inbound_audit

Company resolution
------------------
The AP posts to a single endpoint without per-tenant routing.  We find the
correct company by matching receiver_participant_id against
company_settings.peppol_participant_id (same field used on the outbound side).

If no company is found, the webhook returns 404 (AP should not retry unknown
participants).  Multiple companies sharing the same participant ID cannot happen
since Sprint D0 — CompanyService enforces uniqueness at write time.  Any legacy
duplicates are handled by first-match-wins + warning log; use
``scripts/audit_peppol_participant_ids.py`` to identify and fix them.

Webhook signature
-----------------
Re-uses the same PEPPOL_AP_WEBHOOK_SECRET / verify_webhook_request() from
peppol_status_service.  If a separate secret is needed for inbound, set
PEPPOL_AP_INBOUND_WEBHOOK_SECRET; falls back to PEPPOL_AP_WEBHOOK_SECRET.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Header used by AP for inbound document webhooks
_SIG_HEADER = "X-Peppol-Signature"


def verify_inbound_webhook(headers: dict, body_bytes: bytes) -> bool:
    """
    Verify signature on an inbound AP document webhook.

    Uses PEPPOL_AP_INBOUND_WEBHOOK_SECRET if set, otherwise falls back to
    PEPPOL_AP_WEBHOOK_SECRET.
    If neither secret is set:
      - development/sandbox: accept all (log debug)
      - production/prod/staging: **reject** (return False, log error) — fail-closed.
    """
    import hashlib
    import hmac

    secret = (
        os.environ.get("PEPPOL_AP_INBOUND_WEBHOOK_SECRET", "").strip()
        or os.environ.get("PEPPOL_AP_WEBHOOK_SECRET", "").strip()
    )
    if not secret:
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env in ("production", "prod", "staging"):
            logger.error(
                "[PeppolInbound] SECURITY: no PEPPOL_AP_INBOUND_WEBHOOK_SECRET set "
                f"in ENVIRONMENT={env!r}. Rejecting webhook — set PEPPOL_AP_INBOUND_WEBHOOK_SECRET."
            )
            return False  # fail-closed in production/staging
        logger.debug("[PeppolInbound] No inbound webhook secret — accepting (dev mode)")
        return True

    sig_header = (
        headers.get(_SIG_HEADER)
        or headers.get(_SIG_HEADER.lower())
        or ""
    ).strip()
    if not sig_header:
        logger.warning("[PeppolInbound] Missing X-Peppol-Signature — rejecting")
        return False

    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_header.lower()):
        logger.warning("[PeppolInbound] Signature mismatch — rejecting")
        return False

    return True


def parse_inbound_payload(body: dict) -> dict:
    """
    Normalise an AP inbound document webhook payload.

    AP providers use various field names; we normalise to a canonical dict.

    Returns::

        {
            "ap_submission_id":        "<string>",   # required
            "ap_document_id":          "<string>",   # optional
            "sender_participant_id":   "<string>",   # e.g. "0190:12345678901"
            "receiver_participant_id": "<string>",   # used for company resolution
            "xml_url":                 "<string>",   # if AP sends URL instead of bytes
            "xml_base64":              "<string>",   # if AP sends encoded bytes
            "received_at":             "<ISO string>",
            "filename":                "<string>",
        }

    Returns {} if mandatory fields are missing.
    """
    if not body or not isinstance(body, dict):
        return {}

    submission_id = (
        body.get("submissionId")
        or body.get("submission_id")
        or body.get("documentSubmissionId")
        or ""
    )
    if not submission_id:
        logger.warning("[PeppolInbound] Could not extract submission_id from payload")
        return {}

    document_id = (
        body.get("documentId")
        or body.get("document_id")
        or body.get("invoiceId")
        or ""
    )

    sender = (
        body.get("senderId")
        or body.get("sender_id")
        or body.get("senderParticipantId")
        or body.get("sender")
        or ""
    )
    receiver = (
        body.get("receiverId")
        or body.get("receiver_id")
        or body.get("receiverParticipantId")
        or body.get("receiver")
        or ""
    )

    xml_url    = body.get("documentUrl") or body.get("document_url") or body.get("xmlUrl") or ""
    xml_base64 = body.get("documentBase64") or body.get("document_base64") or body.get("xmlContent") or ""
    filename   = body.get("filename") or body.get("fileName") or ""
    received_at = (
        body.get("receivedAt") or body.get("received_at")
        or datetime.now(timezone.utc).isoformat()
    )

    return {
        "ap_submission_id":        submission_id,
        "ap_document_id":          document_id,
        "sender_participant_id":   sender,
        "receiver_participant_id": receiver,
        "xml_url":                 xml_url,
        "xml_base64":              xml_base64,
        "received_at":             received_at,
        "filename":                filename,
    }


async def resolve_company_from_participant_id(participant_id: str) -> Optional[str]:
    """
    Find the company_id whose Peppol participant ID matches the receiver.

    Queries company_settings where peppol_participant_id == participant_id.
    Returns the first matching company_id, or None if no match.
    """
    if not participant_id:
        return None

    from services.erp.base_erp_service import get_firestore_db
    from google.cloud.firestore_v1.base_query import FieldFilter

    db = get_firestore_db()
    try:
        snaps = [
            snap async for snap in
            db.collection("company_settings")
            .where(filter=FieldFilter("peppol_participant_id", "==", participant_id))
            .limit(2)
            .stream()
        ]
    except Exception as exc:
        logger.error(f"[PeppolInbound] Company lookup failed for {participant_id}: {exc}")
        return None

    if not snaps:
        logger.warning(f"[PeppolInbound] No company found for participant_id={participant_id!r}")
        return None

    if len(snaps) > 1:
        company_ids = [s.to_dict().get("company_id", s.id) for s in snaps]
        logger.warning(
            f"[PeppolInbound] Multiple companies share participant_id={participant_id!r}: "
            f"{company_ids}. Using first."
        )

    doc = snaps[0].to_dict() or {}
    return doc.get("company_id") or snaps[0].id


async def fetch_xml_bytes(parsed: dict) -> Optional[bytes]:
    """
    Retrieve UBL XML bytes from the AP payload.

    Priority:
      1. xml_base64  — AP encoded the document inline
      2. xml_url     — AP gave a URL; we fetch it
      3. None        — payload has no document (AP may send a separate delivery notification)
    """
    import base64

    if parsed.get("xml_base64"):
        try:
            return base64.b64decode(parsed["xml_base64"])
        except Exception as exc:
            logger.error(f"[PeppolInbound] Failed to decode xml_base64: {exc}")
            return None

    if parsed.get("xml_url"):
        try:
            import httpx, os
            api_key = os.environ.get("PEPPOL_AP_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(parsed["xml_url"], headers=headers)
            if resp.status_code == 200:
                return resp.content
            logger.error(f"[PeppolInbound] AP document URL returned {resp.status_code}")
            return None
        except Exception as exc:
            logger.error(f"[PeppolInbound] Failed to fetch xml_url: {exc}")
            return None

    return None


def _make_system_ctx(company_id: str):
    """Return a minimal owner-level context for system-to-system inbound operations."""
    from uuid import uuid4
    from services.erp.request_context import ERPRequestContext
    return ERPRequestContext(
        user_id="peppol-ap-inbound",
        company_id=company_id,
        role="owner",
        grants=set(),
        denies=set(),
        request_id=str(uuid4()),
    )


class InboundPeppolTransportService:
    """
    Handle a single inbound Peppol document from an AP webhook.

    Typical call chain:
        payload = parse_inbound_payload(body)
        company_id = await resolve_company_from_participant_id(payload["receiver_participant_id"])
        ctx = _make_system_ctx(company_id)
        xml_bytes = await fetch_xml_bytes(payload)
        result = await InboundPeppolTransportService().process(payload, xml_bytes, ctx)
    """

    async def process(
        self,
        parsed: dict,
        xml_bytes: bytes,
        ctx,
        *,
        credentials=None,
        archive: bool = True,
    ) -> dict:
        """
        Process a validated, parsed Peppol inbound document.

        Args:
            parsed:      Output of parse_inbound_payload().
            xml_bytes:   Raw UBL XML bytes (from fetch_xml_bytes or inline).
            ctx:         ERPRequestContext for the receiver company.
            credentials: OAuth2 credentials for Drive archive (optional).
            archive:     If False, skip Drive archive.

        Returns:
            {status, vendor_invoice_id, display_id, archive_status,
             drive_file_id, ap_submission_id, error}
        """
        from services.erp.inbound_eracun_transport_service import InboundEracunTransportService

        peppol_meta = {
            "ap_submission_id":        parsed.get("ap_submission_id", ""),
            "ap_document_id":          parsed.get("ap_document_id", ""),
            "sender_participant_id":   parsed.get("sender_participant_id", ""),
            "receiver_participant_id": parsed.get("receiver_participant_id", ""),
            "received_at":             parsed.get("received_at", ""),
            "filename":                parsed.get("filename", "") or "peppol_eracun.xml",
        }

        return await InboundEracunTransportService().process_peppol_ubl_document(
            xml_bytes=xml_bytes,
            peppol_meta=peppol_meta,
            ctx=ctx,
            credentials=credentials,
            archive=archive,
        )
