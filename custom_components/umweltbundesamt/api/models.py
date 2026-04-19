"""Domain models for the Umweltbundesamt air-quality API."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Component:
    """A measured pollutant / air component."""

    id: int
    code: str       # e.g. "PM10"
    symbol: str     # e.g. "PM₁₀"
    unit: str       # e.g. "µg/m³"
    name: str       # localized human-readable name


@dataclass(frozen=True)
class Station:
    """An Umweltbundesamt measurement station.

    Invariant: ``active_from`` and ``active_to`` are timezone-aware
    (Europe/Berlin) because ``UBAClient`` constructs them via
    ``_parse_uba_datetime``. Callers MUST pass timezone-aware values to
    ``is_active``; mixing aware and naive datetimes raises ``TypeError``.
    """

    id: int
    code: str
    name: str
    city: str
    latitude: float
    longitude: float
    station_type: str
    network_code: str
    active_from: datetime
    active_to: Optional[datetime]

    def is_active(self, at: datetime) -> bool:
        """Return True if the station is measuring at the given moment.

        ``active_from`` is inclusive, ``active_to`` is exclusive.
        """
        if at < self.active_from:
            return False
        if self.active_to is not None and at >= self.active_to:
            return False
        return True

    def distance_km(self, latitude: float, longitude: float) -> float:
        """Haversine great-circle distance to the given coordinates, in km."""
        r_km = 6371.0088
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(latitude)
        dlat = math.radians(latitude - self.latitude)
        dlon = math.radians(longitude - self.longitude)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return 2 * r_km * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class ComponentReading:
    """A single component's value at the measurement timestamp."""

    value: Optional[float]
    unit: str
    class_index: Optional[int]


@dataclass(frozen=True)
class Measurement:
    """A normalized air-quality observation for one station at one hour."""

    station_id: int
    timestamp: datetime
    index: Optional[int]
    components: dict[str, ComponentReading] = field(default_factory=dict)

    def get_component_value(self, code: str) -> Optional[float]:
        reading = self.components.get(code)
        return reading.value if reading is not None else None
