"""Tests for the generated parts of the Home Assistant dashboard.

The view itself is built against a live Home Assistant, but the naming and
ordering decisions are pure and are what make a room readable rather than a
dump of entity ids.
"""

import importlib.util
import sys
import types
from pathlib import Path

_TOOL = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "home_assistant"
    / "tools"
    / "build_dashboard.py"
)

# The script talks to Home Assistant over a websocket and reads its address from
# the environment at import time; neither is needed to test the pure helpers.
sys.modules.setdefault("websockets", types.ModuleType("websockets"))
import os  # noqa: E402

os.environ.setdefault("HA_URL", "http://example.invalid:8123")
os.environ.setdefault("HA_TOKEN", "token")

_spec = importlib.util.spec_from_file_location("build_dashboard", _TOOL)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def test_the_device_prefix_is_dropped_from_a_room_label():
    """"ESP32 IO Svjetlo kuhinja" in the Kitchen card only needs "Svjetlo kuhinja"."""
    assert builder.short_name("ESP32 IO Svjetlo kuhinja", "switch.x") == "Svjetlo kuhinja"
    assert (
        builder.short_name("BME280 Mux Node Soba temperatura", "sensor.x")
        == "Soba temperatura"
    )


def test_a_name_without_a_known_prefix_is_left_alone():
    assert builder.short_name("Pećnica", "switch.x") == "Pećnica"


def test_a_missing_friendly_name_falls_back_to_the_entity_id():
    assert builder.short_name("", "switch.esp32_io_pecnica") == "Esp32 io pecnica"


def _rooms(entities):
    return builder.rooms_view(entities, {"living_room": "Dnevni boravak"})


def test_controls_come_before_readings():
    """Scrolling past thirty sensors to reach a light switch is the old problem."""
    view = _rooms(
        {
            "living_room": [
                {"entity_id": "sensor.temperatura", "name": "Temperatura"},
                {"entity_id": "switch.svjetlo", "name": "Svjetlo"},
                {"entity_id": "light.fotelja", "name": "Fotelja"},
            ]
        }
    )
    cards = view["sections"][0]["cards"]

    assert cards[0]["type"] == "heading"
    assert [c["entity"] for c in cards[1:]] == [
        "light.fotelja",
        "switch.svjetlo",
        "sensor.temperatura",
    ]


def test_switches_toggle_and_sensors_open_details():
    view = _rooms(
        {
            "living_room": [
                {"entity_id": "switch.svjetlo", "name": "Svjetlo"},
                {"entity_id": "sensor.temperatura", "name": "Temperatura"},
            ]
        }
    )
    cards = {c.get("entity"): c for c in view["sections"][0]["cards"] if "entity" in c}

    assert cards["switch.svjetlo"]["tap_action"] == {"action": "toggle"}
    assert cards["sensor.temperatura"]["tap_action"] == {"action": "more-info"}


def test_entities_of_one_kind_are_sorted_by_name():
    view = _rooms(
        {
            "living_room": [
                {"entity_id": "switch.b", "name": "Zidno"},
                {"entity_id": "switch.a", "name": "Ambijentalno"},
            ]
        }
    )
    cards = [c for c in view["sections"][0]["cards"] if "entity" in c]

    assert [c["name"] for c in cards] == ["Ambijentalno", "Zidno"]


def test_an_empty_room_gets_no_section():
    """An empty heading reads as a fault in the room, not an empty room."""
    view = builder.rooms_view({"living_room": []}, {"living_room": "Dnevni boravak"})

    assert view["sections"] == []


def test_rooms_keep_the_configured_order():
    entities = {
        area_id: [{"entity_id": f"switch.{area_id}", "name": "X"}]
        for area_id, _ in builder.ROOM_ORDER
    }
    names = {area_id: area_id for area_id, _ in builder.ROOM_ORDER}

    view = builder.rooms_view(entities, names)
    headings = [s["cards"][0]["heading"] for s in view["sections"]]

    assert headings == [area_id for area_id, _ in builder.ROOM_ORDER]


def test_every_machine_on_the_system_view_reports_availability():
    """A card that cannot say OFFLINE is what let a dead node look healthy."""
    view = builder.system_view()
    markdown = [
        card["content"]
        for section in view["sections"]
        for card in section["cards"]
        if card.get("type") == "markdown"
    ]

    assert len(markdown) == 4
    assert all("🔴 OFFLINE" in content for content in markdown)
    assert all("🟢 Online" in content for content in markdown)
