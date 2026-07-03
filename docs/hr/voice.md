# Glas: STT i TTS motori

> 🇬🇧 English version: [docs/en/voice.md](../en/voice.md)

Glasovni stog (koriste ga web `/api/tts` + `/api/live` endpointi, Telegram
glasovni handler i RPi wake-word petlja) podržava **više zamjenjivih motora** za
pretvorbu govora u tekst i obrnuto. Gemini/Cloud putanje su zadane; OpenAI je
dodatan i uključuje se po izboru (opt-in).

Izvor istine: [`services/audio/stt_service.py`](../../services/audio/stt_service.py)
i OpenAI TTS blok u [`web/app.py`](../../web/app.py).

---

## Govor u tekst (STT)

Bira se s `STT_ENGINE`:

| `STT_ENGINE` | Motor | Napomene |
|--------------|-------|----------|
| `gemini` (zadano) | Gemini multimodal (Flash) | Općenamjenski; koristi Google AI ključ ili Vertex |
| `chirp` / `cloud` | Cloud Speech-to-Text v2 (Chirp) | Nativni ASR po jeziku — znatno pouzdaniji za **hrvatski**, osobito kratke izgovore |
| `openai` | OpenAI `gpt-4o-transcribe` | Jaka točnost za hrvatski; treba `OPENAI_API_KEY` |

```bash
# Zadano
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
OPENAI_STT_LANGUAGE=hr        # ISO-639-1, zadano hrvatski
```

Podržani ulazni MIME tipovi (Gemini putanja): OGG/Opus (Telegram), WAV, MP3,
WebM, sirovi PCM16 (`audio/L16`).

---

## Tekst u govor (TTS)

Zadano je Gemini/Cloud TTS; postavi `TTS_ENGINE=openai` da `/api/tts` ide na
OpenAI. OpenAI vraća sirovi PCM (24 kHz mono).

```bash
# Zadano (Gemini/Cloud)
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

OpenAI motor je **dodatan**: kad `TTS_ENGINE` nije postavljen ili nije `openai`,
postojeće Gemini/Cloud putanje ostaju netaknute.

---

## Ugađanje glasovnog runtimea (RPi wake-word petlja)

Ove varijable ugađaju snimanje, izmjenu govornika i timeoutove. Zadane
vrijednosti su razumne; mijenjaj samo po potrebi (npr. wm8960 HAT na RPi-u).
Vidi i [`deploy/rpi/RUNBOOK.md`](../../deploy/rpi/RUNBOOK.md).

| Varijabla | Zadano | Svrha |
|-----------|--------|-------|
| `WAKEWORD_THRESHOLD` | `0.4` | Osjetljivost detekcije wake-worda |
| `VOICE_FOLLOW_UP_MODE` | `false` | Dopusti nastavke bez ponovnog buđenja |
| `VOICE_FOLLOW_UP_MAX_TURNS` | `4` | Maks. broj nastavnih poteza |
| `VOICE_MAX_RECORD_TIME` | `30` | Maks. sekundi snimanja |
| `VOICE_SILENCE_TIMEOUT` | `5` | Tišina prije zaustavljanja (s) |
| `VOICE_PRE_SPEECH_TIMEOUT` | `8` | Čekanje na početak govora (s) |
| `VOICE_SPEECH_RMS_THRESHOLD` | `260` | RMS razina koja se smatra govorom |
| `VOICE_SILENCE_RMS_THRESHOLD` | `170` | RMS razina koja se smatra tišinom |
| `VOICE_AGENT_TIMEOUT_SECONDS` | `300` | Tvrdi limit jednog agent poteza — po isteku se run stvarno prekida (ne samo napušta) i izgovara se `VOICE_AGENT_TIMEOUT_MESSAGE` |
| `VOICE_WORKING_ACK_TEXT` | `Radim na tome…` | Izgovorena najava prije dugih orchestrator zadataka (prazno isključuje) |
| `WAKEWORD_VAD_THRESHOLD` | `0` (isklj.) | Silero VAD filtar na buđenju — ne-govorni šum ne može probuditi; razumno 0.4–0.6 |
| `WAKEWORD_MIN_CONSECUTIVE_FRAMES` | `1` | Broj frameova u kojima score mora ostati iznad praga; `2` filtrira jednokratne šiljke šuma (+~80 ms latencije) |
| `VOICE_TTS_TIMEOUT_SECONDS` | `35` | TTS timeout |
| `VOICE_DIRECT_ROUTING` | uklj. (rpi-home) | Usmjeri wake-word na smart_home / christian_guide / socrates prije orchestratora |
| `VOICE_LOCAL_SMART_HOME_FAST_PATH` | — | Lokalna brza putanja za smart-home naredbe |
| `VOICE_DEBUG_AUDIO_METRICS` | — | Logiraj RMS/timing metrike zvuka |

Poruke/znakovi: `VOICE_WAKE_PROMPT_TEXT` (`Slušam.`),
`VOICE_FOLLOW_UP_PROMPT_TEXT` (`Treba li još nešto?`), `VOICE_NO_SPEECH_CUE`,
`VOICE_SUPPRESS_LISTENING_CUE_WHEN_PROMPT`.

---

## Probe / dijagnostika

`scripts/openai_voice_probe.py` je samostalan probe za provjeru OpenAI STT/TTS
putanje neovisno o cijelom stogu.

> ⚠️ Status: OpenAI glasovni rad trenutno je na lokalnom branchu
> `feat/openai-voice` i **još nije pushan** na GitHub. Prekidači iznad postoje u
> `.env.example`, ali su isporučeni isključeni po zadanome.
