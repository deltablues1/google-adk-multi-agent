# Home Assistant Integration Notes

## Recommended Architecture

If Home Assistant already exists in your setup, keep this project as a separate service on the Raspberry Pi and integrate it with HA over LAN.

Recommended split:
- Home Assistant remains the smart-home control plane
- this project remains the agent, voice, Telegram, and orchestration plane

That avoids forcing this repo into a Home Assistant app/add-on shape before it is necessary.

## Best V1 Integration Options

## 1. HA Dashboard Web App

Use a Home Assistant dashboard `webpage` card or sidebar entry that points to:

`http://<rpi-ip>:8000`

This is the fastest path if you want the web UI available inside Home Assistant.

Example YAML is in:
- `deploy/home_assistant/examples/webpage_dashboard.yaml`

## 2. HA REST Status + Trigger Bridge

Use Home Assistant `rest` and `rest_command` definitions to:
- show API health and deployment profile in HA
- trigger simple agent requests from HA automations

Example YAML is in:
- `deploy/home_assistant/examples/google_clause_status.yaml`

## 3. MQTT Bridge

This is the strongest long-term integration if your house already relies on MQTT.

Recommended next step for HA-native feel:
- publish health and voice-mode state over MQTT
- publish command/result events over MQTT
- expose entities with MQTT Discovery

Current minimal implementation exposes these MQTT Discovery entities:
- current voice mode
- online/offline status
- last command/result

Home Assistant can also send a mode change back through MQTT:
- `agent`
- `live`

## 4. Future HA-Native Paths

If you later want tighter HA ownership, there are two stronger options:

- custom HA integration
  - best when you want entities, services, config flow, and better HA UX
- HA app/add-on
  - best when you want the whole service lifecycle managed by Home Assistant Supervisor

The add-on path is possible, but it is not the best first deployment target because the current repo is already shaped around `venv + systemd`.

## Recommended Decision

For v1:
- run this project on `Raspberry Pi OS Lite 64-bit`
- keep Home Assistant separate
- embed the web UI in HA
- add REST status now
- add MQTT Discovery next if you want HA-native entities
