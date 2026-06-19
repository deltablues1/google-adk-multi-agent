"""
Speech-to-Text Service
======================
Shared STT via Gemini multimodal. Used by:
  - Telegram voice handler (OGG/Opus -> text)
  - Wake word interface (PCM16 -> text)

Uses Gemini Flash with Google AI API key (same as TTS endpoint).
"""

import asyncio
import logging
import os

from config.google_runtime import (
    genai_vertex_env_keys,
    get_gemini_location,
    get_google_api_key,
    get_google_cloud_project,
)
from services.google_retry import run_with_bounded_retry
from tools.resilience.retry_handler import RetryConfig

logger = logging.getLogger(__name__)

# Supported MIME types for Gemini audio input
SUPPORTED_MIME_TYPES = {
    "audio/ogg",        # Telegram voice messages (OGG/Opus)
    "audio/wav",        # WAV files
    "audio/mpeg",       # MP3
    "audio/webm",       # WebM audio
    "audio/x-wav",      # Alternative WAV
    "audio/L16",        # Raw PCM16
}


def _stt_use_vertex() -> bool:
    override = os.getenv("STT_USE_VERTEXAI", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# --- Cloud Speech-to-Text v2 (Chirp) credentials --------------------------
# Cloud STT uses native per-language ASR (Chirp), far more reliable for
# Croatian than Gemini multimodal, especially on short utterances. We call the
# REST API with the service-account token via google.auth (no extra dependency).
_cloud_stt_creds = None


def _cloud_stt_access_token() -> str:
    global _cloud_stt_creds
    import google.auth
    from google.auth.transport.requests import Request as _AuthRequest

    if _cloud_stt_creds is None:
        _cloud_stt_creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if not _cloud_stt_creds.valid:
        _cloud_stt_creds.refresh(_AuthRequest())
    return _cloud_stt_creds.token


class STTService:
    """Speech-to-Text via Gemini multimodal audio input."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("STT_MODEL", "gemini-2.5-flash")
        self.default_language = os.getenv("STT_LANGUAGE", "Croatian").strip() or "Croatian"
        # STT engine: "gemini" (default, multimodal) or "chirp"/"cloud"
        # (Cloud Speech-to-Text v2, native Croatian ASR).
        self.engine = os.getenv("STT_ENGINE", "gemini").strip().lower()
        self.cloud_model = os.getenv("STT_CLOUD_MODEL", "chirp_2").strip() or "chirp_2"
        self.cloud_location = os.getenv("STT_CLOUD_LOCATION", "us-central1").strip() or "us-central1"
        self.cloud_language_code = os.getenv("STT_LANGUAGE_CODE", "hr-HR").strip() or "hr-HR"

    def _transcribe_cloud_sync(self, audio_bytes: bytes) -> str:
        """Transcribe via Cloud Speech-to-Text v2 (Chirp). Returns plain text."""
        import base64
        import json as _json
        import urllib.request

        project = get_google_cloud_project(required=True)
        location = self.cloud_location
        url = (
            "https://%s-speech.googleapis.com/v2/projects/%s/locations/%s"
            "/recognizers/_:recognize" % (location, project, location)
        )
        payload = {
            "config": {
                "model": self.cloud_model,
                "languageCodes": [self.cloud_language_code],
                "features": {"enableAutomaticPunctuation": True},
                "autoDecodingConfig": {},
            },
            "content": base64.b64encode(audio_bytes).decode("ascii"),
        }
        req = urllib.request.Request(
            url,
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer %s" % _cloud_stt_access_token(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
        parts = []
        for result in body.get("results", []):
            alternatives = result.get("alternatives") or []
            if alternatives and alternatives[0].get("transcript"):
                parts.append(alternatives[0]["transcript"].strip())
        return " ".join(parts).strip()

    def _openai_model(self) -> str:
        return os.getenv("OPENAI_STT_MODEL", "").strip() or "gpt-4o-transcribe"

    def _transcribe_openai_sync(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe via OpenAI audio transcriptions. Returns plain text."""
        import io
        from openai import OpenAI

        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set - required for STT_ENGINE=openai")
        client = OpenAI(api_key=key)

        ext = {
            "audio/ogg": "ogg",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
            "audio/webm": "webm",
            "audio/L16": "wav",
        }.get(mime_type, "wav")
        buf = io.BytesIO(audio_bytes)
        buf.name = "audio.%s" % ext

        # ISO-639-1 code; default Croatian. Overridable via OPENAI_STT_LANGUAGE.
        lang = os.getenv("OPENAI_STT_LANGUAGE", "").strip() or "hr"
        resp = client.audio.transcriptions.create(
            model=self._openai_model(),
            file=buf,
            language=lang,
        )
        return (getattr(resp, "text", "") or "").strip()

    def _get_client(self):
        from google import genai as _genai

        if _stt_use_vertex():
            project = get_google_cloud_project(required=True)
            location = get_gemini_location(default="global")
            # If an API key is present in the env, google-genai would attach it
            # to Vertex requests ("express mode"), which fails when the key is
            # not enabled for aiplatform.googleapis.com (API_KEY_SERVICE_BLOCKED).
            # Remove it during construction so the client authenticates via the
            # service account (ADC), exactly like the ADK agent path.
            _kkeys = ["GOOGLE_API_KEY", "GEMINI_API_KEY"]
            _kbackup = {k: os.environ.pop(k) for k in _kkeys if k in os.environ}
            try:
                return _genai.Client(vertexai=True, project=project, location=location)
            finally:
                os.environ.update(_kbackup)

        api_key = get_google_api_key()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set - required for STT")

        # Temporarily disable Vertex AI env vars (same pattern as TTS in web/app.py)
        _vkeys = genai_vertex_env_keys()
        _backup = {k: os.environ.pop(k) for k in _vkeys if k in os.environ}
        try:
            client = _genai.Client(api_key=api_key)
        finally:
            os.environ.update(_backup)
        return client

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/ogg",
        language: str | None = None,
    ) -> str:
        """
        Transcribe audio to text using Gemini multimodal.

        Args:
            audio_bytes: Raw audio data
            mime_type: Audio MIME type (audio/ogg, audio/wav, etc.)
            language: Target language for transcription. Falls back to STT_LANGUAGE env.

        Returns:
            Transcribed text string

        Raises:
            RuntimeError: If API key missing or transcription fails
            ValueError: If audio is empty or mime_type unsupported
        """
        if not audio_bytes:
            raise ValueError("Empty audio data")

        if mime_type not in SUPPORTED_MIME_TYPES:
            logger.warning(f"Unsupported MIME type {mime_type}, attempting anyway")

        # OpenAI STT path (opt-in via STT_ENGINE=openai). gpt-4o-transcribe has
        # strong Croatian accuracy; the Gemini/Chirp defaults are untouched.
        if self.engine == "openai":
            async def _call_openai():
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._transcribe_openai_sync, audio_bytes, mime_type
                )

            transcript = await run_with_bounded_retry(
                "stt_openai_transcribe",
                _call_openai,
                config=RetryConfig(max_retries=1, base_delay=1.0, max_delay=4.0),
                log=logger,
            )
            logger.info(
                f"STT[openai:{self._openai_model()}] transcription "
                f"({len(audio_bytes)} bytes): {transcript[:100]}"
            )
            return transcript

        # Native Cloud STT (Chirp) path — native Croatian ASR.
        if self.engine in {"chirp", "chirp_2", "chirp2", "cloud"}:
            async def _call_cloud():
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._transcribe_cloud_sync, audio_bytes
                )

            transcript = await run_with_bounded_retry(
                "stt_cloud_recognize",
                _call_cloud,
                config=RetryConfig(max_retries=1, base_delay=1.0, max_delay=4.0),
                log=logger,
            )
            logger.info(
                f"STT[{self.cloud_model}] transcription ({len(audio_bytes)} bytes): {transcript[:100]}"
            )
            return transcript

        client = self._get_client()
        from google.genai import types as _types
        target_language = (language or self.default_language).strip() or self.default_language

        prompt = (
            f"Transcribe this {target_language} audio message exactly as spoken. "
            f"The speaker is speaking {target_language}; do NOT interpret it as a "
            "different language (e.g. Polish, Russian, Serbian or Slovenian) and "
            "do NOT translate it. Preserve native orthography and diacritics "
            "(for Croatian: č, ć, š, ž, đ). "
            "Return ONLY the transcription text, nothing else. "
            "If the audio is unclear or empty, return '[nečujno]'."
        )

        audio_part = _types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = _types.Part.from_text(text=prompt)

        try:
            async def _call_model():
                return await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.models.generate_content(
                        model=self.model,
                        contents=[audio_part, text_part],
                    ),
                )

            response = await run_with_bounded_retry(
                "stt_transcribe",
                _call_model,
                config=RetryConfig(max_retries=1, base_delay=1.5, max_delay=6.0),
                log=logger,
            )
            transcript = response.text.strip()
            logger.info(f"STT transcription ({len(audio_bytes)} bytes): {transcript[:100]}...")
            return transcript

        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            raise RuntimeError(f"Transcription failed: {e}") from e

    async def transcribe_pcm16(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """
        Transcribe raw PCM16 audio (from microphone) to text.

        Wraps PCM bytes in a WAV container before sending to Gemini.

        Args:
            pcm_bytes: Raw PCM16 little-endian audio data
            sample_rate: Sample rate in Hz (default 16000)
            language: Target language. Falls back to STT_LANGUAGE env.

        Returns:
            Transcribed text string
        """
        import io
        import wave

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        wav_bytes = wav_buffer.getvalue()
        return await self.transcribe(wav_bytes, "audio/wav", language)
