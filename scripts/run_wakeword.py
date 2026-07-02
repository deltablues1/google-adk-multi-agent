"""
Raspberry Pi wake-word runner.

Modes:
- --stdin: manual transcript mode for local testing
- --audio-file: transcribe and route one file through shared STT
- --wakeword: live microphone loop. Engine via WAKEWORD_ENGINE env:
    openwakeword (default, free/Apache-2.0, no key) or porcupine (needs
    PICOVOICE_ACCESS_KEY). Both use sounddevice for mic + RMS capture.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import sys
import time
import wave
from array import array
from pathlib import Path
from typing import Iterable, Optional

# This script lives in scripts/; put the repo root on sys.path so `services`,
# `interfaces`, etc. import whether launched as `python scripts/run_wakeword.py`
# or from systemd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from services.audio_ingress import get_audio_ingress_service

load_dotenv()
os.environ.setdefault("HITL_INTERFACE", "wakeword")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def pcm16_rms(frame_bytes: bytes) -> float:
    """Return RMS energy for a mono PCM16 frame."""
    if not frame_bytes:
        return 0.0
    samples = array("h")
    samples.frombytes(frame_bytes)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0.0
    square_sum = sum(sample * sample for sample in samples)
    return (square_sum / len(samples)) ** 0.5


def looks_like_noise_transcript(text: str) -> bool:
    """Heuristic for background/appliance noise that the STT hallucinated into a
    string of isolated digits (e.g. "3 7 1 2 0 6 8 3 8 3" from a washing
    machine). Used to end follow-up turns cleanly instead of answering and
    looping on garbage. Real speech with a number ("koliko je 2 i 2", "21:23")
    has few isolated-digit tokens and is not flagged."""
    tokens = (text or "").split()
    if not tokens:
        return True
    digit_tokens = sum(1 for token in tokens if token.isdigit())
    return digit_tokens >= 4 and digit_tokens >= 0.6 * len(tokens)


def pcm16_to_wav_bytes(
    frames: Iterable[bytes],
    sample_rate: int,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM16 frames into a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        for frame in frames:
            wav_file.writeframes(frame)
    return buffer.getvalue()


class PiLiveVoiceBridge:
    """Client bridge from Raspberry Pi microphone/speaker to existing /api/live."""

    def __init__(self, interface):
        self.interface = interface
        self.sample_rate = int(os.getenv("LIVE_INPUT_SAMPLE_RATE", "16000"))
        self.output_sample_rate = int(os.getenv("LIVE_OUTPUT_SAMPLE_RATE", "24000"))
        self.block_size = int(os.getenv("LIVE_BLOCK_SIZE", "8192"))
        self.energy_threshold = float(os.getenv("LIVE_ENERGY_THRESHOLD", "650"))
        self.idle_timeout_seconds = float(os.getenv("LIVE_IDLE_TIMEOUT_SECONDS", "8"))
        self.min_session_seconds = float(os.getenv("LIVE_MIN_SESSION_SECONDS", "2"))
        self.max_session_seconds = float(os.getenv("LIVE_MAX_SESSION_SECONDS", "90"))
        self.control_silence_seconds = float(os.getenv("LIVE_CONTROL_SILENCE_SECONDS", "1.0"))
        self.control_min_speech_seconds = float(os.getenv("LIVE_CONTROL_MIN_SPEECH_SECONDS", "0.5"))
        self.control_max_record_seconds = float(os.getenv("LIVE_CONTROL_MAX_RECORD_SECONDS", "4.0"))
        self.input_device = os.getenv("WAKEWORD_INPUT_DEVICE", "").strip() or None
        self.output_device = os.getenv("WAKEWORD_OUTPUT_DEVICE", "").strip() or None

    async def run_session(self) -> None:
        try:
            import aiohttp
            import sounddevice as sd
        except ImportError as e:
            raise RuntimeError(
                "Live bridge requires aiohttp and sounddevice."
            ) from e

        ws_url = self.interface.get_live_ws_url()
        logger.info("Starting Pi live bridge: %s", ws_url)

        last_input_activity = time.monotonic()
        last_output_activity = time.monotonic()
        started_at = time.monotonic()
        stop_event = asyncio.Event()
        command_task: Optional[asyncio.Task] = None

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="int16",
            channels=1,
            device=self.input_device,
        ) as input_stream, sd.RawOutputStream(
            samplerate=self.output_sample_rate,
            channels=1,
            dtype="int16",
            device=self.output_device,
        ) as output_stream:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=20) as ws:
                    logger.info("Connected to /api/live")

                    async def sender():
                        nonlocal last_input_activity, command_task
                        utterance_frames: list[bytes] = []
                        utterance_started_at: Optional[float] = None
                        last_voice_at = time.monotonic()
                        speech_detected = False

                        while not stop_event.is_set():
                            data, _overflowed = await asyncio.to_thread(input_stream.read, self.block_size)
                            frame_bytes = bytes(data)
                            if not frame_bytes:
                                continue
                            rms = pcm16_rms(frame_bytes)
                            now = time.monotonic()
                            if rms >= self.energy_threshold:
                                last_input_activity = now
                                last_voice_at = now
                                speech_detected = True
                                if utterance_started_at is None:
                                    utterance_started_at = now
                                utterance_frames.append(frame_bytes)
                            elif utterance_started_at is not None:
                                utterance_frames.append(frame_bytes)

                            if utterance_started_at is not None:
                                utterance_elapsed = now - utterance_started_at
                                silence_elapsed = now - last_voice_at
                                should_finalize = False
                                if utterance_elapsed >= self.control_max_record_seconds:
                                    should_finalize = True
                                elif (
                                    speech_detected
                                    and utterance_elapsed >= self.control_min_speech_seconds
                                    and silence_elapsed >= self.control_silence_seconds
                                ):
                                    should_finalize = True

                                if should_finalize:
                                    wav_bytes = pcm16_to_wav_bytes(
                                        utterance_frames,
                                        sample_rate=self.sample_rate,
                                    )
                                    if command_task is None or command_task.done():
                                        command_task = asyncio.create_task(
                                            self._handle_local_control_transcript(wav_bytes, stop_event)
                                        )
                                    utterance_frames = []
                                    utterance_started_at = None
                                    speech_detected = False

                            await ws.send_bytes(frame_bytes)

                    async def receiver():
                        nonlocal last_output_activity
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                last_output_activity = time.monotonic()
                                await asyncio.to_thread(output_stream.write, msg.data)
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    payload = msg.json()
                                except Exception:
                                    logger.warning("Live bridge received non-JSON text: %s", msg.data[:200])
                                    continue
                                if payload.get("type") == "transcript":
                                    logger.info("Live transcript: %s", payload.get("text", "")[:160])
                                elif payload.get("type") == "error":
                                    logger.warning("Live backend error: %s", payload.get("message"))
                            elif msg.type in {aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                                break

                    async def idle_monitor():
                        while not stop_event.is_set():
                            await asyncio.sleep(0.5)
                            now = time.monotonic()
                            session_elapsed = now - started_at
                            idle_for = now - max(last_input_activity, last_output_activity)
                            if session_elapsed >= self.max_session_seconds:
                                logger.info("Live session reached max duration (%.1fs)", session_elapsed)
                                stop_event.set()
                                break
                            if session_elapsed >= self.min_session_seconds and idle_for >= self.idle_timeout_seconds:
                                logger.info("Live session idle timeout reached (%.1fs)", idle_for)
                                stop_event.set()
                                break

                    async def command_monitor():
                        while not stop_event.is_set():
                            await asyncio.sleep(0.1)
                            if command_task and command_task.done():
                                try:
                                    command_triggered = command_task.result()
                                except Exception as e:
                                    logger.warning("Local live command detector failed: %s", e)
                                    command_triggered = False
                                if command_triggered:
                                    stop_event.set()
                                    break

                    sender_task = asyncio.create_task(sender())
                    receiver_task = asyncio.create_task(receiver())
                    monitor_task = asyncio.create_task(idle_monitor())
                    command_monitor_task = asyncio.create_task(command_monitor())

                    done, pending = await asyncio.wait(
                        {sender_task, receiver_task, monitor_task, command_monitor_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    stop_event.set()

                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    await asyncio.gather(*done, return_exceptions=True)

                    await ws.close()
                    logger.info("Pi live bridge session ended")

    async def _handle_local_control_transcript(self, wav_bytes: bytes, stop_event: asyncio.Event) -> bool:
        """
        Detect mode-switch commands from the same microphone audio used for live mode.

        This lets the Pi exit live mode with a spoken command without changing the
        server-side /api/live protocol.
        """
        transcript_result = await get_audio_ingress_service().transcribe_audio(
            audio_bytes=wav_bytes,
            mime_type="audio/wav",
            source="wakeword_live_control",
            metadata={"session_id": self.interface.session_id},
        )
        transcript = transcript_result.transcript.strip()
        if not transcript:
            return False

        requested_mode = self.interface.detect_mode_switch(transcript)
        if requested_mode != "agent":
            logger.debug("Live control transcript ignored: %s", transcript[:120])
            return False

        self.interface.set_voice_mode("agent")
        logger.info("Live control command detected, switching to agent mode: %s", transcript)
        stop_event.set()
        return True


class PorcupineWakeWordRunner:
    def __init__(self, interface, loop: asyncio.AbstractEventLoop):
        self.interface = interface
        self.loop = loop
        self.access_key = os.getenv("PICOVOICE_ACCESS_KEY", "").strip()
        self.keywords = [
            keyword.strip()
            for keyword in os.getenv("WAKEWORD_KEYWORDS", "porcupine").split(",")
            if keyword.strip()
        ]
        self.sensitivity = float(os.getenv("WAKEWORD_SENSITIVITY", "0.65"))
        self.max_record_seconds = float(os.getenv("WAKEWORD_RECORD_SECONDS_MAX", "8.0"))
        self.silence_seconds = float(os.getenv("WAKEWORD_SILENCE_SECONDS", "1.2"))
        self.min_speech_seconds = float(os.getenv("WAKEWORD_MIN_SPEECH_SECONDS", "0.6"))
        self.energy_threshold = float(os.getenv("WAKEWORD_ENERGY_THRESHOLD", "900"))
        self.input_device = os.getenv("WAKEWORD_INPUT_DEVICE", "").strip() or None
        self.output_device = os.getenv("WAKEWORD_OUTPUT_DEVICE", "").strip() or None
        self.tts_enabled = os.getenv("WAKEWORD_TTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        self.tts_timeout_seconds = float(os.getenv("WAKEWORD_TTS_TIMEOUT_SECONDS", "30"))
        # Hard cap on one agent turn. Without it a runaway agent (e.g. a tool
        # retry loop) blocks the wake loop forever AND keeps billing LLM calls.
        # Multi-step orchestrations (research -> doc -> mail) legitimately take
        # minutes, hence the generous default.
        self.agent_timeout_seconds = float(os.getenv("VOICE_AGENT_TIMEOUT_SECONDS", "300"))
        self.agent_timeout_message = os.getenv(
            "VOICE_AGENT_TIMEOUT_MESSAGE",
            "Oprosti, zadatak traje predugo pa sam ga prekinuo. "
            "Pokušaj ponovno ili pojednostavi zahtjev.",
        ).strip()
        self.live_bridge = PiLiveVoiceBridge(interface)
        # Multi-turn follow-up. After an answer, optionally re-prompt
        # ("Treba li jos nesto?") and keep listening without a new wake word for
        # up to N more turns. The interface reuses one ADK session_id across
        # turns, so conversation context carries over between them.
        self.follow_up_mode = os.getenv("VOICE_FOLLOW_UP_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
        self.follow_up_max_turns = int(os.getenv("VOICE_FOLLOW_UP_MAX_TURNS", "4"))
        self.follow_up_prompt = os.getenv("VOICE_FOLLOW_UP_PROMPT_TEXT", "Treba li jos nesto?").strip()
        self.wake_prompt = os.getenv("VOICE_WAKE_PROMPT_TEXT", "").strip()
        # Open-mic echo guard: this hardware has no acoustic echo cancellation,
        # so right after the assistant speaks, the mic still holds the tail of
        # its own TTS. Before each follow-up capture we settle briefly and flush
        # the buffered audio, otherwise Jarvis transcribes itself and loops.
        self.follow_up_guard_seconds = float(os.getenv("VOICE_FOLLOW_UP_GUARD_SECONDS", "0.4"))
        # Let the interface speak a short "working on it" cue before long
        # orchestrator runs (VOICE_WORKING_ACK_TEXT), so minutes of task work
        # don't feel like a dead assistant.
        if self.tts_enabled:
            self.interface.voice_ack_hook = self._speak_response

    def _require_dependencies(self):
        try:
            import pvporcupine  # noqa: F401
            import sounddevice  # noqa: F401
            import requests  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "Wake-word mode requires optional Pi audio dependencies. "
                "Install requirements including pvporcupine and sounddevice."
            ) from e

        if not self.access_key:
            raise RuntimeError("PICOVOICE_ACCESS_KEY is required for --wakeword mode")

    def run_forever(self) -> None:
        self._require_dependencies()

        import pvporcupine
        import sounddevice as sd

        porcupine = pvporcupine.create(
            access_key=self.access_key,
            keywords=self.keywords,
            sensitivities=[self.sensitivity] * len(self.keywords),
        )

        sample_rate = porcupine.sample_rate
        frame_length = porcupine.frame_length
        logger.info(
            "Wake-word loop started: keywords=%s sample_rate=%s frame_length=%s",
            ",".join(self.keywords),
            sample_rate,
            frame_length,
        )

        try:
            with sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=frame_length,
                dtype="int16",
                channels=1,
                device=self.input_device,
            ) as stream:
                while True:
                    pcm_frame, _overflowed = stream.read(frame_length)
                    frame_bytes = bytes(pcm_frame)
                    samples = array("h")
                    samples.frombytes(frame_bytes)
                    if sys.byteorder != "little":
                        samples.byteswap()

                    keyword_index = porcupine.process(samples)
                    if keyword_index < 0:
                        continue

                    keyword = self.keywords[keyword_index] if keyword_index < len(self.keywords) else str(keyword_index)
                    logger.info("Wake word detected: %s", keyword)
                    self._process_wake_event(stream, sample_rate, frame_length)
        finally:
            porcupine.delete()

    def _process_wake_event(self, stream, sample_rate: int, frame_length: int) -> None:
        """Shared post-detection flow used by every wake-word engine:
        live bridge, or capture utterance -> agent -> TTS playback.

        With VOICE_FOLLOW_UP_MODE enabled, after the first answer Jarvis
        re-prompts ("Treba li jos nesto?") and keeps listening for up to
        VOICE_FOLLOW_UP_MAX_TURNS more turns without a new wake word. The same
        ADK session_id is reused across turns, so context carries over. Silence
        after a prompt ends the conversation and returns to wake-word waiting.

        Any failure in a single turn (empty transcript, transient network/DNS,
        STT/agent/TTS error) MUST be caught here so the wake loop keeps
        listening instead of crashing the whole assistant.
        """
        try:
            if self.interface.voice_mode == "live":
                self._run_live_bridge()
                return

            # Optional "I'm listening" cue right after the wake word.
            if self.wake_prompt and self.tts_enabled:
                self._speak_response(self.wake_prompt)

            handled = self._run_agent_turn(stream, sample_rate, frame_length)
            if not handled:
                logger.warning("Wake-word detected but no usable speech was captured")
                return
            if self.interface.voice_mode == "live":
                self._run_live_bridge()
                return

            if not self.follow_up_mode:
                return

            for _turn in range(max(0, self.follow_up_max_turns)):
                if self.follow_up_prompt and self.tts_enabled:
                    self._speak_response(self.follow_up_prompt)
                handled = self._run_agent_turn(stream, sample_rate, frame_length, drain_first=True)
                if not handled:
                    # Silence after the re-prompt = user is done.
                    logger.info("Follow-up ended: no further speech")
                    break
                if self.interface.voice_mode == "live":
                    self._run_live_bridge()
                    break
        except Exception as exc:
            # Log and recover — never let one bad turn kill the wake loop.
            logger.warning("Wake turn failed (continuing to listen): %s: %s",
                           type(exc).__name__, str(exc)[:200])

    def _run_live_bridge(self) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self.live_bridge.run_session(),
            self.loop,
        )
        future.result()

    def _drain_input(self, stream, frame_length: int) -> None:
        """Settle briefly, then discard any buffered mic audio so the next
        capture starts clean. Without acoustic echo cancellation the buffer
        holds the tail of the assistant's own TTS plus ambient noise that would
        otherwise be (mis)transcribed during follow-up turns."""
        try:
            time.sleep(self.follow_up_guard_seconds)
            while getattr(stream, "read_available", 0) >= frame_length:
                stream.read(frame_length)
        except Exception:
            pass

    def _run_agent_turn(self, stream, sample_rate: int, frame_length: int,
                        drain_first: bool = False) -> bool:
        """Capture one utterance, route it through the agent, speak the reply.

        Returns True if speech was captured and a turn ran; False on silence
        (the signal the follow-up loop uses to stop). When the turn switches the
        interface into live mode, the caller starts the live bridge instead of
        speaking.
        """
        if drain_first:
            self._drain_input(stream, frame_length)
        utterance_wav = self._capture_utterance(stream, sample_rate, frame_length)
        if not utterance_wav:
            return False

        future = asyncio.run_coroutine_threadsafe(
            self.interface.process_audio(
                audio_bytes=utterance_wav,
                mime_type="audio/wav",
                source="wakeword",
            ),
            self.loop,
        )
        try:
            result = future.result(timeout=self.agent_timeout_seconds)
        except TimeoutError:
            # Cancel the coroutine in the loop too — result(timeout=) alone
            # abandons the wait but leaves the agent run (and its LLM billing)
            # alive in the background.
            future.cancel()
            logger.error(
                "Agent turn exceeded %.0fs; cancelled the run.",
                self.agent_timeout_seconds,
            )
            if self.tts_enabled and self.agent_timeout_message:
                self._speak_response(self.agent_timeout_message)
            return True
        logger.info("Wake-word result [%s]: %s", result["mode"], result["response"][:160])

        # In a follow-up turn (open mic, no wake word), reject noise that the STT
        # hallucinated into digits so we don't answer it and loop on garbage.
        if drain_first and looks_like_noise_transcript(result.get("transcript", "")):
            logger.info("Follow-up noise rejected, ending conversation: %r",
                        result.get("transcript", "")[:80])
            return False

        if result["mode"] != "live" and self.tts_enabled:
            self._speak_response(result["response"])
        return True

    def _capture_utterance(self, stream, sample_rate: int, frame_length: int) -> Optional[bytes]:
        frames: list[bytes] = []
        started_at = time.monotonic()
        last_voice_at = started_at
        speech_detected = False

        while True:
            pcm_frame, _overflowed = stream.read(frame_length)
            frame_bytes = bytes(pcm_frame)
            frames.append(frame_bytes)

            rms = pcm16_rms(frame_bytes)
            now = time.monotonic()
            elapsed = now - started_at

            if rms >= self.energy_threshold:
                speech_detected = True
                last_voice_at = now

            if elapsed >= self.max_record_seconds:
                break

            if speech_detected and elapsed >= self.min_speech_seconds and (now - last_voice_at) >= self.silence_seconds:
                break

        if not speech_detected:
            return None

        return pcm16_to_wav_bytes(frames, sample_rate=sample_rate)

    def _speak_response(self, text: str) -> None:
        if not text.strip():
            return

        try:
            import requests
            import sounddevice as sd
        except ImportError as e:
            logger.warning("TTS playback skipped because dependency is missing: %s", e)
            return

        headers = {"Content-Type": "application/json"}
        if self.interface.api_token:
            headers["Authorization"] = f"Bearer {self.interface.api_token}"

        # Streamed playback: start speaking on the first PCM chunk instead of
        # waiting for the full synthesis + download. Falls back to unary when
        # disabled or when the server ignores the stream flag.
        use_stream = os.getenv("WAKEWORD_TTS_STREAMING", "true").lower() in {
            "1", "true", "yes", "on"
        }

        try:
            response = requests.post(
                f"{self.interface.api_base_url}/api/tts",
                json={"text": text[:4000], "stream": use_stream},
                headers=headers,
                timeout=self.tts_timeout_seconds,
                stream=use_stream,
            )
            response.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch TTS audio from %s: %s", self.interface.api_base_url, e)
            return

        try:
            with sd.RawOutputStream(
                samplerate=24000,
                channels=1,
                dtype="int16",
                device=self.output_device,
            ) as output_stream:
                if use_stream:
                    played = False
                    pending = b""  # keep int16 frame alignment across chunks
                    for chunk in response.iter_content(chunk_size=4800):
                        if not chunk:
                            continue
                        pending += chunk
                        writable = len(pending) - (len(pending) % 2)
                        if writable:
                            output_stream.write(pending[:writable])
                            pending = pending[writable:]
                            played = True
                    if not played:
                        logger.warning("TTS endpoint returned empty audio")
                else:
                    pcm_bytes = response.content
                    if not pcm_bytes:
                        logger.warning("TTS endpoint returned empty audio")
                        return
                    output_stream.write(pcm_bytes)
        except Exception as e:
            logger.warning("Failed to play TTS audio: %s", e)
        finally:
            response.close()


class OpenWakeWordRunner(PorcupineWakeWordRunner):
    """Free, offline wake-word engine (openWakeWord, Apache-2.0, no access key).

    Reuses PorcupineWakeWordRunner's mic capture (sounddevice + RMS), utterance
    capture, TTS playback and post-detection flow; only the detection loop and
    dependency check differ. Selected by default (WAKEWORD_ENGINE=openwakeword).
    """

    def __init__(self, interface, loop: asyncio.AbstractEventLoop):
        super().__init__(interface, loop)
        # openWakeWord ships pretrained models; "hey_jarvis" is bundled.
        self.model_name = os.getenv("WAKEWORD_MODEL", "hey_jarvis").strip() or "hey_jarvis"
        # Reuse WAKEWORD_THRESHOLD (0..1); openWakeWord scores are probabilities.
        self.threshold = float(os.getenv("WAKEWORD_THRESHOLD", "0.5"))

    def _require_dependencies(self):
        try:
            import openwakeword  # noqa: F401
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
            import requests  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "openWakeWord mode requires openwakeword, sounddevice and numpy "
                "(see requirements-rpi.txt)."
            ) from e
        # No access key required — that is the point of choosing openWakeWord.

    def run_forever(self) -> None:
        self._require_dependencies()

        import numpy as np
        import sounddevice as sd
        import openwakeword
        from openwakeword.model import Model

        # Bundled models download once and cache; no-op afterwards.
        try:
            openwakeword.utils.download_models()
        except Exception as e:
            logger.warning("openWakeWord model download skipped: %s", e)

        model = Model(wakeword_models=[self.model_name], inference_framework="onnx")

        sample_rate = 16000
        frame_length = 1280  # 80 ms @ 16 kHz — openWakeWord's expected chunk size
        logger.info(
            "openWakeWord loop started: model=%s threshold=%.2f sample_rate=%s frame_length=%s",
            self.model_name, self.threshold, sample_rate, frame_length,
        )

        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=frame_length,
            dtype="int16",
            channels=1,
            device=self.input_device,
        ) as stream:
            while True:
                pcm_frame, _overflowed = stream.read(frame_length)
                samples = np.frombuffer(bytes(pcm_frame), dtype=np.int16)

                scores = model.predict(samples)
                top = max(scores.values()) if scores else 0.0
                if top < self.threshold:
                    continue

                logger.info("Wake word detected: %s (score=%.2f)", self.model_name, top)
                self._process_wake_event(stream, sample_rate, frame_length)
                # Reset model state so the speech tail doesn't immediately retrigger.
                model.reset()


def _make_wakeword_runner(interface, loop):
    """Pick the wake-word engine from WAKEWORD_ENGINE (default: openwakeword)."""
    engine = os.getenv("WAKEWORD_ENGINE", "openwakeword").strip().lower()
    if engine in {"porcupine", "pv", "picovoice"}:
        return PorcupineWakeWordRunner(interface, loop)
    return OpenWakeWordRunner(interface, loop)


async def _run_stdin(interface) -> None:
    print("Wakeword stdin mode. Type transcript lines. Ctrl+C to stop.")
    loop = asyncio.get_running_loop()
    while True:
        text = await loop.run_in_executor(None, lambda: input("wakeword> ").strip())
        if not text:
            continue
        result = await interface.process_transcript(text)
        print(f"[{result['mode']}] {result['response']}")


async def _run_audio_file(interface, path: str, mime_type: str) -> None:
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    audio_bytes = audio_path.read_bytes()
    result = await interface.process_audio(audio_bytes=audio_bytes, mime_type=mime_type)
    print(f"Transcript: {result['transcript']}")
    print(f"[{result['mode']}] {result['response']}")


async def _run_wakeword(interface) -> None:
    loop = asyncio.get_running_loop()
    runner = _make_wakeword_runner(interface, loop)
    logger.info("Wake-word engine: %s", type(runner).__name__)
    await loop.run_in_executor(None, runner.run_forever)


async def main() -> None:
    parser = argparse.ArgumentParser(description="RPi wake-word voice runner")
    parser.add_argument("--stdin", action="store_true", help="Manual transcript mode for local testing")
    parser.add_argument("--audio-file", help="Transcribe and route a single audio file")
    parser.add_argument("--mime-type", default="audio/ogg", help="MIME type for --audio-file input")
    parser.add_argument("--wakeword", action="store_true", help="Live Pi microphone loop (engine via WAKEWORD_ENGINE: openwakeword default, or porcupine)")
    args = parser.parse_args()

    from interfaces.wakeword_interface import WakeWordInterface

    interface = WakeWordInterface()
    await interface.start()
    try:
        if args.stdin:
            await _run_stdin(interface)
        elif args.audio_file:
            await _run_audio_file(interface, args.audio_file, args.mime_type)
        elif args.wakeword:
            await _run_wakeword(interface)
        else:
            parser.error("Choose one of: --stdin, --audio-file, --wakeword")
    finally:
        await interface.stop()


if __name__ == "__main__":
    asyncio.run(main())
