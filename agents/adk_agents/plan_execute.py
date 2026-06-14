"""
Plan-Execute orchestration layer.

Problem this solves: the LLM Smart Orchestrator must chain several AgentTools in a
single run. On long multi-step requests it is non-deterministic — after a big
worker result (e.g. a long research report) the model sometimes "feels done" and
stops, so the rest of the chain (rolodex -> mailer) never runs.

This layer makes multi-step requests deterministic:

  1. PLAN   - a lightweight planner LLM decomposes the request into an ordered list
              of steps ({id, agent, task, use_results}).
  2. EXECUTE - a plain Python loop runs each step as its OWN isolated agent call
              (fresh session = clean context, no bloat). Each result is saved to a
              ledger; only the explicitly referenced upstream results are injected
              into a later step.
  3. TRACK  - after every step we record done/failed. If a step fails we STOP and
              report what succeeded; we never feed an empty result downstream.
  4. SUMMARIZE - a final LLM pass turns the ledger into one natural answer in the
              user's language (preserving [IMAGE:...] media tags).

It is intentionally narrow: the planner only takes over for genuine multi-agent
chains. Single actions, fiscalization, confirmations and ambiguous requests get
``multi_step=false`` and fall back to the battle-tested Smart Orchestrator, so this
path can only help the failing case — it never degrades the working ones.
"""

import os
import re
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from google.genai import types

from agents.adk_agents.adk_agent_factory import create_adk_agent
from agents.adk_agents.datetime_context import inject_datetime_context
from agents.adk_agents.runner_utils import run_agent_simple

logger = logging.getLogger(__name__)

FLASH_MODEL = os.getenv("FLASH_MODEL", "gemini-3.5-flash")

# Sentinel the empty-result guardrail (control_callbacks) injects on failure, plus
# the no-text fallback string. Either means the step did not really produce output.
_FAILURE_MARKERS = ("⚠️ TOOL FAILURE", "No response generated")


# ---------------------------------------------------------------------------
# Planner / summarizer agents
# ---------------------------------------------------------------------------

def _build_available_agents(worker_agents: List[Any]) -> str:
    """Render the worker list the planner is allowed to choose from."""
    parts = []
    for agent in worker_agents:
        name = getattr(agent, "name", "unknown")
        desc = getattr(agent, "description", "") or ""
        parts.append(f"- **{name}**: {desc}")
    return "\n".join(parts) if parts else "(no agents available)"


def create_workflow_planner(
    worker_agents: List[Any],
    model: str = FLASH_MODEL,
    user_timezone: str = "Europe/Zagreb",
):
    """Create the planner agent that emits a JSON workflow plan (no tools)."""
    instruction_file = os.path.join(
        os.path.dirname(__file__), "..", "orchestrator", "planner_instructions.md"
    )
    try:
        with open(instruction_file, "r", encoding="utf-8") as f:
            instruction = f.read()
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Failed to load planner instructions: {e}")
        instruction = (
            "Output strict JSON: {\"multi_step\": false, \"language\": \"hr\", "
            "\"reason\": \"fallback\", \"steps\": []}"
        )

    instruction = instruction.replace(
        "{AVAILABLE_AGENTS}", _build_available_agents(worker_agents)
    )
    instruction = inject_datetime_context(instruction, user_timezone=user_timezone)

    planner = create_adk_agent(
        name="workflow_planner",
        model=model,
        description="Decomposes a user request into an ordered multi-agent plan (JSON).",
        instruction=instruction,
        load_instruction_from_file=False,
    )
    planner.generate_content_config = types.GenerateContentConfig(
        temperature=0.0,  # deterministic planning
        max_output_tokens=2048,
    )
    return planner


