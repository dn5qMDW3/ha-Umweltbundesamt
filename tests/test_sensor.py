"""Tests for the Umweltbundesamt sensor platform."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant

from custom_components.umweltbundesamt.api.models import (
    ComponentReading,
    Measurement,
    Station,
)
from custom_components.umweltbundesamt.const import (
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DOMAIN,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _station() -> Station:
    return Station(
        id=282, code="DEBE010", name="Wedding", city="Berlin",
        latitude=52.543, longitude=13.349,
        station_type="Hintergrund städtisch", network_code="1",
        active_from=datetime(2000, 1, 1, tzinfo=BERLIN), active_to=None,
    )


def _measurement() -> Measurement:
    return Measurement(
        station_id=282,
        timestamp=datetime(2026, 4, 19, 12, tzinfo=BERLIN),
        index=2,
        components={
            "PM10": ComponentReading(18.5, "µg/m³", 2),
            "NO2": ComponentReading(22.1, "µg/m³", 1),
        },
    )


def _mock_component(cid: int, code: str, unit: str, cname: str) -> MagicMock:
    """MagicMock for a Component. ``name`` is special on Mock, so set it."""
    m = MagicMock(id=cid, code=code, unit=unit)
    m.name = cname
    return m


async def _install_entry(hass: HomeAssistant) -> str:
    """Mock out the API, register a config entry, return entry_id."""
    client = MagicMock()
    client.fetch_components = AsyncMock(
        return_value={
            1: _mock_component(1, "PM10", "µg/m³", "Feinstaub (PM10)"),
            5: _mock_component(5, "NO2", "µg/m³", "Stickstoffdioxid"),
        }
    )
    client.fetch_stations = AsyncMock(return_value=[_station()])
    client.fetch_current_airquality = AsyncMock(return_value=_measurement())

    from homeassistant import config_entries

    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)",
        data={CONF_STATION_ID: 282},
        options={CONF_INCLUDE_AQI: True},
        source=config_entries.SOURCE_USER, unique_id="282",
        discovery_keys={}, subentries_data={},
    )
    hass.config_entries._entries[entry.entry_id] = entry

    with patch(
        "custom_components.umweltbundesamt.UBAClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.entry_id


@pytest.mark.asyncio
async def test_sensors_created_for_each_component(hass: HomeAssistant):
    await _install_entry(hass)
    pm10 = hass.states.get("sensor.wedding_berlin_feinstaub_pm10")
    assert pm10 is not None
    assert float(pm10.state) == pytest.approx(18.5)
    # HA normalizes U+00B5 (MICRO SIGN) to U+03BC (GREEK SMALL LETTER MU).
    assert pm10.attributes["unit_of_measurement"] in ("µg/m³", "μg/m³")
    assert pm10.attributes["device_class"] == SensorDeviceClass.PM10
    assert pm10.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.asyncio
async def test_aqi_sensor_has_level_text_attribute(hass: HomeAssistant):
    await _install_entry(hass)
    aqi = hass.states.get("sensor.wedding_berlin_air_quality_index")
    assert aqi is not None
    assert int(aqi.state) == 2
    assert aqi.attributes["level_text"] in ("good", "Gut", "Good")
    assert "measurement_time" in aqi.attributes


@pytest.mark.asyncio
async def test_aqi_sensor_disabled_when_option_off(hass: HomeAssistant):
    from homeassistant import config_entries

    client = MagicMock()
    client.fetch_components = AsyncMock(
        return_value={1: _mock_component(1, "PM10", "µg/m³",
                                         "Feinstaub (PM10)")}
    )
    client.fetch_stations = AsyncMock(return_value=[_station()])
    client.fetch_current_airquality = AsyncMock(return_value=_measurement())

    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)",
        data={CONF_STATION_ID: 282},
        options={CONF_INCLUDE_AQI: False},
        source=config_entries.SOURCE_USER, unique_id="282",
        discovery_keys={}, subentries_data={},
    )
    hass.config_entries._entries[entry.entry_id] = entry
    with patch(
        "custom_components.umweltbundesamt.UBAClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.wedding_berlin_air_quality_index") is None
