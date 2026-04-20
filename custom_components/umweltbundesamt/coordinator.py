"""DataUpdateCoordinator for the Umweltbundesamt integration."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api.client import UBAClient
from .api.errors import UBAError
from .api.models import Measurement
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, FAILURE_RETRY_INTERVAL

_LOGGER = logging.getLogger(__name__)


class UBADataUpdateCoordinator(DataUpdateCoordinator[Measurement]):
    """Polls the UBA air-quality endpoint for a single station.

    Normal cadence is :data:`DEFAULT_SCAN_INTERVAL` (60 min, matching the
    UBA publishing interval). When a poll fails — network error, API
    error, or an empty publishing window — the coordinator temporarily
    drops to :data:`FAILURE_RETRY_INTERVAL` (5 min) so the next attempt
    arrives quickly. The normal cadence is restored on the next
    successful refresh.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: UBAClient,
        station_id: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_station_{station_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client
        self.station_id = station_id

    async def _async_update_data(self) -> Measurement:
        try:
            measurement = await self._client.fetch_current_airquality(
                self.station_id
            )
        except UBAError as err:
            self.update_interval = FAILURE_RETRY_INTERVAL
            raise UpdateFailed(str(err)) from err
        if measurement is None:
            self.update_interval = FAILURE_RETRY_INTERVAL
            raise UpdateFailed(
                f"No air-quality data available for station {self.station_id}"
            )
        # Success: restore the normal 60-minute cadence.
        self.update_interval = DEFAULT_SCAN_INTERVAL
        return measurement
