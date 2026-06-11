"""
Peppol Status Service (Sprint C2.2)
=====================================
Fetches and normalises delivery-status from an AP REST endpoint.

AP status → internal status mapping
-------------------------------------
  pending   — submitted to AP, not yet delivered to receiver's inbox
  delivered — AP confirmed inbox delivery (AS4 MDN received)
  accepted  — buyer's system sent a positive business-level acknowledgement
  rejected  — buyer's system sent a negative business-level acknowledgement
  failed    — AP could not deliver (invalid endpoint, timeout, etc.)

When PEPPOL_AP_ENDPOINT is not configured the service returns ``{"status": "pending",
"_stub": True}`` — safe for dev and sandbox environments.

Webhook verification
---------------------
``verify_webhook_request(headers, body_bytes)`` validates an incoming AP callback.
Strategy: if PEPPOL_AP_WEBHOOK_SECRET is set, require an ``X-Peppol-Signature`` HMAC-
SHA256 header (shared secret method — cheap, enough for most CTC providers).
If secret is not set, all webhooks are accepted (no verification).

Environment variables
---------------------
  PEPPOL_AP_ENDPOINT          — base URL of AP REST API (same as in dispatch service)
  PEPPOL_AP_API_KEY           — Bearer token issued by AP
  PEPPOL_AP_WEBHOOK_SECRET    — Optional HMAC-SHA256 secret for webhook verification
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal AP status → canonical status mapping
# ---------------------------------------------------------------------------

# Keys are normalised AP status strings (lowercase); values are our canonical
# internal status names.  Add more entries as AP providers return new values.
_STATUS_MAP: dict[str, str] = {
    # Generic / PEPPOL baseline
    "pending":           "pending",
    "queued":            "pending",
    "processing":        "pending",
    "submitted":         "pending",
    "delivered":         "delivered",
    "in_delivery":       "delivered",
    "acknowledged":      "accepted",
    "accepted":          "accepted",
    "approved":          "accepted",
    "rejected":          "rejected",
    "declined":          "rejected",
    "failed":            "failed",
    "error":             "failed",
    "undeliverable":     "failed",
    "expired":           "failed",
    # FINA-specific strings (guessed from Croatian AP naming conventions)
    "dostavljeno":       "delivered",
    "prihvaceno":        "accepted",
    "odbijeno":          "rejected",
    "neisporuceno":      "failed",
}

_TERMINAL_STATUSES = frozenset({"accepted", "rejected", "failed"})
_POLL_WORTHY_STATUSES = frozenset({"pending", "delivered"})


def normalise_status(raw: str) -> str:
    """
    Map a raw AP status string to one of: pending / delivered / accepted / rejected / failed.
    Unknown values fall back to "pending" (conservative — keeps polling alive).
    """
    return _STATUS_MAP.get((raw or "").lower().strip(), "pending")


def is_terminal(status: str) -> bool:
    """True when no further status changes are expected."""
    return status in _TERMINAL_STATUSES


def needs_poll(status: str) -> bool:
    """True when the document is still in-flight and polling should continue."""
    return status in _POLL_WORTHY_STATUSES


# ---------------------------------------------------------------------------
# AP status query
# ---------------------------------------------------------------------------

async def fetch_submission_status(
    submission_id: str,
    *,
    company_id: Optional[str] = None,
) -> dict:
    """
    Query the AP for the current delivery status of a submission.

    Returns::

        {
            "submission_id": "<id>",
            "raw_status":    "<string from AP>",
            "status":        "pending|delivered|accepted|rejected|failed",
            "is_terminal":   True/False,
            "checked_at":    "<ISO timestamp>",
            "_stub":         True   # only in stub mode
        }

    Raises nothing — always returns a dict.  Callers should check ``"error"`` key.
    """
    ap_endpoint = os.environ.get("PEPPOL_AP_ENDPOINT", "").strip()
    checked_at = datetime.now(timezone.utc).isoformat()

    if not ap_endpoint:
        logger.debug(
            f"[PeppolStatus] PEPPOL_AP_ENDPOINT not set — stub mode for {submission_id}"
        )
        return {
            "submission_id": submission_id,
            "raw_status":    "pending",
            "status":        "pending",
            "is_terminal":   False,
            "checked_at":    checked_at,
            "_stub":         True,
        }

    # Build status URL.  Most AP providers follow /submissions/{id}/status
    # or /status?submissionId=<id>.  We try the path-based form first and
    # let the AP correct us if needed.
    status_url = f"{ap_endpoint.rstrip('/')}/submissions/{submission_id}/status"
    api_key = os.environ.get("PEPPOL_AP_API_KEY", "").strip()
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(status_url, headers=headers)

        if resp.status_code == 200:
            try:
                body = resp.json()
            except Exception:
                body = {}
            raw = (
                body.get("status")
                or body.get("deliveryStatus")
                or body.get("state")
                or "pending"
            )
            canon = normalise_status(raw)
            logger.info(
                f"[PeppolStatus] {submission_id}: AP={raw!r} → internal={canon!r}"
            )
            return {
                "submission_id": submission_id,
                "raw_status":    raw,
                "status":        canon,
                "is_terminal":   is_terminal(canon),
                "checked_at":    checked_at,
            }

        elif resp.status_code == 404:
            logger.warning(f"[PeppolStatus] {submission_id} not found on AP (404)")
            return {
                "submission_id": submission_id,
                "raw_status":    "not_found",
                "status":        "failed",
                "is_terminal":   True,
                "checked_at":    checked_at,
                "error":         "Submission not found on AP",
            }
        else:
            logger.error(
                f"[PeppolStatus] AP returned HTTP {resp.status_code} for {submission_id}"
            )
            return {
                "submission_id": submission_id,
                "raw_status":    f"http_{resp.status_code}",
                "status":        "pending",   # conservative — keep polling
                "is_terminal":   False,
                "checked_at":    checked_at,
                "error":         f"AP HTTP {resp.status_code}",
            }

    except Exception as exc:
        logger.error(f"[PeppolStatus] fetch failed for {submission_id}: {exc}")
        return {
            "submission_id": submission_id,
            "raw_status":    "error",
            "status":        "pending",   # conservative
            "is_terminal":   False,
            "checked_at":    checked_at,
            "error":         str(exc),
        }


# ---------------------------------------------------------------------------
# Webhook verification
# ---------------------------------------------------------------------------

def verify_webhook_request(headers: dict, body_bytes: bytes) -> bool:
    """
    Verify an inbound AP webhook request.

    If PEPPOL_AP_WEBHOOK_SECRET is set: validate ``X-Peppol-Signature`` HMAC-SHA256.
    If not set:
      - development/sandbox: accept all (log debug)
      - production/prod/staging: **reject** (return False, log error) — fail-closed.

    Returns True if the request is considered authentic.
    """
    secret = os.environ.get("PEPPOL_AP_WEBHOOK_SECRET", "").strip()
    if not secret:
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env in ("production", "prod", "staging"):
            logger.error(
                "[PeppolStatus/webhook] SECURITY: PEPPOL_AP_WEBHOOK_SECRET is not set in "
                f"ENVIRONMENT={env!r}. Rejecting webhook — set PEPPOL_AP_WEBHOOK_SECRET."
            )
            return False  # fail-closed in production/staging
        logger.debug("[PeppolStatus/webhook] No PEPPOL_AP_WEBHOOK_SECRET — accepting without verification (dev mode)")
        return True

    sig_header = (
        headers.get("X-Peppol-Signature")
        or headers.get("x-peppol-signature")
        or ""
    ).strip()
    if not sig_header:
        logger.warning("[PeppolStatus/webhook] Missing X-Peppol-Signature header — rejecting")
        return False

    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    # Constant-time comparison
    if not hmac.compare_digest(expected, sig_header.lower()):
        logger.warning("[PeppolStatus/webhook] Signature mismatch — rejecting")
        return False

    return True


# ---------------------------------------------------------------------------
# Webhook payload parser
# ---------------------------------------------------------------------------

def parse_webhook_payload(body: dict) -> dict:
    """
    Extract canonical status information from an AP webhook payload.

    Returns::

        {
            "submission_id":           "<string>",
            "status":                  "pending|delivered|accepted|rejected|failed",
            "raw_status":              "<original string>",
            "buyer_message":           "<optional rejection reason>",
            "receiver_participant_id": "<buyer Peppol ID, if present>",
            "sender_participant_id":   "<seller Peppol ID, if present>",
        }

    The ``receiver_participant_id`` and ``sender_participant_id`` fields are used
    as disambiguation hints in ``get_by_submission_id_global()`` when an AP recycles
    submission IDs.

    Returns {} if the payload cannot be parsed.
    """
    if not body or not isinstance(body, dict):
        return {}

    submission_id = (
        body.get("submissionId")
        or body.get("submission_id")
        or body.get("id")
        or ""
    )
    if not submission_id:
        logger.warning("[PeppolStatus/webhook] Could not extract submission_id from payload")
        return {}

    raw = (
        body.get("status")
        or body.get("deliveryStatus")
        or body.get("state")
        or ""
    )
    canon = normalise_status(raw)

    buyer_message = (
        body.get("rejectionReason")
        or body.get("rejection_reason")
        or body.get("message")
        or ""
    )

    # Participant IDs for disambiguation (varies by AP provider)
    receiver = (
        body.get("receiverId")
        or body.get("receiver_id")
        or body.get("receiverParticipantId")
        or body.get("receiver")
        or ""
    )
    sender = (
        body.get("senderId")
        or body.get("sender_id")
        or body.get("senderParticipantId")
        or body.get("sender")
        or ""
    )

    return {
        "submission_id":           submission_id,
        "status":                  canon,
        "raw_status":              raw,
        "buyer_message":           buyer_message,
        "receiver_participant_id": receiver,
        "sender_participant_id":   sender,
    }
