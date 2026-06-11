"""Runtime patches for known third-party ADK issues."""

from __future__ import annotations

import logging

from config.deployment_config import DISABLE_ADK_TELEMETRY

logger = logging.getLogger(__name__)

_PATCHED = False


def apply_runtime_patches() -> None:
    """Apply idempotent runtime patches for unstable optional telemetry."""
    global _PATCHED
    if _PATCHED:
        return

    if DISABLE_ADK_TELEMETRY:
        _disable_adk_telemetry()

    _PATCHED = True


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
