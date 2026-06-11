"""
Raspberry Pi wake-word voice interface.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from config.deployment_config import get_deployment_config, is_wake_word_enabled
from config.voice_persona import wrap_agent_voice_message
from config.voice_persona import get_voice_assistant_name
from services.ha_mqtt_bridge import HomeAssistantMqttBridge
from services.audio_ingress import get_audio_ingress_service

from .base_interface import BaseInterface

logger = logging.getLogger(__name__)


class WakeWordInterface(BaseInterface):
    def __init__(self):
        super().__init__(session_prefix="wakeword")
        if not is_wake_word_enabled():
            raise ValueError("Wake word interface is disabled by deployment profile")

        deployment = get_deployment_config()
        self.voice_mode = deployment.voice_mode_default
        self.api_base_url = os.getenv("WAKEWORD_API_BASE_URL", "http://127.0.0.1:8000")
        self.api_token = os.getenv("API_TOKEN", "")
        self.user_id = os.getenv("WAKEWORD_USER_ID", "wakeword-user")
        self.session_id = self.generate_session_id(self.user_id)
        self.ha_mqtt_bridge: Optional[HomeAssistantMqttBridge] = None

    def format_response(self, response: str) -> str:
        return response

    async def start(self) -> None:
        self.initialize_system()
        self.ha_mqtt_bridge = HomeAssistantMqttBridge(
            api_base_url=self.api_base_url,
            voice_assistant_name=get_voice_assistant_name(),
            mode_command_callback=self._handle_external_voice_mode_command,
        )
        self.ha_mqtt_bridge.start(initial_voice_mode=self.voice_mode)
        logger.info("WakeWordInterface initialized in %s mode", self.voice_mode)

    async def stop(self) -> None:
        if self.ha_mqtt_bridge:
            self.ha_mqtt_bridge.stop()
        logger.info("WakeWordInterface stopped")

    def get_live_ws_url(self) -> str:
        base = self.api_base_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        elif base.startswith("wss://") or base.startswith("ws://"):
            ws_base = base
        else:
            ws_base = f"ws://{base}"

        if self.api_token:
            return f"{ws_base}/api/live?token={self.api_token}"
        return f"{ws_base}/api/live"

    def _extract_mode_switch(self, transcript: str) -> Optional[str]:
        text = transcript.lower().strip()
        if any(phrase in text for phrase in (
            "vrati na agent mod",
            "prebaci na agent mod",
            "izadi iz live moda",
            "prekini live mod",
            "zatvori live mod",
            "vrati se na agent mod",
            "agent mod",
        )):
            return "agent"
        if any(phrase in text for phrase in (
            "prebaci na live mod",
            "ukljuci live mod",
            "idi u live mod",
            "live mod",
        )):
            return "live"
        return None

    def detect_mode_switch(self, transcript: str) -> Optional[str]:
        return self._extract_mode_switch(transcript)

    def set_voice_mode(self, mode: str) -> dict:
        if mode not in {"agent", "live"}:
            raise ValueError(f"Unsupported voice mode: {mode}")
        self.voice_mode = mode
        if self.ha_mqtt_bridge:
            self.ha_mqtt_bridge.update_voice_mode(mode)
        return {
            "mode": self.voice_mode,
            "response": f"Prebacen sam u {self.voice_mode} mod.",
        }

    def _handle_external_voice_mode_command(self, mode: str) -> None:
        try:
            self.set_voice_mode(mode)
            logger.info("Voice mode changed from HA MQTT command: %s", mode)
        except Exception:
            logger.exception("Failed to apply HA MQTT voice mode command: %s", mode)

    async def process_transcript(self, transcript: str) -> dict:
        if self.ha_mqtt_bridge:
            self.ha_mqtt_bridge.update_last_transcript(transcript)

        requested_mode = self.detect_mode_switch(transcript)
        if requested_mode:
            self.set_voice_mode(requested_mode)
            result = {
                "mode": self.voice_mode,
                "transcript": transcript,
                "response": f"Prebacen sam u {self.voice_mode} mod.",
            }
            if self.ha_mqtt_bridge:
                self.ha_mqtt_bridge.update_last_response(result["response"])
            return result

        if self.voice_mode == "live":
            result = {
                "mode": self.voice_mode,
                "transcript": transcript,
                "response": (
                    "Live mod za Pi koristi postojeci /api/live websocket i raw audio stream. "
                    "Taj hardware streaming nije aktiviran u ovom simulacijskom runneru."
                ),
            }
            if self.ha_mqtt_bridge:
                self.ha_mqtt_bridge.update_last_response(result["response"])
            return result

        response = await self.process_message(
            user_id=self.user_id,
            message=wrap_agent_voice_message(transcript),
            session_id=self.session_id,
        )
        result = {
            "mode": self.voice_mode,
            "transcript": transcript,
            "response": response,
        }
        if self.ha_mqtt_bridge:
            self.ha_mqtt_bridge.update_last_response(response)
        return result

    async def process_audio(self, audio_bytes: bytes, mime_type: str, source: str = "wakeword") -> dict:
        transcript_result = await get_audio_ingress_service().transcribe_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            source=source,
            metadata={"session_id": self.session_id},
        )
        result = await self.process_transcript(transcript_result.transcript)
        result["metadata"] = transcript_result.metadata
        return result
