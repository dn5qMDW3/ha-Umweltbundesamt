"""Sensor platform for the Umweltbundesamt integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api.models import Measurement, Station
from .const import (
    AQI_LEVEL_KEYS,
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DEFAULT_INCLUDE_AQI,
    DOMAIN,
)
from .coordinator import UBADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_COMPONENT_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    "PM10": SensorDeviceClass.PM10,
    "PM25": SensorDeviceClass.PM25,
    "PM2": SensorDeviceClass.PM25,   # some UBA payloads use "PM2"
    "NO2": SensorDeviceClass.NITROGEN_DIOXIDE,
    "O3": SensorDeviceClass.OZONE,
    "SO2": SensorDeviceClass.SULPHUR_DIOXIDE,
    "CO": SensorDeviceClass.CO,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    bucket = hass.data[DOMAIN][entry.entry_id]
    coordinator: UBADataUpdateCoordinator = bucket["coordinator"]
    client = bucket["client"]
    station = await _find_station(client, entry.data[CONF_STATION_ID])
    components_by_id = await client.fetch_components()
    code_to_component = {c.code: c for c in components_by_id.values()}

    include_aqi = entry.options.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)

    entities: list[SensorEntity] = []
    for code, reading in coordinator.data.components.items():
        component = code_to_component.get(code)
        if component is None:
            continue
        entities.append(
            UBAComponentSensor(coordinator, station, code, component.name,
                               reading.unit)
        )
    if include_aqi:
        entities.append(UBAAirQualityIndexSensor(coordinator, station))

    async_add_entities(entities)


async def _find_station(client, station_id: int) -> Station:
    stations = await client.fetch_stations()
    for s in stations:
        if s.id == station_id:
            return s
    raise LookupError(f"Station {station_id} not in UBA station list")


def _device_info(station: Station) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, str(station.id))},
        name=f"{station.name} ({station.city})",
        manufacturer="Umweltbundesamt",
        model=station.station_type or "UBA-Messstation",
        configuration_url=(
            "https://www.umweltbundesamt.de/daten/luft/luftdaten/stationen"
            f"?lat={station.latitude}&lng={station.longitude}"
        ),
    )


class UBAComponentSensor(
    CoordinatorEntity[UBADataUpdateCoordinator], SensorEntity
):
    """Sensor for a single UBA pollutant reading."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UBADataUpdateCoordinator,
        station: Station,
        code: str,
        friendly_name: str,
        unit: str,
    ) -> None:
        super().__init__(coordinator)
        self._code = code
        self._attr_name = friendly_name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"uba_{station.id}_{code.lower()}"
        self._attr_device_info = _device_info(station)
        self._attr_device_class = _COMPONENT_DEVICE_CLASSES.get(code)

    @property
    def native_value(self) -> float | None:
        data: Measurement = self.coordinator.data
        reading = data.components.get(self._code)
        return reading.value if reading is not None else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class UBAAirQualityIndexSensor(
    CoordinatorEntity[UBADataUpdateCoordinator], SensorEntity
):
    """Aggregate 1..5 air-quality index for the station."""

    _attr_has_entity_name = True
    _attr_translation_key = "air_quality_index"

    def __init__(
        self,
        coordinator: UBADataUpdateCoordinator,
        station: Station,
    ) -> None:
        super().__init__(coordinator)
        self._station = station
        self._attr_name = "Air quality index"
        self._attr_unique_id = f"uba_{station.id}_aqi"
        self._attr_device_info = _device_info(station)

    @property
    def native_value(self) -> int | None:
        data: Measurement = self.coordinator.data
        return data.index

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: Measurement = self.coordinator.data
        level_key = AQI_LEVEL_KEYS.get(data.index) if data.index else None
        return {
            "level_text": level_key,
            "measurement_time": data.timestamp.isoformat(),
            "station_code": self._station.code,
            "station_city": self._station.city,
        }