_SUMMARIZER_INSTRUCTION = """You write the FINAL answer to the user after a
multi-step workflow has run. You receive the original request and the result of
each step. Produce ONE natural, conversational reply in the user's language.

Rules:
- Respond in the SAME language as the original request (hr -> Croatian, en -> English).
- Be natural and human, like a helpful assistant. NO robotic markers like
  "[Completed]", "[Završeno]", "[OK]", "[Task]".
- For a multi-step success, briefly say what was done (a short natural list is fine).
- If a step FAILED, be direct about what succeeded and what did not, and suggest
  the next move (e.g. ask for the missing email).
- PRESERVE media tags EXACTLY: if a result contains an `[IMAGE:/api/media/...]`
  tag, copy it verbatim into your reply. Never describe or alter it.
- Do not invent results that are not in the step outputs.
"""


def create_workflow_summarizer(model: str = FLASH_MODEL):
    """Create the agent that turns the ledger into a final user-facing answer."""
    summarizer = create_adk_agent(
        name="workflow_summarizer",
        model=model,
        description="Summarizes multi-step workflow results into one natural reply.",
        instruction=_SUMMARIZER_INSTRUCTION,
        load_instruction_from_file=False,
    )
    summarizer.generate_content_config = types.GenerateContentConfig(
        temperature=0.4,
        max_output_tokens=4096,
    )
    return summarizer


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

