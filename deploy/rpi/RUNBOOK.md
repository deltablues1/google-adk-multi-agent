# Raspberry Pi 5 Deployment Runbook

## Recommended Host OS

Use `Raspberry Pi OS Lite 64-bit` on the Pi that will run this project.

Reason:
- the current deployment model in this repo is native `venv + systemd`
- wake-word audio access is simpler on a normal Linux host
- Home Assistant OS is better when the box is dedicated to Home Assistant apps/add-ons, not arbitrary Python services

If you want Home Assistant on the same Pi, the cleaner long-term path is:
- either keep this project on `Raspberry Pi OS Lite 64-bit` and connect it to an existing HA instance
- or later package this project as a real Home Assistant app/add-on

## 1. Flash And First Boot

Flash `Raspberry Pi OS Lite 64-bit` with Raspberry Pi Imager.

Recommended Imager options:
- hostname: `rpi5-jarvis`
- enable SSH
- set Wi-Fi only if you will not use Ethernet
- set locale/timezone correctly

After first boot:

```bash
sudo apt-get update && sudo apt-get full-upgrade -y
sudo reboot
```

## 2. Copy The Repo

Clone or copy this repo to `/opt/google-clause`.

Example:

```bash
sudo mkdir -p /opt/google-clause
sudo chown -R $USER:$USER /opt/google-clause
git clone <your-repo-url> /opt/google-clause
cd /opt/google-clause
```

## 3. Run Setup

```bash
cd /opt/google-clause
chmod +x deploy/rpi/setup.sh
./deploy/rpi/setup.sh
```

This will:
- install system dependencies
- create `.venv`
- install Python dependencies
- create `deploy/rpi/.env.rpi` from the example if needed
- copy systemd units into `/etc/systemd/system`

## 4. Fill In Environment

Edit:

```bash
nano /opt/google-clause/deploy/rpi/.env.rpi
```

Minimum required values:
- `API_TOKEN`
- `GEMINI_API_KEY`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN` if Telegram is enabled
- `MQTT_*` if HA and smart-home actions rely on MQTT

Voice defaults:
- `GEMINI_VOICE_NAME=Charon`
- `VOICE_ASSISTANT_NAME=Jarvis`
- `WAKEWORD_ENGINE=openwakeword` (free, no key; default)
- `WAKEWORD_MODEL=hey_jarvis`
- `WAKEWORD_THRESHOLD=0.5`

To use Porcupine instead: set `WAKEWORD_ENGINE=porcupine`, provide
`PICOVOICE_ACCESS_KEY`, and `pip install pvporcupine`.

HA MQTT Discovery defaults:
- `HA_MQTT_DISCOVERY_ENABLED=true`
- `HA_MQTT_DISCOVERY_PREFIX=homeassistant`
- `HA_MQTT_STATE_PREFIX=google_clause/rpi_voice`

Recommended RPi profile:
- `DEPLOYMENT_PROFILE=rpi-home`
- `ERP_ENABLED=false`
- `API_TOKEN_REQUIRED=true`

Create a secrets directory for the service account file:

```bash
mkdir -p /opt/google-clause/secrets
chmod 700 /opt/google-clause/secrets
```

Then copy your service account JSON to:

```bash
/opt/google-clause/secrets/service_account_key.json
```

If you already have a working OAuth token file from your current machine, also copy it to:

```bash
/opt/google-clause/state/oauth/tokens.json
```

## 5. Audio Device Check

List ALSA devices:

```bash
arecord -l
aplay -l
```

List sounddevice devices:

```bash
/opt/google-clause/.venv/bin/python -c "import sounddevice as sd; print(sd.query_devices())"
```

Then set:
- `WAKEWORD_INPUT_DEVICE`   (e.g. `0` — raw wm8960 capture, 16 kHz mono)
- `WAKEWORD_OUTPUT_DEVICE`  (use `default`, NOT the raw card — see note)

If left empty, the default devices are used.

### WM8960 audio HAT (important)

The wm8960 powers up with output mixers routed OFF and a capture gain that
makes speech untranscribable. Configure it once:

```bash
bash deploy/rpi/setup_audio.sh
```

Two gotchas this solves (both cost real debugging time):
- **Playback silent**: the raw card (`hw:2,0`, device index `0`) rejects the
  24 kHz TTS audio (`Invalid sample rate`). Set `WAKEWORD_OUTPUT_DEVICE=default`
  so ALSA's plug layer resamples. The DAC→output-mixer routing
  (`Left/Right Output Mixer PCM`) must also be `on` or nothing comes out.
- **STT hears garbage** (e.g. "Waqfati" for Croatian): capture gain wrong.
  Full boost CLIPS (empty transcript); too low mishears. `Capture 50%` with no
  input boost gives clean transcripts.

If you are using a `ReSpeaker 2-Mics Pi HAT`, read:
- `deploy/rpi/MIC2_HAT.md`

Recommended order for that board:
- install the overlay/driver first
- verify `arecord` and `aplay`
- only then enable `adk-wakeword.service`

## 6. Smoke Tests

Web app:

```bash
cd /opt/google-clause
source .venv/bin/activate
python run_web.py --host 0.0.0.0 --port 8000
```

Wake word runner:

```bash
cd /opt/google-clause
source .venv/bin/activate
python scripts/run_wakeword.py --wakeword
```

Telegram bot:

```bash
cd /opt/google-clause
source .venv/bin/activate
python scripts/telegram_bot.py
```

## 7. Enable Services

After the smoke tests succeed:

```bash
sudo systemctl enable --now adk-web.service
sudo systemctl enable --now adk-scheduler.service
sudo systemctl enable --now adk-telegram.service
sudo systemctl enable --now adk-wakeword.service
```

## 8. Logs

```bash
sudo journalctl -u adk-web.service -f
sudo journalctl -u adk-wakeword.service -f
sudo journalctl -u adk-telegram.service -f
sudo journalctl -u adk-scheduler.service -f
```

## 9. Recommended Validation Order

1. `/api/status` responds over LAN
2. web chat works
3. Telegram text works
4. Telegram voice works
5. wake word triggers
6. `agent` mode handles commands
7. `live` mode opens and exits back to `agent`

## 10. LAN Exposure

Recommended v1 network model:
- keep port `8000` available only on the home LAN
- use Telegram polling for remote access
- add reverse proxy or tunnel later, not in the first deployment pass
