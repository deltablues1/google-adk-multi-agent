"""
Unit tests for smart-home/voice safety (Phase A2):

- fast-path intent gate: questions, negations and deferred requests must NOT
  fire device actions from the substring shortcut
- protected devices need confirm=True (fridge/boiler OFF, oven ON)
- film scene turns off other outlets too (matching the prompt), never
  the protected ones
- noise-gate catches STT placeholders like "[nečujno]"
- unknown STT_ENGINE fails loudly instead of silently using Gemini

No network, no broker — MQTT clients are faked.

Run with:
    pytest tests/unit/test_voice_fast_path_intent.py -v
"""

import asyncio

import pytest

import services.voice_fast_path as voice_fast_path
from services.voice_fast_path import (
    classify_fast_path_intent,
    execute_fast_smart_home_command,
    normalize_voice_text,
)


# ---------------------------------------------------------------------------
# Intent gate
# ---------------------------------------------------------------------------

class TestIntentGate:
    @pytest.mark.parametrize("text", [
        "Koji film preporučuješ?",
        "Koji film preporučuješ",
        "Kakvo je stanje u kuhinji",
        "Je li upaljeno svjetlo u kuhinji",
        "Da li je ugašeno sve",
        "Nemoj ugasiti sve",
        "Nemoj upaliti svjetlo u kuhinji",
        "Ne gasi svjetlo u kuhinji",
        "Sutra ugasi sve",
        "Ugasi sve za sat vremena",
        "Kad odem, ugasi sve",
        "Ako nikoga nema, ugasi sve",
        "Podsjeti me da ugasim bojler",
        "Zakaži gašenje svih svjetala",
        # review phrases: deferred/negated/questions without "?"
        "Večeras ugasi sve",
        "Prekosutra ugasi sve",
        "U 22 sata ugasi sve",
        "U 7:30 upali svjetlo u kuhinji",
        "Nikad ugasi sve",
        "Jesu li upaljena svjetla u kuhinji",
        "Može li se ugasiti svjetlo u kuhinji",
        "Možeš li ugasiti sve kad završi film",
        "Hoćeš li upaliti svjetlo",
    ])
    def test_blocked_phrases(self, text):
        assert classify_fast_path_intent(normalize_voice_text(text)) == "blocked"

    @pytest.mark.parametrize("text", [
        "Upali svjetlo u kuhinji",
        "Ugasi sve",
        "Idemo gledati film",
        "Ugasi svjetlo u hodniku",
        "Uključi svjetlo na terasi",
    ])
    def test_commands_pass(self, text):
        assert classify_fast_path_intent(normalize_voice_text(text)) == "command"

    def test_no_imperative_verb_blocked(self):
        # Positive grammar: without a command verb or scene alias, nothing fires
        assert classify_fast_path_intent(
            normalize_voice_text("svjetla u kuhinji")
        ) == "blocked"

    def test_overlong_sentence_blocked(self):
        text = ("upali svjetlo u kuhinji ali samo ako je vani mrak i "
                "nitko nije u dnevnom boravku niti na terasi")
        assert classify_fast_path_intent(normalize_voice_text(text)) == "blocked"

    def test_persona_wrapped_text_is_blocked(self):
        # Documents WHY the persona wrapper must never enter the routing path:
        # its own text trips the gate. The pipeline passes raw transcripts.
        from config.voice_persona import wrap_agent_voice_message

        wrapped = wrap_agent_voice_message("Upali svjetlo u kuhinji")
        assert classify_fast_path_intent(normalize_voice_text(wrapped)) == "blocked"

    def test_question_never_fires_device(self, monkeypatch):
        called = {"scene": False, "switch": False}

        async def fake_scene(scene):
            called["scene"] = True
            return {"status": "ok"}

        async def fake_switch(device_name, state):
            called["switch"] = True
            return {"status": "ok"}

        monkeypatch.setattr(voice_fast_path, "mqtt_scene_control", fake_scene)
        monkeypatch.setattr(voice_fast_path, "mqtt_switch_control", fake_switch)

        result = asyncio.run(
            execute_fast_smart_home_command("Koji film preporučuješ?")
        )
        assert result is None
        assert called == {"scene": False, "switch": False}

    def test_negation_never_fires_device(self, monkeypatch):
        called = {"scene": False}

        async def fake_scene(scene):
            called["scene"] = True
            return {"status": "ok"}

        monkeypatch.setattr(voice_fast_path, "mqtt_scene_control", fake_scene)

        result = asyncio.run(
            execute_fast_smart_home_command("Nemoj ugasiti sve")
        )
        assert result is None
        assert called["scene"] is False

    def test_plain_command_still_works(self, monkeypatch):
        async def fake_switch(device_name, state):
            assert device_name == "svjetlo_kuhinja"
            assert state == "ON"
            return {"status": "confirmed"}

        monkeypatch.setattr(voice_fast_path, "mqtt_switch_control", fake_switch)

        result = asyncio.run(
            execute_fast_smart_home_command(
                "Upali svjetlo u kuhinji", response_mode="full"
            )
        )
        assert result is not None and "kuhinji" in result

    def test_default_response_mode_is_ok(self, monkeypatch):
        monkeypatch.delenv("VOICE_SMART_HOME_RESPONSE_MODE", raising=False)
        assert voice_fast_path.resolve_voice_smart_home_response("Nešto") == "U redu."


