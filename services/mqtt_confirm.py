"""Publish-and-confirm layer for smart-home MQTT commands.

"status: ok" used to mean only "publish was called" — the device may have been
offline and nobody would know. ESP32 devices echo their real state on
``esp32-io/.../state`` topics, so confirmation is: subscribe first, publish the
command, then wait until every expected state is observed (or a timeout).

Pragmatic constraints (paho-mqtt on an RPi, not a message bus cluster):
- one short-lived client per operation, no background daemon
- the confirm layer must NEVER block the action: if anything in it fails,
  commands are blindly published and marked "unconfirmed"
- everything is synchronous inside a worker thread; the public API is async

Env:
    MQTT_CONFIRM_ENABLED  (default true; false restores fire-and-forget)
    MQTT_CONFIRM_TIMEOUT  (seconds to wait for state echoes, default 3.0)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class DeviceCommand:
    """One MQTT command plus how to recognize its confirmation."""

    name: str                    # result key, e.g. "svjetlo_kuhinja"
    command_topic: str
    payload: str
    state_topic: str
    # Either the exact expected state payload ("ON") or a predicate over the
    # observed payload (for JSON dimmer states).
    expected: Union[str, Callable[[str], bool]]

    def matches(self, observed_payload: str) -> bool:
        if callable(self.expected):
            try:
                return bool(self.expected(observed_payload))
            except Exception:
                return False
        return observed_payload.strip() == self.expected


def expect_json_state(state: str) -> Callable[[str], bool]:
    """Predicate for JSON state payloads like {"state": "ON", "brightness": 64}."""

    def _match(payload: str) -> bool:
        try:
            return json.loads(payload).get("state") == state
        except (json.JSONDecodeError, AttributeError):
            return False

    return _match


def _confirm_enabled() -> bool:
    return os.getenv("MQTT_CONFIRM_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _confirm_timeout() -> float:
    try:
        return float(os.getenv("MQTT_CONFIRM_TIMEOUT", "3.0"))
    except ValueError:
        return 3.0


def _default_client_factory():
    from tools.adk_tools.mqtt_adk_tools import _get_mqtt_client

    return _get_mqtt_client()


# Injectable for tests (FakeMqttClient) — module-level on purpose.
_client_factory = _default_client_factory


def _blind_publish(commands: List[DeviceCommand]) -> None:
    """Fire-and-forget fallback: the action must not be lost because the
    confirmation machinery failed."""
    client = _client_factory()
    try:
        for cmd in commands:
            client.publish(cmd.command_topic, cmd.payload, qos=1)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass


def _confirm_worker(commands: List[DeviceCommand], timeout: float) -> Dict[str, dict]:
    """Sync worker: subscribe → publish → await expected state echoes."""
    confirmed: Dict[str, bool] = {cmd.name: False for cmd in commands}
    observed: Dict[str, Optional[str]] = {cmd.name: None for cmd in commands}
    all_confirmed = threading.Event()
    lock = threading.Lock()

    def on_message(_client, _userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        with lock:
            for cmd in commands:
                if cmd.state_topic == msg.topic:
                    observed[cmd.name] = payload
                    if cmd.matches(payload):
                        confirmed[cmd.name] = True
            if all(confirmed.values()):
                all_confirmed.set()

    client = _client_factory()
    try:
        client.on_message = on_message
        # Subscribe BEFORE publishing so the echo cannot be missed. Retained
        # old states arriving now are harmless: they only confirm a device
        # that is already in the target state.
        for topic in {cmd.state_topic for cmd in commands}:
            client.subscribe(topic, qos=1)
        client.loop_start()
        try:
            for cmd in commands:
                client.publish(cmd.command_topic, cmd.payload, qos=1)
            all_confirmed.wait(timeout)
        finally:
            client.loop_stop()
    finally:
        try:
            client.disconnect()
        except Exception:
            pass

    with lock:
        return {
            name: {
                "status": "confirmed" if confirmed[name] else "timeout",
                "observed": observed[name],
            }
            for name in confirmed
        }


async def publish_and_confirm(
    commands: List[DeviceCommand],
    timeout: Optional[float] = None,
) -> dict:
    """Publish commands and wait for device state confirmation.

    Returns::

        {
            "status": "confirmed" | "partial" | "timeout" | "ok" | "error",
            "operation_id": "1a2b3c4d",
            "confirmed": 3, "total": 5,
            "devices": {name: {"status": ..., "observed": ...}, ...},
        }

    "ok" = confirmation disabled (fire-and-forget succeeded);
    "partial" = some but not all devices confirmed;
    "error" = even the blind publish failed (broker unreachable).
    """
    operation_id = uuid.uuid4().hex[:8]
    timeout = timeout if timeout is not None else _confirm_timeout()
    total = len(commands)
    loop = asyncio.get_event_loop()

    if not _confirm_enabled():
        try:
            await loop.run_in_executor(None, _blind_publish, commands)
            return {
                "status": "ok",
                "operation_id": operation_id,
                "confirmed": 0,
                "total": total,
                "devices": {
                    cmd.name: {"status": "unconfirmed", "observed": None}
                    for cmd in commands
                },
            }
        except Exception as e:
            logger.error(f"[{operation_id}] MQTT publish failed: {e}")
            return {
                "status": "error",
                "operation_id": operation_id,
                "error": str(e),
                "confirmed": 0,
                "total": total,
                "devices": {},
            }

    try:
        devices = await loop.run_in_executor(None, _confirm_worker, commands, timeout)
    except Exception as e:
        # Confirmation machinery failed — degrade to blind publish so the
        # user's action still happens, and be honest that it's unconfirmed.
        logger.warning(f"[{operation_id}] confirm worker failed ({e}); blind publish")
        try:
            await loop.run_in_executor(None, _blind_publish, commands)
            return {
                "status": "partial" if total > 1 else "unconfirmed",
                "operation_id": operation_id,
                "confirmed": 0,
                "total": total,
                "devices": {
                    cmd.name: {"status": "unconfirmed", "observed": None}
                    for cmd in commands
                },
                "warning": f"confirmation unavailable: {e}",
            }
        except Exception as publish_err:
            logger.error(f"[{operation_id}] MQTT publish failed: {publish_err}")
            return {
                "status": "error",
                "operation_id": operation_id,
                "error": str(publish_err),
                "confirmed": 0,
                "total": total,
                "devices": {},
            }

    confirmed_count = sum(1 for d in devices.values() if d["status"] == "confirmed")
    if confirmed_count == total:
        status = "confirmed"
    elif confirmed_count > 0:
        status = "partial"
    else:
        status = "timeout"

    logger.info(
        f"[{operation_id}] MQTT confirm: {confirmed_count}/{total} devices ({status})"
    )
    return {
        "status": status,
        "operation_id": operation_id,
        "confirmed": confirmed_count,
        "total": total,
        "devices": devices,
    }
