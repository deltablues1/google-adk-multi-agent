"""
STT_ENGINE=gemini_transcribe — the Gemini 3.5 Transcribe path.

What matters here is not that the SDK gets called, but *what* it is told: the
language is pinned (detection is what mistook Croatian for Macedonian and Czech
on the two engines rejected before this one), the audio travels inline, and a
failure falls back to Chirp instead of leaving the house deaf.

Run with:
    pytest tests/unit/test_gemini_transcribe_stt.py -v
"""

import base64

import pytest

from services.audio import stt_service as stt


class _FakeInteractions:
    def __init__(self, text="Upali svjetlo u dnevnoj sobi.", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return type("Interaction", (), {"output_text": self.text})()


class _FakeClient:
    def __init__(self, interactions):
        self.interactions = interactions


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("STT_ENGINE", "gemini_transcribe")
    monkeypatch.setenv("STT_LANGUAGE_CODE", "hr-HR")
    for name in ("GEMINI_TRANSCRIBE_MODEL", "GEMINI_TRANSCRIBE_LANGUAGES",
                 "GEMINI_TRANSCRIBE_MODE", "GEMINI_TRANSCRIBE_VOCABULARY",
                 "STT_FALLBACK_ENGINE"):
        monkeypatch.delenv(name, raising=False)
    return stt.STTService()


def _install(monkeypatch, interactions):
    monkeypatch.setattr(stt, "get_interactions_client", lambda: _FakeClient(interactions))
    return interactions


class TestRequestShape:

    @pytest.mark.asyncio
    async def test_audio_travels_inline_with_the_language_pinned(self, engine, monkeypatch):
        fake = _install(monkeypatch, _FakeInteractions())

        text = await engine.transcribe(b"RIFFfake-wav-bytes", "audio/wav")

        assert text == "Upali svjetlo u dnevnoj sobi."
        call = fake.calls[0]
        assert call["model"] == "gemini-3.5-transcribe"
        item = call["input"][0]
        assert item["type"] == "audio"
        assert item["mime_type"] == "audio/wav"
        assert base64.b64decode(item["data"]) == b"RIFFfake-wav-bytes"
        assert "uri" not in item  # no Files API round trip
        config = call["generation_config"]["transcription_config"]
        assert config["language_codes"] == ["hr-HR"]
        # Nothing is sent that was not asked for.
        assert "mode" not in config and "custom_vocabulary" not in config

    @pytest.mark.asyncio
    async def test_wav_aliases_and_pcm_carry_their_rate(self, engine, monkeypatch):
        fake = _install(monkeypatch, _FakeInteractions())

        await engine.transcribe(b"pcm", "audio/L16")

        item = fake.calls[0]["input"][0]
        assert item["mime_type"] == "audio/l16"
        assert item["rate"] == 16000 and item["channels"] == 1

    @pytest.mark.asyncio
    async def test_mode_and_vocabulary_come_from_the_environment(self, engine, monkeypatch):
        monkeypatch.setenv("GEMINI_TRANSCRIBE_MODE", "smart")
        monkeypatch.setenv("GEMINI_TRANSCRIBE_VOCABULARY", "Jarvis, kupaona , bojler")
        fake = _install(monkeypatch, _FakeInteractions())

        await engine.transcribe(b"wav", "audio/wav")

        config = fake.calls[0]["generation_config"]["transcription_config"]
        assert config["mode"] == {"type": "smart"}
        assert config["custom_vocabulary"] == ["Jarvis", "kupaona", "bojler"]

    @pytest.mark.asyncio
    async def test_vocabulary_is_cut_at_the_documented_limit(self, engine, monkeypatch):
        monkeypatch.setenv("GEMINI_TRANSCRIBE_VOCABULARY", ",".join(f"t{i}" for i in range(1200)))
        fake = _install(monkeypatch, _FakeInteractions())

        await engine.transcribe(b"wav", "audio/wav")

        assert len(fake.calls[0]["generation_config"]["transcription_config"]["custom_vocabulary"]) == 1000

    @pytest.mark.asyncio
    async def test_several_languages_can_be_listed(self, engine, monkeypatch):
        monkeypatch.setenv("GEMINI_TRANSCRIBE_LANGUAGES", "hr-HR, en-US")
        fake = _install(monkeypatch, _FakeInteractions())

        await engine.transcribe(b"wav", "audio/wav")

        assert fake.calls[0]["generation_config"]["transcription_config"]["language_codes"] == ["hr-HR", "en-US"]


class TestFailureFallsBackToChirp:

    @pytest.mark.asyncio
    async def test_api_failure_is_answered_by_chirp(self, engine, monkeypatch):
        _install(monkeypatch, _FakeInteractions(error=RuntimeError("429 credits depleted")))
        monkeypatch.setattr(
            stt.STTService, "_transcribe_cloud_sync", lambda self, audio: "chirp je čuo ovo"
        )

        assert await engine.transcribe(b"wav", "audio/wav") == "chirp je čuo ovo"

    @pytest.mark.asyncio
    async def test_unsupported_container_falls_back_rather_than_failing(self, engine, monkeypatch):
        _install(monkeypatch, _FakeInteractions())
        monkeypatch.setattr(
            stt.STTService, "_transcribe_cloud_sync", lambda self, audio: "chirp je čuo webm"
        )

        assert await engine.transcribe(b"webm", "audio/webm") == "chirp je čuo webm"

    @pytest.mark.asyncio
    async def test_fallback_can_be_switched_off(self, engine, monkeypatch):
        monkeypatch.setenv("STT_FALLBACK_ENGINE", "none")
        _install(monkeypatch, _FakeInteractions(error=RuntimeError("boom")))

        with pytest.raises(Exception, match="boom"):
            await engine.transcribe(b"wav", "audio/wav")


class TestOtherEnginesAreUntouched:

    @pytest.mark.asyncio
    async def test_chirp_never_reaches_the_interactions_api(self, monkeypatch):
        monkeypatch.setenv("STT_ENGINE", "chirp")
        service = stt.STTService()
        fake = _install(monkeypatch, _FakeInteractions())
        monkeypatch.setattr(
            stt.STTService, "_transcribe_cloud_sync", lambda self, audio: "chirp"
        )

        assert await service.transcribe(b"wav", "audio/wav") == "chirp"
        assert fake.calls == []
