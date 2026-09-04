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

from services import approvals, known_recipients

logger = logging.getLogger(__name__)


def _recipients(args: Dict[str, Any]) -> list:
    out = []
    for field in ("to", "cc", "bcc"):
        value = args.get(field) or ""
        out.extend(part.strip() for part in str(value).replace(";", ",").split(",") if part.strip())
    return out


def _unknown_recipients(args: Dict[str, Any]) -> list:
    """Addresses the house has never written to and does not have on file.

    Filtering by domain was the first attempt and it asked about every client,
    which is most of the real mail — friction on the normal case and no extra
    safety, since a plausible domain is the easy half of a redirect to forge.
    A recipient nobody has ever written to is the actual signal."""
    return [a for a in _recipients(args) if not known_recipients.is_known(a)]


class _Rule:
    def __init__(
        self,
        when: Callable[[Dict[str, Any]], bool],
        key: Callable[[Dict[str, Any]], Dict[str, Any]],
        question: Callable[[Dict[str, Any]], str],
        lane: str = "",
        on_confirmed: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ):
        self.when = when
        self.key = key
        self.question = question
        self.lane = lane
        self.on_confirmed = on_confirmed


RULES: Dict[str, _Rule] = {
    "gmail_send_message": _Rule(
        when=lambda a: bool(_unknown_recipients(a)),
        key=lambda a: {"to": sorted(_recipients(a)), "subject": a.get("subject", "")},
        question=lambda a: (
            f"poslati mail na {', '.join(_unknown_recipients(a))} "
            f"({a.get('subject', 'bez naslova')})"
        ),
        lane="mailer",
        # Confirmed once is known from then on, so the gate narrows to genuinely
        # new addresses instead of nagging about the same client every time.
        on_confirmed=lambda a: known_recipients.remember(_recipients(a)),
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


# How many times one action has already been held inside the current run.
# Asking the user is a thing you do once: on 2026-09-04 a model re-issued the
# same held call five times in a single turn, each a billed round-trip that
# could not possibly succeed, because nothing said "you already asked".
_holds_this_run: Dict[tuple, int] = {}


def _record_hold(tool_context, action_id: str) -> int:
    # Keyed on the user's session, not the ADK invocation id: the orchestrator
    # calls a worker as a sub-agent, and each of those calls is its own
    # invocation. Keying on invocation counted every retry as "attempt 1",
    # which is exactly the loop this counter exists to interrupt.
    key = (approvals.current_session(), action_id)
    count = _holds_this_run.get(key, 0) + 1
    _holds_this_run[key] = count
    if len(_holds_this_run) > 2048:  # bounded memory
        _holds_this_run.clear()
    return count


def _clear_holds(tool_context, action_id: str) -> None:
    _holds_this_run.pop((approvals.current_session(), action_id), None)


def reset_holds(session_id: Optional[str] = None) -> None:
    """A new user message starts the count over: asking once per turn is fine."""
    session = session_id or approvals.current_session()
    for key in [k for k in _holds_this_run if k[0] == session]:
        del _holds_this_run[key]


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
        question = rule.question(args)
    except Exception as exc:  # a broken rule must not block the house
        logger.warning("Approval rule for '%s' failed, letting the call through: %s", name, exc)
        return None

    if approvals.is_autonomous():
        # Nobody is listening. Registering here would leave a pending approval
        # that a later "da" in some other channel could arm, and returning
        # "ask the user" would send the model round the loop guard for nothing.
        logger.warning("[APPROVAL] refusing %s in an autonomous run: %s", name, question)
        return {
            "status": "not_permitted",
            "action": name,
            "error": "AUTONOMOUS_RUN_NEEDS_CONFIRMATION",
            "message": (
                f"Radnja '{question}' traži potvrdu korisnika, a ovo je automatski "
                "posao bez korisnika. Nemoj ponavljati poziv — javi u odgovoru da "
                "radnja nije izvršena i zašto."
            ),
        }

    try:
        action_id = approvals.fingerprint(name, **rule.key(args))
    except Exception as exc:  # a broken rule must not block the house
        logger.warning("Approval key for '%s' failed, letting the call through: %s", name, exc)
        return None

    if approvals.redeem(action_id):
        logger.info("[APPROVAL] redeemed for %s", name)
        _clear_holds(tool_context, action_id)
        if rule.on_confirmed is not None:
            try:
                rule.on_confirmed(args)
            except Exception as exc:
                logger.warning("Post-approval hook for '%s' failed: %s", name, exc)
        return None

    approvals.register(action_id, question=question, lane=rule.lane)
    holds = _record_hold(tool_context, action_id)
    logger.info(
        "[APPROVAL] holding %s until the user confirms (attempt %d): %s",
        name, holds, question,
    )

    if holds > 1:
        # Repeating the call cannot help: the approval only arms on the user's
        # NEXT message, which cannot arrive while this turn is still running.
        return {
            "status": "needs_confirmation",
            "action": name,
            "question": question,
            "message": (
                f"Već si u ovom turnusu {holds} puta pokušao '{question}'. "
                "Ponavljanje NE MOŽE uspjeti — odobrenje se aktivira tek kad "
                "korisnik odgovori, a on ne može odgovoriti dok ti radiš. "
                "PRESTANI zvati ovaj alat, postavi korisniku pitanje i završi "
                "odgovor."
            ),
        }

    return {
        "status": "needs_confirmation",
        "action": name,
        "question": question,
        "message": (
            f"Radnja '{question}' čeka potvrdu korisnika i NIJE izvršena. "
            "Prenesi to pitanje korisniku i stani. Kad korisnik potvrdi, mora "
            "se ponoviti CIJELI zahtjev s identičnim argumentima — sama riječ "
            "'da' proslijeđena agentu ne znači ništa, jer agent nastaje iznova "
            "i ne pamti što je pitao. Ne mijenjaj argumente i ne pretpostavljaj "
            "potvrdu."
        ),
    }
