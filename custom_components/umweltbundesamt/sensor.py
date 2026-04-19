"""Sensor platform for the Umweltbundesamt integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import UBAConfigEntry
from .api.models import Measurement, Station
from .const import CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI, DOMAIN
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
    entry: UBAConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    client = runtime.client
    station = await _find_station(client, coordinator.station_id)
    components_by_id = await client.fetch_components()
    code_to_component = {c.code: c for c in components_by_id.values()}

    include_aqi = entry.options.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)

    entities: list[SensorEntity] = []
    for code, reading in coordinator.data.components.items():
        component = code_to_component.get(code)
        if component is None:
            continue
        device_class = _COMPONENT_DEVICE_CLASSES.get(code)
        # When we have a matching HA device class, let HA localize the name;
        # fall back to the API's German label only for unknown components.
        friendly_name = None if device_class is not None else component.name
        entities.append(
            UBAComponentSensor(
                coordinator,
                station,
                code,
                friendly_name,
                reading.unit,
                device_class,
            )
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
        friendly_name: str | None,
        unit: str,
        device_class: SensorDeviceClass | None,
    ) -> None:
        super().__init__(coordinator)
        self._code = code
        if friendly_name is not None:
            self._attr_name = friendly_name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"uba_{station.id}_{code.lower()}"
        self._attr_device_info = _device_info(station)
        self._attr_device_class = device_class

    @property
    def native_value(self) -> float | None:
        data: Measurement = self.coordinator.data
        reading = data.components.get(self._code)
        return reading.value if reading is not None else None


class UBAAirQualityIndexSensor(
    CoordinatorEntity[UBADataUpdateCoordinator], SensorEntity
):
    """Aggregate 1..5 air-quality index for the station."""

    _attr_has_entity_name = True
    _attr_translation_key = "air_quality_index"
    _attr_device_class = SensorDeviceClass.AQI
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UBADataUpdateCoordinator,
        station: Station,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"uba_{station.id}_aqi"
        self._attr_device_info = _device_info(station)

    @property
    def native_value(self) -> int | None:
        data: Measurement = self.coordinator.data
        return data.index

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data: Measurement = self.coordinator.data
        return {"measurement_time": data.timestamp.isoformat()}