# ---------------------------------------------------------------------------
# Protected devices
# ---------------------------------------------------------------------------

class TestProtectedDevices:
    @pytest.fixture(autouse=True)
    def clean_approvals(self):
        import tools.adk_tools.mqtt_adk_tools as mqtt_tools

        mqtt_tools._PENDING_APPROVALS.clear()
        yield
        mqtt_tools._PENDING_APPROVALS.clear()

    @pytest.mark.parametrize("device,state", [
        ("uticnica_frizider", "OFF"),
        ("uticnica_bojler", "OFF"),
        ("pecnica", "ON"),
    ])
    def test_protected_needs_confirmation(self, device, state):
        from tools.adk_tools.mqtt_adk_tools import mqtt_switch_control

        result = asyncio.run(mqtt_switch_control(device, state))
        assert result["status"] == "needs_confirmation"

    def test_same_turn_confirm_rejected(self):
        # confirm=True without a user turn in between must NOT execute —
        # the model cannot self-approve.
        from tools.adk_tools.mqtt_adk_tools import mqtt_switch_control

        first = asyncio.run(mqtt_switch_control("uticnica_bojler", "OFF"))
        assert first["status"] == "needs_confirmation"

        same_turn = asyncio.run(
            mqtt_switch_control("uticnica_bojler", "OFF", confirm=True)
        )
        assert same_turn["status"] == "needs_confirmation"

    def test_cold_confirm_rejected(self):
        # confirm=True out of nowhere (no prior needs_confirmation) is rejected.
        from tools.adk_tools.mqtt_adk_tools import mqtt_switch_control

        result = asyncio.run(
            mqtt_switch_control("uticnica_frizider", "OFF", confirm=True)
        )
        assert result["status"] == "needs_confirmation"

    def test_approval_expires(self, monkeypatch):
        import time as time_mod

        import tools.adk_tools.mqtt_adk_tools as mqtt_tools

        asyncio.run(mqtt_tools.mqtt_switch_control("uticnica_bojler", "OFF"))
        # simulate TTL expiry
        entry = mqtt_tools._PENDING_APPROVALS[("uticnica_bojler", "OFF")]
        entry["created_at"] = time_mod.monotonic() - 999
        mqtt_tools.arm_pending_approvals()  # purges expired

        assert ("uticnica_bojler", "OFF") not in mqtt_tools._PENDING_APPROVALS

    @pytest.mark.parametrize("device,state", [
        ("uticnica_frizider", "ON"),   # turning fridge ON is safe
        ("pecnica", "OFF"),            # turning oven OFF is safe
        ("svjetlo_kuhinja", "OFF"),
    ])
    def test_unprotected_publishes(self, device, state, monkeypatch):
        import services.mqtt_confirm as mqtt_confirm
        import tools.adk_tools.mqtt_adk_tools as mqtt_tools

        captured = {}

        async def fake_confirm(commands, timeout=None):
            captured["payload"] = commands[0].payload
            return {
                "status": "confirmed", "operation_id": "op1",
                "confirmed": 1, "total": 1,
                "devices": {commands[0].name: {"status": "confirmed", "observed": state}},
            }

        monkeypatch.setattr(mqtt_confirm, "publish_and_confirm", fake_confirm)

        result = asyncio.run(mqtt_tools.mqtt_switch_control(device, state))
        assert result["status"] == "confirmed"
        assert captured["payload"] == state

    def test_confirmed_protected_publishes_after_user_turn(self, monkeypatch):
        # Full turn-gated cycle: needs_confirmation -> new user turn arms the
        # approval -> confirm=True executes.
        import services.mqtt_confirm as mqtt_confirm
        import tools.adk_tools.mqtt_adk_tools as mqtt_tools

        captured = {}

        async def fake_confirm(commands, timeout=None):
            captured["payload"] = commands[0].payload
            return {
                "status": "confirmed", "operation_id": "op1",
                "confirmed": 1, "total": 1,
                "devices": {commands[0].name: {"status": "confirmed", "observed": "OFF"}},
            }

        monkeypatch.setattr(mqtt_confirm, "publish_and_confirm", fake_confirm)

        first = asyncio.run(mqtt_tools.mqtt_switch_control("uticnica_bojler", "OFF"))
        assert first["status"] == "needs_confirmation"

        mqtt_tools.arm_pending_approvals()  # user replied in a new turn

        result = asyncio.run(
            mqtt_tools.mqtt_switch_control("uticnica_bojler", "OFF", confirm=True)
        )
        assert result["status"] == "confirmed"
        assert captured["payload"] == "OFF"

        # approval was consumed — a repeat needs a fresh confirmation
        repeat = asyncio.run(
            mqtt_tools.mqtt_switch_control("uticnica_bojler", "OFF", confirm=True)
        )
        assert repeat["status"] == "needs_confirmation"


