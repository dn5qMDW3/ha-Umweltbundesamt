"""Tests for the UBAClient."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.umweltbundesamt.api.client import UBAClient
from custom_components.umweltbundesamt.api.errors import UBAApiError

from .conftest import load_fixture


BASE = "https://www.umweltbundesamt.de/api/air_data/v2"


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
