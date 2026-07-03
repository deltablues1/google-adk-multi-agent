# Voice: STT & TTS Engines

> 🇭🇷 Hrvatska verzija: [docs/hr/voice.md](../hr/voice.md)

The voice stack (used by the web `/api/tts` + `/api/live` endpoints, the Telegram
voice handler, and the RPi wake-word loop) supports **multiple interchangeable
engines** for speech-to-text and text-to-speech. The Gemini/Cloud paths are the
default; OpenAI is additive and opt-in.

Source of truth: [`services/audio/stt_service.py`](../../services/audio/stt_service.py)
and the OpenAI TTS block in [`web/app.py`](../../web/app.py).

---

## Speech-to-Text (STT)

Selected with `STT_ENGINE`:

| `STT_ENGINE` | Engine | Notes |
|--------------|--------|-------|
| `gemini` (default) | Gemini multimodal (Flash) | General-purpose; uses Google AI key or Vertex |
| `chirp` / `cloud` | Cloud Speech-to-Text v2 (Chirp) | Native per-language ASR — far more reliable for **Croatian**, especially short utterances |
| `openai` | OpenAI `gpt-4o-transcribe` | Strong Croatian accuracy; requires `OPENAI_API_KEY` |

```bash
# Default
STT_MODEL=gemini-2.5-flash
STT_LANGUAGE=Croatian
STT_USE_VERTEXAI=true

# Cloud Chirp
STT_ENGINE=chirp
STT_CLOUD_MODEL=chirp_2

# OpenAI
STT_ENGINE=openai
OPENAI_API_KEY=sk-...
OPENAI_STT_MODEL=gpt-4o-transcribe
OPENAI_STT_LANGUAGE=hr        # ISO-639-1, default Croatian
```

Supported input MIME types (Gemini path): OGG/Opus (Telegram), WAV, MP3, WebM,
raw PCM16 (`audio/L16`).

---

## Text-to-Speech (TTS)

Default is Gemini/Cloud TTS; set `TTS_ENGINE=openai` to route `/api/tts` to
OpenAI. OpenAI returns raw PCM (24 kHz mono).

```bash
# Default (Gemini/Cloud)
TTS_MODEL=gemini-2.5-flash-tts
TTS_VOICE_NAME=Charon
TTS_LANGUAGE_CODE=hr-HR
TTS_USE_VERTEXAI=false
VOICE_ASSISTANT_GENDER=male

# OpenAI
TTS_ENGINE=openai
OPENAI_API_KEY=sk-...
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
OPENAI_TTS_INSTRUCTIONS=Govori prirodno i poslovno, na hrvatskom.
```

The OpenAI engine is **additive**: when `TTS_ENGINE` is unset/not `openai`, the
existing Gemini/Cloud paths are untouched.

---

## Voice runtime tuning (RPi wake-word loop)

These tune capture, turn-taking, and timeouts. Defaults are sensible; override
only when needed (e.g. wm8960 HAT on the RPi). See also
[`deploy/rpi/RUNBOOK.md`](../../deploy/rpi/RUNBOOK.md).

| Variable | Default | Purpose |
|----------|---------|---------|
| `WAKEWORD_THRESHOLD` | `0.4` | Wake-word detection sensitivity |
| `VOICE_FOLLOW_UP_MODE` | `false` | Allow follow-ups without re-waking |
| `VOICE_FOLLOW_UP_MAX_TURNS` | `4` | Max follow-up turns |
| `VOICE_MAX_RECORD_TIME` | `30` | Max recording seconds |
| `VOICE_SILENCE_TIMEOUT` | `5` | Silence before stop (s) |
| `VOICE_PRE_SPEECH_TIMEOUT` | `8` | Wait for speech to start (s) |
| `VOICE_SPEECH_RMS_THRESHOLD` | `260` | RMS level treated as speech |
| `VOICE_SILENCE_RMS_THRESHOLD` | `170` | RMS level treated as silence |
| `VOICE_AGENT_TIMEOUT_SECONDS` | `300` | Hard cap on one agent turn — on expiry the run is cancelled (not just abandoned) and `VOICE_AGENT_TIMEOUT_MESSAGE` is spoken |
| `VOICE_WORKING_ACK_TEXT` | `Radim na tome…` | Spoken cue before long orchestrator runs (empty disables) |
| `WAKEWORD_VAD_THRESHOLD` | `0` (off) | Silero VAD gate on wake-word activations — non-speech noise can't wake; 0.4–0.6 sensible |
| `WAKEWORD_MIN_CONSECUTIVE_FRAMES` | `1` | Frames the score must stay above threshold; `2` filters single-frame noise spikes (+~80 ms latency) |
| `VOICE_TTS_TIMEOUT_SECONDS` | `35` | TTS timeout |
| `VOICE_DIRECT_ROUTING` | on (rpi-home) | Route wake-word to smart_home / christian_guide / socrates before orchestrator |
| `VOICE_LOCAL_SMART_HOME_FAST_PATH` | — | Local fast path for smart-home commands |
| `VOICE_DEBUG_AUDIO_METRICS` | — | Log audio RMS/timing metrics |

Prompts/cues: `VOICE_WAKE_PROMPT_TEXT` (`Slušam.`),
`VOICE_FOLLOW_UP_PROMPT_TEXT` (`Treba li još nešto?`), `VOICE_NO_SPEECH_CUE`,
`VOICE_SUPPRESS_LISTENING_CUE_WHEN_PROMPT`.

---

## Probe / debugging

`scripts/openai_voice_probe.py` is a standalone probe for validating the OpenAI
STT/TTS path independently of the full stack.

> ⚠️ Status: the OpenAI voice work currently lives on the local
> `feat/openai-voice` branch and is **not yet pushed** to GitHub. The toggles
> above are present in `.env.example` but ship disabled by default.
