# `.env.rpi` Checklist

Koristi ovo uz [deploy/rpi/.env.rpi.example](/c:/Users/Tomislav/Desktop/ai%20agenti/Rpi5_codex/google_claude/deploy/rpi/.env.rpi.example).

## 1. Deployment profil

```env
DEPLOYMENT_PROFILE=rpi-home
ERP_ENABLED=false
TELEGRAM_ENABLED=true
WAKE_WORD_ENABLED=true
VOICE_MODE_DEFAULT=agent
API_TOKEN_REQUIRED=true
```

Preporuka:
- ostavi ovako za prvi deployment

## 2. Obavezne tajne

```env
API_TOKEN=stavi_dugacak_random_token
GEMINI_API_KEY=stavi_google_gemini_api_kljuc
PICOVOICE_ACCESS_KEY=stavi_picovoice_kljuc
```

Napomena:
- `API_TOKEN` koristi web API i Pi `/api/live`
- neka bude dugačak i nasumičan

## 3. Google Cloud i Google Workspace

Ako želiš da Pi vrti puni sustav, ne samo voice gateway, onda ovo također mora biti na Pi-u:

```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=lyrical-star-497817-m3
GOOGLE_APPLICATION_CREDENTIALS=/opt/google-clause/secrets/service_account_key.json
GOOGLE_CLOUD_LOCATION=global
VERTEX_AI_LOCATION=us-west1
GOOGLE_OAUTH_CLIENT_ID=stavi_oauth_client_id
GOOGLE_OAUTH_CLIENT_SECRET=stavi_oauth_client_secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback
USE_CLOUD_LOGGING=false
```

Što to znači:
- `GOOGLE_CLOUD_PROJECT` i `GOOGLE_APPLICATION_CREDENTIALS` trebaju se na Pi-u za Vertex AI, Firestore i dio Google Cloud servisa
- `GOOGLE_OAUTH_CLIENT_ID` i `GOOGLE_OAUTH_CLIENT_SECRET` trebaju se na Pi-u za Gmail, Drive, Calendar, Contacts, Tasks i refresh postojećih OAuth tokena
- `GEMINI_API_KEY` i dalje treba na Pi-u jer voice put (`/api/tts`, `/api/live`, shared STT) trenutno koristi Gemini API key direktno

Važna razlika:
- core agent/orchestrator put u dijelu koda preferira `Vertex AI`
- voice put koristi `GEMINI_API_KEY`
- za puni deployment na Pi-u zato u praksi trebaš i `Vertex` env i `GEMINI_API_KEY`

## 4. Glas i persona

```env
GEMINI_VOICE_NAME=Charon
VOICE_ASSISTANT_NAME=Jarvis
VOICE_ASSISTANT_STYLE=smiren, profesionalan, kratak, diskretno butlerovski
```

Preporuka:
- za v1 ostavi točno ovako

## 5. Telegram

```env
TELEGRAM_BOT_TOKEN=stavi_bot_token
TELEGRAM_CHAT_ID=
TELEGRAM_AUTHORIZED_CHAT_IDS=
```

Preporuka:
- `TELEGRAM_BOT_TOKEN` je obavezan ako pališ Telegram
- `TELEGRAM_CHAT_ID` može ostati prazan ako ga kod ne treba za current flow
- `TELEGRAM_AUTHORIZED_CHAT_IDS` upiši ako želiš ograničiti pristup, npr. `123456789,987654321`

Ako Telegram ne želiš odmah:

```env
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
```

## 6. OAuth tokeni i persistent state

```env
OAUTH_TOKEN_STORAGE_PATH=/opt/google-clause/state/oauth/tokens.json
USE_PERSISTENT_ADK_SESSIONS=true
```

Preporuka:
- ostavi ovako

Napomena:
- ako već imaš valjani `tokens.json`, najpraktičnije je prebaciti ga na Pi na ovu lokaciju
- time izbjegavaš novu prijavu odmah pri prvom bootu
- ali `GOOGLE_OAUTH_CLIENT_ID` i `GOOGLE_OAUTH_CLIENT_SECRET` i dalje moraju biti prisutni da bi refresh radio nakon restarta ili isteka access tokena

## 7. MQTT i HA

```env
MQTT_BROKER=IP_ILI_HOST_MQTT_BROKERA
MQTT_PORT=1883
MQTT_USER=korisnik_ako_postoji
MQTT_PASS=lozinka_ako_postoji
HA_MQTT_DISCOVERY_ENABLED=true
HA_MQTT_DISCOVERY_PREFIX=homeassistant
HA_MQTT_STATE_PREFIX=google_clause/rpi_voice
HA_MQTT_DEVICE_ID=google_clause_rpi_voice
HA_MQTT_DEVICE_NAME=Jarvis
```

Što upisati:
- `MQTT_BROKER`: IP od brokera koji već koristi HA
- ako koristiš HA Mosquitto add-on, koristi njegove dodatne credentials, ne admin HA account

## 8. Wake word i voice gateway

