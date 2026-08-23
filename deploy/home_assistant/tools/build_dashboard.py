"""Rebuild the Pregled, Sobe and Sustav views of the Jarvis dashboard.

Sobe is generated from the entity registry rather than written by hand, so a
room shows everything that is actually assigned to it and a new sensor turns up
by rerunning this instead of being forgotten.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict

import websockets

URL = os.environ["HA_URL"].replace("http://", "ws://") + "/api/websocket"
TOKEN = os.environ["HA_TOKEN"]
BOARD = "jarvis-dom"
PIPELINE = "01m0qf25e4jzkgg20eterh9jbf"
BACKUP = os.getenv("DASHBOARD_BACKUP", "/tmp/jarvis-dom-backup.json")

# Rooms in the order they should appear, with an icon each.
ROOM_ORDER = [
    ("living_room", "mdi:sofa"),
    ("kitchen", "mdi:countertop"),
    ("blagavaona", "mdi:table-furniture"),
    ("bedroom", "mdi:bed"),
    ("kupaona", "mdi:shower"),
    ("hodnik", "mdi:door-open"),
    ("ulaz", "mdi:door"),
    ("terasa", "mdi:flower"),
    ("vani", "mdi:tree"),
    ("kuca", "mdi:home-lightning-bolt"),
]

# Within a room, controls first and readings after.
DOMAIN_ORDER = ["light", "switch", "media_player", "button", "binary_sensor", "sensor"]

DEVICE_PREFIXES = ("ESP32 IO ", "BME280 Mux Node ", "Bme280 Mux Node ")


def short_name(friendly: str, entity_id: str) -> str:
    name = friendly or entity_id.split(".", 1)[1].replace("_", " ")
    for prefix in DEVICE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name[:1].upper() + name[1:]


# --- Sustav: one markdown card per machine ------------------------------------

def _status(entity: str) -> str:
    """Jinja that prints a green or red line depending on availability."""
    return (
        "{% if states('" + entity + "') in ['unavailable', 'unknown', 'none'] %}"
        "### 🔴 OFFLINE\n"
        "{% else %}"
        "### 🟢 Online\n"
        "{% endif %}"
    )


def _uptime_from_boot(entity: str) -> str:
    return (
        "{% set b = states('" + entity + "') %}"
        "{% if b not in ['unavailable','unknown','none'] %}"
        "{% set s = (now().timestamp() - as_timestamp(b)) | int %}"
        "{{ s // 86400 }} d {{ (s % 86400) // 3600 }} h"
        "{% else %}—{% endif %}"
    )


def _uptime_from_seconds(entity: str) -> str:
    return (
        "{% set v = states('" + entity + "') %}"
        "{% if v not in ['unavailable','unknown','none'] %}"
        "{% set s = v | float(0) | int %}"
        "{{ s // 86400 }} d {{ (s % 86400) // 3600 }} h"
        "{% else %}—{% endif %}"
    )


HOME_ASSISTANT_CARD = (
    "## 🖥 Home Assistant\n"
    + _status("sensor.system_monitor_processor_use")
    + "\n"
    "| | |\n|---|--:|\n"
    "| Procesor | {{ states('sensor.system_monitor_processor_use') }} % |\n"
    "| Memorija | {{ states('sensor.system_monitor_memory_usage') }} % |\n"
    "| Temperatura | {{ states('sensor.system_monitor_processor_temperature') }} °C |\n"
    "| Ventilator | {{ states('sensor.system_monitor_pwmfan_fan_speed') }} o/min |\n"
    "| Disk | {{ states('sensor.system_monitor_disk_usage') }} % "
    "({{ states('sensor.system_monitor_disk_free_config') }} GiB slobodno) |\n"
    "| Radi | " + _uptime_from_boot("sensor.system_monitor_last_boot") + " |\n"
    "| IP | {{ states('sensor.system_monitor_ipv4_address_end0') }} |\n"
    "| Verzija | {{ state_attr('update.home_assistant_core_update','installed_version') }}"
    "{% if is_state('update.home_assistant_core_update','on') %} → "
    "{{ state_attr('update.home_assistant_core_update','latest_version') }} dostupno{% endif %} |\n"
    "| Napajanje | {% if is_state('binary_sensor.rpi_power_status','on') %}"
    "⚠️ podnapon{% else %}u redu{% endif %} |\n"
)

JARVIS_CARD = (
    "## 🤖 Jarvis\n"
    + _status("sensor.jarvis_pi_cpu")
    + "\n"
    "| | |\n|---|--:|\n"
    "| Procesor | {{ states('sensor.jarvis_pi_cpu') }} % |\n"
    "| Memorija | {{ states('sensor.jarvis_pi_memory') }} % |\n"
    "| Temperatura | {{ states('sensor.jarvis_pi_temperature') }} °C |\n"
    "| Opterećenje | {{ states('sensor.jarvis_pi_load_1m') }} |\n"
    "| Disk | {{ states('sensor.jarvis_pi_disk') }} % "
    "({{ states('sensor.jarvis_pi_disk_free_gb') }} GB slobodno) |\n"
    "| Radi | " + _uptime_from_boot("sensor.jarvis_pi_boot") + " |\n"
    "| IP | {{ states('sensor.jarvis_pi_ip') }} |\n"
    "| Glas | {% if states('stt.jarvis_stt') not in ['unavailable','unknown'] %}"
    "sluša i govori{% else %}⚠️ nedostupan{% endif %} |\n"
)

ESP32_CARD = (
    "## 🔌 ESP32 I/O\n"
    + _status("switch.esp32_io_svjetlo_kuhinja")
    + "\n"
    "| | |\n|---|--:|\n"
    "| Firmware | {{ state_attr('update.esp32_io_firmware','installed_version') or '—' }}"
    "{% if is_state('update.esp32_io_firmware','on') %} → novi dostupan{% endif %} |\n"
    "| Upaljenih svjetala | {{ states.switch "
    "| selectattr('entity_id','search','esp32_io_svjetlo') | selectattr('state','eq','on') "
    "| list | count }} |\n"
    "| Uključenih utičnica | {{ states.switch "
    "| selectattr('entity_id','search','esp32_io_uticnica') | selectattr('state','eq','on') "
    "| list | count }} |\n"
    "\n_Uptime i jačina Wi-Fi signala nisu dostupni — čvor ih ne objavljuje; "
    "traži dopunu ESPHome konfiguracije._\n"
)

BME_CARD = (
    "## 🌡 BME280 Mux Node\n"
    + _status("sensor.bme280_mux_node_bme280_mux_uptime")
    + "\n"
    "| | |\n|---|--:|\n"
    "| Wi-Fi | {{ states('sensor.bme280_mux_node_bme280_mux_wifi_signal') }} dBm |\n"
    "| Radi | " + _uptime_from_seconds("sensor.bme280_mux_node_bme280_mux_uptime") + " |\n"
    "| Senzora temperature | {{ states.sensor "
    "| selectattr('entity_id','search','bme280_mux_node_.*temperatura') "
    "| rejectattr('state','in',['unavailable','unknown']) | list | count }} / 5 |\n"
    "| PM2.5 | {{ states('sensor.bme280_mux_node_kvaliteta_zraka_pm2_5') "
    "| float(0) | round(1) }} µg/m³ |\n"
    "| Mrežni napon | {% set v = states('sensor.bme280_mux_node_mrezni_napon') %}"
    "{% if v in ['unavailable','unknown','none'] %}— (mjerenje snage ne radi)"
    "{% else %}{{ v | float(0) | round(1) }} V{% endif %} |\n"
)


def system_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 2,
        "title": "Sustav",
        "path": "sustav",
        "icon": "mdi:heart-pulse",
        "sections": [
            {"type": "grid", "cards": [{"type": "markdown", "content": HOME_ASSISTANT_CARD}]},
            {"type": "grid", "cards": [{"type": "markdown", "content": JARVIS_CARD}]},
            {"type": "grid", "cards": [{"type": "markdown", "content": ESP32_CARD}]},
            {"type": "grid", "cards": [{"type": "markdown", "content": BME_CARD}]},
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Nadogradnje i dodaci",
                     "heading_style": "subtitle", "icon": "mdi:package-up"},
                    {"type": "entities", "entities": [
                        {"entity": "update.home_assistant_core_update", "name": "Home Assistant"},
                        {"entity": "update.home_assistant_operating_system_update", "name": "Operativni sustav"},
                        {"entity": "update.home_assistant_supervisor_update", "name": "Supervisor"},
                        {"entity": "update.esphome_device_builder_update", "name": "ESPHome"},
                        {"entity": "update.mosquitto_broker_update", "name": "Mosquitto"},
                        {"entity": "update.tailscale_update", "name": "Tailscale"},
                    ]},
                    {"type": "entities", "title": "Dodaci rade", "entities": [
                        {"entity": "binary_sensor.mosquitto_broker_running", "name": "Mosquitto"},
                        {"entity": "binary_sensor.tailscale_running", "name": "Tailscale"},
                        {"entity": "binary_sensor.esphome_device_builder_running", "name": "ESPHome"},
                        {"entity": "binary_sensor.studio_code_server_running", "name": "Studio Code"},
                        {"entity": "binary_sensor.samba_share_running", "name": "Samba"},
                        {"entity": "binary_sensor.advanced_ssh_web_terminal_running", "name": "SSH terminal"},
                    ]},
                ],
            },
        ],
    }


# --- Pregled -------------------------------------------------------------------

SUN_CARD = (
    "## ☀️ Sunce\n"
    "| | |\n|---|--:|\n"
    "| Izlazak | {{ as_timestamp(states('sensor.sun_next_rising')) "
    "| timestamp_custom('%H:%M') }} |\n"
    "| Zalazak | {{ as_timestamp(states('sensor.sun_next_setting')) "
    "| timestamp_custom('%H:%M') }} |\n"
    "| Svanuće | {{ as_timestamp(states('sensor.sun_next_dawn')) "
    "| timestamp_custom('%H:%M') }} |\n"
    "| Sumrak | {{ as_timestamp(states('sensor.sun_next_dusk')) "
    "| timestamp_custom('%H:%M') }} |\n"
    "| Podne | {{ as_timestamp(states('sensor.sun_next_noon')) "
    "| timestamp_custom('%H:%M') }} |\n"
    "\n{% set s = as_timestamp(states('sensor.sun_next_setting')) - now().timestamp() %}"
    "{% if is_state('sun.sun','above_horizon') %}"
    "Dan traje još {{ (s // 3600) | int }} h {{ ((s % 3600) // 60) | int }} min."
    "{% else %}Sunce je zašlo.{% endif %}\n"
)

ZADNJI_RAZGOVOR = (
    "{% set t = state_attr('sensor.jarvis_razgovor','povijest') %}"
    "{% if t %}**{{ as_timestamp(t[0]['vrijeme']) | timestamp_custom('%H:%M') }} · ti**\n"
    "{{ t[0]['pitanje'] }}\n\n**Jarvis**\n{{ t[0]['odgovor'] }}\n"
    "{% else %}_Još nema razgovora._{% endif %}"
)

STANJE_KUCE = (
    "{% set sv = states.switch | selectattr('entity_id','search','esp32_io_svjetlo') "
    "| selectattr('state','eq','on') | list %}"
    "{% set ut = states.switch | selectattr('entity_id','search','esp32_io_uticnica') "
    "| selectattr('state','eq','on') | list %}"
    "🔆 **{{ sv | count }}** upaljenih svjetala &nbsp;·&nbsp; "
    "🔌 **{{ ut | count }}** uključenih utičnica\n\n"
    "{% if sv %}{{ sv | map(attribute='name') | map('replace','ESP32 IO Svjetlo ','') "
    "| join(', ') }}{% else %}Sva svjetla su ugašena.{% endif %}\n"
)


def overview_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 4,
        "title": "Pregled",
        "path": "pregled",
        "icon": "mdi:view-dashboard",
        "sections": [
            {"type": "grid", "cards": [
                {"type": "clock", "clock_style": "digital", "clock_size": "large",
                 "show_seconds": False, "no_background": False,
                 "time_zone": "Europe/Zagreb", "face_style": "markers",
                 "grid_options": {"columns": 12, "rows": 2}},
                {"type": "weather-forecast", "entity": "weather.forecast_dom",
                 "forecast_type": "daily", "show_current": True, "show_forecast": True},
                {"type": "markdown", "content": SUN_CARD},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": "Klima sada", "heading_style": "subtitle",
                 "icon": "mdi:thermometer"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_vanjska_temperatura", "name": "Vani"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_dnevni_prostor_temperatura",
                 "name": "Dnevni boravak"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_soba_temperatura", "name": "Soba"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_kupaona_temperatura", "name": "Kupaona"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_ulaz_temperatura", "name": "Ulaz"},
                {"type": "statistic", "entity": "sensor.bme280_mux_node_vanjska_temperatura",
                 "name": "Vani — najviša danas", "stat_type": "max",
                 "period": {"calendar": {"period": "day"}}},
                {"type": "statistic", "entity": "sensor.bme280_mux_node_vanjska_temperatura",
                 "name": "Vani — najniža danas", "stat_type": "min",
                 "period": {"calendar": {"period": "day"}}},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": "Stanje kuće", "heading_style": "subtitle",
                 "icon": "mdi:home-heart"},
                {"type": "markdown", "content": STANJE_KUCE},
                {"type": "tile", "entity": "media_player.tv", "name": "TV",
                 "features": [{"type": "media-player-volume-slider"}]},
                {"type": "tile", "entity": "person.tomislav", "name": "Tomislav"},
                {"type": "tile", "entity": "todo.shopping_list", "name": "Popis za kupovinu"},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": "Zrak", "heading_style": "subtitle",
                 "icon": "mdi:air-filter"},
                {"type": "gauge", "entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm2_5",
                 "name": "PM2.5", "min": 0, "max": 250, "needle": True,
                 "severity": {"green": 0, "yellow": 35, "red": 100}},
                {"type": "tile", "entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm10", "name": "PM10"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_dnevni_prostor_vlaga", "name": "Vlaga"},
                {"type": "tile", "entity": "sensor.bme280_mux_node_vanjski_tlak", "name": "Tlak"},
            ]},
            {"type": "grid", "cards": [
                {"type": "heading", "heading": "Jarvis", "heading_style": "subtitle",
                 "icon": "mdi:robot"},
                {"type": "button", "name": "Pitaj Jarvisa", "icon": "mdi:microphone",
                 "show_state": False,
                 "tap_action": {"action": "assist", "pipeline_id": PIPELINE,
                                "start_listening": True}},
                {"type": "markdown", "content": ZADNJI_RAZGOVOR},
            ]},
        ],
    }


# --- Sobe, generated from the registry ------------------------------------------

def rooms_view(by_area: dict, area_names: dict) -> dict:
    sections = []
    for area_id, icon in ROOM_ORDER:
        entities = by_area.get(area_id) or []
        if not entities:
            continue
        cards = [{
            "type": "heading",
            "heading": area_names.get(area_id, area_id),
            "heading_style": "title",
            "icon": icon,
        }]
        for domain in DOMAIN_ORDER:
            group = [e for e in entities if e["entity_id"].startswith(domain + ".")]
            for item in sorted(group, key=lambda e: e["name"].lower()):
                card = {"type": "tile", "entity": item["entity_id"], "name": item["name"]}
                if domain in ("light", "switch"):
                    card["tap_action"] = {"action": "toggle"}
                    card["icon_tap_action"] = {"action": "toggle"}
                else:
                    card["tap_action"] = {"action": "more-info"}
                cards.append(card)
        sections.append({"type": "grid", "cards": cards})
    return {
        "type": "sections",
        "max_columns": 3,
        "title": "Sobe",
        "path": "sobe",
        "icon": "mdi:floor-plan",
        "sections": sections,
    }


async def call(ws, ident, payload):
    await ws.send(json.dumps({"id": ident, **payload}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == ident and msg.get("type") == "result":
            if not msg.get("success"):
                sys.exit("GRESKA: " + json.dumps(msg.get("error"), ensure_ascii=False))
            return msg.get("result")


async def main():
    async with websockets.connect(URL, open_timeout=10, max_size=40_000_000) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": TOKEN}))
        if json.loads(await ws.recv()).get("type") != "auth_ok":
            sys.exit("auth odbijen")

        areas = await call(ws, 1, {"type": "config/area_registry/list"})
        entities = await call(ws, 2, {"type": "config/entity_registry/list"})
        states = {s["entity_id"]: s for s in await call(ws, 3, {"type": "get_states"})}
        area_names = {a["area_id"]: a["name"] for a in areas}

        by_area = defaultdict(list)
        for entry in entities:
            area_id = entry.get("area_id")
            if not area_id or entry.get("disabled_by") or entry.get("hidden_by"):
                continue
            state = states.get(entry["entity_id"])
            if state is None:
                continue
            by_area[area_id].append({
                "entity_id": entry["entity_id"],
                "name": short_name(state["attributes"].get("friendly_name", ""), entry["entity_id"]),
            })

        print("  entiteta po prostoriji:")
        for area_id, _ in ROOM_ORDER:
            print(f"    {area_names.get(area_id, area_id):18} {len(by_area.get(area_id) or [])}")

        cfg = await call(ws, 4, {"type": "lovelace/config", "url_path": BOARD})
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f"\n  kopija prije izmjene: {BACKUP}")

        replacements = {
            "pregled": overview_view(),
            "sobe": rooms_view(by_area, area_names),
            "sustav": system_view(),
        }
        views = []
        for view in cfg["views"]:
            path = view.get("path")
            views.append(replacements.pop(path, view))
        views.extend(replacements.values())
        cfg["views"] = views

        await call(ws, 5, {"type": "lovelace/config/save", "url_path": BOARD, "config": cfg})
        after = await call(ws, 6, {"type": "lovelace/config", "url_path": BOARD})
        print("  prikazi:", [v.get("title") for v in after["views"]])


if __name__ == "__main__":  # importable, so the pure helpers can be tested
    asyncio.run(main())
