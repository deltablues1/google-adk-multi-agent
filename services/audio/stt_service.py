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


class STTService:
    """Speech-to-Text via Gemini multimodal audio input."""

    def __init__(self, model: str = "gemini-2.5-flash-preview-04-17"):
        self.model = model

    def _get_client(self):
        """Create Gemini client with AI API key (not Vertex)."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set - required for STT")

        from google import genai as _genai

        # Temporarily disable Vertex AI env vars (same pattern as TTS in web/app.py)
        _vkeys = ['GOOGLE_GENAI_USE_VERTEXAI', 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION']
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
        language: str = "Croatian",
    ) -> str:
        """
        Transcribe audio to text using Gemini multimodal.

        Args:
            audio_bytes: Raw audio data
            mime_type: Audio MIME type (audio/ogg, audio/wav, etc.)
            language: Target language for transcription

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

        prompt = (
            f"Transcribe this {language} audio message exactly as spoken. "
            "Return ONLY the transcription text, nothing else. "
            "If the audio is unclear or empty, return '[nečujno]'."
        )

        audio_part = _types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
        text_part = _types.Part.from_text(prompt)

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model,
                    contents=[audio_part, text_part],
                )
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
        language: str = "Croatian",
    ) -> str:
        """
        Transcribe raw PCM16 audio (from microphone) to text.

        Wraps PCM bytes in a WAV container before sending to Gemini.

        Args:
            pcm_bytes: Raw PCM16 little-endian audio data
            sample_rate: Sample rate in Hz (default 16000)
            language: Target language

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
