from services.ha_mqtt_bridge import HomeAssistantMqttBridge


def test_build_discovery_messages_exposes_expected_entities(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER", "127.0.0.1")
    monkeypatch.setenv("HA_MQTT_STATE_PREFIX", "google_clause/rpi_voice")

    bridge = HomeAssistantMqttBridge(
        api_base_url="http://127.0.0.1:8000",
        voice_assistant_name="Jarvis",
    )

    messages = dict(bridge.build_discovery_messages())

    assert any("/binary_sensor/" in topic for topic in messages)
    assert any("/select/" in topic for topic in messages)
    assert any("_last_transcript/config" in topic for topic in messages)
    assert any("_last_response/config" in topic for topic in messages)

    select_payload = next(payload for topic, payload in messages.items() if "/select/" in topic)
    assert select_payload["state_topic"] == "google_clause/rpi_voice/voice_mode/state"
    assert select_payload["command_topic"] == "google_clause/rpi_voice/voice_mode/set"
    assert select_payload["options"] == ["agent", "live"]


def test_mode_command_callback_runs_for_supported_modes(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER", "127.0.0.1")
    commands = []

    bridge = HomeAssistantMqttBridge(
        api_base_url="http://127.0.0.1:8000",
        voice_assistant_name="Jarvis",
        mode_command_callback=commands.append,
    )

    class Message:
        topic = bridge.voice_mode_command_topic
        payload = b"live"

    bridge._on_message(None, None, Message())

    assert commands == ["live"]
