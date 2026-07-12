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


def test_process_transcript_passes_raw_transcript(monkeypatch):
    # The persona wrapper must NOT be applied here: its text ("Ako je...",
    # "Nemoj...") trips the smart-home intent gate and once killed the entire
    # wakeword fast path. Persona is injected at the LLM boundary instead.
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
    assert captured["message"] == "upali svjetlo u dnevnom boravku"
    assert "VOICE_ASSISTANT_PROFILE" not in captured["message"]


def test_wakeword_flow_reaches_fast_path_end_to_end(monkeypatch):
    """E2E-shaped: raw transcript -> routing -> smart-home fast path fires MQTT.

    Guards against the regression where a persona-wrapped message was blocked
    by the intent gate and every command silently fell to the LLM lane.
    """
    from types import SimpleNamespace

    import services.mqtt_confirm as mqtt_confirm
    import services.voice_fast_path as vfp

    reset_deployment_config_cache()
    monkeypatch.setenv("WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "rpi-home")
    monkeypatch.setenv("WAKEWORD_USER_ID", "rpi-voice-test")
    monkeypatch.setenv("VOICE_DIRECT_ROUTING", "true")
    monkeypatch.setenv("VOICE_SMART_HOME_RESPONSE_MODE", "full")

    interface = WakeWordInterface()
    interface.system = SimpleNamespace(
        active_mode="LEGACY",
        orchestrator_helper=None,
        philosophy_keywords=set(),
        session_id=None,
        user_id=None,
    )
    interface.initialize_system = lambda: None

    published = {}

    async def fake_confirm(commands, timeout=None):
        published["topics"] = [c.command_topic for c in commands]
        return {
            "status": "confirmed", "operation_id": "op1",
            "confirmed": len(commands), "total": len(commands),
            "devices": {
                c.name: {"status": "confirmed", "observed": c.payload}
                for c in commands
            },
        }

    monkeypatch.setattr(mqtt_confirm, "publish_and_confirm", fake_confirm)

    # Record what the intent gate actually receives — persona text must
    # never reach it.
    gate_inputs = []
    real_classify = vfp.classify_fast_path_intent

    def recording_classify(normalized):
        gate_inputs.append(normalized)
        return real_classify(normalized)

    monkeypatch.setattr(vfp, "classify_fast_path_intent", recording_classify)

    result = asyncio.run(interface.process_transcript("upali svjetlo u kuhinji"))

    assert published["topics"] == ["esp32-io/switch/svjetlo_kuhinja/command"]
    assert "kuhinji" in result["response"]
    assert gate_inputs, "fast path gate was never consulted"
    for text in gate_inputs:
        assert "voice_assistant_profile" not in text
        assert "korisnik je rekao" not in text


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
