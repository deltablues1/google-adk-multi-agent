"""Turn-gated confirmation for tools whose effects leave the house.

Until now exactly three MQTT switches and proposed meeting slots were defended
by code. Sending mail, sharing a document with the world, moving stock and
deleting a calendar entry were defended by sentences in a prompt — which is the
same defence that fails whenever the model believes the user already agreed, and
the same defence that a prompt injection in a fetched web page or an email body
argues with directly.

This plugs into ADK's before_tool_callback, whose contract the loop guard in
adk_agent_factory already relies on: return a dict and the tool never runs, the
dict goes back to the model as the tool's result. So a gated call comes back as
"ask the user", in the model's own result channel, and the next real user
message is what makes it executable.

Gating is deliberately narrow. A tool that is annoying to confirm every time
gets confirmed for the cases that actually cost something: mail to an address
outside the trusted domains, sharing set to "anyone", and every write that
moves money or stock.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Optional

from services import approvals

logger = logging.getLogger(__name__)


def _trusted_email_domains() -> set:
    raw = os.getenv("APPROVAL_TRUSTED_EMAIL_DOMAINS", "")
    return {d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()}


def _recipients(args: Dict[str, Any]) -> list:
    out = []
    for field in ("to", "cc", "bcc"):
        value = args.get(field) or ""
        out.extend(part.strip() for part in str(value).replace(";", ",").split(",") if part.strip())
    return out


def _untrusted_recipients(args: Dict[str, Any]) -> list:
    trusted = _trusted_email_domains()
    if not trusted:
        # Nothing declared as trusted: confirm every send rather than silently
        # trusting everything, which is the failure this gate exists to prevent.
        return _recipients(args)
    return [
        address for address in _recipients(args)
        if address.rsplit("@", 1)[-1].lower() not in trusted
    ]


class _Rule:
    def __init__(
        self,
        when: Callable[[Dict[str, Any]], bool],
        key: Callable[[Dict[str, Any]], Dict[str, Any]],
        question: Callable[[Dict[str, Any]], str],
        lane: str = "",
    ):
        self.when = when
        self.key = key
        self.question = question
        self.lane = lane


RULES: Dict[str, _Rule] = {
    "gmail_send_message": _Rule(
        when=lambda a: bool(_untrusted_recipients(a)),
        key=lambda a: {"to": sorted(_recipients(a)), "subject": a.get("subject", "")},
        question=lambda a: (
            f"poslati mail na {', '.join(_untrusted_recipients(a))} "
            f"({a.get('subject', 'bez naslova')})"
        ),
        lane="mailer",
    ),
    "drive_share_file": _Rule(
        # Sharing with a named person is ordinary work; "anyone" is publishing.
        when=lambda a: str(a.get("type", "user")).lower() == "anyone",
        key=lambda a: {"file_id": a.get("file_id"), "type": a.get("type"), "role": a.get("role")},
        question=lambda a: f"dokument {a.get('file_id')} javno dostupan svima s linkom",
        lane="librarian",
    ),
    "calendar_delete_event": _Rule(
        when=lambda a: True,
        key=lambda a: {"event_id": a.get("event_id"), "calendar_id": a.get("calendar_id", "primary")},
        question=lambda a: f"obrisati termin {a.get('event_id')}",
        lane="secretary",
    ),
    "erp_adjust_stock": _Rule(
        when=lambda a: True,
        key=lambda a: {"product_id": a.get("product_id"), "delta": a.get("quantity_delta")},
        question=lambda a: (
            f"promijeniti zalihu artikla {a.get('product_id')} za {a.get('quantity_delta')}"
        ),
        lane="skladistar",
    ),
    "erp_create_product": _Rule(
        when=lambda a: True,
        key=lambda a: {"name": a.get("name"), "sku": a.get("sku", "")},
        question=lambda a: f"upisati novi artikl '{a.get('name')}'",
        lane="skladistar",
    ),
    "erp_record_payment": _Rule(
        when=lambda a: True,
        key=lambda a: {"invoice_id": a.get("invoice_id"), "amount": a.get("amount")},
        question=lambda a: "proknjižiti uplatu {} na račun {}".format(
            a.get("amount"),
            a.get("invoice_display_id") or a.get("invoice_id"),
        ),
        lane="tracker",
    ),
}


def gate_enabled() -> bool:
    return os.getenv("APPROVAL_GATE_ENABLED", "true").lower() in ("1", "true", "yes", "on")


def approval_before_tool(tool=None, args=None, tool_context=None, **_kwargs):
    """ADK before_tool_callback: hold a consequential call for a real user yes."""
    if not gate_enabled():
        return None

    name = getattr(tool, "name", None) or getattr(tool, "__name__", "")
    rule = RULES.get(name)
    if rule is None:
        return None

    args = args or {}
    try:
        if not rule.when(args):
            return None
        action_id = approvals.fingerprint(name, **rule.key(args))
        question = rule.question(args)
    except Exception as exc:  # a broken rule must not block the house
        logger.warning("Approval rule for '%s' failed, letting the call through: %s", name, exc)
        return None

    if approvals.redeem(action_id):
        logger.info("[APPROVAL] redeemed for %s", name)
        return None

    approvals.register(action_id, question=question, lane=rule.lane)
    logger.info("[APPROVAL] holding %s until the user confirms: %s", name, question)
    return {
        "status": "needs_confirmation",
        "action": name,
        "question": question,
        "message": (
            f"Radnja '{question}' čeka potvrdu. Pitaj korisnika, PRIČEKAJ njegov "
            "odgovor u sljedećoj poruci, pa ponovi ovaj isti poziv s istim "
            "argumentima. Ne mijenjaj argumente i ne pretpostavljaj potvrdu."
        ),
    }
