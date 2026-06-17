"""Runtime patches for known third-party ADK issues."""

from __future__ import annotations

import os
import logging

from config.deployment_config import is_adk_telemetry_disabled

logger = logging.getLogger(__name__)

_PATCHED = False


def apply_runtime_patches() -> None:
    """Apply idempotent runtime patches for unstable optional telemetry."""
    global _PATCHED
    if _PATCHED:
        return

    if is_adk_telemetry_disabled():
        _disable_adk_telemetry()

    if os.getenv("CLAUDE_PROMPT_CACHE", "true").lower() in ("1", "true", "yes", "on"):
        _enable_litellm_prompt_cache()

    _PATCHED = True


def _enable_litellm_prompt_cache() -> None:
    """Mark the system prompt for Anthropic prompt caching on LiteLLM calls.

    ADK's LiteLlm wrapper inserts the agent instruction as a plain-string
    system/developer message. Anthropic only caches a content *block* carrying
    ``cache_control``. We wrap ``_get_completion_inputs`` to convert that string
    into a cache-marked text block, so the large static agent instructions are
    cached (~90% cheaper on subsequent calls within the TTL).

    Only affects LiteLLM (Claude) calls — the Gemini path never calls this
    function. No-ops if litellm/ADK LiteLlm is unavailable. Cache hits show up
    in usage as cached tokens (the /tokens "cached" column).
    """
    try:
        import google.adk.models.lite_llm as ll
    except Exception as exc:  # litellm not installed, or import error
        logger.debug("LiteLLM prompt-cache patch skipped: %s", exc)
        return

    if getattr(ll, "_prompt_cache_patched", False):
        return

    original = ll._get_completion_inputs

    def _patched(*args, **kwargs):
        # Arity-agnostic: ADK versions differ in this function's signature, so
        # pass everything through and return the original result unchanged in
        # shape — we only mutate the messages list in place.
        result = original(*args, **kwargs)
        try:
            messages = result[0] if isinstance(result, (tuple, list)) else None
            for msg in messages or []:
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                if role in ("system", "developer"):
                    content = (
                        msg.get("content") if isinstance(msg, dict)
                        else getattr(msg, "content", None)
                    )
                    if isinstance(content, str) and content.strip():
                        block = [{
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }]
                        if isinstance(msg, dict):
                            msg["content"] = block
                        else:
                            msg.content = block
                    break  # only the (single) system/developer message
        except Exception as exc:  # never break the request over caching
            logger.debug("prompt-cache marking skipped: %s", exc)
        return result

    ll._get_completion_inputs = _patched
    ll._prompt_cache_patched = True
    logger.info("LiteLLM Anthropic prompt-caching patch applied (system block cache_control)")


def _disable_adk_telemetry() -> None:
    """Disable ADK tracing hooks that can crash on non-JSON-safe payloads."""
    try:
        import google.adk.telemetry as telemetry

        def _noop(*args, **kwargs):
            return None

        telemetry.trace_call_llm = _noop
        telemetry.trace_send_data = _noop
        telemetry.trace_tool_call = _noop
        telemetry.trace_tool_response = _noop
        logger.info("ADK telemetry tracing disabled by runtime patch")
    except Exception as exc:
        logger.warning("Failed to disable ADK telemetry tracing: %s", exc)
