# RPi Voice Runtime Stabilization

This guide covers the runtime changes in the repo that reduce voice latency,
separate smart-home commands from longer conversations, and improve telemetry.

## 1. Required Pi env baseline

Use the RPi template in `deploy/rpi/.env.rpi.example` and make sure the live Pi
`.env` contains at least:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
VERTEX_AI_LOCATION=us-west1
USE_CLOUD_LOGGING=true

TTS_USE_VERTEXAI=false
STT_USE_VERTEXAI=true

WAKEWORD_RECORD_SECONDS_MAX=8.0
WAKEWORD_SILENCE_SECONDS=1.2
WAKEWORD_MIN_SPEECH_SECONDS=0.6
WAKEWORD_ENERGY_THRESHOLD=900

GOOGLE_CUSTOM_SEARCH_CX=your-search-engine-cx
FIRECRAWL_API_KEY=your-firecrawl-api-key
```

## 2. What the runtime now does

- structured telemetry for voice turns, web chat, and TTS
- local smart-home fast path before `/api/chat`
- bounded retry/backoff for:
  - STT
  - TTS
  - safe voice agent lanes (`voice_qa`, `christian_guide`, `socrates`, `secretary`)
- consistent Gemini location policy for core runtime calls

## 3. Monitoring views

Local summary endpoint:

```bash
curl http://localhost:8000/api/monitoring/summary
```

Important Cloud Logging filters:

```text
jsonPayload.event_type="voice_turn_summary"
jsonPayload.event_type="web_chat_request"
jsonPayload.event_type="web_tts_request"
jsonPayload.event_type="voice_turn_summary" AND jsonPayload.quota_error=true
jsonPayload.local_smart_home_fast=true
```

Useful fields in `voice_turn_summary`:

- `audio_ms`
- `stt_elapsed_ms`
- `agent_elapsed_ms`
- `tts_elapsed_ms`
- `local_fast_elapsed_ms`
- `total_elapsed_ms`
- `route_hint`
- `quota_error`
- `error_type`

## 4. Expected behavior after deploy

- `upali svjetlo u kuhinji` should not execute twice
- smart-home commands should avoid the full `/api/chat` path when deterministic
- knowledge turns should keep follow-up behavior
- `RESOURCE_EXHAUSTED` should be clearly separated from permission/billing errors
- search fallback warnings should disappear if the Pi `.env` really contains the
  search keys

## 5. Smoke checks

Start web:

```bash
cd ~/google_claude
set -a
source .env
set +a
source .venv/bin/activate
python run_web.py --host 0.0.0.0 --port 8000
```

Start wakeword:

```bash
cd ~/google_claude
set -a
source .env
set +a
source .venv/bin/activate
python scripts/run_wakeword.py --threshold 0.4
```

Test:

1. `Hej Jarvise, upali svjetlo u kuhinji`
2. `Hej Jarvise, sto Augustin kaze o nemirnom srcu`
3. `Hej Jarvise, mozes li istraziti ... i poslati mail`

Capture:

- one `voice_turn_summary` event per turn
- `/api/monitoring/summary`
- web startup log to confirm no missing search-fallback keys
