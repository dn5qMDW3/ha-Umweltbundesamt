"""The Umweltbundesamt integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import UBAClient
from .const import CONF_STATION_ID
from .coordinator import UBADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class UBARuntimeData:
    """Per-entry runtime state accessed via ``entry.runtime_data``."""

    client: UBAClient
    coordinator: UBADataUpdateCoordinator


type UBAConfigEntry = ConfigEntry[UBARuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: UBAConfigEntry) -> bool:
    """Set up Umweltbundesamt from a config entry."""
    station_id = int(entry.data[CONF_STATION_ID])
    session = async_get_clientsession(hass)
    client = UBAClient(session)
    # Prime component metadata once so sensor setup and polls can both use it.
    await client.fetch_components()
    coordinator = UBADataUpdateCoordinator(hass, client, station_id)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = UBARuntimeData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UBAConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(
    hass: HomeAssistant, entry: UBAConfigEntry,
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
