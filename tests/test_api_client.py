"""Tests for the UBAClient."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.umweltbundesamt.api.client import UBAClient
from custom_components.umweltbundesamt.api.errors import UBAApiError

from .conftest import load_fixture


BASE = "https://www.umweltbundesamt.de/api/air_data/v2"
AIRQUALITY_URL_RE = re.compile(
    r"^https://www\.umweltbundesamt\.de/api/air_data/v2/airquality/json\?.*$"
)


@pytest.mark.asyncio
async def test_fetch_components_parses_fixture():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            components = await client.fetch_components()
    assert components[1].code == "PM10"
    assert components[5].code == "NO2"
    assert components[3].unit == "µg/m³"


@pytest.mark.asyncio
async def test_fetch_stations_parses_active_and_inactive():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/stations/json?lang=de&index=id",
                payload=load_fixture("stations.json"),
            )
            stations = await client.fetch_stations()
    by_id = {s.id: s for s in stations}
    assert by_id[282].city == "Berlin"
    assert by_id[282].active_to is None
    assert by_id[999].active_to == datetime(
        2015, 12, 31, tzinfo=ZoneInfo("Europe/Berlin")
    )
    assert by_id[1083].latitude == pytest.approx(48.137)


@pytest.mark.asyncio
async def test_fetch_components_raises_on_http_error():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(f"{BASE}/components/json?lang=de&index=id", status=500)
            with pytest.raises(UBAApiError):
                await client.fetch_components()


@pytest.mark.asyncio
async def test_fetch_components_raises_on_unexpected_shape():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload={"unexpected": "shape"},
            )
            with pytest.raises(UBAApiError):
                await client.fetch_components()


@pytest.mark.asyncio
async def test_fetch_current_airquality_returns_newest_row():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            m.get(
                AIRQUALITY_URL_RE,
                payload=load_fixture("airquality_full.json"),
            )
            measurement = await client.fetch_current_airquality(282)
    assert measurement is not None
    assert measurement.station_id == 282
    assert measurement.index == 2
    assert measurement.timestamp == datetime(
        2026, 4, 19, 12, tzinfo=ZoneInfo("Europe/Berlin")
    )
    assert measurement.components["PM10"].value == pytest.approx(19)
    assert measurement.components["NO2"].value == pytest.approx(22)
    assert measurement.components["O3"].value == pytest.approx(80)


@pytest.mark.asyncio
async def test_fetch_current_airquality_handles_incomplete_row():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            m.get(
                AIRQUALITY_URL_RE,
                payload=load_fixture("airquality_incomplete.json"),
            )
            measurement = await client.fetch_current_airquality(282)
    assert measurement is not None
    assert measurement.index is None  # blanked because incomplete=1
    assert measurement.components["NO2"].value == pytest.approx(22)


@pytest.mark.asyncio
async def test_fetch_current_airquality_returns_none_when_no_data():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            m.get(AIRQUALITY_URL_RE, payload={"data": {}})
            measurement = await client.fetch_current_airquality(282)
    assert measurement is None
