"""
MQTT ADK Tools - Smart Home upravljanje preko ESP32 + Home Assistant

Svi alati komuniciraju s ESP32-IO MQTT brokerom za upravljanje
svjetlima, utičnicama i dimmerom u kući.
"""

import json
import logging
import asyncio
import os
from typing import Optional

logger = logging.getLogger(__name__)

# MQTT broker config (credentials via .env, not hardcoded)
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.100.200")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Topic prefixes
SWITCH_PREFIX = "esp32-io/switch"
LIGHT_PREFIX = "esp32-io/light"
SENSOR_PREFIX = "esp32-io/binary_sensor"

# Valid switch names (lights + outlets)
VALID_LIGHTS = [
    "svjetlo_vani", "svjetlo_terasa1", "svjetlo_terasa2", "svjetlo_ulaz",
    "svjetlo_hidrofor", "svjetlo_tv", "svjetlo_stup", "svjetlo_boravak",
    "svjetlo_blagavaona", "svjetlo_kuhinja", "svjetlo_sank", "svjetlo_hodnik",
    "svjetlo_kupaona", "svjetlo_soba1", "svjetlo_soba2"
]

VALID_OUTLETS = [
    "uticnica_ulaz", "uticnica_kuhinja", "uticnica_frizider", "uticnica_kupaona",
    "uticnica_bojler", "uticnica_terasa", "uticnica_tv", "uticnica_boravak",
    "uticnica_blagavaona", "pecnica", "uticnica_soba1", "uticnica_soba2",
    "slobodno1", "slobodno2"
]

VALID_SWITCHES = VALID_LIGHTS + VALID_OUTLETS

# Human-readable names (Croatian)
DEVICE_NAMES = {
    "svjetlo_vani": "Vanjsko svjetlo",
    "svjetlo_terasa1": "Terasa 1",
    "svjetlo_terasa2": "Terasa 2",
    "svjetlo_ulaz": "Ulaz",
    "svjetlo_hidrofor": "Hidrofor",
    "svjetlo_tv": "TV svjetlo",
    "svjetlo_stup": "Stup",
    "svjetlo_boravak": "Boravak",
    "svjetlo_blagavaona": "Blagavaona",
    "svjetlo_kuhinja": "Kuhinja",
    "svjetlo_sank": "Šank",
    "svjetlo_hodnik": "Hodnik",
    "svjetlo_kupaona": "Kupaona",
    "svjetlo_soba1": "Soba 1",
    "svjetlo_soba2": "Soba 2",
    "svjetlo_fotelja": "Fotelja (dimmer)",
    "uticnica_ulaz": "Utičnica ulaz",
    "uticnica_kuhinja": "Utičnica kuhinja",
    "uticnica_frizider": "Frižider",
    "uticnica_kupaona": "Utičnica kupaona",
    "uticnica_bojler": "Bojler",
    "uticnica_terasa": "Utičnica terasa",
    "uticnica_tv": "Utičnica TV",
    "uticnica_boravak": "Utičnica boravak",
    "uticnica_blagavaona": "Utičnica blagavaona",
    "pecnica": "Pećnica",
    "uticnica_soba1": "Utičnica soba 1",
    "uticnica_soba2": "Utičnica soba 2",
    "slobodno1": "Rezerva 1",
    "slobodno2": "Rezerva 2",
}


def _get_mqtt_client():
    """Create and connect MQTT client (sync)"""
    import paho.mqtt.client as mqtt

    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
    return client


def _publish_and_disconnect(topic: str, payload: str) -> dict:
    """Publish a single message and disconnect"""
    try:
        client = _get_mqtt_client()
        result = client.publish(topic, payload, qos=1)
        result.wait_for_publish(timeout=5)
        client.disconnect()
        return {"status": "ok", "topic": topic, "payload": payload}
    except Exception as e:
        logger.error(f"MQTT publish failed: {e}")
        return {"status": "error", "error": str(e)}


# ============================================================================
# ADK TOOL FUNCTIONS
# ============================================================================

async def mqtt_switch_control(device_name: str, state: str) -> dict:
    """
    Turn a light or outlet ON or OFF.

    Controls any switch-type device in the smart home system (lights and outlets).
    Note: turning on svjetlo_kupaona automatically turns off bojler (hardware interlock).

    Args:
        device_name: Device identifier, e.g. "svjetlo_kuhinja", "uticnica_tv", "pecnica".
                     Use mqtt_list_devices to see all available devices.
        state: "ON" or "OFF"

    Returns:
        Dictionary with status, topic, and payload sent.
    """
    state = state.upper().strip()
    if state not in ("ON", "OFF"):
        return {"status": "error", "error": f"State must be ON or OFF, got: {state}"}

    device_name = device_name.strip().lower()
    if device_name not in VALID_SWITCHES:
        return {
            "status": "error",
            "error": f"Unknown device: {device_name}. Use mqtt_list_devices to see valid names.",
        }

    topic = f"{SWITCH_PREFIX}/{device_name}/command"
    friendly = DEVICE_NAMES.get(device_name, device_name)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _publish_and_disconnect, topic, state)
    result["device"] = friendly
    result["action"] = f"{'Uključeno' if state == 'ON' else 'Isključeno'}: {friendly}"
    logger.info(f"MQTT switch: {friendly} -> {state}")
    return result


