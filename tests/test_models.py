"""Tests for UBA domain models."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.umweltbundesamt.api.models import (
    Component,
    Measurement,
    Station,
)


def test_station_is_active_no_end_date():
    station = Station(
        id=282, code="DEBE010", name="Wedding", city="Berlin",
        latitude=52.54, longitude=13.35, station_type="Hintergrund städtisch",
        network_code="BE", active_from=datetime(2000, 1, 1), active_to=None,
    )
    assert station.is_active(datetime(2026, 4, 19)) is True


def test_station_is_inactive_after_end_date():
    station = Station(
        id=1, code="X", name="Old", city="Nowhere",
        latitude=0.0, longitude=0.0, station_type="",
        network_code="", active_from=datetime(2000, 1, 1),
        active_to=datetime(2020, 1, 1),
    )
    assert station.is_active(datetime(2026, 4, 19)) is False


def test_station_distance_km_home_to_itself_is_zero():
    s = Station(
        id=1, code="X", name="A", city="B", latitude=52.0, longitude=13.0,
        station_type="", network_code="",
        active_from=datetime(2000, 1, 1), active_to=None,
    )
    assert s.distance_km(52.0, 13.0) == pytest.approx(0.0, abs=1e-6)


def test_station_distance_km_known_pair():
    # Berlin (52.52, 13.405) to Munich (48.137, 11.576) ~ 504 km
    berlin = Station(
        id=1, code="B", name="B", city="B", latitude=52.52, longitude=13.405,
        station_type="", network_code="",
        active_from=datetime(2000, 1, 1), active_to=None,
    )
    assert berlin.distance_km(48.137, 11.576) == pytest.approx(504, abs=5)


def test_component_roundtrip():
    c = Component(id=1, code="PM10", symbol="PM₁₀", unit="µg/m³", name="Feinstaub")
    assert c.code == "PM10"
    assert c.unit == "µg/m³"


def test_measurement_get_component_missing_returns_none():
    m = Measurement(
        station_id=1,
        timestamp=datetime(2026, 4, 19, 12, tzinfo=ZoneInfo("Europe/Berlin")),
        index=2,
        components={},
    )
    assert m.get_component_value("PM10") is None
