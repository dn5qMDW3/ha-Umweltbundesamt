"""Config + options flow for the Umweltbundesamt integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api.client import UBAClient
from .api.errors import UBAError
from .api.models import Station
from .const import (
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DEFAULT_INCLUDE_AQI,
    DOMAIN,
    STATION_STALENESS_THRESHOLD,
)

_LOGGER = logging.getLogger(__name__)
BERLIN_TZ = ZoneInfo("Europe/Berlin")


class UBAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        session = async_get_clientsession(self.hass)
        client = UBAClient(session)
        try:
            stations = await client.fetch_stations()
            limits = await client.fetch_airquality_limits()
        except UBAError as err:
            _LOGGER.warning("UBA station fetch failed: %s", err)
            return self.async_abort(reason="cannot_connect")

        now = datetime.now(BERLIN_TZ)
        active = [
            s for s in stations
            if s.is_active(now) and _has_recent_data(limits, s.id, now)
        ]
        if not active:
            return self.async_abort(reason="no_active_stations")

        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude
        active.sort(key=lambda s: s.distance_km(home_lat, home_lon))
        nearest = active[0]

        if user_input is not None:
            picked_id = int(user_input[CONF_STATION_ID])
            await self.async_set_unique_id(str(picked_id))
            self._abort_if_unique_id_configured()
            picked = next(
                (s for s in active if s.id == picked_id), nearest,
            )
            return self.async_create_entry(
                title=f"{picked.name} ({picked.city})",
                data={CONF_STATION_ID: picked.id},
                options={CONF_INCLUDE_AQI: bool(user_input.get(
                    CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI
                ))},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_station_schema(
                active, home_lat, home_lon, default_id=nearest.id
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return UBAOptionsFlow()


class UBAOptionsFlow(config_entries.OptionsFlow):
    """Options flow — change station, toggle AQI sensor."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        session = async_get_clientsession(self.hass)
        client = UBAClient(session)
        try:
            stations = await client.fetch_stations()
            limits = await client.fetch_airquality_limits()
        except UBAError as err:
            _LOGGER.warning("UBA station fetch failed: %s", err)
            return self.async_abort(reason="cannot_connect")
        now = datetime.now(BERLIN_TZ)
        active = [
            s for s in stations
            if s.is_active(now) and _has_recent_data(limits, s.id, now)
        ]
        if not active:
            return self.async_abort(reason="no_active_stations")

        entry = self.config_entry

        if user_input is not None:
            new_station_id = int(user_input[CONF_STATION_ID])
            include_aqi = bool(
                user_input.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)
            )
            if new_station_id != entry.data[CONF_STATION_ID]:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_STATION_ID: new_station_id},
                    unique_id=str(new_station_id),
                )
            return self.async_create_entry(
                title="",
                data={CONF_INCLUDE_AQI: include_aqi},
            )

        current_id = int(entry.data[CONF_STATION_ID])
        include_aqi = bool(
            entry.options.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)
        )
        schema = _build_station_schema(
            active,
            self.hass.config.latitude,
            self.hass.config.longitude,
            default_id=current_id,
            default_include_aqi=include_aqi,
        )
        return self.async_show_form(step_id="init", data_schema=schema)


def _has_recent_data(
    limits: dict[int, datetime | None],
    station_id: int,
    now: datetime,
) -> bool:
    """True if the station has published air-quality data recently.

    ``STATION_STALENESS_THRESHOLD`` defines "recently". Stations missing
    from the limits map or explicitly listed with ``None`` are treated as
    not publishing.
    """
    last = limits.get(station_id)
    if last is None:
        return False
    return (now - last) <= STATION_STALENESS_THRESHOLD


def _build_station_schema(
    active: list[Station],
    home_lat: float,
    home_lon: float,
    *,
    default_id: int,
    default_include_aqi: bool = DEFAULT_INCLUDE_AQI,
) -> vol.Schema:
    options: list[SelectOptionDict] = []
    for station in sorted(
        active, key=lambda s: s.distance_km(home_lat, home_lon)
    ):
        distance = station.distance_km(home_lat, home_lon)
        options.append(
            SelectOptionDict(
                value=str(station.id),
                label=(
                    f"{station.code} — {station.name}, {station.city} "
                    f"({distance:.0f} km)"
                ),
            )
        )

    # The selector returns a string (SelectSelectorConfig values are strings);
    # int conversion happens in the flow handlers after user_input arrives.
    # We cannot use vol.All(..., _coerce_station_id) here: HA serializes the
    # schema to JSON for the frontend via voluptuous_serialize, which cannot
    # walk plain Python callables.
    return vol.Schema(
        {
            vol.Required(
                CONF_STATION_ID, default=str(default_id)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=False,
                )
            ),
            vol.Required(
                CONF_INCLUDE_AQI, default=default_include_aqi
            ): bool,
        }
    )
