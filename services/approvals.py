"""One approval gate for every action with consequences.

The prompt is not a gate. "Wait for the user to confirm" is an instruction the
model can talk itself out of, and a model that believes the user already said
yes will act in the same turn it asked. Two hand-rolled gates grew out of that
realisation independently — one for MQTT switches, one for proposed meeting
slots — with different TTLs, different session semantics and one of them no
session scoping at all, so a turn in one conversation armed a pending action
from another. This is that mechanism, once.

The property that matters: an approval becomes redeemable only when a *new user
message* arrives. Proposing and executing inside one model turn is therefore
impossible, whatever the model believes. Redeeming consumes the approval, so a
repeated "da" — an echo, a re-transcription — cannot execute twice.

Two arming modes, because the two callers ask different questions:

- ``affirmative`` — "Ugasiti bojler?" needs an actual yes, and only the most
  recently asked question is armed. One "da" must not authorise a queue.
- ``next_turn``   — "Which of these three slots?" is answered by choosing, not
  by saying yes, so any next turn arms every slot proposed together.

State is per-process and in memory: one Pi, one worker. A restart drops pending
approvals, which fails safe (the action does not happen). Anything needing to
survive that belongs in services/hitl_firestore_service.py.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

AFFIRMATIVE = "affirmative"
NEXT_TURN = "next_turn"

DEFAULT_TTL_SECONDS = 120.0
# Choosing between proposed meeting slots is a slower conversation than
# confirming a switch, and the old calendar gate used 600s.
PROPOSAL_TTL_SECONDS = 600.0

_session_var: ContextVar[str] = ContextVar("approval_session", default="global")
_seq = itertools.count()


@dataclass
class _Pending:
    action_id: str
    session: str
    arm_mode: str
    created_at: float
    ttl: float
    seq: int
    question: str = ""
    armed: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def expired(self, now: float) -> bool:
        return now - self.created_at > self.ttl


_PENDING: Dict[Tuple[str, str], _Pending] = {}


def default_ttl() -> float:
    try:
        return float(os.getenv("APPROVAL_TTL_SECONDS", DEFAULT_TTL_SECONDS))
    except ValueError:
        return DEFAULT_TTL_SECONDS


# --- session binding --------------------------------------------------------
# Tools run deep inside the agent call and cannot see the session id, so the
# interface binds it to the context before dispatching the turn.

def set_session(session_id: Optional[str]) -> None:
    _session_var.set(session_id or "global")


def current_session() -> str:
    return _session_var.get()


def _norm(session_id: Optional[str]) -> str:
    return session_id or "global"


# --- identity ---------------------------------------------------------------

def fingerprint(tool: str, **parts: Any) -> str:
    """A stable id for "this exact action with these exact arguments".

    Only the arguments that change what happens belong here. Including a
    free-text note would let a reworded retry slip past a consumed approval;
    leaving out the amount would let a confirmed 5 become an executed 50.
    """
    payload = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{tool}:{digest}"


# --- lifecycle --------------------------------------------------------------

def register(
    action_id: str,
    *,
    question: str = "",
    arm_mode: str = AFFIRMATIVE,
    ttl: Optional[float] = None,
    session: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Record that this action is waiting for the user. Never armed on creation."""
    sess = _norm(session or current_session())
    _PENDING[(sess, action_id)] = _Pending(
        action_id=action_id,
        session=sess,
        arm_mode=arm_mode,
        created_at=time.monotonic(),
        ttl=default_ttl() if ttl is None else ttl,
        seq=next(_seq),
        question=question,
        meta=dict(meta or {}),
    )


def _purge(now: float) -> None:
    for key, entry in list(_PENDING.items()):
        if entry.expired(now):
            del _PENDING[key]


def _live(session_id: str, now: float):
    return [e for (s, _), e in _PENDING.items() if s == session_id and not e.expired(now)]


def on_user_turn(session_id: Optional[str], *, affirmative: bool) -> Optional[str]:
    """A new user message arrived. Returns the action_id armed by a yes, if any.

    Slot-style proposals arm on any turn — the user answers them by choosing.
    Yes/no approvals arm only on an actual yes, and only the newest: two
    questions pending and one "da" must authorise one of them, not both.
    A non-yes drops them, so "ne" and a change of subject both cancel.
    """
    sess = _norm(session_id)
    now = time.monotonic()
    _purge(now)

    armed_id = None
    for entry in _live(sess, now):
        if entry.arm_mode == NEXT_TURN:
            entry.armed = True

    if affirmative:
        candidates = [e for e in _live(sess, now) if e.arm_mode == AFFIRMATIVE]
        if candidates:
            newest = max(candidates, key=lambda e: e.seq)
            newest.armed = True
            armed_id = newest.action_id
            for other in candidates:
                if other is not newest:
                    del _PENDING[(sess, other.action_id)]
    else:
        for entry in list(_live(sess, now)):
            if entry.arm_mode == AFFIRMATIVE:
                del _PENDING[(sess, entry.action_id)]

    return armed_id


def redeem(action_id: str, *, session: Optional[str] = None) -> bool:
    """Consume an armed, unexpired approval. False means: do not act."""
    sess = _norm(session or current_session())
    entry = _PENDING.get((sess, action_id))
    if entry is None:
        return False
    if entry.expired(time.monotonic()):
        del _PENDING[(sess, action_id)]
        return False
    if not entry.armed:
        return False
    del _PENDING[(sess, action_id)]
    return True


def has_pending(session_id: Optional[str]) -> bool:
    """Used by voice routing to keep a bare "da" in the lane that asked."""
    return bool(_live(_norm(session_id), time.monotonic()))


def pending_question(session_id: Optional[str]) -> Optional[str]:
    live = _live(_norm(session_id), time.monotonic())
    if not live:
        return None
    return max(live, key=lambda e: e.seq).question or None


def cancel(session_id: Optional[str]) -> None:
    sess = _norm(session_id)
    for key in [k for k in _PENDING if k[0] == sess]:
        del _PENDING[key]


def reset() -> None:
    """Tests only."""
    _PENDING.clear()
