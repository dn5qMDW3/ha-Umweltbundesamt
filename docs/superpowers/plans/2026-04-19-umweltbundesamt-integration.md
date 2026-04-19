# Umweltbundesamt HA Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom integration that exposes UBA air-quality measurements (per-pollutant + 1–5 air-quality index) as sensors, auto-picking the nearest active measurement station with a user-changeable override.

**Architecture:** Standard HA `config entry → DataUpdateCoordinator → sensor platform`, with a thin async aiohttp client under `api/` that isolates UBA HTTP/parsing from HA concerns. One device per station, dynamic per-component sensors, hourly polling against `https://www.umweltbundesamt.de/api/air_data/v2`.

**Tech Stack:** Python 3.13, Home Assistant 2025.x, aiohttp, `pytest-homeassistant-custom-component`, `aioresponses`, flake8 (max-line-length 120).

**Spec:** `docs/superpowers/specs/2026-04-19-umweltbundesamt-integration-design.md`

**Naming correction vs. spec:** HA requires the integration directory name to match the lowercase domain (regex `^[a-z_]+$`). The spec and existing `CLAUDE.md` reference `custom_components/Umweltbundesamt/` (capital-U). This plan uses `custom_components/umweltbundesamt/` and `DOMAIN = "umweltbundesamt"`. `CLAUDE.md` and the release workflow reference the lowercase path accordingly.

## File layout produced by this plan

```
ha-Umweltbundesamt/
├── .flake8
├── .github/
│   └── workflows/
│       ├── hassfest.yaml          # HA manifest validator (CI)
│       ├── hacs.yaml              # HACS validation (CI)
│       └── release.yaml           # Stamp manifest version + attach zip on release
├── hacs.json                      # HACS manifest (repo-root)
├── README.md
├── custom_components/
│   └── umweltbundesamt/
│       ├── __init__.py            # async_setup_entry / async_unload_entry
│       ├── manifest.json
│       ├── const.py               # DOMAIN, BASE_URL, intervals, index labels
│       ├── config_flow.py         # ConfigFlow + OptionsFlow
│       ├── coordinator.py         # UBADataUpdateCoordinator
│       ├── sensor.py              # Per-component + AQI sensors
│       ├── strings.json           # Canonical EN source
│       ├── translations/
│       │   └── de.json
│       └── api/
│           ├── __init__.py        # Public re-exports
│           ├── errors.py          # UBAApiError, UBATimeoutError
│           ├── models.py          # Station, Component, Measurement
│           └── client.py          # UBAClient (aiohttp)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── stations.json
│   │   ├── components.json
│   │   ├── airquality_full.json
│   │   └── airquality_incomplete.json
│   ├── test_api_client.py
│   ├── test_coordinator.py
│   ├── test_config_flow.py
│   └── test_sensor.py
└── docs/
    └── superpowers/
        ├── specs/2026-04-19-umweltbundesamt-integration-design.md
        └── plans/2026-04-19-umweltbundesamt-integration.md   (this file)
```

---

## Task 0: Bootstrap project (git, venv, CI, HACS skeleton)

**Files:**
- Init: git repository
- Create: `.flake8`, `.gitignore`, `hacs.json`, `README.md`
- Create: `.github/workflows/hassfest.yaml`, `.github/workflows/hacs.yaml`, `.github/workflows/release.yaml`
- Create: `custom_components/umweltbundesamt/manifest.json`
- Create: `custom_components/umweltbundesamt/__init__.py` (empty-ish)
- Create: `custom_components/umweltbundesamt/const.py` (DOMAIN only for now)
- Create: `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Initialise git repository**

```bash
cd /Users/borisgrushenko/Documents/GitHub/ha-Umweltbundesamt
git init
git checkout -b main
```

- [ ] **Step 2: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.idea/
.DS_Store
dist/
build/
```

- [ ] **Step 3: Create `.flake8`**

```ini
[flake8]
max-line-length = 120
exclude = .git,.github,docs,venv,.venv
extend-ignore = E203,W503
```

