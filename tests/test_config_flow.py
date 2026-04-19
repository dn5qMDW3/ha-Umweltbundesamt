"""Tests for the Umweltbundesamt config flow."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.umweltbundesamt.api.errors import UBAApiError
from custom_components.umweltbundesamt.api.models import Station
from custom_components.umweltbundesamt.const import (
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DOMAIN,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _fresh_limits() -> dict[int, datetime]:
    """Limits map with all sample stations publishing right now."""
    now = datetime.now(BERLIN).replace(microsecond=0)
    return {282: now, 1083: now, 999: now, 1: now}


def _sample_stations() -> list[Station]:
    now_active = datetime(2000, 1, 1, tzinfo=BERLIN)
    return [
        Station(
            id=282, code="DEBE010", name="Wedding", city="Berlin",
            latitude=52.543, longitude=13.349,
            station_type="Hintergrund städtisch", network_code="1",
            active_from=now_active, active_to=None,
        ),
        Station(
            id=1083, code="DEBY072", name="Marienplatz", city="München",
            latitude=48.137, longitude=11.576,
            station_type="Verkehr städtisch", network_code="1",
            active_from=now_active, active_to=None,
        ),
        Station(
            id=999, code="DE_OLD", name="Stillgelegt", city="Nirgendwo",
            latitude=50.0, longitude=10.0,
            station_type="Hintergrund ländlich", network_code="1",
            active_from=now_active,
            active_to=datetime(2015, 12, 31, tzinfo=BERLIN),
        ),
    ]


@pytest.fixture(autouse=True)
def _set_home_coords(hass: HomeAssistant):
    hass.config.latitude = 52.5
    hass.config.longitude = 13.4
    yield


@pytest.mark.asyncio
async def test_user_flow_preselects_nearest_and_creates_entry(
    hass: HomeAssistant,
):
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )
        client_cls.return_value.fetch_airquality_limits = AsyncMock(
            return_value=_fresh_limits()
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"
        # The default in the schema should be the nearest (Berlin, id=282).
        schema = result["data_schema"].schema
        station_key = next(
            k for k in schema if getattr(k, "schema", None) == CONF_STATION_ID
        )
        # Default is stored as a string so it matches SelectSelector options.
        assert station_key.default() == "282"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_STATION_ID: "1083", CONF_INCLUDE_AQI: True},
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATION_ID] == 1083
    assert result["options"][CONF_INCLUDE_AQI] is True


@pytest.mark.asyncio
async def test_user_flow_cannot_connect(hass: HomeAssistant):
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            side_effect=UBAApiError("down")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.asyncio
async def test_user_flow_no_active_stations(hass: HomeAssistant):
    expired = Station(
        id=1, code="X", name="X", city="X",
        latitude=0.0, longitude=0.0, station_type="", network_code="",
        active_from=datetime(1990, 1, 1, tzinfo=BERLIN),
        active_to=datetime(2000, 1, 1, tzinfo=BERLIN),
    )
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=[expired]
        )
        client_cls.return_value.fetch_airquality_limits = AsyncMock(
            return_value={}
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_active_stations"


@pytest.mark.asyncio
async def test_user_flow_rejects_duplicate_station(hass: HomeAssistant):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)", data={CONF_STATION_ID: 282},
        source=config_entries.SOURCE_USER, options={}, unique_id="282",
        discovery_keys={}, subentries_data={},
    )
    hass.config_entries._entries[entry.entry_id] = entry

    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )
        client_cls.return_value.fetch_airquality_limits = AsyncMock(
            return_value=_fresh_limits()
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_STATION_ID: "282", CONF_INCLUDE_AQI: True},
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_user_flow_schema_is_json_serializable(hass: HomeAssistant):
    """Regression test: HA serializes the schema for the frontend via
    voluptuous_serialize.convert(). A bare callable inside vol.All() makes
    that conversion raise "Unable to convert schema" and surfaces as a
    500 "Config flow could not be loaded" in the UI.
    """
    import voluptuous_serialize
    from homeassistant.helpers import config_validation as cv

    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )
        client_cls.return_value.fetch_airquality_limits = AsyncMock(
            return_value=_fresh_limits()
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    # This is exactly what HA's config-entries REST view does before returning
    # the schema to the frontend.
    voluptuous_serialize.convert(
        result["data_schema"], custom_serializer=cv.custom_serializer,
    )


@pytest.mark.asyncio
async def test_user_flow_hides_stations_without_recent_data(
    hass: HomeAssistant,
):
    """Stations with None or stale limits must not appear in the dropdown."""
    now = datetime.now(BERLIN).replace(microsecond=0)
    stale_limits = {
        282: now,                                       # fresh
        1083: now - __import__("datetime").timedelta(   # 10 days old → stale
            days=10
        ),
        999: None,                                      # never published
    }
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )
        client_cls.return_value.fetch_airquality_limits = AsyncMock(
            return_value=stale_limits
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    schema_dict = result["data_schema"].schema
    station_key = next(
        k for k in schema_dict if getattr(k, "schema", None) == CONF_STATION_ID
    )
    options = schema_dict[station_key].config["options"]
    station_ids_in_dropdown = {int(opt["value"]) for opt in options}
    assert station_ids_in_dropdown == {282}