# ---------------------------------------------------------------------------
# Scene composition
# ---------------------------------------------------------------------------

class TestSceneComposition:
    def _run_scene(self, monkeypatch, scene):
        import services.mqtt_confirm as mqtt_confirm
        import tools.adk_tools.mqtt_adk_tools as mqtt_tools

        captured = {}

        async def fake_confirm(commands, timeout=None):
            captured["commands"] = commands
            return {
                "status": "confirmed", "operation_id": "op1",
                "confirmed": len(commands), "total": len(commands),
                "devices": {
                    c.name: {"status": "confirmed", "observed": c.payload}
                    for c in commands
                },
            }

        monkeypatch.setattr(mqtt_confirm, "publish_and_confirm", fake_confirm)
        result = asyncio.run(mqtt_tools.mqtt_scene_control(scene))
        return result, captured["commands"]

    def test_film_turns_off_other_outlets(self, monkeypatch):
        result, commands = self._run_scene(monkeypatch, "film")
        assert result["status"] == "confirmed"
        topics_off = [c.command_topic for c in commands if c.payload == "OFF"]
        topics_on = [c.command_topic for c in commands if c.payload == "ON"]

        assert "esp32-io/switch/uticnica_boravak/command" in topics_off
        assert "esp32-io/switch/uticnica_tv/command" in topics_on
        assert "esp32-io/switch/svjetlo_tv/command" in topics_on
        # protected devices untouched
        all_topics = [c.command_topic for c in commands]
        assert "esp32-io/switch/uticnica_frizider/command" not in all_topics
        assert "esp32-io/switch/uticnica_bojler/command" not in all_topics

    def test_sve_ugasi_spares_protected(self, monkeypatch):
        result, commands = self._run_scene(monkeypatch, "sve_ugasi")
        assert result["status"] == "confirmed"
        assert result["summary"].endswith("potvrđeno")
        all_topics = [c.command_topic for c in commands]
        assert "esp32-io/switch/uticnica_frizider/command" not in all_topics
        assert "esp32-io/switch/uticnica_bojler/command" not in all_topics
        assert "esp32-io/switch/svjetlo_kuhinja/command" in all_topics


# ---------------------------------------------------------------------------
# Noise gate placeholders
# ---------------------------------------------------------------------------

class TestNoiseGate:
    @pytest.mark.parametrize("text", [
        "[nečujno]", "[necujno]", "(nerazumljivo)", "[inaudible]",
        "[glazba]", "(tišina)", "...", "3 7 1 2 0 6 8 3",
    ])
    def test_noise_flagged(self, text):
        from interfaces.wakeword_interface import looks_like_noise_transcript

        assert looks_like_noise_transcript(text) is True

    @pytest.mark.parametrize("text", [
        "Koliko je 2 i 2",
        "Upali svjetlo u kuhinji",
        "Sastanak u 21:30",
    ])
    def test_speech_passes(self, text):
        from interfaces.wakeword_interface import looks_like_noise_transcript

        assert looks_like_noise_transcript(text) is False


# ---------------------------------------------------------------------------
# STT engine dispatch
# ---------------------------------------------------------------------------

class TestSttEngineDispatch:
    def test_unknown_engine_fails_loudly(self, monkeypatch):
        from services.audio_ingress import AudioIngressError, AudioIngressService

        monkeypatch.setenv("STT_ENGINE", "whisperx")
        service = AudioIngressService(api_key="dummy")

        with pytest.raises(AudioIngressError, match="Unsupported STT_ENGINE"):
            asyncio.run(
                service.transcribe_audio(b"RIFF....", "audio/wav", "test")
            )

    @pytest.mark.parametrize("engine", ["openai", "chirp", "chirp_2", "cloud"])
    def test_stt_service_engines_delegated(self, engine, monkeypatch):
        # STT_ENGINE=openai is implemented by STTService and must be
        # delegated, not rejected (regression: it was rejected once).
        from services.audio.stt_service import STTService
        from services.audio_ingress import AudioIngressService

        monkeypatch.setenv("STT_ENGINE", engine)

        async def fake_transcribe(self, audio_bytes, mime_type):
            return "upali svjetlo"

        monkeypatch.setattr(STTService, "transcribe", fake_transcribe)

        service = AudioIngressService(api_key="dummy")
        result = asyncio.run(
            service.transcribe_audio(b"RIFF....", "audio/wav", "test")
        )
        assert result.transcript == "upali svjetlo"
