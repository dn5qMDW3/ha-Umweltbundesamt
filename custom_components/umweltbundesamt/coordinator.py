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
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class UBADataUpdateCoordinator(DataUpdateCoordinator[Measurement]):
    """Polls the UBA air-quality endpoint for a single station."""

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
            raise UpdateFailed(str(err)) from err
        if measurement is None:
            raise UpdateFailed(
                f"No air-quality data available for station {self.station_id}"
            )
        return measurement
