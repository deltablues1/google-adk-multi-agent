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

    if os.getenv("LLM_PROVIDER", "gemini").lower() == "anthropic":
        _enable_litellm_drop_params()

    _PATCHED = True


def _enable_litellm_drop_params() -> None:
    """Drop sampling params the target Claude model doesn't accept.

    Claude Sonnet 5 / Opus 4.7+ reject non-default temperature/top_p/top_k
    (LiteLLM raises UnsupportedParamsError client-side and retries pointlessly).
    The agent factory strips these for agents built through create_adk_agent,
    but some call sites set generate_content_config directly on the agent
    (smart_orchestrator, plan_execute planner/summarizer). drop_params makes
    LiteLLM silently drop whatever the model doesn't support — the safety net
    for every current and future call site.
    """
    try:
        import litellm
    except Exception as exc:  # litellm not installed
        logger.debug("LiteLLM drop_params patch skipped: %s", exc)
        return
    litellm.drop_params = True
    logger.info("LiteLLM drop_params enabled (unsupported sampling params are dropped)")


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

    import inspect

    original = ll._get_completion_inputs

    def _mark(result):
        """Mark the system message content for Anthropic prompt caching, in place."""
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
                        # LiteLLM reads cache_control only from role=="system".
                        if isinstance(msg, dict):
                            msg["content"] = block
                            msg["role"] = "system"
                        else:
                            msg.content = block
                            try:
                                msg.role = "system"
                            except Exception:
                                pass
                    break  # only the (single) system/developer message
        except Exception as exc:  # never break the request over caching
            logger.debug("prompt-cache marking skipped: %s", exc)
        return result

    # ADK versions differ: _get_completion_inputs may be sync or async, and take
    # 1 or 2 positional args. Handle both, passing args straight through.
    if inspect.iscoroutinefunction(original):
        async def _patched(*args, **kwargs):
            return _mark(await original(*args, **kwargs))
    else:
        def _patched(*args, **kwargs):
            return _mark(original(*args, **kwargs))

    ll._get_completion_inputs = _patched
    ll._prompt_cache_patched = True
    logger.info(
        "LiteLLM Anthropic prompt-caching patch applied (async=%s)",
        inspect.iscoroutinefunction(original),
    )


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