```env
WAKEWORD_API_BASE_URL=http://127.0.0.1:8000
WAKEWORD_USER_ID=rpi-voice
WAKEWORD_KEYWORDS=jarvis
WAKEWORD_SENSITIVITY=0.65
WAKEWORD_RECORD_SECONDS_MAX=8
WAKEWORD_SILENCE_SECONDS=1.2
WAKEWORD_MIN_SPEECH_SECONDS=0.6
WAKEWORD_ENERGY_THRESHOLD=900
WAKEWORD_INPUT_DEVICE=
WAKEWORD_OUTPUT_DEVICE=
WAKEWORD_TTS_ENABLED=true
```

Preporuka:
- `WAKEWORD_API_BASE_URL` ostavi na `127.0.0.1` ako web servis i wakeword rade na istom Pi-u
- `WAKEWORD_INPUT_DEVICE` i `WAKEWORD_OUTPUT_DEVICE` ostavi prazno dok ne vidiš da default device nije dobar

## 9. Live mod parametri

```env
LIVE_INPUT_SAMPLE_RATE=16000
LIVE_OUTPUT_SAMPLE_RATE=24000
LIVE_BLOCK_SIZE=8192
LIVE_ENERGY_THRESHOLD=650
LIVE_IDLE_TIMEOUT_SECONDS=8
LIVE_MIN_SESSION_SECONDS=2
LIVE_MAX_SESSION_SECONDS=90
LIVE_CONTROL_SILENCE_SECONDS=1.0
LIVE_CONTROL_MIN_SPEECH_SECONDS=0.5
LIVE_CONTROL_MAX_RECORD_SECONDS=4.0
```

Preporuka:
- ostavi ovako za prvi deployment

## 10. Telegram audio limit

```env
TELEGRAM_AUDIO_MAX_DURATION_SECONDS=120
```

Preporuka:
- ostavi ovako

## 11. Najkraći mogući v1 profil

Ako želiš krenuti s najmanje pokretnih dijelova:

```env
DEPLOYMENT_PROFILE=rpi-home
ERP_ENABLED=false
TELEGRAM_ENABLED=true
WAKE_WORD_ENABLED=true
VOICE_MODE_DEFAULT=agent
API_TOKEN_REQUIRED=true
API_TOKEN=stavi_dugacak_random_token
GEMINI_API_KEY=stavi_google_gemini_api_kljuc
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=lyrical-star-497817-m3
GOOGLE_APPLICATION_CREDENTIALS=/opt/google-clause/secrets/service_account_key.json
GOOGLE_CLOUD_LOCATION=global
VERTEX_AI_LOCATION=us-west1
GOOGLE_OAUTH_CLIENT_ID=stavi_oauth_client_id
GOOGLE_OAUTH_CLIENT_SECRET=stavi_oauth_client_secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback
USE_CLOUD_LOGGING=false
GEMINI_VOICE_NAME=Charon
VOICE_ASSISTANT_NAME=Jarvis
VOICE_ASSISTANT_STYLE=smiren, profesionalan, kratak, diskretno butlerovski
TELEGRAM_BOT_TOKEN=stavi_bot_token
OAUTH_TOKEN_STORAGE_PATH=/opt/google-clause/state/oauth/tokens.json
USE_PERSISTENT_ADK_SESSIONS=true
MQTT_BROKER=IP_ILI_HOST_MQTT_BROKERA
MQTT_PORT=1883
MQTT_USER=korisnik_ako_postoji
MQTT_PASS=lozinka_ako_postoji
HA_MQTT_DISCOVERY_ENABLED=true
HA_MQTT_DISCOVERY_PREFIX=homeassistant
HA_MQTT_STATE_PREFIX=google_clause/rpi_voice
HA_MQTT_DEVICE_ID=google_clause_rpi_voice
HA_MQTT_DEVICE_NAME=Jarvis
WAKEWORD_API_BASE_URL=http://127.0.0.1:8000
WAKEWORD_USER_ID=rpi-voice
PICOVOICE_ACCESS_KEY=stavi_picovoice_kljuc
WAKEWORD_KEYWORDS=jarvis
WAKEWORD_SENSITIVITY=0.65
WAKEWORD_RECORD_SECONDS_MAX=8
WAKEWORD_SILENCE_SECONDS=1.2
WAKEWORD_MIN_SPEECH_SECONDS=0.6
WAKEWORD_ENERGY_THRESHOLD=900
WAKEWORD_INPUT_DEVICE=
WAKEWORD_OUTPUT_DEVICE=
WAKEWORD_TTS_ENABLED=true
LIVE_INPUT_SAMPLE_RATE=16000
LIVE_OUTPUT_SAMPLE_RATE=24000
LIVE_BLOCK_SIZE=8192
LIVE_ENERGY_THRESHOLD=650
LIVE_IDLE_TIMEOUT_SECONDS=8
LIVE_MIN_SESSION_SECONDS=2
LIVE_MAX_SESSION_SECONDS=90
LIVE_CONTROL_SILENCE_SECONDS=1.0
LIVE_CONTROL_MIN_SPEECH_SECONDS=0.5
LIVE_CONTROL_MAX_RECORD_SECONDS=4.0
TELEGRAM_AUDIO_MAX_DURATION_SECONDS=120
```
