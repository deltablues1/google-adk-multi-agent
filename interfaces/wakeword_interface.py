"""
Wake Word Interface
===================
Listens for "Hey Jarvis" wake word via microphone, then:
  1. Records speech until silence
  2. Transcribes via shared STT service (Gemini)
  3. Sends text to orchestrator via /api/chat/stream (full agent access)
  4. Speaks response via /api/tts (Gemini TTS)

Architecture:
  - Separate process from web server (its own systemd service)
  - Connects to local web server as HTTP client
  - Wake word detection: OpenWakeWord (local, no API key)
  - STT: Gemini multimodal (shared service)
  - TTS: Web server's /api/tts endpoint

Requires:
  - openwakeword, pyaudio, webrtcvad
  - portaudio19-dev system package (apt install)
  - Mic HAT configured in ALSA
  - Web server running at api_url
"""

import asyncio
import logging
import struct
import io
import wave

logger = logging.getLogger(__name__)

# Audio constants
SAMPLE_RATE = 16000       # OpenWakeWord requires 16kHz
CHANNELS = 1              # Mono
SAMPLE_WIDTH = 2          # 16-bit PCM
CHUNK_SAMPLES = 1280      # 80ms chunks (OpenWakeWord optimal)
CHUNK_BYTES = CHUNK_SAMPLES * SAMPLE_WIDTH

# Silence detection
SILENCE_TIMEOUT = 2.0     # Seconds of silence to stop recording
MAX_RECORD_TIME = 30.0    # Maximum recording duration

# Wake word
WAKE_WORD_THRESHOLD = 0.5 # Detection confidence threshold


