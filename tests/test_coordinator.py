"""Tests for UBADataUpdateCoordinator."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.umweltbundesamt.api.errors import UBAApiError
from custom_components.umweltbundesamt.api.models import (
    ComponentReading,
    Measurement,
)
from custom_components.umweltbundesamt.const import (
    DEFAULT_SCAN_INTERVAL,
    FAILURE_RETRY_INTERVAL,
)
from custom_components.umweltbundesamt.coordinator import (
    UBADataUpdateCoordinator,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _make_measurement() -> Measurement:
    return Measurement(
        station_id=282,
        timestamp=datetime(2026, 4, 19, 12, tzinfo=BERLIN),
        index=2,
        components={"PM10": ComponentReading(18.5, "µg/m³", 2)},
    )


@pytest.mark.asyncio
async def test_coordinator_caches_measurement_on_success(hass):
    client = AsyncMock()
    client.fetch_current_airquality.return_value = _make_measurement()
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    data = await coord._async_update_data()
    assert data.index == 2
    assert data.components["PM10"].value == pytest.approx(18.5)
    client.fetch_current_airquality.assert_awaited_once_with(282)


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_on_api_error(hass):
    client = AsyncMock()
    client.fetch_current_airquality.side_effect = UBAApiError("boom")
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_when_no_rows(hass):
    client = AsyncMock()
    client.fetch_current_airquality.return_value = None
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_shortens_interval_on_failure(hass):
    """A failed poll drops the interval to FAILURE_RETRY_INTERVAL so the
    next attempt arrives quickly; a subsequent success restores
    DEFAULT_SCAN_INTERVAL."""
    client = AsyncMock()
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    assert coord.update_interval == DEFAULT_SCAN_INTERVAL

    # Network / API error -> short retry interval.
    client.fetch_current_airquality.side_effect = UBAApiError("boom")
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == FAILURE_RETRY_INTERVAL

    # "No rows" is also a failure from HA's POV -> keep retry interval.
    client.fetch_current_airquality.side_effect = None
    client.fetch_current_airquality.return_value = None
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    assert coord.update_interval == FAILURE_RETRY_INTERVAL

    # Success -> back to the normal cadence.
    client.fetch_current_airquality.return_value = _make_measurement()
    await coord._async_update_data()
    assert coord.update_interval == DEFAULT_SCAN_INTERVAL
