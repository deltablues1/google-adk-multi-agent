"""Tests for the generated parts of the Home Assistant dashboard.

The view itself is built against a live Home Assistant, but the naming and
ordering decisions are pure and are what make a room readable rather than a
dump of entity ids.
"""

import importlib.util
import os
from pathlib import Path

import pytest

_TOOL = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "home_assistant"
    / "tools"
    / "build_dashboard.py"
)

pytest.importorskip("websockets", reason="the tool imports websockets at module level")

# The script reads the Home Assistant address at import time. It never connects
# unless run as a program, but the names have to exist.
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


def test_controls_come_first_and_readings_share_one_card():
    """Controls are what a room is touched for; readings are one glance below."""
    view = _rooms(
        {
            "living_room": [
                {"entity_id": "sensor.bme280_mux_node_soba_temperatura", "name": "Temperatura"},
                {"entity_id": "switch.svjetlo", "name": "Svjetlo"},
                {"entity_id": "light.fotelja", "name": "Fotelja"},
            ]
        }
    )
    cards = view["sections"][0]["cards"]

    assert [c["type"] for c in cards] == ["heading", "tile", "tile", "glance"]
    assert [c["entity"] for c in cards[1:3]] == ["light.fotelja", "switch.svjetlo"]
    assert [e["entity"] for e in cards[3]["entities"]] == [
        "sensor.bme280_mux_node_soba_temperatura"
    ]


def test_a_room_without_readings_gets_no_empty_glance():
    view = _rooms({"living_room": [{"entity_id": "switch.svjetlo", "name": "Svjetlo"}]})

    assert [c["type"] for c in view["sections"][0]["cards"]] == ["heading", "tile"]


def test_switches_toggle_on_tap():
    view = _rooms({"living_room": [{"entity_id": "switch.svjetlo", "name": "Svjetlo"}]})
    card = view["sections"][0]["cards"][1]

    assert card["tap_action"] == {"action": "toggle"}
    assert card["icon_tap_action"] == {"action": "toggle"}


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


def test_a_reading_is_labelled_by_what_it_measures():
    """"Dnevni prostor temperatura" under a heading that says the room is noise."""
    assert (
        builder.reading_name("sensor.bme280_mux_node_dnevni_prostor_temperatura", "x")
        == "Temperatura"
    )
    assert builder.reading_name("sensor.bme280_mux_node_soba_vlaga", "x") == "Vlaga"
    assert (
        builder.reading_name("sensor.bme280_mux_node_kvaliteta_zraka_pm2_5", "x") == "PM2.5"
    )


def test_an_unrecognised_reading_keeps_its_own_name():
    assert builder.reading_name("sensor.nesto_novo", "Nešto novo") == "Nešto novo"


def test_the_wall_buttons_and_spare_relays_stay_out_of_rooms():
    """They are real entities, and useless when you are looking at a room."""
    assert not builder.wanted_in_room("binary_sensor.esp32_io_tipkalo_svjetlo_kuhinja")
    assert not builder.wanted_in_room("switch.esp32_io_slobodno1")
    assert not builder.wanted_in_room("sensor.bme280_mux_node_bme280_mux_wifi_signal")
    assert not builder.wanted_in_room("sensor.bme280_mux_node_broj_cestica_pm1")
    assert builder.wanted_in_room("switch.esp32_io_svjetlo_kuhinja")
    assert builder.wanted_in_room("sensor.bme280_mux_node_kupaona_temperatura")


def test_the_house_is_not_a_room():
    """Power measurement and node diagnostics belong on the System view."""
    assert "kuca" not in [area_id for area_id, _ in builder.ROOM_ORDER]


def test_every_view_fits_the_seven_inch_panel():
    """800 px wide takes two columns; three squeezes tiles below a fingertip."""
    for view in (builder.climate_view(), builder.air_view(), builder.system_view()):
        assert view["max_columns"] <= 2


def test_room_tiles_are_finger_sized():
    view = builder.rooms_view(
        {"living_room": [{"entity_id": "switch.svjetlo", "name": "Svjetlo"}]},
        {"living_room": "Dnevni boravak"},
    )
    card = view["sections"][0]["cards"][1]

    assert card["vertical"] is True
    assert card["grid_options"]["columns"] == builder.TILE_COLUMNS


def test_a_switch_is_a_socket_unless_it_is_a_light():
    """Listing sockets by the word "utičnica" silently lost the oven.

    Split by what an entity IS, not by what it happens to be called, so an
    appliance added tomorrow lands somewhere instead of nowhere.
    """
    ids = [
        "switch.esp32_io_svjetlo_kuhinja",
        "light.esp32_io_svjetlo_fotelja",
        "switch.esp32_io_uticnica_tv",
        "switch.esp32_io_pecnica",
    ]

    lights = [e for e in ids if "svjetlo" in e]
    sockets = [e for e in ids if "svjetlo" not in e]

    assert sockets == ["switch.esp32_io_uticnica_tv", "switch.esp32_io_pecnica"]
    assert len(lights) + len(sockets) == len(ids)
