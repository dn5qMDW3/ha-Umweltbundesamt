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
        """Fetch the component (pollutant) metadata.

        The real /components/json payload contains ``count`` (int) and
        ``indices`` (list) alongside integer-id keys mapping to rows of
        ``[id, code, symbol, unit, name]``. We treat the presence of
        ``indices`` as the marker of a well-formed payload and iterate
        only the digit-string keys.
        """
        if self._components is not None:
            return self._components
        payload = await self._get_json(
            "/components/json", {"lang": "de", "index": "id"}
        )
        if not isinstance(payload, dict) or "indices" not in payload:
            raise UBAApiError("components: unexpected payload shape")
        try:
            parsed: dict[int, Component] = {}
            for key, raw in payload.items():
                if not isinstance(key, str) or not key.isdigit():
                    continue
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
        """Fetch the full station list.

        The real /stations/json payload wraps the station rows in a
        ``data`` dict keyed by station id. Rows are 20-element positional
        arrays; see the UBA v2 ``indices`` header for the full layout.
        """
        if self._stations is not None:
            return self._stations
        payload = await self._get_json(
            "/stations/json", {"lang": "de", "index": "id"}
        )
        if not isinstance(payload, dict):
            raise UBAApiError("stations: unexpected payload shape")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise UBAApiError("stations: 'data' key missing or wrong type")
        parsed: list[Station] = []
        for raw in data.values():
            if not isinstance(raw, list) or len(raw) < 17:
                raise UBAApiError("stations: unexpected row shape")
            try:
                station = Station(
                    id=int(raw[0]),
                    code=str(raw[1]),
                    name=str(raw[2]),
                    city=str(raw[3]),
                    active_from=_parse_uba_datetime(raw[5]),
                    active_to=(
                        _parse_uba_datetime(raw[6]) if raw[6] else None
                    ),
                    longitude=float(raw[7]),
                    latitude=float(raw[8]),
                    network_code=str(raw[12]),
                    station_type=f"{raw[16]} {raw[15]}".strip(),
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
    """Parse a UBA timestamp in Europe/Berlin tz.

    Accepts both ``"YYYY-MM-DD HH:MM:SS"`` (used by measurement rows) and
    ``"YYYY-MM-DD"`` (used by station active_from/active_to). Date-only
    values are interpreted as midnight local time.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=BERLIN_TZ)
    if not isinstance(raw, str):
        raise UBAApiError(f"expected datetime string, got {type(raw).__name__}")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=BERLIN_TZ)
        except ValueError:
            continue
    raise UBAApiError(f"unrecognised UBA datetime: {raw!r}")