- [ ] **Step 4: Create Python virtual environment and install deps**

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install homeassistant pytest-homeassistant-custom-component aiohttp aioresponses flake8
.venv/bin/pip freeze > requirements_dev.txt
```

Expected: all packages install cleanly. Record the HA version pulled in — it drives `hacs.json` minimum version.

- [ ] **Step 5: Create `hacs.json`**

```json
{
  "name": "Umweltbundesamt",
  "render_readme": true,
  "homeassistant": "2024.1.0",
  "content_in_root": false
}
```

- [ ] **Step 6: Create `custom_components/umweltbundesamt/manifest.json`**

```json
{
  "domain": "umweltbundesamt",
  "name": "Umweltbundesamt",
  "codeowners": [],
  "config_flow": true,
  "documentation": "https://github.com/borisgrushenko/ha-Umweltbundesamt",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/borisgrushenko/ha-Umweltbundesamt/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 7: Create `custom_components/umweltbundesamt/const.py`**

```python
"""Constants for the Umweltbundesamt integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "umweltbundesamt"
BASE_URL = "https://www.umweltbundesamt.de/api/air_data/v2"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=60)

CONF_STATION_ID = "station_id"
CONF_INCLUDE_AQI = "include_aqi"

DEFAULT_INCLUDE_AQI = True

# Air-quality index level (1..5) -> localized label keys. Resolved at sensor runtime.
AQI_LEVEL_KEYS = {
    1: "very_good",
    2: "good",
    3: "moderate",
    4: "poor",
    5: "very_poor",
}
```

- [ ] **Step 8: Create `custom_components/umweltbundesamt/__init__.py` stub**

```python
"""The Umweltbundesamt integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Umweltbundesamt from a config entry."""
    # Real setup wired up in Task 8.
    hass.data.setdefault(DOMAIN, {})
    return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

> Step 8 deliberately returns `False` so the stub can't produce a working entry; Task 8 replaces the body.

- [ ] **Step 9: Create `.github/workflows/hassfest.yaml`**

```yaml
name: Validate with hassfest

on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"

jobs:
  validate:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - uses: "home-assistant/actions/hassfest@master"
```

- [ ] **Step 10: Create `.github/workflows/hacs.yaml`**

```yaml
name: HACS Validation

on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"

jobs:
  validate:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - name: HACS validation
        uses: "hacs/action@main"
        with:
          category: "integration"
```

- [ ] **Step 11: Create `.github/workflows/release.yaml`**

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set version in manifest.json
        run: |
          python - <<'PY'
          import json, os, pathlib
          tag = os.environ["GITHUB_REF_NAME"].lstrip("v")
          path = pathlib.Path("custom_components/umweltbundesamt/manifest.json")
          data = json.loads(path.read_text())
          data["version"] = tag
          path.write_text(json.dumps(data, indent=2) + "\n")
          PY

      - name: Create release zip
        run: |
          cd custom_components/umweltbundesamt
          zip -r "$GITHUB_WORKSPACE/umweltbundesamt.zip" .

      - name: Attach zip to release
        uses: softprops/action-gh-release@v2
        with:
          files: umweltbundesamt.zip
```

- [ ] **Step 12: Create `README.md`**

```markdown
# Umweltbundesamt Home Assistant Integration

Home Assistant integration for the German Federal Environment Agency (Umweltbundesamt) air-quality API.

## Features

- Auto-picks the nearest active UBA measurement station (user-changeable in options).
- One sensor per pollutant the station reports (PM10, PM2.5, NO2, O3, SO2, CO, …).
- A 1–5 air-quality-index sensor with localized level labels.
- Hourly polling of the public UBA API (no authentication required).
- Long-term statistics via HA's `measurement` state class.

## Installation (HACS)

1. In HACS, add this repository as a custom repository of type **Integration**.
2. Install **Umweltbundesamt**, then restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → "Umweltbundesamt".

## Data source

Data is provided by the Umweltbundesamt under their open-data terms: <https://www.umweltbundesamt.de/daten/luft/luftdaten>.
```

- [ ] **Step 13: Create `tests/__init__.py`** (empty file)

- [ ] **Step 14: Create `tests/conftest.py`**

```python
"""Test fixtures for the Umweltbundesamt integration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture from tests/fixtures/."""
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield
```

- [ ] **Step 15: Verify flake8 passes**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output (exit 0).

- [ ] **Step 16: Commit**

```bash
git add .gitignore .flake8 hacs.json README.md .github custom_components tests requirements_dev.txt
git commit -m "chore: bootstrap project scaffolding and CI"
```

---

## Task 1: Domain models (`api/models.py`)

**Files:**
- Create: `custom_components/umweltbundesamt/api/__init__.py` (empty)
- Create: `custom_components/umweltbundesamt/api/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

`tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: custom_components.umweltbundesamt.api.models`.

- [ ] **Step 3: Create empty `api/__init__.py`**

```python
"""UBA API client package."""
```

- [ ] **Step 4: Implement `api/models.py`**

```python
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
    """An Umweltbundesamt measurement station."""

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
        """Return True if the station is measuring at the given moment."""
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_models.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 6: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add custom_components/umweltbundesamt/api tests/test_models.py
git commit -m "feat(api): add Station/Component/Measurement domain models"
```

---

## Task 2: API errors (`api/errors.py`)

**Files:**
- Create: `custom_components/umweltbundesamt/api/errors.py`

- [ ] **Step 1: Create `api/errors.py`**

```python
"""Exceptions raised by the Umweltbundesamt API client."""
from __future__ import annotations


class UBAError(Exception):
    """Base exception for UBA client errors."""


class UBAApiError(UBAError):
    """Raised when the API returns an error status or unexpected shape."""


class UBATimeoutError(UBAError):
    """Raised when the API does not respond in time."""
```

- [ ] **Step 2: flake8**

Run: `.venv/bin/python -m flake8 custom_components`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add custom_components/umweltbundesamt/api/errors.py
git commit -m "feat(api): add client exception hierarchy"
```

---

## Task 3: API client — metadata endpoints

**Files:**
- Create: `tests/fixtures/stations.json`, `tests/fixtures/components.json`
- Create: `custom_components/umweltbundesamt/api/client.py`
- Create: `tests/test_api_client.py`

- [ ] **Step 1: Create `tests/fixtures/components.json`**

```json
{
  "1": [1, "PM10", "PM\u2081\u2080", "\u00b5g/m\u00b3", "Feinstaub (PM\u2081\u2080)"],
  "5": [5, "NO2", "NO\u2082", "\u00b5g/m\u00b3", "Stickstoffdioxid"],
  "3": [3, "O3", "O\u2083", "\u00b5g/m\u00b3", "Ozon"]
}
```

> The UBA components endpoint returns a top-level object where each key is a component ID and the value is a positional array `[id, code, symbol, unit, name]`. We include a minimal realistic subset; expand only if tests require it.

- [ ] **Step 2: Create `tests/fixtures/stations.json`**

```json
{
  "282": [282, "DEBE010", "Wedding", "Berlin", "2000-01-01 00:00:00", null, "52.543", "13.349", "1", "2", "Hintergrund", "st\u00e4dtisch"],
  "1083": [1083, "DEBY072", "Marienplatz", "M\u00fcnchen", "2012-06-01 00:00:00", null, "48.137", "11.576", "1", "2", "Verkehr", "st\u00e4dtisch"],
  "999": [999, "DE_OLD", "Stillgelegt", "Nirgendwo", "1990-01-01 00:00:00", "2015-12-31 23:00:00", "50.0", "10.0", "1", "2", "Hintergrund", "l\u00e4ndlich"]
}
```

> Positional layout follows the UBA `/stations/json` response: `[id, code, name, city, active_from, active_to, lat, lng, network_id, station_setting_id, station_type, station_type_subcategory]`. This shape will be re-verified in Task 3 Step 8 (`client.py` parsing).

- [ ] **Step 3: Write failing tests**

`tests/test_api_client.py`:

```python
"""Tests for the UBAClient."""
from __future__ import annotations

import json
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
        2015, 12, 31, 23, 0, tzinfo=ZoneInfo("Europe/Berlin")
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v`
Expected: FAIL — `ModuleNotFoundError: custom_components.umweltbundesamt.api.client`.

- [ ] **Step 5: Implement minimal `api/client.py` for metadata**

```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 7: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 8: Quick live-API spot check (optional, human-verified)**

```bash
.venv/bin/python -c "
import asyncio, aiohttp, json
from custom_components.umweltbundesamt.api.client import UBAClient
async def main():
    async with aiohttp.ClientSession() as s:
        c = UBAClient(s)
        comps = await c.fetch_components()
        stns = await c.fetch_stations()
        print('components:', len(comps), 'example:', next(iter(comps.values())))
        print('stations:', len(stns), 'example:', stns[0])
asyncio.run(main())
"
```

Expected: prints a non-empty component and station. If the response shape differs from `tests/fixtures/*.json`, adjust the parser **and** the fixtures to match, re-run Step 6.

- [ ] **Step 9: Commit**

```bash
git add custom_components/umweltbundesamt/api/client.py tests/fixtures tests/test_api_client.py
git commit -m "feat(api): fetch_components and fetch_stations"
```

---

## Task 4: API client — air-quality endpoint

**Files:**
- Create: `tests/fixtures/airquality_full.json`, `tests/fixtures/airquality_incomplete.json`
- Modify: `custom_components/umweltbundesamt/api/client.py` (implement `fetch_current_airquality`)
- Modify: `tests/test_api_client.py`

- [ ] **Step 1: Create `tests/fixtures/airquality_full.json`**

```json
{
  "indices": {"start": "2026-04-19 10:00:00", "end": "2026-04-19 12:00:00"},
  "data": {
    "282": {
      "2026-04-19 12:00:00": [
        2,
        0,
        {"1": [18.5, 2, "2026-04-19", 12], "5": [22.1, 1, "2026-04-19", 12], "3": [80.0, 2, "2026-04-19", 12]}
      ],
      "2026-04-19 11:00:00": [
        1,
        0,
        {"1": [10.0, 1, "2026-04-19", 11], "5": [18.0, 1, "2026-04-19", 11]}
      ]
    }
  }
}
```

- [ ] **Step 2: Create `tests/fixtures/airquality_incomplete.json`**

```json
{
  "data": {
    "282": {
      "2026-04-19 12:00:00": [
        null,
        1,
        {"1": [null, null, "2026-04-19", 12], "5": [22.1, 1, "2026-04-19", 12]}
      ]
    }
  }
}
```

- [ ] **Step 3: Add failing tests**

Append to `tests/test_api_client.py`:

```python
@pytest.mark.asyncio
async def test_fetch_current_airquality_returns_newest_row():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        # Prime component metadata so the client can map IDs -> codes.
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            m.get(
                f"{BASE}/airquality/json",
                payload=load_fixture("airquality_full.json"),
                # match query params via partial matching
            )
            measurement = await client.fetch_current_airquality(282)
    assert measurement is not None
    assert measurement.station_id == 282
    assert measurement.index == 2
    assert measurement.timestamp == datetime(
        2026, 4, 19, 12, tzinfo=ZoneInfo("Europe/Berlin")
    )
    assert measurement.components["PM10"].value == pytest.approx(18.5)
    assert measurement.components["NO2"].value == pytest.approx(22.1)
    assert measurement.components["O3"].value == pytest.approx(80.0)


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
                f"{BASE}/airquality/json",
                payload=load_fixture("airquality_incomplete.json"),
            )
            measurement = await client.fetch_current_airquality(282)
    assert measurement is not None
    assert measurement.index is None
    assert measurement.components["PM10"].value is None
    assert measurement.components["NO2"].value == pytest.approx(22.1)


@pytest.mark.asyncio
async def test_fetch_current_airquality_returns_none_when_no_data():
    async with aiohttp.ClientSession() as session:
        client = UBAClient(session)
        with aioresponses() as m:
            m.get(
                f"{BASE}/components/json?lang=de&index=id",
                payload=load_fixture("components.json"),
            )
            m.get(f"{BASE}/airquality/json", payload={"data": {}})
            measurement = await client.fetch_current_airquality(282)
    assert measurement is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v -k airquality`
Expected: 3 tests FAIL with `NotImplementedError`.

- [ ] **Step 5: Replace `fetch_current_airquality` in `api/client.py`**

Delete the `raise NotImplementedError` body and replace with:

```python
    async def fetch_current_airquality(
        self, station_id: int
    ) -> Measurement | None:
        """Fetch the newest available air-quality row for `station_id`.

        We ask for a 2-day window (yesterday + today) at hours 1..24 so the
        caller is robust to UBA's ~60-90 minute publication lag.
        """
        components_by_id = await self.fetch_components()
        now = datetime.now(BERLIN_TZ)
        today = now.date()
        yesterday = (now - _ONE_DAY).date()
        params = {
            "station": station_id,
            "date_from": yesterday.isoformat(),
            "date_to": today.isoformat(),
            "time_from": 1,
            "time_to": 24,
            "lang": "de",
            "index": "id",
        }
        payload = await self._get_json("/airquality/json", params)
        if not isinstance(payload, dict):
            raise UBAApiError("airquality: unexpected payload shape")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise UBAApiError("airquality: missing 'data' key")
        station_rows = data.get(str(station_id)) or data.get(station_id)
        if not station_rows:
            return None

        newest_ts_str = max(station_rows.keys())
        row = station_rows[newest_ts_str]
        if not isinstance(row, list) or len(row) < 3:
            raise UBAApiError("airquality: unexpected row shape")
        index_raw, incomplete_raw, comp_map = row[0], row[1], row[2]
        if not isinstance(comp_map, dict):
            raise UBAApiError("airquality: unexpected components shape")

        from .models import ComponentReading

        components: dict[str, ComponentReading] = {}
        for comp_id_raw, reading in comp_map.items():
            if not isinstance(reading, list) or len(reading) < 2:
                continue
            try:
                comp_id = int(comp_id_raw)
            except (TypeError, ValueError):
                continue
            component = components_by_id.get(comp_id)
            if component is None:
                continue
            raw_value = reading[0]
            value = float(raw_value) if raw_value is not None else None
            class_raw = reading[1]
            class_index = int(class_raw) if class_raw is not None else None
            components[component.code] = ComponentReading(
                value=value,
                unit=component.unit,
                class_index=class_index,
            )

        index = int(index_raw) if index_raw is not None else None
        if incomplete_raw:
            # UBA publishes a per-row "incomplete" flag — we preserve the
            # per-component values but blank the overall index.
            index = None

        return Measurement(
            station_id=station_id,
            timestamp=_parse_uba_datetime(newest_ts_str),
            index=index,
            components=components,
        )
```

Also add at module top (next to the other imports):

```python
from datetime import timedelta

_ONE_DAY = timedelta(days=1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_client.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 7: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add custom_components/umweltbundesamt/api/client.py tests/fixtures tests/test_api_client.py
git commit -m "feat(api): fetch_current_airquality with newest-row selection"
```

---

## Task 5: DataUpdateCoordinator (`coordinator.py`)

**Files:**
- Create: `custom_components/umweltbundesamt/coordinator.py`
- Create: `tests/test_coordinator.py`

- [ ] **Step 1: Write failing tests**

`tests/test_coordinator.py`:

```python
"""Tests for UBADataUpdateCoordinator."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.umweltbundesamt.api.errors import UBAApiError
from custom_components.umweltbundesamt.api.models import (
    ComponentReading,
    Measurement,
)
from custom_components.umweltbundesamt.coordinator import (
    UBADataUpdateCoordinator,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _make_measurement() -> Measurement:
    return Measurement(
        station_id=282,
        timestamp=datetime(2026, 4, 19, 12, tzinfo=BERLIN),
        index=2,
        components={"PM10": ComponentReading(18.5, "µg/m³", 2)},
    )


@pytest.mark.asyncio
async def test_coordinator_caches_measurement_on_success(hass):
    client = AsyncMock()
    client.fetch_current_airquality.return_value = _make_measurement()
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    data = await coord._async_update_data()
    assert data.index == 2
    assert data.components["PM10"].value == pytest.approx(18.5)
    client.fetch_current_airquality.assert_awaited_once_with(282)


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_on_api_error(hass):
    client = AsyncMock()
    client.fetch_current_airquality.side_effect = UBAApiError("boom")
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_update_failed_when_no_rows(hass):
    client = AsyncMock()
    client.fetch_current_airquality.return_value = None
    coord = UBADataUpdateCoordinator(hass, client, station_id=282)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_coordinator.py -v`
Expected: FAIL — coordinator module not found.

- [ ] **Step 3: Implement `coordinator.py`**

```python
"""DataUpdateCoordinator for the Umweltbundesamt integration."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api.client import UBAClient
from .api.errors import UBAError
from .api.models import Measurement
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class UBADataUpdateCoordinator(DataUpdateCoordinator[Measurement]):
    """Polls the UBA air-quality endpoint for a single station."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: UBAClient,
        station_id: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_station_{station_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._client = client
        self.station_id = station_id

    async def _async_update_data(self) -> Measurement:
        try:
            measurement = await self._client.fetch_current_airquality(
                self.station_id
            )
        except UBAError as err:
            raise UpdateFailed(str(err)) from err
        if measurement is None:
            raise UpdateFailed(
                f"No air-quality data available for station {self.station_id}"
            )
        return measurement
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_coordinator.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add custom_components/umweltbundesamt/coordinator.py tests/test_coordinator.py
git commit -m "feat: add UBADataUpdateCoordinator with UpdateFailed mapping"
```

---

## Task 6: Integration setup/unload (`__init__.py`)

**Files:**
- Modify: `custom_components/umweltbundesamt/__init__.py`

- [ ] **Step 1: Replace file contents**

```python
"""The Umweltbundesamt integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import UBAClient
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import UBADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Umweltbundesamt from a config entry."""
    station_id = int(entry.data[CONF_STATION_ID])
    session = async_get_clientsession(hass)
    client = UBAClient(session)
    # Prime component metadata once so sensor setup and polls can both use it.
    await client.fetch_components()
    coordinator = UBADataUpdateCoordinator(hass, client, station_id)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 2: flake8**

Run: `.venv/bin/python -m flake8 custom_components`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add custom_components/umweltbundesamt/__init__.py
git commit -m "feat: wire async_setup_entry via UBAClient and coordinator"
```

---

## Task 7: Config flow (`config_flow.py`) — initial setup

**Files:**
- Create: `custom_components/umweltbundesamt/config_flow.py`
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

`tests/test_config_flow.py`:

```python
"""Tests for the Umweltbundesamt config flow."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.umweltbundesamt.api.errors import UBAApiError
from custom_components.umweltbundesamt.api.models import Station
from custom_components.umweltbundesamt.const import (
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DOMAIN,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _sample_stations() -> list[Station]:
    now_active = datetime(2000, 1, 1, tzinfo=BERLIN)
    return [
        Station(
            id=282, code="DEBE010", name="Wedding", city="Berlin",
            latitude=52.543, longitude=13.349,
            station_type="Hintergrund städtisch", network_code="1",
            active_from=now_active, active_to=None,
        ),
        Station(
            id=1083, code="DEBY072", name="Marienplatz", city="München",
            latitude=48.137, longitude=11.576,
            station_type="Verkehr städtisch", network_code="1",
            active_from=now_active, active_to=None,
        ),
        Station(
            id=999, code="DE_OLD", name="Stillgelegt", city="Nirgendwo",
            latitude=50.0, longitude=10.0,
            station_type="Hintergrund ländlich", network_code="1",
            active_from=now_active,
            active_to=datetime(2015, 12, 31, tzinfo=BERLIN),
        ),
    ]


@pytest.fixture(autouse=True)
def _set_home_coords(hass: HomeAssistant):
    hass.config.latitude = 52.5
    hass.config.longitude = 13.4
    yield


@pytest.mark.asyncio
async def test_user_flow_preselects_nearest_and_creates_entry(
    hass: HomeAssistant,
):
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"
        # The default in the schema should be the nearest (Berlin, id=282).
        schema = result["data_schema"].schema
        station_key = next(
            k for k in schema if getattr(k, "schema", None) == CONF_STATION_ID
        )
        assert station_key.default() == 282

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_STATION_ID: 1083, CONF_INCLUDE_AQI: True},
        )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STATION_ID] == 1083
    assert result["options"][CONF_INCLUDE_AQI] is True


@pytest.mark.asyncio
async def test_user_flow_cannot_connect(hass: HomeAssistant):
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            side_effect=UBAApiError("down")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.asyncio
async def test_user_flow_no_active_stations(hass: HomeAssistant):
    expired = Station(
        id=1, code="X", name="X", city="X",
        latitude=0.0, longitude=0.0, station_type="", network_code="",
        active_from=datetime(1990, 1, 1, tzinfo=BERLIN),
        active_to=datetime(2000, 1, 1, tzinfo=BERLIN),
    )
    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=[expired]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_active_stations"


@pytest.mark.asyncio
async def test_user_flow_rejects_duplicate_station(hass: HomeAssistant):
    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)", data={CONF_STATION_ID: 282},
        source=config_entries.SOURCE_USER, options={}, unique_id="282",
        discovery_keys={},
    )
    hass.config_entries._entries[entry.entry_id] = entry

    with patch(
        "custom_components.umweltbundesamt.config_flow.UBAClient"
    ) as client_cls:
        client_cls.return_value.fetch_stations = AsyncMock(
            return_value=_sample_stations()
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_STATION_ID: 282, CONF_INCLUDE_AQI: True},
        )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
```

> The duplicate-rejection test manipulates `hass.config_entries._entries` directly because the pytest fixture doesn't expose a clean "add a fake entry" helper. If HA's API makes `async_add` public, prefer it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config_flow.py -v`
Expected: FAIL — `custom_components.umweltbundesamt.config_flow` doesn't exist.

- [ ] **Step 3: Implement `config_flow.py`**

```python
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
)

_LOGGER = logging.getLogger(__name__)
BERLIN_TZ = ZoneInfo("Europe/Berlin")


class UBAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the user-initiated config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        session = async_get_clientsession(self.hass)
        client = UBAClient(session)
        try:
            stations = await client.fetch_stations()
        except UBAError as err:
            _LOGGER.warning("UBA station fetch failed: %s", err)
            return self.async_abort(reason="cannot_connect")

        active = [s for s in stations if s.is_active(datetime.now(BERLIN_TZ))]
        if not active:
            return self.async_abort(reason="no_active_stations")

        home_lat = self.hass.config.latitude
        home_lon = self.hass.config.longitude
        active.sort(key=lambda s: s.distance_km(home_lat, home_lon))
        nearest = active[0]

        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_STATION_ID]))
            self._abort_if_unique_id_configured()
            picked = next(
                (s for s in active if s.id == user_input[CONF_STATION_ID]),
                nearest,
            )
            return self.async_create_entry(
                title=f"{picked.name} ({picked.city})",
                data={CONF_STATION_ID: picked.id},
                options={CONF_INCLUDE_AQI: user_input.get(
                    CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI
                )},
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
        return UBAOptionsFlow(entry)


class UBAOptionsFlow(config_entries.OptionsFlow):
    """Options flow — change station, toggle AQI sensor."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        session = async_get_clientsession(self.hass)
        client = UBAClient(session)
        try:
            stations = await client.fetch_stations()
        except UBAError as err:
            _LOGGER.warning("UBA station fetch failed: %s", err)
            return self.async_abort(reason="cannot_connect")
        active = [s for s in stations if s.is_active(datetime.now(BERLIN_TZ))]
        if not active:
            return self.async_abort(reason="no_active_stations")

        if user_input is not None:
            new_station_id = int(user_input[CONF_STATION_ID])
            include_aqi = bool(
                user_input.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)
            )
            if new_station_id != self._entry.data[CONF_STATION_ID]:
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={**self._entry.data, CONF_STATION_ID: new_station_id},
                    unique_id=str(new_station_id),
                )
            return self.async_create_entry(
                title="",
                data={CONF_INCLUDE_AQI: include_aqi},
            )

        current_id = int(self._entry.data[CONF_STATION_ID])
        include_aqi = bool(
            self._entry.options.get(CONF_INCLUDE_AQI, DEFAULT_INCLUDE_AQI)
        )
        schema = _build_station_schema(
            active,
            self.hass.config.latitude,
            self.hass.config.longitude,
            default_id=current_id,
            default_include_aqi=include_aqi,
        )
        return self.async_show_form(step_id="init", data_schema=schema)


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

    return vol.Schema(
        {
            vol.Required(
                CONF_STATION_ID, default=default_id
            ): vol.All(
                SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                        custom_value=False,
                    )
                ),
                _coerce_station_id,
            ),
            vol.Required(
                CONF_INCLUDE_AQI, default=default_include_aqi
            ): bool,
        }
    )


def _coerce_station_id(value: Any) -> int:
    """Selectors return strings; config entries need ints."""
    return int(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config_flow.py -v`
Expected: all 4 tests PASS.

> If the duplicate-rejection test fails because `ConfigEntry(...)` signature changed in the installed HA version, adapt the constructor arguments (HA 2024.11+ added `discovery_keys` / `subentries_data`). The intent of the test — verifying `_abort_if_unique_id_configured()` — must be preserved.

- [ ] **Step 5: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add custom_components/umweltbundesamt/config_flow.py tests/test_config_flow.py
git commit -m "feat: config + options flow with nearest-station pre-selection"
```

---

## Task 8: Sensor platform (`sensor.py`)

**Files:**
- Create: `custom_components/umweltbundesamt/sensor.py`
- Create: `tests/test_sensor.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sensor.py`:

```python
"""Tests for the Umweltbundesamt sensor platform."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant

from custom_components.umweltbundesamt.api.models import (
    ComponentReading,
    Measurement,
    Station,
)
from custom_components.umweltbundesamt.const import (
    CONF_INCLUDE_AQI,
    CONF_STATION_ID,
    DOMAIN,
)


BERLIN = ZoneInfo("Europe/Berlin")


def _station() -> Station:
    return Station(
        id=282, code="DEBE010", name="Wedding", city="Berlin",
        latitude=52.543, longitude=13.349,
        station_type="Hintergrund städtisch", network_code="1",
        active_from=datetime(2000, 1, 1, tzinfo=BERLIN), active_to=None,
    )


def _measurement() -> Measurement:
    return Measurement(
        station_id=282,
        timestamp=datetime(2026, 4, 19, 12, tzinfo=BERLIN),
        index=2,
        components={
            "PM10": ComponentReading(18.5, "µg/m³", 2),
            "NO2": ComponentReading(22.1, "µg/m³", 1),
        },
    )


async def _install_entry(hass: HomeAssistant) -> str:
    """Mock out the API, register a config entry, return entry_id."""
    client = MagicMock()
    client.fetch_components = AsyncMock(
        return_value={
            1: MagicMock(id=1, code="PM10", unit="µg/m³",
                         name="Feinstaub (PM10)"),
            5: MagicMock(id=5, code="NO2", unit="µg/m³",
                         name="Stickstoffdioxid"),
        }
    )
    client.fetch_stations = AsyncMock(return_value=[_station()])
    client.fetch_current_airquality = AsyncMock(return_value=_measurement())

    from homeassistant import config_entries

    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)",
        data={CONF_STATION_ID: 282},
        options={CONF_INCLUDE_AQI: True},
        source=config_entries.SOURCE_USER, unique_id="282",
        discovery_keys={},
    )
    hass.config_entries._entries[entry.entry_id] = entry

    with patch(
        "custom_components.umweltbundesamt.UBAClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.entry_id


@pytest.mark.asyncio
async def test_sensors_created_for_each_component(hass: HomeAssistant):
    await _install_entry(hass)
    pm10 = hass.states.get("sensor.wedding_berlin_feinstaub_pm10")
    assert pm10 is not None
    assert float(pm10.state) == pytest.approx(18.5)
    assert pm10.attributes["unit_of_measurement"] == "µg/m³"
    assert pm10.attributes["device_class"] == SensorDeviceClass.PM10
    assert pm10.attributes["state_class"] == SensorStateClass.MEASUREMENT


@pytest.mark.asyncio
async def test_aqi_sensor_has_level_text_attribute(hass: HomeAssistant):
    await _install_entry(hass)
    aqi = hass.states.get("sensor.wedding_berlin_air_quality_index")
    assert aqi is not None
    assert int(aqi.state) == 2
    assert aqi.attributes["level_text"] in ("good", "Gut", "Good")
    assert "measurement_time" in aqi.attributes


@pytest.mark.asyncio
async def test_aqi_sensor_disabled_when_option_off(hass: HomeAssistant):
    from homeassistant import config_entries

    client = MagicMock()
    client.fetch_components = AsyncMock(
        return_value={1: MagicMock(id=1, code="PM10", unit="µg/m³",
                                   name="Feinstaub (PM10)")}
    )
    client.fetch_stations = AsyncMock(return_value=[_station()])
    client.fetch_current_airquality = AsyncMock(return_value=_measurement())

    entry = config_entries.ConfigEntry(
        version=1, minor_version=1, domain=DOMAIN,
        title="Wedding (Berlin)",
        data={CONF_STATION_ID: 282},
        options={CONF_INCLUDE_AQI: False},
        source=config_entries.SOURCE_USER, unique_id="282",
        discovery_keys={},
    )
    hass.config_entries._entries[entry.entry_id] = entry
    with patch(
        "custom_components.umweltbundesamt.UBAClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("sensor.wedding_berlin_air_quality_index") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sensor.py -v`
Expected: FAIL — sensor module missing / entities not created.

- [ ] **Step 3: Implement `sensor.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sensor.py -v`
Expected: all 3 tests PASS. If HA's slugification produces a different `entity_id`, adjust the `hass.states.get(...)` string to match actual output; the assertions on state/attributes are what matters.

- [ ] **Step 5: flake8**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add custom_components/umweltbundesamt/sensor.py tests/test_sensor.py
git commit -m "feat: sensor platform with per-component + AQI entities"
```

---

## Task 9: Translations (`strings.json` + `translations/de.json`)

**Files:**
- Create: `custom_components/umweltbundesamt/strings.json`
- Create: `custom_components/umweltbundesamt/translations/de.json`

- [ ] **Step 1: Create `strings.json`** (canonical English)

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Umweltbundesamt",
        "description": "Pick the UBA station to monitor. The closest active station to your Home Assistant home location is pre-selected.",
        "data": {
          "station_id": "Measurement station",
          "include_aqi": "Include air-quality index sensor"
        }
      }
    },
    "abort": {
      "already_configured": "This station is already configured.",
      "cannot_connect": "Could not reach the Umweltbundesamt API. Try again later.",
      "no_active_stations": "The Umweltbundesamt API returned no active stations."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Umweltbundesamt options",
        "description": "Change the monitored station or toggle the air-quality index sensor.",
        "data": {
          "station_id": "Measurement station",
          "include_aqi": "Include air-quality index sensor"
        }
      }
    },
    "abort": {
      "cannot_connect": "Could not reach the Umweltbundesamt API. Try again later.",
      "no_active_stations": "The Umweltbundesamt API returned no active stations."
    }
  },
  "entity": {
    "sensor": {
      "air_quality_index": {
        "name": "Air quality index",
        "state_attributes": {
          "level_text": {
            "state": {
              "very_good": "Very good",
              "good": "Good",
              "moderate": "Moderate",
              "poor": "Poor",
              "very_poor": "Very poor"
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Create `translations/de.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Umweltbundesamt",
        "description": "Wählen Sie die UBA-Messstation. Die nächstgelegene aktive Station zu Ihrem Home-Assistant-Standort ist vorausgewählt.",
        "data": {
          "station_id": "Messstation",
          "include_aqi": "Luftqualitätsindex-Sensor hinzufügen"
        }
      }
    },
    "abort": {
      "already_configured": "Diese Station ist bereits konfiguriert.",
      "cannot_connect": "Die Umweltbundesamt-API ist nicht erreichbar. Bitte später erneut versuchen.",
      "no_active_stations": "Die Umweltbundesamt-API hat keine aktiven Stationen zurückgegeben."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Umweltbundesamt-Optionen",
        "description": "Messstation ändern oder Luftqualitätsindex-Sensor umschalten.",
        "data": {
          "station_id": "Messstation",
          "include_aqi": "Luftqualitätsindex-Sensor hinzufügen"
        }
      }
    },
    "abort": {
      "cannot_connect": "Die Umweltbundesamt-API ist nicht erreichbar. Bitte später erneut versuchen.",
      "no_active_stations": "Die Umweltbundesamt-API hat keine aktiven Stationen zurückgegeben."
    }
  },
  "entity": {
    "sensor": {
      "air_quality_index": {
        "name": "Luftqualitätsindex",
        "state_attributes": {
          "level_text": {
            "state": {
              "very_good": "Sehr gut",
              "good": "Gut",
              "moderate": "Mäßig",
              "poor": "Schlecht",
              "very_poor": "Sehr schlecht"
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add custom_components/umweltbundesamt/strings.json custom_components/umweltbundesamt/translations
git commit -m "feat: EN strings + DE translation"
```

---

## Task 10: Final verification & README polish

**Files:**
- Modify: `README.md` (add entities section)
- Modify: `CLAUDE.md` (update path reference to lowercase)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests -v`
Expected: every test passes, zero skips from our suite.

- [ ] **Step 2: Run flake8 on the whole project**

Run: `.venv/bin/python -m flake8 custom_components tests`
Expected: no output.

- [ ] **Step 3: Install into a local HA dev instance and manually verify**

```bash
# If the user has a HA dev container or dev installation:
ln -sf "$(pwd)/custom_components/umweltbundesamt" \
  ~/.homeassistant/custom_components/umweltbundesamt
# Restart HA, add the integration via UI, confirm sensors appear,
# change the station via options, confirm reload works.
```

If no dev HA is available, document the manual steps in the PR description instead of running them.

- [ ] **Step 4: Update `CLAUDE.md`**

Replace references to `custom_components/Umweltbundesamt/` with `custom_components/umweltbundesamt/` so the release-workflow description matches reality. Update the release zip name to `umweltbundesamt.zip` as well.

- [ ] **Step 5: Expand `README.md` with the entity list**

Append before the "Data source" section:

```markdown
## Entities

For a station with UBA code `DEBE010` (Berlin Wedding) the integration creates:

| Entity | Description |
|---|---|
| `sensor.wedding_berlin_feinstaub_pm10` | PM10 (µg/m³), `device_class: pm10` |
| `sensor.wedding_berlin_stickstoffdioxid` | NO₂ (µg/m³), `device_class: nitrogen_dioxide` |
| `sensor.wedding_berlin_ozon` | O₃ (µg/m³), `device_class: ozone` |
| `sensor.wedding_berlin_air_quality_index` | Overall index 1–5 with `level_text` attribute |

The exact entity set depends on which components the chosen station reports.
```

- [ ] **Step 6: Commit docs**

```bash
git add README.md CLAUDE.md
git commit -m "docs: entity list, CLAUDE.md path correction"
```

- [ ] **Step 7: Push initial branch and open a PR**

```bash
git remote -v
# If no remote yet, the user will add one; otherwise:
git push -u origin main
```

(If this is the first push, leave the remote setup to the user — do not invent URLs.)

---

## Self-review notes (author-run)

- **Spec coverage** — every spec section maps to a task: API client + errors (Tasks 1–4), coordinator (Task 5), entry setup (Task 6), config + options flow with nearest-station selection (Task 7), device + dynamic per-component sensors + AQI sensor (Task 8), EN/DE translations (Task 9), validation + release plumbing (Tasks 0, 10). The spec's note that changing stations leaves orphan registry entries is acknowledged via the `async_update_entry` + `async_reload_entry` flow in Tasks 6–7; automatic cleanup remains explicitly out of scope.
- **Placeholder scan** — no `TBD`/`TODO` markers left in steps. Every step that introduces code includes the full code body. The Task 3 Step 8 "live-API spot check" is marked as optional because it depends on live network; it exists specifically to surface any fixture drift and route back to Step 6.
- **Type consistency** — `Station`, `Component`, `ComponentReading`, `Measurement` are defined once in Task 1 and every subsequent usage matches their signatures (`distance_km(lat, lon) -> float`, `Measurement.components: dict[str, ComponentReading]`, etc.). `UBAClient` exposes the three method names quoted in the spec: `fetch_stations`, `fetch_components`, `fetch_current_airquality`.
