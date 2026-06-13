"""
Orchestration control callbacks.

ADK-native guardrails wired into the orchestrator via `after_tool_callback`.
The orchestrator's tools are the worker agents (wrapped as AgentTools), so this
callback fires on the worker -> orchestrator boundary. When a worker returns an
empty/failed result, we REPLACE the tool response with an explicit failure
instruction so the orchestrator LLM cannot silently proceed (e.g. emailing a
link to a document that was never actually written).

ADK contract (google/adk/flows/llm_flows/functions.py): if an after_tool_callback
returns a non-None value, it replaces the original function response. Returning
None keeps the original response unchanged.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ADK control-flow tools that hand control to a sub-agent. They return an empty
# tool result by design (the response comes from the target agent), so the
# empty-result guardrail must never fire on them.
_CONTROL_FLOW_TOOLS = {"transfer_to_agent"}


def _is_empty_result(tool_response: Any) -> bool:
    """True when a worker AgentTool result is empty/missing.

    Worker AgentTool responses are dicts shaped like ``{"result": "<text>"}``.
    An empty/whitespace ``result`` (or an empty response object) means the step
    did not actually produce anything — the exact scribe-empty-doc failure mode.
    """
    if tool_response is None:
        return True
    if isinstance(tool_response, dict):
        # Empty dict, or {"result": ""}/{"result": None}/whitespace.
        if not tool_response:
            return True
        if "result" in tool_response:
            result = tool_response.get("result")
            return result is None or (isinstance(result, str) and not result.strip())
        # Other dict shapes (e.g. raw error dicts) are left to the LLM; we only
        # hard-fail on the proven empty-result case to avoid false positives.
        return False
    if isinstance(tool_response, str):
        return not tool_response.strip()
    return False


def validate_worker_result(
    *,
    tool: Any,
    args: Any,
    tool_context: Any,
    tool_response: Any,
) -> Optional[dict]:
    """after_tool_callback: block silent empty/failed worker results.

    Returns an overriding response dict on failure (forcing the orchestrator to
    stop and report), or None to keep the original response.
    """
    tool_name = getattr(tool, "name", "unknown")

    # ADK control-flow tools hand control to a sub-agent and legitimately return
    # an empty tool result — the real response is produced by the target agent.
    # Treating that as a failure wrongly hijacks the turn with an error message.
    if tool_name in _CONTROL_FLOW_TOOLS:
        return None

    if _is_empty_result(tool_response):
        logger.error(
            "[CONTROL] Worker '%s' returned an empty result (args=%s) — "
            "overriding with failure instruction to halt workflow.",
            tool_name,
            str(args)[:200],
        )
        return {
            "result": (
                f"⚠️ TOOL FAILURE: agent '{tool_name}' je vratio prazan rezultat — "
                f"korak NIJE dovršen. Prema Rule 3, ODMAH zaustavi workflow i javi "
                f"korisniku da je '{tool_name}' zakazao. NE pozivaj alate koji ovise o "
                f"ovom rezultatu (npr. slanje maila s linkom na dokument koji možda nije "
                f"kreiran)."
            )
        }

    return None
