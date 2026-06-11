"""
Outbound B2B Delivery Capability Model (Faza 2D)
=================================================
Defines what each delivery adapter can and cannot do.

Consumers
---------
  - outbound_b2b_service.send()       — stores snapshot on doc at send time
  - outbound_b2b_service.list_pending_ack() — filters by ack_expected
  - erp_routes.py GET /outbound-b2b/capabilities — UI discovery

Adding a new adapter
--------------------
  1. Add entry to ADAPTER_CAPABILITIES.
  2. Implement the adapter in outbound_dispatch_service.py.
  3. No other changes needed — capability queries go through get_capabilities().
"""

from __future__ import annotations

from typing import Dict, Any

# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

ADAPTER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "manual": {
        "can_dispatch":    True,
        "auto_ack":        False,  # operator confirms manually; no transport receipt
        "polling":         False,  # nothing to poll
        "ack_expected":    False,  # do NOT include in pending-ack monitoring
        "description":     "Ručna predaja (fax, osobno, pošta, portal upload)",
    },
    "email": {
        "can_dispatch":    True,
        "auto_ack":        False,  # delivery receipt ≠ buyer acceptance
        "polling":         False,  # no email delivery API to poll
        "ack_expected":    True,   # buyer should explicitly accept; monitor for followup
        "description":     "E-mail dostava s UBL XML prilogom (Gmail API)",
    },
    "peppol": {
        "can_dispatch":    True,
        "auto_ack":        True,   # real AP provides AS4 delivery callback
        "polling":         True,   # AS4 status polling supported (stub in Faza 2B/2F)
        "ack_expected":    True,   # buyer acknowledgement expected
        "description":     "Peppol BIS Billing 3.0 / AS4 (stub — zamjena planirana u Fazi 2F)",
    },
}

# Fallback for unknown methods (treat as manual — safest default)
_DEFAULT_CAPABILITIES = ADAPTER_CAPABILITIES["manual"].copy()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_capabilities(method: str) -> Dict[str, Any]:
    """
    Return the capability dict for a delivery method.
    Falls back to manual if method is unknown.
    """
    return ADAPTER_CAPABILITIES.get((method or "").lower(), _DEFAULT_CAPABILITIES)


def ack_expected(method: str) -> bool:
    """True if buyer acknowledgement is expected for this delivery method."""
    return bool(get_capabilities(method).get("ack_expected", False))


def polling_supported(method: str) -> bool:
    """True if this adapter supports external status polling."""
    return bool(get_capabilities(method).get("polling", False))


def can_dispatch(method: str) -> bool:
    """True if this method can actually dispatch a document."""
    return bool(get_capabilities(method).get("can_dispatch", False))
