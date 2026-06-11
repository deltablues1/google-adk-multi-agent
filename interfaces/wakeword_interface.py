"""
Wake Word Interface
===================
Listens for "Hey Jarvis" wake word via microphone, then:
  1. Says "Slušam."
  2. Records speech until silence
  3. Transcribes via shared STT service (Gemini)
  4. Sends text to the standard /api/chat endpoint
  5. Speaks response via /api/tts (Gemini TTS)
  6. Optionally asks "Treba li još nešto?" and listens briefly for a follow-up
"""

import asyncio
import audioop
import logging
import math
import os
import struct
import time
import unicodedata

from services.google_retry import classify_google_runtime_error, run_with_bounded_retry
from tools.resilience.retry_handler import RetryConfig

logger = logging.getLogger(__name__)


def _env_str(primary: str, fallback: str | None, default: str) -> str:
    value = os.getenv(primary, "").strip()
    if value:
        return value
    if fallback:
        fallback_value = os.getenv(fallback, "").strip()
        if fallback_value:
            return fallback_value
    return default


def _env_float(primary: str, fallback: str | None, default: float) -> float:
    raw = _env_str(primary, fallback, "")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(primary: str, fallback: str | None, default: int) -> int:
    raw = _env_str(primary, fallback, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

# Audio constants
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
CHUNK_SAMPLES = 1280  # 80 ms chunks (OpenWakeWord optimal)

# Recording limits
SILENCE_TIMEOUT = _env_float("VOICE_SILENCE_TIMEOUT", "WAKEWORD_SILENCE_SECONDS", 2.0)
MAX_RECORD_TIME = _env_float("VOICE_MAX_RECORD_TIME", "WAKEWORD_RECORD_SECONDS_MAX", 30.0)
PRE_SPEECH_TIMEOUT = float(os.getenv("VOICE_PRE_SPEECH_TIMEOUT", "8.0"))

# Wake word / follow-up
WAKE_WORD_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.4"))
FOLLOW_UP_MODE = os.getenv("VOICE_FOLLOW_UP_MODE", "false").lower() in (
    "1", "true", "yes", "on"
)
FOLLOW_UP_TIMEOUT = float(os.getenv("VOICE_FOLLOW_UP_TIMEOUT", "4.0"))
FOLLOW_UP_MIN_SPEECH_FRAMES = int(os.getenv("VOICE_FOLLOW_UP_MIN_SPEECH_FRAMES", "3"))
FOLLOW_UP_MAX_TURNS = int(os.getenv("VOICE_FOLLOW_UP_MAX_TURNS", "4"))
SILENCE_RMS_THRESHOLD = int(os.getenv("VOICE_SILENCE_RMS_THRESHOLD", "170"))
SPEECH_RMS_THRESHOLD = _env_int("VOICE_SPEECH_RMS_THRESHOLD", "WAKEWORD_ENERGY_THRESHOLD", 260)
DEBUG_AUDIO_METRICS = os.getenv("VOICE_DEBUG_AUDIO_METRICS", "false").lower() in (
    "1", "true", "yes", "on"
)
WAKE_PROMPT_TEXT = os.getenv("VOICE_WAKE_PROMPT_TEXT", "Slušam.").strip()
FOLLOW_UP_PROMPT_TEXT = os.getenv("VOICE_FOLLOW_UP_PROMPT_TEXT", "Treba li još nešto?").strip()
AGENT_TIMEOUT_SECONDS = int(os.getenv("VOICE_AGENT_TIMEOUT_SECONDS", "90"))
TTS_TIMEOUT_SECONDS = int(os.getenv("VOICE_TTS_TIMEOUT_SECONDS", "35"))
TTS_STREAM_MIN_PLAY_BYTES = int(os.getenv("VOICE_TTS_STREAM_MIN_PLAY_BYTES", "4800"))
TTS_STREAM_MAX_CHARS = int(os.getenv("VOICE_TTS_STREAM_MAX_CHARS", "320"))
SAFE_AGENT_RETRY_ROUTES = {"voice_qa", "christian_guide", "socrates", "secretary"}
VOICE_SMART_HOME_RESPONSE_MODE = os.getenv(
    "VOICE_SMART_HOME_RESPONSE_MODE",
    "none",
).strip().lower()
SUPPRESS_LISTENING_CUE_WHEN_PROMPT = os.getenv(
    "VOICE_SUPPRESS_LISTENING_CUE_WHEN_PROMPT",
    "true",
).lower() in ("1", "true", "yes", "on")
NO_SPEECH_CUE = os.getenv("VOICE_NO_SPEECH_CUE", "true").lower() in (
    "1", "true", "yes", "on"
)
LOCAL_SMART_HOME_FAST_PATH = os.getenv(
    "VOICE_LOCAL_SMART_HOME_FAST_PATH",
    "true",
).lower() in ("1", "true", "yes", "on")

SMART_HOME_ROOM_SYNONYMS = {
    "boravak": ("boravak", "dnevni", "dnevni boravak", "dnevnom boravku"),
    "kupaona": ("kupaona", "kupaonici", "kupatilo", "kupatilu"),
    "kuhinja": ("kuhinja", "kuhinji"),
    "hodnik": ("hodnik", "hodniku"),
    "terasa": ("terasa", "terasi"),
    "ulaz": ("ulaz",),
    "blagavaona": ("blagavaona", "blagovaona", "blagavaonici", "blagovaonici"),
    "soba1": ("soba 1", "soba1"),
    "soba2": ("soba 2", "soba2"),
    "vani": ("vani", "dvoriste", "dvoristu"),
}

YES_WORDS = {"da", "moze", "potvrdi", "tocno", "izvrsi"}
NO_WORDS = {"ne", "nemoj", "odustani", "prekini", "stop", "cancel", "ponisti"}
FOLLOW_UP_EXIT_PREFIXES = (
    "ne",
    "ne hvala",
    "hvala",
    "to je sve",
    "to je to",
    "nista",
    "ništa",
    "dosta",
    "nemam vise",
    "nemam više",
)
TIME_DATE_KEYWORDS = (
    "koliko je sati",
    "koliko sati",
    "koliko je ura",
    "koji je datum",
    "koji je dan",
    "koji dan",
    "datum",
    "vrijeme",
)
BUSINESS_KEYWORDS = (
    "mail",
    "email",
    "gmail",
    "kalendar",
    "calendar",
    "drive",
    "docs",
    "dokument",
    "dokumenti",
    "sheet",
    "sheets",
    "tablica",
    "tablice",
    "zadatak",
    "zadaci",
    "kontakt",
    "kontakti",
)
CHRISTIAN_KEYWORDS = (
    "krsc",
    "kršć",
    "biblij",
    "katekiz",
    "molitv",
    "duhovn",
    "augustin",
    "ignacije",
    "razluc",
    "razluč",
    "examen",
    "egzamen",
)
PHILOSOPHY_KEYWORDS = (
    "filozof",
    "filozofij",
    "sokrat",
    "platon",
    "aristotel",
    "stoic",
    "stoik",
    "epiktet",
    "seneka",
    "marko aurelije",
)
GENERAL_VOICE_PREFIXES = (
    "sto ",
    "što ",
    "tko ",
    "ko je ",
    "objasni",
    "reci mi",
    "reci nesto",
    "reci nešto",
    "kako ",
    "zasto ",
    "zašto ",
)


class WakeWordInterface:
    """Wake word listener -> STT -> agent -> TTS -> speaker."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        wake_word: str = "hey_jarvis",
        threshold: float = WAKE_WORD_THRESHOLD,
        mic_device: int | None = None,
        speaker_device: int | None = None,
        api_token: str | None = None,
        user_id: str = "rpi-voice",
        listening_cue: bool = True,
    ):
        self.api_url = api_url.rstrip("/")
        self.wake_word = wake_word
        self.threshold = threshold
        self.mic_device = mic_device
        self.speaker_device = speaker_device
        self.api_token = api_token
        self.user_id = user_id
        self.listening_cue = listening_cue

        self._running = False
        self._speaking = False
        self._pending_confirmation: dict | None = None
        self._tts_cache: dict[str, bytes] = {}
        self._tts_cache_warm_task: asyncio.Task | None = None
        self._active_followup_lane: str | None = None

        self._pyaudio = None
        self._oww_model = None
        self._vad = None
        self._stt = None

    def _init_audio(self):
        import pyaudio
        import openwakeword
        from openwakeword.model import Model as OWWModel
        import webrtcvad

        self._pyaudio = pyaudio.PyAudio()
        openwakeword.utils.download_models()
        self._oww_model = OWWModel(
            wakeword_models=[self.wake_word],
            inference_framework="onnx",
        )
        self._vad = webrtcvad.Vad(2)

        from services.audio.stt_service import STTService

        self._stt = STTService()
        logger.info("Audio initialized: mic=%s, wake_word=%s", self.mic_device, self.wake_word)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.lower())
        return "".join(ch for ch in normalized if not unicodedata.combining(ch))

    def _open_mic_stream(self):
        return self._pyaudio.open(
            format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=self.mic_device,
            frames_per_buffer=CHUNK_SAMPLES,
        )

    def _use_listening_cue(self) -> bool:
        if not self.listening_cue:
            return False
        if WAKE_PROMPT_TEXT and SUPPRESS_LISTENING_CUE_WHEN_PROMPT:
            return False
        return True

    def _reset_wake_model(self):
        try:
            if self._oww_model is not None:
                self._oww_model.reset()
        except Exception:
            logger.debug("Wake model reset failed", exc_info=True)

    async def _play_listening_cue(self):
        if not self._pyaudio:
            return

        cue_rate = 24000
        cue_volume = 0.22
        segments = [
            (880, 0.09),
            (0, 0.04),
            (1175, 0.11),
        ]

        pcm = bytearray()
        for freq, duration_s in segments:
            samples = int(cue_rate * duration_s)
            if freq <= 0:
                pcm.extend(b"\x00\x00" * samples)
                continue
            for i in range(samples):
                sample = int(
                    32767 * cue_volume * math.sin(2 * math.pi * freq * (i / cue_rate))
                )
                pcm.extend(struct.pack("<h", sample))

        self._speaking = True
        output_stream = None
        try:
            output_stream = self._pyaudio.open(
                format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
                channels=CHANNELS,
                rate=cue_rate,
                output=True,
                output_device_index=self.speaker_device,
            )
            output_stream.write(bytes(pcm))
            await asyncio.sleep(0)
        finally:
            if output_stream is not None:
                output_stream.stop_stream()
                output_stream.close()
            self._speaking = False
            self._reset_wake_model()

    async def _play_no_speech_cue(self):
        if not self._pyaudio:
            return

        cue_rate = 24000
        cue_volume = 0.18
        segments = [
            (880, 0.08),
            (0, 0.03),
            (660, 0.10),
        ]

        pcm = bytearray()
        for freq, duration_s in segments:
            samples = int(cue_rate * duration_s)
            if freq <= 0:
                pcm.extend(b"\x00\x00" * samples)
                continue
            for i in range(samples):
                sample = int(
                    32767 * cue_volume * math.sin(2 * math.pi * freq * (i / cue_rate))
                )
                pcm.extend(struct.pack("<h", sample))

        self._speaking = True
        output_stream = None
        try:
            output_stream = self._pyaudio.open(
                format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
                channels=CHANNELS,
                rate=cue_rate,
                output=True,
                output_device_index=self.speaker_device,
            )
            output_stream.write(bytes(pcm))
            await asyncio.sleep(0)
        finally:
            if output_stream is not None:
                output_stream.stop_stream()
                output_stream.close()
            self._speaking = False
            self._reset_wake_model()

    def _extract_smart_home_rooms(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        found = []
        for room, variants in SMART_HOME_ROOM_SYNONYMS.items():
            if any(variant in normalized for variant in variants):
                found.append(room)
        return found

    def _looks_like_smart_home_command(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        keywords = ("svjetlo", "ukljuci", "upali", "ugas", "bojler", "utic", "scena")
        return any(keyword in normalized for keyword in keywords) or bool(
            self._extract_smart_home_rooms(text)
        )

    def _is_time_or_date_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(keyword in normalized for keyword in TIME_DATE_KEYWORDS)

    def _looks_like_business_task(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        return any(keyword in normalized for keyword in BUSINESS_KEYWORDS)

    def _should_offer_followup(self, text: str) -> bool:
        normalized = self._normalize_text(text)

        if self._looks_like_smart_home_command(text):
            return False
        if self._is_time_or_date_request(text):
            return False
        if self._looks_like_business_task(text):
            return False
        if normalized.startswith(GENERAL_VOICE_PREFIXES):
            return True
        if any(keyword in normalized for keyword in CHRISTIAN_KEYWORDS):
            return True
        if any(keyword in normalized for keyword in PHILOSOPHY_KEYWORDS):
            return True

        return True

    def _is_followup_exit_phrase(self, text: str) -> bool:
        normalized = self._normalize_text(text).strip(" .!?")
        return any(
            normalized == phrase or normalized.startswith(f"{phrase} ")
            for phrase in FOLLOW_UP_EXIT_PREFIXES
        )

    def _determine_conversational_lane(self, text: str) -> str | None:
        normalized = self._normalize_text(text)
        if self._looks_like_smart_home_command(text):
            return "smart_home"
        if self._is_time_or_date_request(text):
            return "secretary"
        if self._looks_like_business_task(text):
            return None
        if any(keyword in normalized for keyword in CHRISTIAN_KEYWORDS):
            return "christian_guide"
        if any(keyword in normalized for keyword in PHILOSOPHY_KEYWORDS):
            return "socrates"
        if normalized.startswith(GENERAL_VOICE_PREFIXES):
            return "voice_qa"
        if self._should_offer_followup(text):
            return "voice_qa"
        return None

    def _resolve_route_hint(self, text: str) -> str | None:
        explicit_lane = self._determine_conversational_lane(text)

        if explicit_lane in {"smart_home", "secretary"}:
            return explicit_lane

        if self._looks_like_business_task(text):
            return None

        if explicit_lane in {"christian_guide", "socrates", "voice_qa"}:
            return explicit_lane

        if self._active_followup_lane in {"christian_guide", "socrates", "voice_qa"}:
            return self._active_followup_lane

        return explicit_lane

    def _build_confirmation_prompt(self, rooms: list[str]) -> str:
        room_text = ", ".join(rooms)
        if len(rooms) == 1:
            return (
                f"Cuo sam naredbu za {room_text}, ali transkript nije dovoljno cist. "
                "Zelis li da ipak izvrsim tu naredbu?"
            )
        return (
            f"Cuo sam vise prostorija: {room_text}. "
            "Zelis li da izvrsim sve te naredbe?"
        )

    def _maybe_require_confirmation(self, transcript: str) -> str | None:
        if self._pending_confirmation is not None:
            return None
        if not self._looks_like_smart_home_command(transcript):
            return None

        rooms = self._extract_smart_home_rooms(transcript)
        if len(rooms) < 2:
            return None

        self._pending_confirmation = {
            "original_transcript": transcript,
            "rooms": rooms or ["vise akcija"],
        }
        return self._build_confirmation_prompt(self._pending_confirmation["rooms"])

    def _handle_confirmation_reply(self, transcript: str) -> tuple[str | None, str | None]:
        if self._pending_confirmation is None:
            return transcript, None

        words = set(self._normalize_text(transcript).split())
        pending = self._pending_confirmation

        if words & YES_WORDS:
            self._pending_confirmation = None
            return pending["original_transcript"], None

        if words & NO_WORDS:
            self._pending_confirmation = None
            return None, "U redu, nisam nista izvrsio."

        rooms_text = ", ".join(pending["rooms"])
        return None, f"Molim reci samo da ili ne. Pitao sam za: {rooms_text}."

    async def _record_until_silence(
        self,
        stream,
        prefix_audio: list[bytes] | None = None,
        pre_speech_timeout: float | None = None,
    ) -> bytes | None:
        """Record user speech until post-speech silence is detected."""
        logger.info("Recording...")

        frames = list(prefix_audio or [])
        vad_frame_ms = 30
        vad_frame_samples = SAMPLE_RATE * vad_frame_ms // 1000
        silence_chunks_required = int(SILENCE_TIMEOUT * 1000 / vad_frame_ms)
        max_chunks = int(MAX_RECORD_TIME * 1000 / vad_frame_ms)
        pre_speech_chunks_limit = int((pre_speech_timeout or PRE_SPEECH_TIMEOUT) * 1000 / vad_frame_ms)

        speech_started = bool(frames)
        silent_chunks = 0
        total_chunks = 0
        waiting_chunks = 0
        rms_samples: list[int] = []
        vad_speech_chunks = 0
        force_silence_chunks = 0

        while total_chunks < max_chunks:
            try:
                audio = stream.read(vad_frame_samples, exception_on_overflow=False)
            except Exception:
                break

            total_chunks += 1
            rms = audioop.rms(audio, SAMPLE_WIDTH)
            rms_samples.append(rms)
            try:
                is_speech = self._vad.is_speech(audio, SAMPLE_RATE)
            except Exception:
                is_speech = rms >= SPEECH_RMS_THRESHOLD

            if is_speech:
                vad_speech_chunks += 1
            speech_like = is_speech or rms >= SPEECH_RMS_THRESHOLD
            silence_like = rms <= SILENCE_RMS_THRESHOLD

            if not speech_started:
                waiting_chunks += 1
                if speech_like:
                    speech_started = True
                    frames.append(audio)
                    silent_chunks = 0
                elif waiting_chunks >= pre_speech_chunks_limit:
                    logger.info("No speech start detected within %.1fs", pre_speech_timeout or PRE_SPEECH_TIMEOUT)
                    return None
                await asyncio.sleep(0)
                continue

            frames.append(audio)

            # Let a clearly low RMS floor override VAD false-positives. This is
            # the main escape hatch that stops 30s recordings in noisy rooms.
            if silence_like:
                silent_chunks += 1
                force_silence_chunks += 1
            elif (not is_speech) and rms < SPEECH_RMS_THRESHOLD:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= silence_chunks_required:
                break

            await asyncio.sleep(0)

        if not frames:
            return None

        captured_ms = len(frames) * vad_frame_ms
        if DEBUG_AUDIO_METRICS and rms_samples:
            avg_rms = sum(rms_samples) // len(rms_samples)
            logger.info(
                "Recorded %sms of audio (avg_rms=%s max_rms=%s vad_speech_chunks=%s force_silence_chunks=%s speech_threshold=%s silence_threshold=%s)",
                captured_ms,
                avg_rms,
                max(rms_samples),
                vad_speech_chunks,
                force_silence_chunks,
                SPEECH_RMS_THRESHOLD,
                SILENCE_RMS_THRESHOLD,
            )
        else:
            logger.info("Recorded %sms of audio", captured_ms)
        return b"".join(frames)

    async def _wait_for_followup(self, stream) -> bytes | None:
        """Listen briefly for a real follow-up after asking the user."""
        logger.info("Waiting for follow-up...")

        vad_frame_ms = 30
        vad_frame_samples = SAMPLE_RATE * vad_frame_ms // 1000
        max_chunks = int(FOLLOW_UP_TIMEOUT * 1000 / vad_frame_ms)
        speech_frames = []
        consecutive_speech = 0

        for _ in range(max_chunks):
            try:
                audio = stream.read(vad_frame_samples, exception_on_overflow=False)
            except Exception:
                return None

            rms = audioop.rms(audio, SAMPLE_WIDTH)
            try:
                is_speech = self._vad.is_speech(audio, SAMPLE_RATE)
            except Exception:
                is_speech = False

            if rms >= SPEECH_RMS_THRESHOLD and is_speech:
                speech_frames.append(audio)
                consecutive_speech += 1
                if consecutive_speech >= FOLLOW_UP_MIN_SPEECH_FRAMES:
                    logger.info("Follow-up detected")
                    return await self._record_until_silence(
                        stream,
                        prefix_audio=speech_frames,
                        pre_speech_timeout=1.0,
                    )
            else:
                speech_frames.clear()
                consecutive_speech = 0

            await asyncio.sleep(0)

        logger.info("No follow-up detected")
        return None

    async def _send_to_agent(
        self,
        text: str,
        route_hint: str | None = None,
        response_mode: str | None = None,
    ) -> str:
        import aiohttp

        url = f"{self.api_url}/api/chat"
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        payload = {
            "message": text,
            "user_id": self.user_id,
        }
        if route_hint:
            payload["route_hint"] = route_hint
        if response_mode:
            payload["response_mode"] = response_mode

        timeout = aiohttp.ClientTimeout(
            total=AGENT_TIMEOUT_SECONDS,
            connect=15,
            sock_connect=15,
            sock_read=AGENT_TIMEOUT_SECONDS,
        )

        should_retry = route_hint in SAFE_AGENT_RETRY_ROUTES

        async def _post_once() -> str:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Agent API returned {resp.status}: {body}")
                    body = await resp.json()
            return body.get("response", "")

        try:
            if should_retry:
                return await run_with_bounded_retry(
                    f"voice_agent_{route_hint}",
                    _post_once,
                    config=RetryConfig(max_retries=1, base_delay=1.5, max_delay=6.0),
                    log=logger,
                )
            return await _post_once()
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Agent response timed out") from exc

    def _should_cache_tts(self, text: str) -> bool:
        return text in {
            WAKE_PROMPT_TEXT,
            FOLLOW_UP_PROMPT_TEXT,
            "Trenutno ne mogu dovrsiti odgovor. Pokusaj ponovo.",
            "U redu, nisam nista izvrsio.",
        }

    def _should_stream_tts(self, text: str) -> bool:
        if self._should_cache_tts(text):
            return False
        return len(text.strip()) <= TTS_STREAM_MAX_CHARS

    async def _fetch_tts_pcm(self, text: str) -> bytes:
        import aiohttp

        url = f"{self.api_url}/api/tts"
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        timeout = aiohttp.ClientTimeout(
            total=TTS_TIMEOUT_SECONDS,
            connect=10,
            sock_connect=10,
            sock_read=TTS_TIMEOUT_SECONDS,
        )

        async def _post_once() -> bytes:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={"text": text, "stream": False},
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"TTS API returned {resp.status}")
                    return await resp.read()

        return await run_with_bounded_retry(
            "voice_tts_unary",
            _post_once,
            config=RetryConfig(max_retries=1, base_delay=1.0, max_delay=4.0),
            log=logger,
        )

    async def _stream_tts_to_speaker(self, text: str) -> tuple[bool, bool]:
        import aiohttp

        url = f"{self.api_url}/api/tts"
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        timeout = aiohttp.ClientTimeout(
            total=TTS_TIMEOUT_SECONDS + 10,
            connect=10,
            sock_connect=10,
            sock_read=TTS_TIMEOUT_SECONDS + 10,
        )

        attempt = 0
        max_retries = 1
        while True:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url,
                    json={"text": text, "stream": True},
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        exc = RuntimeError(f"TTS API returned {resp.status}")
                        error_type, retryable, is_quota = classify_google_runtime_error(exc)
                        if attempt >= max_retries or not retryable:
                            raise exc
                        attempt += 1
                        delay = 1.0 * attempt
                        logger.warning(
                            "voice_tts_stream failed (%s quota=%s), retrying in %.2fs",
                            error_type,
                            is_quota,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                    output_stream = self._pyaudio.open(
                        format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
                        channels=CHANNELS,
                        rate=24000,
                        output=True,
                        output_device_index=self.speaker_device,
                    )

                    audio_buf = bytearray()
                    playback_started = False

                    try:
                        async for chunk in resp.content.iter_chunked(2048):
                            if not chunk:
                                continue
                            audio_buf.extend(chunk)
                            if len(audio_buf) >= TTS_STREAM_MIN_PLAY_BYTES:
                                output_stream.write(bytes(audio_buf))
                                audio_buf = bytearray()
                                playback_started = True
                                await asyncio.sleep(0)

                        if audio_buf:
                            output_stream.write(bytes(audio_buf))
                            playback_started = True
                            await asyncio.sleep(0)
                    finally:
                        output_stream.stop_stream()
                        output_stream.close()

                    return playback_started, playback_started

    async def _warm_tts_cache(self):
        logger.info("Warming TTS cache...")
        texts = [WAKE_PROMPT_TEXT]
        if FOLLOW_UP_MODE and FOLLOW_UP_PROMPT_TEXT:
            texts.append(FOLLOW_UP_PROMPT_TEXT)

        for text in texts:
            if not text or text in self._tts_cache:
                continue
            try:
                pcm_data = await self._fetch_tts_pcm(text)
                if pcm_data:
                    self._tts_cache[text] = pcm_data
            except Exception as exc:
                logger.warning("TTS cache warmup failed for '%s': %s", text, exc)

    def _start_tts_cache_warmup(self):
        if self._tts_cache_warm_task and not self._tts_cache_warm_task.done():
            return

        async def _runner():
            try:
                await self._warm_tts_cache()
            finally:
                self._tts_cache_warm_task = None

        self._tts_cache_warm_task = asyncio.create_task(_runner())

    @staticmethod
    def _recorded_audio_ms(audio_bytes: bytes | None) -> int:
        if not audio_bytes:
            return 0
        return int(len(audio_bytes) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000)

    @staticmethod
    def _classify_exception(exc: Exception) -> tuple[str, bool]:
        error_type, _, is_quota = classify_google_runtime_error(exc)
        return error_type, is_quota

    def _emit_voice_event(self, event_type: str, payload: dict) -> None:
        try:
            from monitoring.metrics import get_metrics_collector

            get_metrics_collector().log_event(event_type, payload)
        except Exception:
            logger.debug("Voice telemetry export failed", exc_info=True)

    async def _speak_response(self, text: str):
        self._speaking = True
        try:
            try:
                pcm_data = self._tts_cache.get(text)
                if pcm_data is None and self._should_stream_tts(text):
                    try:
                        streamed, completed = await self._stream_tts_to_speaker(text)
                        if streamed or completed:
                            return
                    except Exception as exc:
                        logger.warning("TTS streaming failed before playback, falling back to unary: %s", exc)

                if pcm_data is None:
                    pcm_data = await self._fetch_tts_pcm(text)
                    if pcm_data and self._should_cache_tts(text):
                        self._tts_cache[text] = pcm_data
            except asyncio.TimeoutError:
                logger.error("TTS request timed out")
                return
            except Exception as exc:
                logger.error("TTS request failed: %s", exc)
                return

            if not pcm_data:
                return

            output_stream = self._pyaudio.open(
                format=self._pyaudio.get_format_from_width(SAMPLE_WIDTH),
                channels=CHANNELS,
                rate=24000,
                output=True,
                output_device_index=self.speaker_device,
            )

            try:
                play_chunk_size = 4800
                for i in range(0, len(pcm_data), play_chunk_size):
                    output_stream.write(pcm_data[i:i + play_chunk_size])
                    await asyncio.sleep(0)
            finally:
                output_stream.stop_stream()
                output_stream.close()

        finally:
            self._speaking = False
            self._reset_wake_model()

    async def _run_turn(
        self,
        stream,
        recorded_audio: bytes | None,
        allow_followup: bool,
        followup_turns_remaining: int | None = None,
        turn_started_at: float | None = None,
    ) -> None:
        from monitoring.metrics import get_metrics_collector

        metrics = get_metrics_collector()
        turn_started_at = turn_started_at or time.perf_counter()
        route_hint: str | None = None
        transcript = ""
        transcript_to_run: str | None = None
        response_text = ""
        response_mode: str | None = None
        summary_error_type = ""
        summary_quota_error = False
        stt_elapsed_ms = 0
        agent_elapsed_ms = 0
        tts_elapsed_ms = 0
        local_fast_elapsed_ms = 0
        local_smart_home_fast = False
        agent_call_failed = False
        audio_ms = self._recorded_audio_ms(recorded_audio)

        def emit_summary(outcome: str, error_message: str | None = None) -> None:
            total_elapsed_ms = int((time.perf_counter() - turn_started_at) * 1000)
            labels = {
                "route": route_hint or "none",
                "outcome": outcome,
                "local_fast": str(local_smart_home_fast),
            }
            metrics.record_timing("voice_turn_latency", total_elapsed_ms / 1000, labels=labels)
            self._emit_voice_event(
                "voice_turn_summary",
                {
                    "user_id": self.user_id,
                    "route_hint": route_hint,
                    "outcome": outcome,
                    "allow_followup": allow_followup,
                    "followup_turns_remaining": followup_turns_remaining,
                    "local_smart_home_fast": local_smart_home_fast,
                    "audio_ms": audio_ms,
                    "audio_bytes": len(recorded_audio or b""),
                    "transcript_chars": len(transcript),
                    "transcript_preview": transcript[:180],
                    "response_chars": len(response_text or ""),
                    "response_mode": response_mode,
                    "stt_elapsed_ms": stt_elapsed_ms,
                    "agent_elapsed_ms": agent_elapsed_ms,
                    "tts_elapsed_ms": tts_elapsed_ms,
                    "local_fast_elapsed_ms": local_fast_elapsed_ms,
                    "total_elapsed_ms": total_elapsed_ms,
                    "error_type": summary_error_type,
                    "quota_error": summary_quota_error,
                    "error": error_message or "",
                },
            )

        if not recorded_audio:
            logger.info("No speech detected after wake word")
            metrics.increment("voice_turn_no_speech", labels={"channel": "wakeword"})
            emit_summary("no_speech")
            self._active_followup_lane = None
            if NO_SPEECH_CUE:
                try:
                    await self._play_no_speech_cue()
                except Exception as exc:
                    logger.debug("No-speech cue failed: %s", exc)
            return

        try:
            stt_started_at = time.perf_counter()
            transcript = await self._stt.transcribe_pcm16(recorded_audio, SAMPLE_RATE)
            stt_elapsed_ms = int((time.perf_counter() - stt_started_at) * 1000)
            metrics.record_timing(
                "voice_stt_latency",
                stt_elapsed_ms / 1000,
                labels={"channel": "wakeword"},
            )
            normalized = self._normalize_text(transcript or "")
            if not transcript or "necujno" in normalized:
                logger.info("STT returned empty/inaudible")
                emit_summary("inaudible")
                self._active_followup_lane = None
                if NO_SPEECH_CUE:
                    try:
                        await self._play_no_speech_cue()
                    except Exception as exc:
                        logger.debug("No-speech cue failed: %s", exc)
                return
            logger.info("Transcript: %s", transcript)
        except Exception as exc:
            logger.error("STT failed: %s", exc)
            error_type, is_quota = self._classify_exception(exc)
            summary_error_type = error_type
            summary_quota_error = is_quota
            metrics.record_error(
                "voice_stt_error",
                labels={"channel": "wakeword", "error_type": error_type},
            )
            if is_quota:
                metrics.increment("voice_quota_error", labels={"service": "stt"})
            emit_summary("stt_error", str(exc))
            return

        if allow_followup and self._is_followup_exit_phrase(transcript):
            logger.info("Follow-up exit phrase detected")
            emit_summary("followup_exit")
            self._active_followup_lane = None
            return

        route_hint = self._resolve_route_hint(transcript)
        transcript_to_run, immediate_response = self._handle_confirmation_reply(transcript)
        if transcript_to_run is not None and immediate_response is None:
            immediate_response = self._maybe_require_confirmation(transcript_to_run)
            if immediate_response:
                transcript_to_run = None

        response_text = immediate_response
        if transcript_to_run:
            try:
                response_mode = (
                    VOICE_SMART_HOME_RESPONSE_MODE
                    if route_hint == "smart_home"
                    else None
                )
                if route_hint == "smart_home" and LOCAL_SMART_HOME_FAST_PATH:
                    from services.voice_fast_path import execute_fast_smart_home_command

                    local_started_at = time.perf_counter()
                    fast_response = await execute_fast_smart_home_command(
                        transcript_to_run,
                        response_mode=response_mode,
                    )
                    local_fast_elapsed_ms = int((time.perf_counter() - local_started_at) * 1000)
                    metrics.record_timing(
                        "voice_smart_home_local_latency",
                        local_fast_elapsed_ms / 1000,
                        labels={"success": str(fast_response is not None)},
                    )
                    if fast_response is not None:
                        local_smart_home_fast = True
                        response_text = fast_response
                        logger.info("Local voice smart_home fast path hit")
                    else:
                        agent_started_at = time.perf_counter()
                        response_text = await self._send_to_agent(
                            transcript_to_run,
                            route_hint=route_hint,
                            response_mode=response_mode,
                        )
                        agent_elapsed_ms = int((time.perf_counter() - agent_started_at) * 1000)
                else:
                    agent_started_at = time.perf_counter()
                    response_text = await self._send_to_agent(
                        transcript_to_run,
                        route_hint=route_hint,
                        response_mode=response_mode,
                    )
                    agent_elapsed_ms = int((time.perf_counter() - agent_started_at) * 1000)

                if agent_elapsed_ms:
                    metrics.record_timing(
                        "voice_agent_latency",
                        agent_elapsed_ms / 1000,
                        labels={"route": route_hint or "none"},
                    )
                logger.info("Agent response: %s...", response_text[:100])
            except Exception as exc:
                logger.error("Agent call failed: %s", exc)
                agent_call_failed = True
                error_type, is_quota = self._classify_exception(exc)
                summary_error_type = error_type
                summary_quota_error = is_quota
                metrics.record_error(
                    "voice_agent_error",
                    labels={
                        "channel": "wakeword",
                        "route": route_hint or "none",
                        "error_type": error_type,
                    },
                )
                if is_quota:
                    metrics.increment("voice_quota_error", labels={"service": "agent"})
                response_text = "Trenutno ne mogu dovrsiti odgovor. Pokusaj ponovo."
        elif response_text:
            logger.info("Voice guard response: %s...", response_text[:100])

        if route_hint in {"voice_qa", "christian_guide", "socrates"}:
            self._active_followup_lane = route_hint
        elif route_hint in {"smart_home", "secretary"} or self._looks_like_business_task(transcript):
            self._active_followup_lane = None

        if response_text:
            try:
                tts_started_at = time.perf_counter()
                await self._speak_response(response_text)
                tts_elapsed_ms = int((time.perf_counter() - tts_started_at) * 1000)
                metrics.record_timing(
                    "voice_tts_latency",
                    tts_elapsed_ms / 1000,
                    labels={"channel": "wakeword"},
                )
            except Exception as exc:
                logger.error("TTS failed: %s", exc)
                error_type, is_quota = self._classify_exception(exc)
                summary_error_type = error_type
                summary_quota_error = is_quota
                metrics.record_error(
                    "voice_tts_error",
                    labels={"channel": "wakeword", "error_type": error_type},
                )
                if is_quota:
                    metrics.increment("voice_quota_error", labels={"service": "tts"})
                emit_summary("tts_error", str(exc))
                return

        if agent_call_failed:
            emit_summary("agent_error", response_text)
            self._active_followup_lane = None
            return

        if (
            not allow_followup
            or not FOLLOW_UP_MODE
            or (followup_turns_remaining is not None and followup_turns_remaining <= 0)
            or not self._should_offer_followup(transcript_to_run or transcript)
        ):
            if not self._should_offer_followup(transcript_to_run or transcript):
                self._active_followup_lane = None
            emit_summary("ok")
            return

        try:
            await self._speak_response(FOLLOW_UP_PROMPT_TEXT)
        except Exception as exc:
            logger.error("Follow-up prompt TTS failed: %s", exc)
            emit_summary("followup_prompt_error", str(exc))
            return

        followup_audio = await self._wait_for_followup(stream)
        if followup_audio:
            emit_summary("followup")
            next_turns_remaining = (
                None
                if followup_turns_remaining is None
                else followup_turns_remaining - 1
            )
            await self._run_turn(
                stream,
                followup_audio,
                allow_followup=True,
                followup_turns_remaining=next_turns_remaining,
                turn_started_at=time.perf_counter(),
            )
        else:
            emit_summary("ok")
            self._active_followup_lane = None

    async def start(self):
        self._init_audio()
        self._running = True
        self._start_tts_cache_warmup()
        logger.info("Wake word listener started (say '%s')", self.wake_word.replace("_", " "))

        stream = self._open_mic_stream()

        try:
            while self._running:
                try:
                    audio_chunk = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                except Exception:
                    await asyncio.sleep(0.01)
                    continue

                if self._speaking:
                    await asyncio.sleep(0.01)
                    continue

                import numpy as np

                audio_array = np.frombuffer(audio_chunk, dtype=np.int16)
                self._oww_model.predict(audio_array)
                scores = self._oww_model.prediction_buffer.get(self.wake_word, [])
                if scores and scores[-1] >= self.threshold:
                    logger.info("Wake word detected! (score: %.2f)", scores[-1])
                    self._reset_wake_model()
                    self._active_followup_lane = None
                    turn_started_at = time.perf_counter()

                    if self._use_listening_cue():
                        try:
                            await self._play_listening_cue()
                        except Exception as exc:
                            logger.warning("Listening cue failed: %s", exc)

                    if WAKE_PROMPT_TEXT:
                        try:
                            await self._speak_response(WAKE_PROMPT_TEXT)
                        except Exception as exc:
                            logger.warning("Wake prompt TTS failed: %s", exc)

                    recorded_audio = await self._record_until_silence(stream)
                    await self._run_turn(
                        stream,
                        recorded_audio,
                        allow_followup=True,
                        followup_turns_remaining=FOLLOW_UP_MAX_TURNS,
                        turn_started_at=turn_started_at,
                    )

                await asyncio.sleep(0)
        finally:
            stream.stop_stream()
            stream.close()
            self._pyaudio.terminate()
            logger.info("Wake word listener stopped")

    def stop(self):
        self._running = False