@dataclass
class WorkflowLedger:
    """Side store for step results so the main context never bloats."""

    language: str = "hr"
    plan: List[Dict[str, Any]] = field(default_factory=list)
    results: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # id -> {agent, task, result}
    done: List[int] = field(default_factory=list)
    failure: Optional[Dict[str, Any]] = None  # {id, agent, reason}

    def record(self, step: Dict[str, Any], result: str) -> None:
        sid = step["id"]
        self.results[sid] = {"agent": step["agent"], "task": step["task"], "result": result}
        self.done.append(sid)

    def context_for(self, step: Dict[str, Any]) -> str:
        """Render only the upstream results this step asked for."""
        blocks = []
        for ref in step.get("use_results", []) or []:
            entry = self.results.get(ref)
            if entry:
                blocks.append(
                    f"### Korak {ref} ({entry['agent']}):\n{entry['result']}"
                )
        if not blocks:
            return ""
        return (
            "\n\n## PODACI IZ PRETHODNIH KORAKA (koristi ih, ne izmišljaj)\n"
            + "\n\n".join(blocks)
        )

    def summary_payload(self, user_message: str) -> str:
        lines = [
            f"ORIGINALNI ZAHTJEV: {user_message}",
            f"JEZIK ODGOVORA: {self.language}",
            "",
            "REZULTATI KORAKA:",
        ]
        for step in self.plan:
            sid = step["id"]
            entry = self.results.get(sid)
            if entry:
                lines.append(f"\n[Korak {sid} - {step['agent']}] OK\n{entry['result']}")
            elif self.failure and self.failure["id"] == sid:
                lines.append(
                    f"\n[Korak {sid} - {step['agent']}] NEUSPJEH: {self.failure['reason']}"
                )
            else:
                lines.append(f"\n[Korak {sid} - {step['agent']}] NIJE IZVRŠEN")
        lines.append("\nNapiši prirodan završni odgovor korisniku.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of the planner's text, tolerating fences."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        # Otherwise grab the outermost {...}.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[PLAN] Could not parse planner JSON: {e}")
        return None


def _validate_plan(plan: dict, valid_agents: set) -> Optional[List[Dict[str, Any]]]:
    """Return a clean step list, or None if the plan is unusable / single-step."""
    if not isinstance(plan, dict):
        return None
    if not plan.get("multi_step"):
        return None
    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        # Fewer than 2 steps is not a chain — let the orchestrator handle it.
        return None

    clean: List[Dict[str, Any]] = []
    for i, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            return None
        agent = raw.get("agent")
        task = raw.get("task")
        if agent not in valid_agents or not isinstance(task, str) or not task.strip():
            logger.warning(f"[PLAN] Invalid step {i}: agent={agent!r}")
            return None
        clean.append(
            {
                "id": int(raw.get("id", i)),
                "agent": agent,
                "task": task.strip(),
                "use_results": [int(r) for r in (raw.get("use_results") or []) if str(r).isdigit()],
            }
        )
    return clean


def _looks_failed(result: str) -> bool:
    if not result or not result.strip():
        return True
    head = result.strip()[:80]
    return any(marker in head for marker in _FAILURE_MARKERS)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_plan_execute(
    user_message: str,
    worker_agents: List[Any],
    *,
    fallback: Callable[[str], Awaitable[str]],
    session_id: str = "default-session",
    user_id: str = "default-user",
    planner_model: str = FLASH_MODEL,
    summarizer_model: str = FLASH_MODEL,
) -> str:
    """Run a request via plan-execute, falling back to ``fallback`` when it is not a
    genuine multi-step chain (or if anything goes wrong).

    Args:
        user_message: Raw user request.
        worker_agents: List of worker LlmAgents (the agents the planner may use).
        fallback: Async callable (the existing Smart Orchestrator run) used for
            single-step / special / error cases. MUST be awaitable -> str.
        session_id/user_id: Base identifiers; each step gets its own derived session.

    Returns:
        Final user-facing answer text.
    """
    agents_by_name = {getattr(a, "name", ""): a for a in worker_agents}
    valid_agents = set(agents_by_name)

    # --- 1. PLAN ---
    try:
        planner = create_workflow_planner(worker_agents, model=planner_model)
        planner_raw = await run_agent_simple(
            planner,
            user_message,
            session_id=f"{session_id}-planner",
            user_id=user_id,
        )
        plan = _extract_json(planner_raw)
        steps = _validate_plan(plan, valid_agents) if plan else None
    except Exception as e:
        logger.error(f"[PLAN] Planner failed, falling back to orchestrator: {e}")
        return await fallback(user_message)

    if not steps:
        logger.info("[PLAN] Not a multi-step chain — deferring to Smart Orchestrator.")
        return await fallback(user_message)

    ledger = WorkflowLedger(language=(plan.get("language") or "hr"), plan=steps)
    logger.info(
        "[PLAN] Multi-step plan accepted: %s",
        " -> ".join(f"{s['id']}:{s['agent']}" for s in steps),
    )

    # --- 2. EXECUTE (deterministic loop, fresh context per step) ---
    for step in steps:
        sid, agent_name = step["id"], step["agent"]
        agent = agents_by_name[agent_name]
        composed = step["task"] + ledger.context_for(step)

        logger.info("[STEP %s] -> %s", sid, agent_name)
        try:
            result = await run_agent_simple(
                agent,
                composed,
                session_id=f"{session_id}-step{sid}-{agent_name}",
                user_id=user_id,
            )
        except Exception as e:
            logger.error("[STEP %s] %s raised: %s", sid, agent_name, e)
            ledger.failure = {"id": sid, "agent": agent_name, "reason": f"greška: {e}"}
            break

        if _looks_failed(result):
            logger.error("[STEP %s] %s returned empty/failed result.", sid, agent_name)
            ledger.failure = {
                "id": sid,
                "agent": agent_name,
                "reason": "agent je vratio prazan rezultat — korak nije dovršen",
            }
            break

        ledger.record(step, result)
        logger.info("[STEP %s] %s OK (%d chars)", sid, agent_name, len(result))

    # --- 3. SUMMARIZE ---
    try:
        summarizer = create_workflow_summarizer(model=summarizer_model)
        final = await run_agent_simple(
            summarizer,
            ledger.summary_payload(user_message),
            session_id=f"{session_id}-summary",
            user_id=user_id,
        )
        if final and final.strip():
            return final
    except Exception as e:
        logger.error(f"[SUMMARY] Summarizer failed: {e}")

    # Summarizer fallback: stitch the ledger together plainly so we never return empty.
    if ledger.failure:
        last = ledger.results.get(ledger.done[-1]) if ledger.done else None
        done_note = f" Zadnji uspješan korak: {last['agent']}." if last else ""
        return (
            f"Dio zadatka je odrađen, ali korak {ledger.failure['id']} "
            f"({ledger.failure['agent']}) nije uspio: {ledger.failure['reason']}.{done_note}"
        )
    last = ledger.results.get(ledger.done[-1]) if ledger.done else None
    return last["result"] if last else "No response generated"
