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
            user_input={CONF_STATION_ID: 1083, CONF_INCLUDE_AQI: True},
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
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_STATION_ID: 282, CONF_INCLUDE_AQI: True},
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
