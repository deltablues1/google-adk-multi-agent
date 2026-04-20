"""
Outbound B2B Dispatch Service
==============================
Adapter layer for sending outgoing B2B invoices via different delivery methods.

Supported adapters
------------------
  manual   — no transport; records intent only (buyer picks up manually or via portal)
  email    — sends UBL XML as attachment via Gmail API (OAuth2 credentials)
  peppol   — Peppol AS4 via AP REST endpoint (configured by PEPPOL_AP_ENDPOINT env var)
             Falls back to stub mode when PEPPOL_AP_ENDPOINT is not set.

Peppol AP configuration (environment variables)
------------------------------------------------
  PEPPOL_AP_ENDPOINT   — required for real send; REST URL of the AP
                         e.g. https://ap.fina.hr/api/v1/send
  PEPPOL_AP_API_KEY    — Bearer token / API key issued by the AP
  PEPPOL_AP_SENDER_ID  — Your Peppol sender ID (scheme:identifier)
                         Falls back to company_settings.peppol_participant_id

Every adapter returns a uniform result dict:

    {
        "ok": True,
        "external_submission_id": "<string or None>",
        "sent_at": "<ISO timestamp>",
        "method": "email|peppol|manual",
    }
    or
    {
        "ok": False,
        "error": "<message>",
        "method": "email|peppol|manual",
    }

Usage (from OutboundB2BService.send())
--------------------------------------
    from .outbound_dispatch_service import dispatch_invoice
    result = await dispatch_invoice(doc, delivery_method, delivery_target, delivery_ref)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def dispatch_invoice(
    invoice_doc: dict,
    delivery_method: str,
    delivery_target: str,
    delivery_ref: str = "",
) -> dict:
    """
    Dispatch an invoice document to the buyer via the specified delivery method.

    Args:
        invoice_doc:      Full Firestore invoice doc (must have ubl_xml, display_id, etc.)
        delivery_method:  "manual" | "email" | "peppol"
        delivery_target:  Email address / Peppol participant ID / empty for manual
        delivery_ref:     Optional AP confirmation ref or note

    Returns:
        {"ok": True/False, "external_submission_id": ..., "sent_at": ..., "method": ...}
    """
    method = delivery_method.lower()
    if method == "manual":
        return await _dispatch_manual(invoice_doc, delivery_target, delivery_ref)
    elif method == "email":
        return await _dispatch_email(invoice_doc, delivery_target, delivery_ref)
    elif method == "peppol":
        return await _dispatch_peppol(invoice_doc, delivery_target, delivery_ref)
    else:
        return {"ok": False, "error": f"Nepoznata delivery_method: {method!r}", "method": method}


# ---------------------------------------------------------------------------
# Manual adapter
# ---------------------------------------------------------------------------

async def _dispatch_manual(invoice_doc: dict, target: str, ref: str) -> dict:
    """
    Manual delivery — records the intent, no actual transport.
    Used for portals, courier, CD-ROM, or any out-of-band delivery.
    """
    display_id = invoice_doc.get("display_id", invoice_doc.get("invoice_id", "?"))
    logger.info(
        f"[Dispatch/manual] Invoice {display_id} marked as manually dispatched. "
        f"target={target!r} ref={ref!r}"
    )
    return {
        "ok": True,
        "external_submission_id": ref or None,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "method": "manual",
    }


# ---------------------------------------------------------------------------
# Email adapter
# ---------------------------------------------------------------------------

async def _dispatch_email(invoice_doc: dict, to_address: str, ref: str) -> dict:
    """
    Send UBL XML as an email attachment via Gmail API.

    The email body is a standard eRačun cover letter in Croatian.
    Subject: eRačun {display_id} — {seller_name}
    Attachment: {display_id}.xml (UBL XML inline content)

    Requires valid Gmail OAuth2 credentials in ADC.
    """
    if not to_address or "@" not in to_address:
        return {
            "ok": False,
            "error": f"Neispravan email: {to_address!r}",
            "method": "email",
        }

    ubl_xml: str = invoice_doc.get("ubl_xml") or ""
    if not ubl_xml:
        return {"ok": False, "error": "UBL XML nije generiran — pozovite /issue prije slanja.", "method": "email"}

    display_id   = invoice_doc.get("display_id", invoice_doc.get("invoice_id", "?"))
    seller_name  = invoice_doc.get("seller_name", "")
    customer_name = invoice_doc.get("customer_name", "")
    issue_date   = str(invoice_doc.get("issue_date", ""))[:10]
    total_gross  = invoice_doc.get("total_gross", 0.0)
    currency     = invoice_doc.get("currency", "EUR")

    subject = f"eRačun {display_id} — {seller_name}"
    body = (
        f"Poštovani,\n\n"
        f"U prilogu se nalazi eRačun {display_id} od {issue_date}.\n\n"
        f"Iznos: {total_gross:.2f} {currency}\n"
        f"Izdavatelj: {seller_name}\n"
        f"Primatelj: {customer_name}\n\n"
        f"eRačun je generiran sukladno HR-FISK 2.0 / UBL 2.1 / EN 16931 standardu "
        f"i Peppol BIS Billing 3.0 profilu.\n\n"
        f"S poštovanjem,\n{seller_name}\n"
    )

    try:
        import tempfile, os, asyncio
        from tools.google_api_client import create_api_client_auto
        from tools.api_implementations.gmail_api import gmail_send_message

        credentials = create_api_client_auto().credentials

        # Write UBL XML to a temp file so gmail_send_message can attach it
        xml_filename = f"{display_id}.xml"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", prefix=f"{display_id}_",
            encoding="utf-8", delete=False
        ) as tmp:
            tmp.write(ubl_xml)
            tmp_path = tmp.name

        try:
            result = await gmail_send_message(
                credentials=credentials,
                to=to_address,
                subject=subject,
                body=body,
                attachment_path=tmp_path,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        logger.info(f"[Dispatch/email] Invoice {display_id} sent to {to_address} — Gmail id={result.get('id')}")
        return {
            "ok": True,
            "external_submission_id": result.get("id"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "method": "email",
        }

    except Exception as exc:
        logger.error(f"[Dispatch/email] Failed to send {display_id} to {to_address}: {exc}")
        return {"ok": False, "error": str(exc), "method": "email"}


# ---------------------------------------------------------------------------
# Peppol adapter (Sprint C2.1 — real AP via REST; stub fallback when unconfigured)
# ---------------------------------------------------------------------------

#: Peppol BIS Billing 3.0 document type identifier (UBL Invoice)
_PEPPOL_DOC_TYPE = (
    "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    "::Invoice"
    "##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
    "::2.1"
)
#: Peppol BIS Billing 3.0 process identifier
_PEPPOL_PROCESS = "urn:fdc:peppol.eu:2017:poacc:billing:3.0"


async def _dispatch_peppol(invoice_doc: dict, participant_id: str, ref: str) -> dict:
    """
    Peppol AS4 delivery via AP REST endpoint.

    When PEPPOL_AP_ENDPOINT is set, POSTs the UBL XML to the AP and returns
    the real external_submission_id from the AP response.

    When PEPPOL_AP_ENDPOINT is not set, runs in stub mode and returns a
    synthetic submission ID with ``_stub: True`` — safe for development.

    AP is called with:
      POST <PEPPOL_AP_ENDPOINT>
      Content-Type: application/xml
      Authorization: Bearer <PEPPOL_AP_API_KEY>
      ?sender=<PEPPOL_AP_SENDER_ID>&receiver=<participant_id>
        &documentType=<BIS3>&processType=<BIS3-PROC>

    Expected AP response (any of):
      {"submission_id": "..."} | {"submissionId": "..."} | {"id": "..."}
    or Location header.
    """
    import os

    display_id = invoice_doc.get("display_id", invoice_doc.get("invoice_id", "?"))

    if not participant_id:
        return {
            "ok": False,
            "error": "delivery_target (Peppol participant ID) je obavezan za peppol dostavu.",
            "method": "peppol",
        }

    ubl_xml = invoice_doc.get("ubl_xml") or ""
    if not ubl_xml:
        return {"ok": False, "error": "UBL XML nije generiran.", "method": "peppol"}

    ap_endpoint = os.environ.get("PEPPOL_AP_ENDPOINT", "").strip()

    # ── Stub mode ────────────────────────────────────────────────────────────
    if not ap_endpoint:
        import hashlib
        synthetic_id = "PEPPOL-STUB-" + hashlib.sha1(
            f"{display_id}:{participant_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12].upper()
        logger.warning(
            f"[Dispatch/peppol] PEPPOL_AP_ENDPOINT not configured — stub mode. "
            f"Invoice {display_id} NOT actually sent. submission_id={synthetic_id}"
        )
        return {
            "ok": True,
            "external_submission_id": synthetic_id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "method": "peppol",
            "_stub": True,
        }

    # ── Real AP call ─────────────────────────────────────────────────────────
    ap_api_key  = os.environ.get("PEPPOL_AP_API_KEY", "").strip()
    sender_id   = os.environ.get("PEPPOL_AP_SENDER_ID", "").strip()

    # Fallback: derive sender from company_settings if env var not set
    if not sender_id:
        company_id = invoice_doc.get("company_id")
        if company_id:
            try:
                from services.erp.company_service import get_company_settings
                cs = await get_company_settings(company_id) or {}
                peppol_id = cs.get("peppol_participant_id", "")
                scheme    = cs.get("peppol_scheme", "0190")
                if peppol_id:
                    sender_id = peppol_id  # already scheme:id if stored that way
                elif cs.get("oib"):
                    sender_id = f"{scheme}:{cs['oib']}"
            except Exception as exc:
                logger.warning(f"[Dispatch/peppol] company_settings lookup failed: {exc}")

    headers = {"Content-Type": "application/xml", "Accept": "application/json"}
    if ap_api_key:
        headers["Authorization"] = f"Bearer {ap_api_key}"

    params = {
        "receiver":     participant_id,
        "documentType": _PEPPOL_DOC_TYPE,
        "processType":  _PEPPOL_PROCESS,
    }
    if sender_id:
        params["sender"] = sender_id

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                ap_endpoint,
                content=ubl_xml.encode("utf-8"),
                headers=headers,
                params=params,
            )

        if resp.status_code in (200, 201, 202):
            submission_id: Optional[str] = None
            try:
                body = resp.json()
                submission_id = (
                    body.get("submission_id")
                    or body.get("submissionId")
                    or body.get("id")
                )
            except Exception:
                pass
            if not submission_id:
                loc = resp.headers.get("Location", "")
                submission_id = loc.rsplit("/", 1)[-1] if loc else None

            logger.info(
                f"[Dispatch/peppol] Invoice {display_id} accepted by AP "
                f"for delivery to {participant_id!r}. submission_id={submission_id}"
            )
            return {
                "ok": True,
                "external_submission_id": submission_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "method": "peppol",
            }
        else:
            error_body = resp.text[:500]
            logger.error(
                f"[Dispatch/peppol] AP returned HTTP {resp.status_code} "
                f"for {display_id}: {error_body}"
            )
            return {
                "ok": False,
                "error": f"AP HTTP {resp.status_code}: {error_body}",
                "method": "peppol",
            }

    except Exception as exc:
        logger.error(f"[Dispatch/peppol] Failed to send {display_id} to AP: {exc}")
        return {"ok": False, "error": str(exc), "method": "peppol"}
