"""Tests for the read-only Home Assistant sensor tools.

These cover the two things that decide whether the assistant is useful or
actively misleading: finding the right sensor for a zone, and refusing to read
out a value the sensor cannot physically have produced.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.adk_tools import ha_sensor_tools as hs  # noqa: E402


def _state(entity_id, state, device_class, unit, friendly_name, last_updated="2026-08-20T18:00:00+00:00"):
    return {
        "entity_id": entity_id,
        "state": state,
        "last_updated": last_updated,
        "attributes": {
            "device_class": device_class,
            "unit_of_measurement": unit,
            "friendly_name": friendly_name,
        },
    }


NODE = "sensor.bme280_mux_node_"

STATES = [
    _state(NODE + "kupaona_temperatura", "27.9", "temperature", "°C", "BME280 Mux Node Kupaona temperatura"),
    _state(NODE + "kupaona_vlaga", "48.3", "humidity", "%", "BME280 Mux Node Kupaona vlaga"),
    _state(NODE + "kupaona_tlak", "995.6", "pressure", "hPa", "BME280 Mux Node Kupaona tlak"),
    _state(NODE + "dnevni_prostor_temperatura", "27.4", "temperature", "°C", "BME280 Mux Node Dnevni prostor temperatura"),
    _state(NODE + "vanjska_temperatura", "31.3", "temperature", "°C", "BME280 Mux Node Vanjska temperatura"),
    _state(NODE + "vanjski_tlak", "995.8", "pressure", "hPa", "BME280 Mux Node Vanjski tlak"),
    _state(NODE + "kvaliteta_zraka_pm2_5", "1433.5", "pm25", "μg/m³", "BME280 Mux Node Kvaliteta zraka PM2.5"),
    _state(NODE + "kvaliteta_zraka_pm1", "12.0", "pm1", "μg/m³", "BME280 Mux Node Kvaliteta zraka PM1"),
    _state(NODE + "mrezni_napon", "unknown", "voltage", "V", "BME280 Mux Node Mrezni napon"),
    _state(NODE + "kat_struja", "2.5", "current", "A", "BME280 Mux Node Kat struja"),
    _state(NODE + "bme280_mux_wifi_signal", "-30", "signal_strength", "dBm", "BME280 Mux Node BME280 Mux WiFi signal"),
    _state("switch.svjetlo_kuhinja", "on", "", "", "Svjetlo kuhinja"),
]


@pytest.fixture(autouse=True)
def _fresh_time(monkeypatch):
    # Readings in the fixture are old; age must not turn every test into "stale".
    monkeypatch.setenv("HA_SENSOR_MAX_AGE_SECONDS", "99999999")


def _with_states(states=STATES):
    return patch.object(hs, "_fetch_states", return_value=states)


def test_climate_read_groups_by_zone_without_the_device_name():
    with _with_states():
        result = hs.home_climate_read()

    zones = {m["zona"] for m in result["mjerenja"]}
    assert "Kupaona" in zones
    assert "Dnevni prostor" in zones          # multi-word zone survives
    assert not any(z.startswith("BME280") for z in zones)
    assert not any("Node" in z for z in zones)


def test_climate_read_filters_by_zone():
    with _with_states():
        result = hs.home_climate_read("kupaona")

    assert result["broj"] == 3
    assert {m["device_class"] for m in result["mjerenja"]} == {"temperature", "humidity", "pressure"}


def test_zone_filter_survives_croatian_word_endings():
    """"vanjska" must also find "Vanjski tlak"."""
    with _with_states():
        result = hs.home_climate_read("vanjska")

    classes = {m["device_class"] for m in result["mjerenja"]}
    assert classes == {"temperature", "pressure"}


def test_impossible_temperature_is_flagged_not_reported():
    broken = [_state(NODE + "kupaona_temperatura", "188.45", "temperature", "°C",
                     "BME280 Mux Node Kupaona temperatura")]
    with _with_states(broken):
        result = hs.home_climate_read()

    reading = result["mjerenja"][0]
    assert reading["sumnjivo"] is True
    assert "greška očitanja" in reading["napomena"]
    assert "upozorenje" in result


def test_high_pm_is_reported_as_real_not_as_a_fault():
    """Smoke and dust genuinely push SPS30 past its specified range.

    The user verified this: cigarette smoke sends the reading over 100000.
    Flagging that as a sensor error would misinform them about their own air.
    """
    smoky = [_state(NODE + "kvaliteta_zraka_pm2_5", "104233.0", "pm25", "μg/m³",
                    "BME280 Mux Node Kvaliteta zraka PM2.5")]
    with _with_states(smoky):
        result = hs.home_air_quality_read()

    reading = result["mjerenja"][0]
    assert reading["vrijednost"] == 104233.0
    assert reading.get("sumnjivo") is None
    assert "upozorenje" not in result


def test_unknown_state_reports_unavailable_not_zero():
    with _with_states():
        result = hs.home_power_read()

    voltage = [m for m in result["mjerenja"] if m["device_class"] == "voltage"][0]
    assert voltage["dostupno"] is False
    assert voltage["vrijednost"] is None


def test_stale_reading_is_marked():
    with patch.dict("os.environ", {"HA_SENSOR_MAX_AGE_SECONDS": "1"}):
        with _with_states():
            result = hs.home_climate_read("kupaona")

    assert all(m.get("zastarjelo") for m in result["mjerenja"])


def test_switches_are_never_returned_as_sensors():
    with _with_states():
        result = hs.home_climate_read()

    assert all(m["entity_id"].startswith("sensor.") for m in result["mjerenja"])


def test_missing_zone_says_so_instead_of_returning_everything():
    with _with_states():
        result = hs.home_climate_read("garaza")

    assert result["mjerenja"] == []
    assert "garaza" in result["napomena"]


def test_sensor_search_finds_uncategorised_sensors():
    with _with_states():
        result = hs.home_sensor_search("wifi")

    assert result["broj"] == 1
    assert result["mjerenja"][0]["vrijednost"] == -30.0


def test_search_without_query_is_rejected():
    assert "error" in hs.home_sensor_search("   ")


def test_ha_unreachable_returns_error_not_exception():
    with patch.object(hs, "_fetch_states", side_effect=RuntimeError("HA API nedostupan")):
        assert "error" in hs.home_climate_read()
        assert "error" in hs.home_air_quality_read()
        assert "error" in hs.home_power_read()
        assert "error" in hs.home_sensor_search("wifi")


def test_tools_are_read_only():
    """No tool in this module may reach a HA service endpoint."""
    import inspect

    source = inspect.getsource(hs)
    assert "/api/services" not in source
    assert "_ha_service" not in source


def test_second_device_keeps_its_own_name_prefix():
    other = STATES + [
        _state("sensor.plug_kuhinja_snaga", "120.0", "power", "W", "Plug Kuhinja Stvarna snaga"),
        _state("sensor.plug_kuhinja_struja", "0.5", "current", "A", "Plug Kuhinja Struja"),
    ]
    with _with_states(other):
        result = hs.home_power_read()

    zones = {m["zona"] for m in result["mjerenja"]}
    assert "Kuhinja" in zones     # its own device prefix stripped separately
    assert "Kat" in zones         # the ESPHome node's channel still intact
