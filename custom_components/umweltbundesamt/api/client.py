"""Async HTTP client for the Umweltbundesamt air-quality API."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from ..const import BASE_URL
from .errors import UBAApiError, UBATimeoutError
from .models import Component, Measurement, Station

_LOGGER = logging.getLogger(__name__)

BERLIN_TZ = ZoneInfo("Europe/Berlin")
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class UBAClient:
    """Thin async client around the public UBA v2 endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._components: dict[int, Component] | None = None
        self._stations: list[Station] | None = None

    async def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{BASE_URL}{path}"
        try:
            async with self._session.get(
                url, params=params, timeout=_REQUEST_TIMEOUT
            ) as resp:
                if resp.status >= 400:
                    raise UBAApiError(
                        f"{url} returned HTTP {resp.status}"
                    )
                return await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise UBATimeoutError(f"{url} timed out") from err
        except aiohttp.ClientError as err:
            raise UBAApiError(f"{url} request failed: {err}") from err

    async def fetch_components(self) -> dict[int, Component]:
        """Fetch the component (pollutant) metadata."""
        if self._components is not None:
            return self._components
        payload = await self._get_json(
            "/components/json", {"lang": "de", "index": "id"}
        )
        if not isinstance(payload, dict):
            raise UBAApiError("components: unexpected payload shape")
        try:
            parsed: dict[int, Component] = {}
            for raw in payload.values():
                if not isinstance(raw, list) or len(raw) < 5:
                    raise UBAApiError("components: unexpected row shape")
                comp_id, code, symbol, unit, name = raw[:5]
                parsed[int(comp_id)] = Component(
                    id=int(comp_id),
                    code=str(code),
                    symbol=str(symbol),
                    unit=str(unit),
                    name=str(name),
                )
        except (TypeError, ValueError) as err:
            raise UBAApiError(f"components: parse error: {err}") from err
        self._components = parsed
        return parsed

    async def fetch_stations(self) -> list[Station]:
        """Fetch the full station list."""
        if self._stations is not None:
            return self._stations
        payload = await self._get_json(
            "/stations/json", {"lang": "de", "index": "id"}
        )
        if not isinstance(payload, dict):
            raise UBAApiError("stations: unexpected payload shape")
        parsed: list[Station] = []
        for raw in payload.values():
            if not isinstance(raw, list) or len(raw) < 12:
                raise UBAApiError("stations: unexpected row shape")
            try:
                station = Station(
                    id=int(raw[0]),
                    code=str(raw[1]),
                    name=str(raw[2]),
                    city=str(raw[3]),
                    active_from=_parse_uba_datetime(raw[4]),
                    active_to=(
                        _parse_uba_datetime(raw[5]) if raw[5] else None
                    ),
                    latitude=float(raw[6]),
                    longitude=float(raw[7]),
                    network_code=str(raw[8]),
                    station_type=f"{raw[10]} {raw[11]}".strip(),
                )
            except (TypeError, ValueError) as err:
                raise UBAApiError(f"stations: parse error: {err}") from err
            parsed.append(station)
        self._stations = parsed
        return parsed

    async def fetch_current_airquality(
        self, station_id: int
    ) -> Measurement | None:
        """Fetch the newest available air-quality row for `station_id`."""
        raise NotImplementedError  # Implemented in Task 4


def _parse_uba_datetime(raw: Any) -> datetime:
    """Parse the UBA 'YYYY-MM-DD HH:MM:SS' format in Europe/Berlin tz."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=BERLIN_TZ)
    if not isinstance(raw, str):
        raise UBAApiError(f"expected datetime string, got {type(raw).__name__}")
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BERLIN_TZ)
