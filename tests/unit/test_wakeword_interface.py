import asyncio

from config.deployment_config import reset_deployment_config_cache
from interfaces.wakeword_interface import WakeWordInterface


def test_live_ws_url_uses_token(monkeypatch):
    reset_deployment_config_cache()
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "rpi-home")
    monkeypatch.setenv("API_TOKEN", "abc123")
    monkeypatch.setenv("WAKEWORD_API_BASE_URL", "http://127.0.0.1:8000")

    interface = WakeWordInterface()

    assert interface.get_live_ws_url() == "ws://127.0.0.1:8000/api/live?token=abc123"


def test_detect_mode_switch_supports_live_exit_phrases(monkeypatch):
    reset_deployment_config_cache()
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "rpi-home")

    interface = WakeWordInterface()

    assert interface.detect_mode_switch("vrati se na agent mod") == "agent"
    assert interface.detect_mode_switch("izadi iz live moda") == "agent"


def test_process_transcript_wraps_agent_prompt_with_voice_persona(monkeypatch):
    reset_deployment_config_cache()
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "rpi-home")
    monkeypatch.setenv("VOICE_ASSISTANT_NAME", "Jarvis")

    interface = WakeWordInterface()
    captured = {}

    async def fake_process_message(*, user_id, message, session_id):
        captured["user_id"] = user_id
        captured["message"] = message
        captured["session_id"] = session_id
        return "U redu."

    interface.process_message = fake_process_message

    result = asyncio.run(interface.process_transcript("upali svjetlo u dnevnom boravku"))

    assert result["response"] == "U redu."
    assert "Ti si Jarvis" in captured["message"]
    assert "u muskom rodu" in captured["message"]
    assert "Korisnik je rekao: upali svjetlo u dnevnom boravku" in captured["message"]


def test_set_voice_mode_updates_ha_bridge(monkeypatch):
    reset_deployment_config_cache()
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "rpi-home")

    interface = WakeWordInterface()
    seen = {}

    class FakeBridge:
        def update_voice_mode(self, mode):
            seen["mode"] = mode

    interface.ha_mqtt_bridge = FakeBridge()

    result = interface.set_voice_mode("live")

    assert result["mode"] == "live"
    assert seen["mode"] == "live"