async def mqtt_dimmer_control(state: str, brightness: int = 255) -> dict:
    """
    Control the dimmable armchair light (svjetlo_fotelja).

    Args:
        state: "ON" or "OFF"
        brightness: Brightness level 0-255 (64=25%, 128=50%, 191=75%, 255=100%).
                    Only used when state is "ON".

    Returns:
        Dictionary with status and payload sent.
    """
    state = state.upper().strip()
    if state not in ("ON", "OFF"):
        return {"status": "error", "error": f"State must be ON or OFF, got: {state}"}

    brightness = max(0, min(255, int(brightness)))

    if state == "ON":
        payload = json.dumps({"state": "ON", "brightness": brightness})
    else:
        payload = json.dumps({"state": "OFF"})

    topic = f"{LIGHT_PREFIX}/svjetlo_fotelja/command"

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _publish_and_disconnect, topic, payload)
    result["device"] = "Fotelja (dimmer)"
    if state == "ON":
        pct = round(brightness / 255 * 100)
        result["action"] = f"Fotelja upaljena na {pct}%"
    else:
        result["action"] = "Fotelja ugašena"
    logger.info(f"MQTT dimmer: fotelja -> {state} (brightness={brightness})")
    return result


async def mqtt_scene_control(scene: str) -> dict:
    """
    Activate a predefined scene (multiple devices at once).

    Available scenes:
    - "sve_ugasi" : Turn off ALL lights and outlets
    - "nocno" : Night mode - only hodnik at low brightness + fotelja at 25%
    - "film" : Movie mode - TV light + TV outlet ON, fotelja 25%, all others OFF
    - "dolazak" : Arrival - ulaz + hodnik + boravak + vani ON
    - "odlazak" : Leaving - everything OFF except frizider
    - "kuhanje" : Cooking - kuhinja + sank + blagavaona ON

    Args:
        scene: Scene name from the list above.

    Returns:
        Dictionary with status and list of actions performed.
    """
    scene = scene.strip().lower()

    scenes = {
        "sve_ugasi": {
            "switches_off": VALID_LIGHTS + [o for o in VALID_OUTLETS if o != "uticnica_frizider"],
            "dimmer": {"state": "OFF"},
            "description": "Sve ugašeno",
        },
        "nocno": {
            "switches_off": [l for l in VALID_LIGHTS if l not in ("svjetlo_hodnik",)],
            "switches_on": ["svjetlo_hodnik"],
            "dimmer": {"state": "ON", "brightness": 64},
            "description": "Noćni režim",
        },
        "film": {
            "switches_off": [l for l in VALID_LIGHTS if l not in ("svjetlo_tv",)],
            "switches_on": ["svjetlo_tv", "uticnica_tv"],
            "dimmer": {"state": "ON", "brightness": 64},
            "description": "Filmski režim",
        },
        "dolazak": {
            "switches_on": ["svjetlo_ulaz", "svjetlo_hodnik", "svjetlo_boravak", "svjetlo_vani"],
            "description": "Dolazak kući",
        },
        "odlazak": {
            "switches_off": VALID_LIGHTS + [o for o in VALID_OUTLETS if o != "uticnica_frizider"],
            "dimmer": {"state": "OFF"},
            "description": "Odlazak - sve ugašeno (osim frižidera)",
        },
        "kuhanje": {
            "switches_on": ["svjetlo_kuhinja", "svjetlo_sank", "svjetlo_blagavaona"],
            "description": "Kuhanje",
        },
    }

    if scene not in scenes:
        return {
            "status": "error",
            "error": f"Unknown scene: {scene}. Available: {', '.join(scenes.keys())}",
        }

    cfg = scenes[scene]
    actions = []

    try:
        client = _get_mqtt_client()

        # Turn OFF switches
        for dev in cfg.get("switches_off", []):
            topic = f"{SWITCH_PREFIX}/{dev}/command"
            client.publish(topic, "OFF", qos=1)
            actions.append(f"{DEVICE_NAMES.get(dev, dev)} -> OFF")

        # Turn ON switches
        for dev in cfg.get("switches_on", []):
            topic = f"{SWITCH_PREFIX}/{dev}/command"
            client.publish(topic, "ON", qos=1)
            actions.append(f"{DEVICE_NAMES.get(dev, dev)} -> ON")

        # Dimmer
        if "dimmer" in cfg:
            d = cfg["dimmer"]
            payload = json.dumps(d)
            client.publish(f"{LIGHT_PREFIX}/svjetlo_fotelja/command", payload, qos=1)
            if d["state"] == "ON":
                pct = round(d.get("brightness", 255) / 255 * 100)
                actions.append(f"Fotelja -> ON ({pct}%)")
            else:
                actions.append("Fotelja -> OFF")

        # Small delay to allow all messages to be sent
        import time
        time.sleep(0.5)
        client.disconnect()

        logger.info(f"MQTT scene '{scene}': {len(actions)} actions")
        return {
            "status": "ok",
            "scene": scene,
            "description": cfg["description"],
            "actions": actions,
            "total_actions": len(actions),
        }
    except Exception as e:
        logger.error(f"MQTT scene '{scene}' failed: {e}")
        return {"status": "error", "error": str(e)}


