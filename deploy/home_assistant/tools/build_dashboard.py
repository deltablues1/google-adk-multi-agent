"""Rebuild the Jarvis dashboard, laid out for the 7" wall panel.

Two things drive every choice here.

First, the panel is 1024x600 -- measured with grim on the panel itself, after
this file spent a long time assuming 800x480 and laying out for a screen that
was never there. Views are three columns wide, tiles are square and
finger-sized rather than full width rows, and prose is kept off the screen -- a
paragraph of explanation is unreadable at arm's length and steals room from the
controls. Height is the scarce axis: about 544px survives the header, roughly
eight grid rows, and a column taller than that has to be scrolled with a
fingertip. Hence three columns rather than two, and hence the lights living on
their own view instead of stacking sixteen tiles onto the overview.

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

PRESSURES = [
    ("sensor.bme280_mux_node_vanjski_tlak", "Vani"),
    ("sensor.bme280_mux_node_dnevni_prostor_tlak", "Boravak"),
    ("sensor.bme280_mux_node_soba_tlak", "Soba"),
    ("sensor.bme280_mux_node_kupaona_tlak", "Kupaona"),
    ("sensor.bme280_mux_node_ulaz_tlak", "Ulaz"),
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


def tile(entity_id: str, name: str, toggle: bool, columns: int = TILE_COLUMNS) -> dict:
    card = {
        "type": "tile",
        "entity": entity_id,
        "name": name,
        "vertical": True,
        "grid_options": {"columns": columns},
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
    "{% endif %}\n\n"
    # The phase name comes from Home Assistant's own moon integration, which is
    # the same answer the sky module computes independently -- worth keeping in
    # step, so a disagreement is visible rather than hidden.
    "{% set faze = {"
    "'new_moon': ['🌑','mlađak'],"
    "'waxing_crescent': ['🌒','mladi srp'],"
    "'first_quarter': ['🌓','prva četvrt'],"
    "'waxing_gibbous': ['🌔','pred uštapom'],"
    "'full_moon': ['🌕','uštap'],"
    "'waning_gibbous': ['🌖','nakon uštapa'],"
    "'last_quarter': ['🌗','zadnja četvrt'],"
    "'waning_crescent': ['🌘','stari srp']} %}"
    "{% set f = faze.get(states('sensor.moon_phase'), ['🌙','—']) %}"
    "{{ f[0] }} {{ f[1] }}"
    "{% set c = state_attr('weather.forecast_dom','cloud_coverage') %}"
    "{% if c is not none %} &nbsp;·&nbsp; naoblaka {{ c | round(0) }} %{% endif %}"
    "{% set w = state_attr('weather.forecast_dom','wind_speed') %}"
    "{% if w is not none %} &nbsp;·&nbsp; vjetar {{ w | round(0) }} km/h{% endif %}"
    "{% set uv = state_attr('weather.forecast_dom','uv_index') %}"
    "{% if uv is not none and uv > 0 %} &nbsp;·&nbsp; UV {{ uv | round(0) }}{% endif %}"
)


def overview_view(all_light_ids: list[str]) -> dict:
    return {
        "type": "sections",
        "max_columns": 3,
        "title": "Pregled",
        "path": "pregled",
        "icon": "mdi:view-dashboard",
        "sections": [
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Svjetla", "heading_style": "title",
                     "icon": "mdi:lightbulb-group"},
                    {
                        "type": "button", "name": "Upravljanje svjetlima",
                        "icon": "mdi:lightbulb-group", "show_state": False,
                        "grid_options": {"columns": 6},
                        "tap_action": {"action": "navigate",
                                       "navigation_path": f"/{BOARD}/svjetla"},
                    },
                    {
                        "type": "button", "name": "Ugasi sva svjetla",
                        "icon": "mdi:lightbulb-off-outline", "show_state": False,
                        "grid_options": {"columns": 6},
                        "tap_action": {
                            "action": "perform-action",
                            "perform_action": "homeassistant.turn_off",
                            "target": {"entity_id": all_light_ids},
                        },
                    },
                    {"type": "heading", "heading": "Temperature", "heading_style": "title",
                     "icon": "mdi:thermometer"},
                    glance(TEMPERATURES),
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {
                        "type": "clock", "clock_style": "digital", "clock_size": "large",
                        "show_seconds": False, "no_background": True,
                        "time_zone": "Europe/Zagreb",
                        "grid_options": {"columns": 12, "rows": 2},
                    },
                    {"type": "markdown", "content": SUN_LINE,
                     "grid_options": {"columns": 12, "rows": 3}},
                    {
                        "type": "weather-forecast", "entity": "weather.forecast_dom",
                        "forecast_type": "daily", "show_current": True,
                        "show_forecast": True,
                        "grid_options": {"columns": 12, "rows": 4},
                    },
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Kuća", "heading_style": "title",
                     "icon": "mdi:home-heart"},
                    {"type": "gauge", "entity": "sensor.bme280_mux_node_kvaliteta_zraka_pm2_5",
                     "name": "PM2.5", "min": 0, "max": 250, "needle": True,
                     "grid_options": {"columns": 12, "rows": 2},
                     "severity": {"green": 0, "yellow": 35, "red": 100}},
                    {"type": "tile", "entity": "media_player.tv", "name": "TV",
                     "vertical": True, "grid_options": {"columns": 4}},
                    {"type": "tile", "entity": "person.tomislav", "name": "Tomislav",
                     "vertical": True, "grid_options": {"columns": 4}},
                    {"type": "tile", "entity": "todo.shopping_list", "name": "Kupovina",
                     "vertical": True, "grid_options": {"columns": 4}},
                    {"type": "button", "name": "Pitaj Jarvisa", "icon": "mdi:microphone",
                     "show_state": False, "grid_options": {"columns": 12},
                     "tap_action": {"action": "assist", "pipeline_id": PIPELINE,
                                    "start_listening": True}},
                    {"type": "tile", "entity": "switch.jarvis_slusanje",
                     "name": "Mikrofon na Pi-ju", "icon": "mdi:microphone",
                     "grid_options": {"columns": 12}},
                ],
            },
        ],
    }


def lights_view(light_tiles: list[dict]) -> dict:
    """Every light, two across, split into thirds.

    One long section would stack in a single column and scroll; three sections
    let the view use all three columns, which is what keeps it on one screen.
    """
    per = -(-len(light_tiles) // 3) or 1
    chunks = [light_tiles[i:i + per] for i in range(0, len(light_tiles), per)]
    return {
        "type": "sections",
        "max_columns": 3,
        "title": "Svjetla",
        "path": "svjetla",
        "icon": "mdi:lightbulb-group",
        "sections": [
            {
                "type": "grid",
                "cards": ([{"type": "heading", "heading": "Svjetla",
                            "heading_style": "title", "icon": "mdi:lightbulb-group"}]
                          if i == 0 else []) + chunk,
            }
            for i, chunk in enumerate(chunks)
        ],
    }


# --- Rooms ----------------------------------------------------------------------

def estimated_rows(cards: list[dict]) -> int:
    """Height of a card list in grid rows, packing the 12-column grid as HA does.

    Approximate by design: it only has to be good enough to balance columns.
    """
    default_rows = {"heading": 1, "tile": 1, "button": 2, "glance": 3, "gauge": 3,
                    "markdown": 3, "clock": 2, "weather-forecast": 5,
                    "history-graph": 5, "statistic": 2, "media-control": 4}
    full_width = {"heading", "glance", "history-graph", "markdown",
                  "weather-forecast", "media-control"}
    total = used = tallest = 0
    for card in cards:
        options = card.get("grid_options") or {}
        columns = options.get("columns") or (12 if card.get("type") in full_width else 4)
        rows = options.get("rows") or default_rows.get(card.get("type"), 2)
        if used + columns > 12:
            total += tallest
            used = tallest = 0
        used += columns
        tallest = max(tallest, rows)
    return total + tallest


def pack_into_columns(groups: list[list[dict]], columns: int) -> list[dict]:
    """Merge card groups into `columns` sections of roughly equal height.

    Sections lay out in rows and a row is as tall as its tallest section, so
    fewer, balanced sections beat many uneven ones: one section row means the
    view is exactly as tall as its fullest column and nothing lands below the
    fold. Groups keep their given order within a column, which matters because
    the first card of each is its room heading.
    """
    if len(groups) <= columns:
        return [{"type": "grid", "cards": cards} for cards in groups]

    # Contiguous split, not the cheapest bin packing. Balancing by height alone
    # would scatter the rooms and leave the panel reading kitchen, hallway,
    # bedroom in whatever order the arithmetic liked; ROOM_ORDER exists because
    # somebody decided how this house should be read. So: keep the order, and
    # pick the two cut points that give the shortest tallest column.
    sizes = [estimated_rows(cards) for cards in groups]
    best, best_cuts = None, None
    for cuts in _cut_points(len(groups), columns):
        bounds = (0, *cuts, len(groups))
        tallest = max(sum(sizes[a:b]) for a, b in zip(bounds, bounds[1:]))
        if best is None or tallest < best:
            best, best_cuts = tallest, bounds
    return [
        {"type": "grid", "cards": [card for cards in groups[a:b] for card in cards]}
        for a, b in zip(best_cuts, best_cuts[1:])
        if b > a
    ]


def _cut_points(count: int, columns: int):
    """Every way to cut `count` ordered groups into `columns` runs."""
    if columns <= 1:
        yield ()
        return
    for first in range(1, count - columns + 2):
        for rest in _cut_points(count - first, columns - 1):
            yield (first, *(first + r for r in rest))


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
            sorted_readings = sorted(readings, key=lambda r: r[1].lower())
            reading_card = glance(sorted_readings)
            # glance wraps at three per row, and pinning every room to two rows
            # clipped the fourth reading in the rooms that have one.
            reading_card["grid_options"] = {
                "columns": 12, "rows": 2 if len(sorted_readings) <= 3 else 3,
            }
            cards.append(reading_card)
        sections.append(cards)

    return {
        "type": "sections",
        "max_columns": 3,
        "title": "Sobe",
        "path": "sobe",
        "icon": "mdi:floor-plan",
        "sections": pack_into_columns(sections, 3),
    }


# --- Climate ---------------------------------------------------------------------

def climate_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 3,
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
                     "grid_options": {"rows": 3},
                     "entities": [{"entity": e, "name": n} for e, n in TEMPERATURES]},
                    *[{"type": "statistic", "entity": ent, "name": label,
                       "stat_type": stat, "grid_options": {"columns": 6, "rows": 1},
                       "period": {"calendar": {"period": "day"}}}
                      for ent, label, stat in (
                          ("sensor.bme280_mux_node_vanjska_temperatura", "Vani max", "max"),
                          ("sensor.bme280_mux_node_vanjska_temperatura", "Vani min", "min"),
                          ("sensor.bme280_mux_node_dnevni_prostor_temperatura", "Boravak max", "max"),
                          ("sensor.bme280_mux_node_dnevni_prostor_temperatura", "Boravak min", "min"),
                      )],
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Vlaga", "heading_style": "title",
                     "icon": "mdi:water-percent"},
                    glance(HUMIDITIES),
                    {"type": "history-graph", "hours_to_show": 24,
                     "grid_options": {"rows": 3},
                     "entities": [{"entity": e, "name": n} for e, n in HUMIDITIES]},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Tlak", "heading_style": "title",
                     "icon": "mdi:gauge"},
                    glance(PRESSURES),
                    {"type": "history-graph", "hours_to_show": 48,
                     "grid_options": {"rows": 3},
                     "entities": [{"entity": e, "name": n} for e, n in PRESSURES]},
                ],
            },
        ],
    }


# --- Air ---------------------------------------------------------------------------

def air_view() -> dict:
    return {
        "type": "sections",
        "max_columns": 3,
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
        "max_columns": 3,
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

def devices_view(lights: list[tuple[str, str]], sockets: list[tuple[str, str]],
                 light_ids: list[str]) -> dict:
    """Lights and appliances on one view -- two tabs to reach them was one too many."""
    light_cards = [
        {"type": "heading", "heading": "Svjetla", "heading_style": "title",
         "icon": "mdi:lightbulb-group"},
        *[tile(entity_id, name, toggle=True) for entity_id, name in lights],
        {"type": "button", "name": "Ugasi sva svjetla", "icon": "mdi:lightbulb-off-outline",
         "show_state": False, "grid_options": {"columns": 12},
         "tap_action": {"action": "perform-action",
                        "perform_action": "homeassistant.turn_off",
                        "target": {"entity_id": light_ids}}},
    ]
    socket_cards = [
        {"type": "heading", "heading": "Trošila", "heading_style": "title",
         "icon": "mdi:power-socket-eu"},
        *[tile(entity_id, name, toggle=True) for entity_id, name in sockets],
    ]
    return {
        "type": "sections", "max_columns": 3, "title": "Uređaji", "path": "uredaji",
        "icon": "mdi:toggle-switch-outline",
        "sections": [
            {"type": "grid", "cards": light_cards},
            {"type": "grid", "cards": socket_cards},
        ],
    }


# --- TV ----------------------------------------------------------------------------------

# What the TV is called on each of the two protocols it speaks. The remote can
# press keys and launch apps; the cast side is the only one that accepts an
# exact volume. Both are used for what each is good at, and neither is
# explained on screen -- a paragraph about protocols is not something anyone
# reads while reaching for the volume.
TV_REMOTE = "remote.tv"
TV_PLAYER = "media_player.tv"
TV_CAST = "media_player.smart_tv_pro"

# How an app is opened matters more than which app it is. A deep link is sent
# as it is; a bare package name does nothing at all on this television, so it
# goes through the small launcher app installed on it -- the same route Jarvis
# uses, and the reason that app exists. Buttons built on raw package names
# would look right and do nothing.
TV_APPS = [
    ("YouTube", "mdi:youtube", "https://www.youtube.com"),
    ("A1 Xplore", "mdi:television-classic", "jarvis://open?pkg=hr.a1.android.tv.xploretv"),
    ("Netflix", "mdi:netflix", "https://www.netflix.com/title"),
]


# The remote entity reports a raw package name; nobody wants to read
# com.google.android.youtube.tv on a wall. Anything unmapped still shows, so a
# newly installed app is visible rather than swallowed.
TV_NOW = (
    "{% set app = state_attr('media_player.tv','app_id') %}"
    "{% set imena = {"
    "'com.google.android.youtube.tv': 'YouTube',"
    "'hr.a1.android.tv.xploretv': 'A1 Xplore TV',"
    "'com.netflix.ninja': 'Netflix',"
    "'com.google.android.apps.tv.launcherx': 'početni zaslon',"
    "'com.google.android.apps.tv.dreamx': 'čuvar zaslona'} %}"
    "{% if is_state('media_player.tv','off') %}Televizor je ugašen."
    "{% else %}Uključen &nbsp;·&nbsp; "
    "{{ imena.get(app, app if app else 'nepoznata aplikacija') }}{% endif %}"
)


def key(name: str, icon: str, command: str, columns: int = 4) -> dict:
    """One remote key. Verified against the TV: send_command moves it."""
    return {
        "type": "button",
        "name": name,
        "icon": icon,
        "show_state": False,
        "grid_options": {"columns": columns},
        "tap_action": {
            "action": "perform-action",
            "perform_action": "remote.send_command",
            "target": {"entity_id": TV_REMOTE},
            "data": {"command": command},
        },
    }


def app_button(name: str, icon: str, package: str) -> dict:
    return {
        "type": "button",
        "name": name,
        "icon": icon,
        "show_state": False,
        "grid_options": {"columns": 4},
        "tap_action": {
            "action": "perform-action",
            "perform_action": "remote.turn_on",
            "target": {"entity_id": TV_REMOTE},
            "data": {"activity": package},
        },
    }


def tv_view() -> dict:
    groups = [
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Sada", "heading_style": "title",
                     "icon": "mdi:television-play"},
                    # The cast side is the one that knows what is playing:
                    # title, artist, artwork, how far in. The remote side knows
                    # only a package name -- measured, with Elvis on screen:
                    # cast said "Elvis Presley - '68 Comeback Special", the
                    # remote said "com.google.android.youtube.tv". It also
                    # takes an absolute volume, so its slider lands where you
                    # put it instead of stepping towards it.
                    {"type": "media-control", "entity": TV_CAST},
                    {"type": "tile", "entity": TV_CAST, "name": "Glasnoća",
                     "features": [{"type": "media-player-volume-slider"}]},
                    # Cast falls silent on broadcast channels, so this line is
                    # what still says the set is on and what it is showing.
                    {"type": "markdown", "content": TV_NOW},
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Daljinski", "heading_style": "title",
                     "icon": "mdi:remote-tv"},
                    key("Natrag", "mdi:arrow-u-left-top", "BACK"),
                    key("Gore", "mdi:chevron-up", "DPAD_UP"),
                    key("Početna", "mdi:home", "HOME"),
                    key("Lijevo", "mdi:chevron-left", "DPAD_LEFT"),
                    key("OK", "mdi:circle-slice-8", "DPAD_CENTER"),
                    key("Desno", "mdi:chevron-right", "DPAD_RIGHT"),
                    key("Izbornik", "mdi:dots-horizontal", "MENU"),
                    key("Dolje", "mdi:chevron-down", "DPAD_DOWN"),
                    key("Pauza", "mdi:play-pause", "MEDIA_PLAY_PAUSE"),
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Glasnoća i kanali",
                     "heading_style": "title", "icon": "mdi:volume-high"},
                    key("Tiše", "mdi:volume-minus", "VOLUME_DOWN"),
                    key("Bez zvuka", "mdi:volume-off", "VOLUME_MUTE"),
                    key("Glasnije", "mdi:volume-plus", "VOLUME_UP"),
                    key("Kanal −", "mdi:chevron-double-down", "CHANNEL_DOWN", columns=6),
                    key("Kanal +", "mdi:chevron-double-up", "CHANNEL_UP", columns=6),
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Aplikacije", "heading_style": "title",
                     "icon": "mdi:apps"},
                    *[app_button(*app) for app in TV_APPS],
                ],
            },
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": "Napajanje", "heading_style": "title",
                     "icon": "mdi:power-plug"},
                    {"type": "tile", "entity": TV_PLAYER, "name": "Televizor",
                     "vertical": True, "grid_options": {"columns": 4},
                     "tap_action": {"action": "toggle"}},
                    {"type": "tile", "entity": "switch.esp32_io_uticnica_tv",
                     "name": "Utičnica", "vertical": True,
                     "grid_options": {"columns": 4}, "tap_action": {"action": "toggle"}},
                    {"type": "tile", "entity": "switch.esp32_io_svjetlo_tv",
                     "name": "Svjetlo", "vertical": True,
                     "grid_options": {"columns": 4}, "tap_action": {"action": "toggle"}},
                ],
            },
    ]
    return {
        "type": "sections",
        "max_columns": 3,
        "title": "TV",
        "path": "tv",
        "icon": "mdi:television",
        # Five sections is two section rows, and the second starts below the
        # tallest of the first three -- the apps and the power tiles ended up
        # off the bottom of the panel. Balanced into three, it is one row.
        "sections": pack_into_columns([g["cards"] for g in groups], 3),
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
                {"type": "tile", "entity": "switch.jarvis_slusanje",
                 "name": "Mikrofon na Pi-ju", "icon": "mdi:microphone",
                 "grid_options": {"columns": 12}},
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


def count_switch_ons(history: dict, entity_ids: list[str]) -> dict[str, int]:
    """How many times each switch was actually turned on, from recorded history.

    Only off -> on counts. A node reboot republishes every entity, and counting
    unavailable -> on made all eleven sockets look equally busy at thirteen
    switches each -- an artefact, not a habit.
    """
    counts = {}
    for entity_id in entity_ids:
        previous = None
        total = 0
        for item in history.get(entity_id) or []:
            state = item.get("s", item.get("state"))
            if state == "on" and previous == "off":
                total += 1
            previous = state
        counts[entity_id] = total
    return counts


async def usage_order(ws, ident: int, entity_ids: list[str], days: int = 14) -> dict[str, int]:
    """Recent switch counts, or an empty map if the recorder cannot answer."""
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    try:
        history = await call(ws, ident, {
            "type": "history/history_during_period",
            "start_time": (end - timedelta(days=days)).isoformat(),
            "end_time": end.isoformat(),
            "entity_ids": entity_ids,
            "minimal_response": True,
            "no_attributes": True,
        })
    except SystemExit:
        print("  (povijest nedostupna — poredak ostaje abecedni)")
        return {}
    return count_switch_ons(history, entity_ids)


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
        # Order by what actually gets touched, so the thumb lands on the bathroom
        # light rather than on whatever starts with B.
        used = await usage_order(ws, 7, switchable)

        def by_use(entity_id: str) -> tuple:
            return (-used.get(entity_id, 0), label(entity_id).lower())

        lights = [(e, label(e)) for e in sorted(
            (e for e in switchable if "svjetlo" in e), key=by_use)]
        sockets = [(e, label(e)) for e in sorted(
            (e for e in switchable if "svjetlo" not in e), key=by_use)]
        if used:
            top = ", ".join(f"{label(e)} ({used.get(e, 0)}×)" for e, _ in lights[:4])
            print(f"  najčešće paljena svjetla u 14 dana: {top}")
        light_ids = [entity_id for entity_id, _ in lights]

        print(f"  svjetala: {len(lights)}, utičnica: {len(sockets)}")
        for area_id, _ in ROOM_ORDER:
            print(f"    {area_names.get(area_id, area_id):16} {len(by_area.get(area_id) or [])}")

        cfg = await call(ws, 8, {"type": "lovelace/config", "url_path": BOARD})
        with open(BACKUP, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f"  kopija prije izmjene: {BACKUP}")

        cfg["views"] = [
            overview_view(light_ids),
            lights_view([tile(e, n, True, columns=6) for e, n in lights]),
            rooms_view(by_area, area_names),
            climate_view(),
            air_view(),
            devices_view(lights, sockets, light_ids),
            tv_view(),
            system_view(),
            conversation_view(),
        ]

        await call(ws, 9, {"type": "lovelace/config/save", "url_path": BOARD, "config": cfg})
        after = await call(ws, 10, {"type": "lovelace/config", "url_path": BOARD})
        print("  prikazi:", [v.get("title") for v in after["views"]])


if __name__ == "__main__":  # importable, so the pure helpers can be tested
    asyncio.run(main())
