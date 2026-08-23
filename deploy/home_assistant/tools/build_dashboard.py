"""Rebuild the Jarvis dashboard, laid out for the 7" wall panel.

Two things drive every choice here.

First, the panel is 800x480. That is narrower than a phone in landscape, so
views are two columns wide, tiles are square and finger-sized rather than full
width rows, and prose is kept off the screen -- a paragraph of explanation is
unreadable at arm's length and steals room from the controls.

Second, the room views are generated from the entity registry rather than
written by hand, so a room shows what is actually in it and a newly added
sensor appears by rerunning this. Generation needs an exclusion list, though:
the wall push-buttons behind each light, the two unconnected spare relays and
the node's own Wi-Fi and uptime readings are all real entities that nobody
wants to see while looking at a room.
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

# Rooms in the order they should appear. "kuca" is deliberately absent: it is
# where house-wide things live, not a room, and it belongs on the System view.
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
]

# Entities that exist for good reasons but are noise inside a room. A room
# should answer "how is it in here", not list every channel of every sensor.
ROOM_EXCLUDE = (
    "tipkalo",              # the physical wall button behind each light
    "slobodno",             # spare relays with nothing wired to them
    "wifi_signal",          # belongs to the node, not the room
    "mux_uptime",
    "pokreni_ciscenje",     # SPS30 maintenance, lives on the Air view
    "broj_cestica",         # five particle counts; the Air view is their place
    "prosjecna_velicina",
    "kvaliteta_zraka_pm1",  # PM2.5 and PM10 are the two worth glancing at
    "kvaliteta_zraka_pm4",
)

CONTROL_DOMAINS = ("light", "switch", "media_player")

TEMPERATURES = [
    ("sensor.bme280_mux_node_vanjska_temperatura", "Vani"),
    ("sensor.bme280_mux_node_dnevni_prostor_temperatura", "Boravak"),
    ("sensor.bme280_mux_node_soba_temperatura", "Soba"),
    ("sensor.bme280_mux_node_kupaona_temperatura", "Kupaona"),
    ("sensor.bme280_mux_node_ulaz_temperatura", "Ulaz"),
]

HUMIDITIES = [
    ("sensor.bme280_mux_node_vanjska_vlaga", "Vani"),
    ("sensor.bme280_mux_node_dnevni_prostor_vlaga", "Boravak"),
    ("sensor.bme280_mux_node_soba_vlaga", "Soba"),
    ("sensor.bme280_mux_node_kupaona_vlaga", "Kupaona"),
    ("sensor.bme280_mux_node_ulaz_vlaga", "Ulaz"),
]

DEVICE_PREFIXES = ("ESP32 IO ", "BME280 Mux Node ", "Bme280 Mux Node ")

# A finger needs about a centimetre; a third of a 800 px view is about right.
TILE_COLUMNS = 4


def short_name(friendly: str, entity_id: str) -> str:
    name = friendly or entity_id.split(".", 1)[1].replace("_", " ")
    for prefix in DEVICE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name[:1].upper() + name[1:]


# Inside a room the only useful label for a reading is what it measures. The
# entity is called "Dnevni prostor temperatura"; the heading already said the
# room, so the card should just say "Temperatura".
MEASUREMENT_LABEL = (
    ("kvaliteta_zraka_pm2_5", "PM2.5"),
    ("kvaliteta_zraka_pm10", "PM10"),
    ("temperatura", "Temperatura"),
    ("vlaga", "Vlaga"),
    ("tlak", "Tlak"),
)


def reading_name(entity_id: str, fallback: str) -> str:
    for suffix, label in MEASUREMENT_LABEL:
        if entity_id.endswith(suffix):
            return label
    return fallback


def room_name(name: str, area_label: str) -> str:
    """Drop the room from the label -- the heading already says it."""
    trimmed = name
    for word in area_label.split():
        lowered = word.lower()
        if len(lowered) > 3 and lowered in trimmed.lower():
            start = trimmed.lower().index(lowered)
            trimmed = (trimmed[:start] + trimmed[start + len(lowered):]).strip(" -–")
    trimmed = " ".join(trimmed.split())
    return (trimmed[:1].upper() + trimmed[1:]) if trimmed else name


def tile(entity_id: str, name: str, toggle: bool) -> dict:
    card = {
        "type": "tile",
        "entity": entity_id,
        "name": name,
        "vertical": True,
        "grid_options": {"columns": TILE_COLUMNS},
        "tap_action": {"action": "toggle"} if toggle else {"action": "more-info"},
    }
    if toggle:
        card["icon_tap_action"] = {"action": "toggle"}
    return card


def glance(entities: list[tuple[str, str]], title: str | None = None) -> dict:
    card = {
        "type": "glance",
        "columns": 3,
        "show_name": True,
        "show_state": True,
        "state_color": True,
        "entities": [{"entity": e, "name": n} for e, n in entities],
    }
    if title:
        card["title"] = title
    return card


# --- Overview ------------------------------------------------------------------

SUN_LINE = (
    "### ☀️ {{ as_timestamp(states('sensor.sun_next_rising')) | timestamp_custom('%H:%M') }}"
    " &nbsp;&nbsp; 🌙 {{ as_timestamp(states('sensor.sun_next_setting')) "
    "| timestamp_custom('%H:%M') }}\n"
    "{% if is_state('sun.sun','above_horizon') %}"
    "{% set s = as_timestamp(states('sensor.sun_next_setting')) - now().timestamp() %}"
    "Dan traje još {{ (s // 3600) | int }} h {{ ((s % 3600) // 60) | int }} min."
    "{% else %}"
    "{% set s = as_timestamp(states('sensor.sun_next_rising')) - now().timestamp() %}"
    "Sunce izlazi za {{ (s // 3600) | int }} h {{ ((s % 3600) // 60) | int }} min."
    "{% endif %}"
)


def overview_view(lights: list[dict], all_light_ids: list[str]) -> dict:
    return {
        "type": "sections",
        "max_columns": 2,
        "title": "Pregled",
        "path": "pregled",
        "icon": "mdi:view-dashboard",
        "sections": [
            {
                "type": "grid",
                "cards": [
                    {
                        "type": "clock", "clock_style": "digital", "clock_size": "large",
                        "show_seconds": False, "no_background": True,
                        "time_zone": "Europe/Zagreb",
                        "grid_options": {"columns": 12, "rows": 2},
                    },
                    {"type": "markdown", "content": SUN_LINE},
                    {
                        "type": "weather-forecast", "entity": "weather.forecast_dom",
                        "forecast_type": "daily", "show_current": True,
                        "show_forecast": True,
                    },
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Svjetla", "heading_style": "title",
                     "icon": "mdi:lightbulb-group"},
                    *lights,
                    {
                        "type": "button", "name": "Ugasi sva svjetla",
                        "icon": "mdi:lightbulb-off-outline", "show_state": False,
                        "grid_options": {"columns": 12},
                        "tap_action": {
                            "action": "perform-action",
                            "perform_action": "homeassistant.turn_off",
                            "target": {"entity_id": all_light_ids},
                        },
                    },
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Temperature", "heading_style": "title",
                     "icon": "mdi:thermometer"},
                    glance(TEMPERATURES),
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Kuća", "heading_style": "title",
                     "icon": "mdi:home-heart"},
                    {"type": "gauge", "entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm2_5",
                     "name": "PM2.5", "min": 0, "max": 250, "needle": True,
                     "grid_options": {"columns": 6},
                     "severity": {"green": 0, "yellow": 35, "red": 100}},
                    {"type": "tile", "entity": "media_player.tv", "name": "TV",
                     "vertical": True, "grid_options": {"columns": 6}},
                    {"type": "tile", "entity": "person.tomislav", "name": "Tomislav",
                     "vertical": True, "grid_options": {"columns": 6}},
                    {"type": "tile", "entity": "todo.shopping_list", "name": "Kupovina",
                     "vertical": True, "grid_options": {"columns": 6}},
                    {"type": "button", "name": "Pitaj Jarvisa", "icon": "mdi:microphone",
                     "show_state": False, "grid_options": {"columns": 12},
                     "tap_action": {"action": "assist", "pipeline_id": PIPELINE,
                                    "start_listening": True}},
                ],
            },
        ],
    }


# --- Rooms ----------------------------------------------------------------------

def rooms_view(by_area: dict, area_names: dict) -> dict:
    sections = []
    for area_id, icon in ROOM_ORDER:
        entities = by_area.get(area_id) or []
        if not entities:
            continue
        label = area_names.get(area_id, area_id)
        controls, readings = [], []
        for item in entities:
            domain = item["entity_id"].split(".", 1)[0]
            name = room_name(item["name"], label)
            if domain in CONTROL_DOMAINS:
                controls.append((domain, item["entity_id"], name))
            elif domain == "sensor":
                readings.append((item["entity_id"], reading_name(item["entity_id"], name)))

        cards = [{"type": "heading", "heading": label, "heading_style": "title", "icon": icon}]
        for domain, entity_id, name in sorted(controls, key=lambda c: (c[0], c[2].lower())):
            cards.append(tile(entity_id, name, toggle=domain in ("light", "switch")))
        if readings:
            cards.append(glance(sorted(readings, key=lambda r: r[1].lower())))
        sections.append({"type": "grid", "cards": cards})

    return {
        "type": "sections",
        "max_columns": 2,
        "title": "Sobe",
        "path": "sobe",
        "icon": "mdi:floor-plan",
        "sections": sections,
    }


# --- Climate ---------------------------------------------------------------------

def climate_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 2,
        "title": "Klima",
        "path": "klima",
        "icon": "mdi:thermometer",
        "sections": [
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Temperatura", "heading_style": "title",
                     "icon": "mdi:thermometer"},
                    glance(TEMPERATURES),
                    {"type": "history-graph", "hours_to_show": 24,
                     "entities": [{"entity": e, "name": n} for e, n in TEMPERATURES]},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Danas", "heading_style": "title",
                     "icon": "mdi:calendar-today"},
                    {"type": "statistic", "entity": "sensor.bme280_mux_node_vanjska_temperatura",
                     "name": "Vani najviša", "stat_type": "max",
                     "grid_options": {"columns": 6},
                     "period": {"calendar": {"period": "day"}}},
                    {"type": "statistic", "entity": "sensor.bme280_mux_node_vanjska_temperatura",
                     "name": "Vani najniža", "stat_type": "min",
                     "grid_options": {"columns": 6},
                     "period": {"calendar": {"period": "day"}}},
                    {"type": "statistic",
                     "entity": "sensor.bme280_mux_node_dnevni_prostor_temperatura",
                     "name": "Boravak najviša", "stat_type": "max",
                     "grid_options": {"columns": 6},
                     "period": {"calendar": {"period": "day"}}},
                    {"type": "statistic",
                     "entity": "sensor.bme280_mux_node_dnevni_prostor_temperatura",
                     "name": "Boravak najniža", "stat_type": "min",
                     "grid_options": {"columns": 6},
                     "period": {"calendar": {"period": "day"}}},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Vlaga", "heading_style": "title",
                     "icon": "mdi:water-percent"},
                    glance(HUMIDITIES),
                    {"type": "history-graph", "hours_to_show": 24,
                     "entities": [{"entity": e, "name": n} for e, n in HUMIDITIES]},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Tlak", "heading_style": "title",
                     "icon": "mdi:gauge"},
                    glance([
                        ("sensor.bme280_mux_node_vanjski_tlak", "Vani"),
                        ("sensor.bme280_mux_node_dnevni_prostor_tlak", "Boravak"),
                        ("sensor.bme280_mux_node_soba_tlak", "Soba"),
                    ]),
                    {"type": "history-graph", "hours_to_show": 48,
                     "entities": [{"entity": "sensor.bme280_mux_node_vanjski_tlak",
                                   "name": "Vani"}]},
                ],
            },
        ],
    }


# --- Air ---------------------------------------------------------------------------

def air_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 2,
        "title": "Zrak",
        "path": "zrak",
        "icon": "mdi:air-filter",
        "sections": [
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Kvaliteta zraka", "heading_style": "title",
                     "icon": "mdi:air-filter"},
                    {"type": "gauge", "entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm2_5",
                     "name": "PM2.5", "min": 0, "max": 250, "needle": True,
                     "severity": {"green": 0, "yellow": 35, "red": 100}},
                    glance([
                        ("sensor.bme280_mux_node_kvaliteta_zraka_pm1", "PM1"),
                        ("sensor.bme280_mux_node_kvaliteta_zraka_pm4", "PM4"),
                        ("sensor.bme280_mux_node_kvaliteta_zraka_pm10", "PM10"),
                    ]),
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Kroz dan", "heading_style": "title",
                     "icon": "mdi:chart-line"},
                    {"type": "history-graph", "hours_to_show": 24, "entities": [
                        {"entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm2_5", "name": "PM2.5"},
                        {"entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm10", "name": "PM10"},
                    ]},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Senzor", "heading_style": "title",
                     "icon": "mdi:tune"},
                    {"type": "tile", "entity": "button.bme280_mux_node_sps30_pokreni_ciscenje",
                     "name": "Očisti SPS30", "vertical": True,
                     "grid_options": {"columns": 6}},
                    {"type": "tile", "entity": "sensor.bme280_mux_node_prosjecna_velicina_cestica",
                     "name": "Veličina čestica", "vertical": True,
                     "grid_options": {"columns": 6}},
                ],
            },
        ],
    }


# --- System -------------------------------------------------------------------------

def _status(entity: str) -> str:
    return (
        "{% if states('" + entity + "') in ['unavailable', 'unknown', 'none'] %}"
        "### 🔴 OFFLINE\n{% else %}### 🟢 Online\n{% endif %}"
    )


def _uptime_from_boot(entity: str) -> str:
    return (
        "{% set b = states('" + entity + "') %}"
        "{% if b not in ['unavailable','unknown','none'] %}"
        "{% set s = (now().timestamp() - as_timestamp(b)) | int %}"
        "{{ s // 86400 }} d {{ (s % 86400) // 3600 }} h{% else %}—{% endif %}"
    )


def _uptime_from_seconds(entity: str) -> str:
    return (
        "{% set v = states('" + entity + "') %}"
        "{% if v not in ['unavailable','unknown','none'] %}"
        "{% set s = v | float(0) | int %}"
        "{{ s // 86400 }} d {{ (s % 86400) // 3600 }} h{% else %}—{% endif %}"
    )


HOME_ASSISTANT_CARD = (
    "## 🖥 Home Assistant\n" + _status("sensor.system_monitor_processor_use") + "\n"
    "| | |\n|---|--:|\n"
    "| Procesor | {{ states('sensor.system_monitor_processor_use') }} % |\n"
    "| Memorija | {{ states('sensor.system_monitor_memory_usage') }} % |\n"
    "| Temperatura | {{ states('sensor.system_monitor_processor_temperature') }} °C |\n"
    "| Disk | {{ states('sensor.system_monitor_disk_usage') }} % "
    "({{ states('sensor.system_monitor_disk_free_config') }} GiB) |\n"
    "| Radi | " + _uptime_from_boot("sensor.system_monitor_last_boot") + " |\n"
    "| IP | {{ states('sensor.system_monitor_ipv4_address_end0') }} |\n"
    "| Verzija | {{ state_attr('update.home_assistant_core_update','installed_version') }}"
    "{% if is_state('update.home_assistant_core_update','on') %} → "
    "{{ state_attr('update.home_assistant_core_update','latest_version') }}{% endif %} |\n"
    "| Napajanje | {% if is_state('binary_sensor.rpi_power_status','on') %}"
    "⚠️ podnapon{% else %}u redu{% endif %} |\n"
)

JARVIS_CARD = (
    "## 🤖 Jarvis\n" + _status("sensor.jarvis_pi_cpu") + "\n"
    "| | |\n|---|--:|\n"
    "| Procesor | {{ states('sensor.jarvis_pi_cpu') }} % |\n"
    "| Memorija | {{ states('sensor.jarvis_pi_memory') }} % |\n"
    "| Temperatura | {{ states('sensor.jarvis_pi_temperature') }} °C |\n"
    "| Disk | {{ states('sensor.jarvis_pi_disk') }} % "
    "({{ states('sensor.jarvis_pi_disk_free_gb') }} GB) |\n"
    "| Radi | " + _uptime_from_boot("sensor.jarvis_pi_boot") + " |\n"
    "| IP | {{ states('sensor.jarvis_pi_ip') }} |\n"
    "| Glas | {% if states('stt.jarvis_stt') not in ['unavailable','unknown'] %}"
    "sluša i govori{% else %}⚠️ nedostupan{% endif %} |\n"
)

ESP32_CARD = (
    "## 🔌 ESP32 I/O\n" + _status("switch.esp32_io_svjetlo_kuhinja") + "\n"
    "| | |\n|---|--:|\n"
    "| Firmware | {{ state_attr('update.esp32_io_firmware','installed_version') or '—' }} |\n"
    "| Svjetla | {{ states.switch | selectattr('entity_id','search','esp32_io_svjetlo') "
    "| selectattr('state','eq','on') | list | count }} upaljenih |\n"
    "| Utičnice | {{ states.switch | selectattr('entity_id','search','esp32_io_uticnica') "
    "| selectattr('state','eq','on') | list | count }} uključenih |\n"
)

BME_CARD = (
    "## 🌡 BME280 Mux Node\n" + _status("sensor.bme280_mux_node_bme280_mux_uptime") + "\n"
    "| | |\n|---|--:|\n"
    "| Wi-Fi | {{ states('sensor.bme280_mux_node_bme280_mux_wifi_signal') "
    "| float(0) | round(0) }} dBm |\n"
    "| Radi | " + _uptime_from_seconds("sensor.bme280_mux_node_bme280_mux_uptime") + " |\n"
    "| Senzori | {{ states.sensor "
    "| selectattr('entity_id','search','bme280_mux_node_.*temperatura') "
    "| rejectattr('state','in',['unavailable','unknown']) | list | count }} / 5 |\n"
    "| PM2.5 | {{ states('sensor.bme280_mux_node_kvaliteta_zraka_pm2_5') "
    "| float(0) | round(1) }} µg/m³ |\n"
    "| Napon | {% set v = states('sensor.bme280_mux_node_mrezni_napon') %}"
    "{% if v in ['unavailable','unknown','none'] %}— (mjerenje ne radi)"
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
                    {"type": "heading", "heading": "Nadogradnje", "heading_style": "title",
                     "icon": "mdi:package-up"},
                    {"type": "entities", "entities": [
                        {"entity": "update.home_assistant_core_update", "name": "Home Assistant"},
                        {"entity": "update.home_assistant_operating_system_update", "name": "OS"},
                        {"entity": "update.home_assistant_supervisor_update", "name": "Supervisor"},
                        {"entity": "update.esphome_device_builder_update", "name": "ESPHome"},
                        {"entity": "update.mosquitto_broker_update", "name": "Mosquitto"},
                        {"entity": "update.tailscale_update", "name": "Tailscale"},
                    ]},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Dodaci", "heading_style": "title",
                     "icon": "mdi:puzzle"},
                    {"type": "entities", "entities": [
                        {"entity": "binary_sensor.mosquitto_broker_running", "name": "Mosquitto"},
                        {"entity": "binary_sensor.tailscale_running", "name": "Tailscale"},
                        {"entity": "binary_sensor.esphome_device_builder_running", "name": "ESPHome"},
                        {"entity": "binary_sensor.studio_code_server_running", "name": "Studio Code"},
                        {"entity": "binary_sensor.samba_share_running", "name": "Samba"},
                        {"entity": "binary_sensor.advanced_ssh_web_terminal_running", "name": "SSH"},
                    ]},
                ],
            },
        ],
    }


# --- Lights and sockets --------------------------------------------------------------

def switch_view(title: str, path: str, icon: str, entries: list[tuple[str, str]],
                turn_off_all: list[str] | None = None) -> dict:
    cards = [{"type": "heading", "heading": title, "heading_style": "title", "icon": icon}]
    cards += [tile(entity_id, name, toggle=True) for entity_id, name in entries]
    if turn_off_all:
        cards.append({
            "type": "button", "name": "Ugasi sve", "icon": "mdi:power-off",
            "show_state": False, "grid_options": {"columns": 12},
            "tap_action": {"action": "perform-action",
                           "perform_action": "homeassistant.turn_off",
                           "target": {"entity_id": turn_off_all}},
        })
    return {
        "type": "sections", "max_columns": 2, "title": title, "path": path, "icon": icon,
        "sections": [{"type": "grid", "cards": cards}],
    }


# --- Conversation ----------------------------------------------------------------------

RAZGOVOR = (
    "{% set turns = state_attr('sensor.jarvis_razgovor', 'povijest') %}"
    "{% if turns %}{% for t in turns %}"
    "**{{ as_timestamp(t['vrijeme']) | timestamp_custom('%d.%m. %H:%M') }} · ti**\n"
    "{{ t['pitanje'] }}\n\n**Jarvis**\n{{ t['odgovor'] }}\n\n---\n"
    "{% endfor %}{% else %}_Još nema zapisanog razgovora._{% endif %}"
)


def conversation_view() -> dict:
    return {
        "type": "sections", "max_columns": 1, "title": "Razgovor", "path": "razgovor",
        "icon": "mdi:message-text-clock",
        "sections": [{
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": "Razgovor s Jarvisom",
                 "heading_style": "title", "icon": "mdi:robot"},
                {"type": "button", "name": "Pitaj Jarvisa", "icon": "mdi:microphone",
                 "show_state": False, "grid_options": {"columns": 12},
                 "tap_action": {"action": "assist", "pipeline_id": PIPELINE,
                                "start_listening": True}},
                {"type": "markdown", "content": RAZGOVOR},
            ],
        }],
    }


# --- wiring ------------------------------------------------------------------------------

async def call(ws, ident, payload):
    await ws.send(json.dumps({"id": ident, **payload}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == ident and msg.get("type") == "result":
            if not msg.get("success"):
                sys.exit("GRESKA: " + json.dumps(msg.get("error"), ensure_ascii=False))
            return msg.get("result")


def wanted_in_room(entity_id: str) -> bool:
    return not any(word in entity_id for word in ROOM_EXCLUDE)


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
            entity_id = entry["entity_id"]
            if not area_id or entry.get("disabled_by") or entry.get("hidden_by"):
                continue
            if entity_id not in states or not wanted_in_room(entity_id):
                continue
            by_area[area_id].append({
                "entity_id": entity_id,
                "name": short_name(states[entity_id]["attributes"].get("friendly_name", ""),
                                   entity_id),
            })

        def label(entity_id: str) -> str:
            name = short_name(states[entity_id]["attributes"].get("friendly_name", ""), entity_id)
            return name.replace("Svjetlo ", "").replace("Utičnica ", "")

        # Everything switchable that is not disabled or hidden. Split by what it
        # IS, not by what it is called: listing sockets by the word "utičnica"
        # silently lost the oven, which is a switch by any other name.
        switchable = [
            entry["entity_id"]
            for entry in entities
            if entry["entity_id"].split(".")[0] in ("switch", "light")
            and not entry.get("disabled_by")
            and not entry.get("hidden_by")
            and entry["entity_id"] in states
        ]
        lights = sorted(
            ((e, label(e)) for e in switchable if "svjetlo" in e),
            key=lambda item: item[1].lower(),
        )
        sockets = sorted(
            ((e, label(e)) for e in switchable if "svjetlo" not in e),
            key=lambda item: item[1].lower(),
        )
        light_ids = [entity_id for entity_id, _ in lights]

        print(f"  svjetala: {len(lights)}, utičnica: {len(sockets)}")
        for area_id, _ in ROOM_ORDER:
            print(f"    {area_names.get(area_id, area_id):16} {len(by_area.get(area_id) or [])}")

        cfg = await call(ws, 4, {"type": "lovelace/config", "url_path": BOARD})
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f"  kopija prije izmjene: {BACKUP}")

        # The TV view is hand-written and kept as it is, but it still has to fit
        # the panel like everything else.
        tv_view = next(v for v in cfg["views"] if v.get("path") == "tv")
        tv_view["max_columns"] = 2

        cfg["views"] = [
            overview_view([tile(e, n, True) for e, n in lights], light_ids),
            rooms_view(by_area, area_names),
            climate_view(),
            air_view(),
            switch_view("Svjetla", "svjetla", "mdi:lightbulb-group", lights, light_ids),
            switch_view("Utičnice", "uticnice", "mdi:power-socket-eu", sockets),
            tv_view,
            system_view(),
            conversation_view(),
        ]

        await call(ws, 5, {"type": "lovelace/config/save", "url_path": BOARD, "config": cfg})
        after = await call(ws, 6, {"type": "lovelace/config", "url_path": BOARD})
        print("  prikazi:", [v.get("title") for v in after["views"]])


if __name__ == "__main__":  # importable, so the pure helpers can be tested
    asyncio.run(main())