async def mqtt_get_status() -> dict:
    """
    Read current state of all devices by subscribing to state topics.

    Connects to MQTT broker, subscribes to all state topics, waits for responses,
    and returns the current state of all lights, outlets, dimmer, and sensors.

    Returns:
        Dictionary with device states grouped by category (lights, outlets, dimmer, sensors).
    """
    import paho.mqtt.client as mqtt
    import time

    states = {}
    received_event = asyncio.Event()

    def on_message(client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        states[topic] = payload

    def _subscribe_and_collect():
        client = mqtt.Client()
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.on_message = on_message
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)

        # Subscribe to all state topics
        client.subscribe(f"{SWITCH_PREFIX}/+/state")
        client.subscribe(f"{LIGHT_PREFIX}/+/state")
        client.subscribe(f"{SENSOR_PREFIX}/+/state")
        client.subscribe("esp32-io/status")

        # Collect messages for 2 seconds
        client.loop_start()
        time.sleep(2)
        client.loop_stop()
        client.disconnect()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _subscribe_and_collect)

    # Organize results
    lights = {}
    outlets = {}
    dimmer = {}
    sensors = {}
    system = {}

    for topic, value in states.items():
        parts = topic.split("/")
        if len(parts) >= 3:
            device = parts[2] if len(parts) > 2 else parts[-1]
            friendly = DEVICE_NAMES.get(device, device)

            if "light/" in topic:
                try:
                    data = json.loads(value)
                    dimmer[friendly] = data
                except json.JSONDecodeError:
                    dimmer[friendly] = value
            elif "binary_sensor/" in topic:
                sensors[friendly] = value
            elif "switch/" in topic:
                if device in VALID_LIGHTS:
                    lights[friendly] = value
                elif device in VALID_OUTLETS:
                    outlets[friendly] = value
                else:
                    system[device] = value
            elif topic == "esp32-io/status":
                system["esp32_status"] = value

    return {
        "status": "ok",
        "lights": lights,
        "outlets": outlets,
        "dimmer": dimmer,
        "sensors": sensors,
        "system": system,
        "total_devices": len(lights) + len(outlets) + len(dimmer),
    }


async def mqtt_list_devices() -> dict:
    """
    List all available smart home devices with their MQTT topics.

    Returns a complete list of controllable devices grouped by type
    (lights, dimmer, outlets) with device IDs and friendly names.

    Returns:
        Dictionary with all devices grouped by category.
    """
    lights = {name: DEVICE_NAMES.get(name, name) for name in VALID_LIGHTS}
    outlets = {name: DEVICE_NAMES.get(name, name) for name in VALID_OUTLETS}

    return {
        "status": "ok",
        "lights": lights,
        "dimmer": {"svjetlo_fotelja": "Fotelja (dimmer) - brightness 0-255"},
        "outlets": outlets,
        "scenes": [
            "sve_ugasi - Ugasi sve",
            "nocno - Noćni režim (hodnik + fotelja 25%)",
            "film - Filmski režim (TV + fotelja 25%)",
            "dolazak - Ulaz + hodnik + boravak + vani",
            "odlazak - Sve ugašeno (osim frižidera)",
            "kuhanje - Kuhinja + šank + blagavaona",
        ],
        "notes": [
            "Kupaona <-> Bojler interlock: paljenje kupaone automatski gasi bojler",
            "PIR senzori: ručno paljenje blokira automatsko gašenje",
        ],
        "total": f"{len(VALID_LIGHTS)} svjetala + 1 dimmer + {len(VALID_OUTLETS)} utičnica = {len(VALID_SWITCHES) + 1} uređaja",
    }


def get_mqtt_adk_tools() -> list:
    """Get all MQTT smart home tools as a list"""
    return [
        mqtt_switch_control,
        mqtt_dimmer_control,
        mqtt_scene_control,
        mqtt_get_status,
        mqtt_list_devices,
    ]
