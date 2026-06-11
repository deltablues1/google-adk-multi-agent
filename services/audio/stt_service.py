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


class STTService:
    """Speech-to-Text via Gemini multimodal audio input."""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("STT_MODEL", "gemini-2.5-flash")
        self.default_language = os.getenv("STT_LANGUAGE", "Croatian").strip() or "Croatian"

    def _get_client(self):
        from google import genai as _genai

        if _stt_use_vertex():
            project = get_google_cloud_project(required=True)
            location = get_gemini_location(default="global")
            return _genai.Client(vertexai=True, project=project, location=location)

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

        client = self._get_client()
        from google.genai import types as _types
        target_language = (language or self.default_language).strip() or self.default_language

        prompt = (
            f"Transcribe this {target_language} audio message exactly as spoken. "
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