class WakeWordInterface:
    """Wake word listener -> STT -> orchestrator -> TTS -> speaker."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        wake_word: str = "hey_jarvis",
        threshold: float = WAKE_WORD_THRESHOLD,
        mic_device: int | None = None,
        speaker_device: int | None = None,
        api_token: str | None = None,
        user_id: str = "rpi-voice",
    ):
        self.api_url = api_url.rstrip("/")
        self.wake_word = wake_word
        self.threshold = threshold
        self.mic_device = mic_device
        self.speaker_device = speaker_device
        self.api_token = api_token
        self.user_id = user_id

        self._running = False
        self._speaking = False  # Half-duplex: mute mic during playback

        # Lazy imports (only available on RPi with proper deps)
        self._pyaudio = None
        self._oww_model = None
        self._vad = None
        self._stt = None

    def _init_audio(self):
        """Initialize PyAudio, OpenWakeWord, and VAD."""
        import pyaudio
        import openwakeword
        from openwakeword.model import Model as OWWModel
        import webrtcvad

        self._pyaudio = pyaudio.PyAudio()

        # Download/load wake word model
        openwakeword.utils.download_models()
        self._oww_model = OWWModel(
            wakeword_models=[self.wake_word],
            inference_framework="onnx",
        )

        # Voice Activity Detection for silence detection
        self._vad = webrtcvad.Vad(2)  # Aggressiveness 0-3 (2 = balanced)

        # Shared STT service
        from services.audio.stt_service import STTService
        self._stt = STTService()

        logger.info(f"Audio initialized: mic={self.mic_device}, wake_word={self.wake_word}")

    def _open_mic_stream(self):
        """Open microphone input stream."""
        return self._pyaudio.open(
            format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=self.mic_device,
            frames_per_buffer=CHUNK_SAMPLES,
        )

    async def start(self):
        """Main loop: wake word -> record -> STT -> agent -> TTS -> repeat."""
        self._init_audio()
        self._running = True
        logger.info(f"Wake word listener started (say '{self.wake_word.replace('_', ' ')}')")

        stream = self._open_mic_stream()

        try:
            while self._running:
                # Read mic chunk
                try:
                    audio_chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                except Exception:
                    await asyncio.sleep(0.01)
                    continue

                # Skip wake word detection while speaking (half-duplex)
                if self._speaking:
                    await asyncio.sleep(0.01)
                    continue

                # Feed to OpenWakeWord
                import numpy as np
                audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
                self._oww_model.predict(audio_array)

                # Check detection
                scores = self._oww_model.prediction_buffer.get(self.wake_word, [])
                if scores and scores[-1] >= self.threshold:
                    logger.info(f"Wake word detected! (score: {scores[-1]:.2f})")
                    self._oww_model.reset()

                    # Record until silence
                    recorded_audio = await self._record_until_silence(stream)
                    if not recorded_audio:
                        logger.info("No speech detected after wake word")
                        continue

                    # STT
                    try:
                        transcript = await self._stt.transcribe_pcm16(
                            recorded_audio, SAMPLE_RATE
                        )
                        if not transcript or transcript == "[nečujno]":
                            logger.info("STT returned empty/inaudible")
                            continue
                        logger.info(f"Transcript: {transcript}")
                    except Exception as e:
                        logger.error(f"STT failed: {e}")
                        continue

                    # Send to orchestrator
                    try:
                        response_text = await self._send_to_agent(transcript)
                        logger.info(f"Agent response: {response_text[:100]}...")
                    except Exception as e:
                        logger.error(f"Agent call failed: {e}")
                        continue

                    # TTS response through speaker
                    if response_text:
                        try:
                            await self._speak_response(response_text)
                        except Exception as e:
                            logger.error(f"TTS failed: {e}")

                # Yield to event loop
                await asyncio.sleep(0)

        finally:
            stream.stop_stream()
            stream.close()
            self._pyaudio.terminate()
            logger.info("Wake word listener stopped")

    async def _record_until_silence(self, stream) -> bytes | None:
        """Record mic audio until silence is detected (or max time)."""
        logger.info("Recording...")
        frames = []
        silent_chunks = 0
        total_chunks = 0

        # VAD works on 10/20/30ms frames at 16kHz
        vad_frame_ms = 30
        vad_frame_samples = SAMPLE_RATE * vad_frame_ms // 1000
        vad_frame_bytes = vad_frame_samples * SAMPLE_WIDTH

        silence_threshold = int(SILENCE_TIMEOUT * 1000 / vad_frame_ms)
        max_chunks = int(MAX_RECORD_TIME * 1000 / vad_frame_ms)

        while total_chunks < max_chunks:
            try:
                audio = stream.read(vad_frame_samples, exception_on_overflow=False)
            except Exception:
                break

            frames.append(audio)
            total_chunks += 1

            # Check VAD
            try:
                is_speech = self._vad.is_speech(audio, SAMPLE_RATE)
            except Exception:
                is_speech = True  # Assume speech on VAD error

            if is_speech:
                silent_chunks = 0
            else:
                silent_chunks += 1

            if silent_chunks >= silence_threshold and total_chunks > 10:
                break

            await asyncio.sleep(0)

        if total_chunks <= 5:
            return None

        logger.info(f"Recorded {total_chunks * vad_frame_ms}ms of audio")
        return b"".join(frames)

    async def _send_to_agent(self, text: str) -> str:
        """Send text to orchestrator via /api/chat/stream SSE endpoint."""
        import aiohttp

        url = f"{self.api_url}/api/chat/stream"
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        payload = {
            "message": text,
            "user_id": self.user_id,
        }

        response_parts = []

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Agent API returned {resp.status}: {body}")

                # Parse SSE stream (format: "event: type\ndata: content\n\n")
                current_event = ""
                async for raw_line in resp.content:
                    line_str = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                    if line_str.startswith("event:"):
                        current_event = line_str.split(":", 1)[1].strip()
                    elif line_str.startswith("data:"):
                        data = line_str.split(":", 1)[1].lstrip(" ")
                        if current_event == "text":
                            response_parts.append(data)
                        elif current_event == "done":
                            break
                    # Empty line = end of SSE block, reset event type
                    elif not line_str:
                        if current_event == "done":
                            break
                        current_event = ""

        return "".join(response_parts)

    async def _speak_response(self, text: str):
        """Convert text to speech via /api/tts and play through speaker."""
        import aiohttp

        self._speaking = True
        try:
            url = f"{self.api_url}/api/tts"
            headers = {"Content-Type": "application/json"}
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json={"text": text}, headers=headers
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"TTS API returned {resp.status}")
                        return

                    pcm_data = await resp.read()

            if not pcm_data:
                return

            # Play PCM16 @ 24kHz through speaker
            output_stream = self._pyaudio.open(
                format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
                channels=CHANNELS,
                rate=24000,  # TTS output is 24kHz
                output=True,
                output_device_index=self.speaker_device,
            )

            try:
                # Play in chunks to avoid blocking
                play_chunk_size = 4800  # 100ms at 24kHz
                for i in range(0, len(pcm_data), play_chunk_size):
                    chunk = pcm_data[i:i + play_chunk_size]
                    output_stream.write(chunk)
                    await asyncio.sleep(0)
            finally:
                output_stream.stop_stream()
                output_stream.close()

        finally:
            self._speaking = False

    def stop(self):
        """Signal the main loop to stop."""
        self._running = False
