# Umweltbundesamt Home Assistant Integration — Design

**Date:** 2026-04-19
**Status:** Approved, pending implementation plan
**Source API:** `https://www.umweltbundesamt.de/api/air_data/v2` (documented at https://luftqualitaet.api.bund.dev/)

## Goal

Ship a HACS-installable Home Assistant custom integration that surfaces German Umweltbundesamt (UBA) air-quality measurements as HA sensors. Users see per-pollutant values and the overall air-quality index for a nearby UBA measurement station, updated hourly.

## Scope

**In scope**

- Config-flow setup with auto-picked nearest station (user-changeable).
- Dynamic sensor creation: one sensor per component the station reports, plus one overall air-quality-index sensor.
- Hourly polling of the public UBA v2 API.
- Options flow to change the selected station after setup.
- English + German UI strings.

**Out of scope (for this spec)**

- Multi-station aggregation in a single entry (users add the integration multiple times for more stations).
- Historical statistics beyond what HA's long-term statistics already provides from `MEASUREMENT` state class.
- Exceedance (`/transgressions/json`) and annual-balance endpoints.
- Map/geographic visualisations.

## API reference (as of 2026-04-19)

- **Base URL:** `https://www.umweltbundesamt.de/api/air_data/v2`
- **Auth:** none.
- **Relevant endpoints:**
  - `GET /stations/json?lang=de&index=id` — full station list with coordinates, activity dates, network.
  - `GET /components/json?lang=de` — component metadata (code, symbol, unit, localized name).
  - `GET /airquality/json?station=<id>&date_from=&time_from=&date_to=&time_to=` — hourly air-quality data including the 1–5 index and per-component values.
- **Status codes:** `200` OK; `422` on missing required params.

The `/airquality/json` response is keyed by station then datetime; each datetime row carries `[indexLevel, incomplete, {componentId: [value, classIdx, ymd, hour]}]`. The client normalises this into a flat record.

> Implementation note: the exact station-list endpoint path/shape will be verified against the live API during the first implementation task. If `/stations/json` isn't present, fall back to `/meta/json?use=airquality` which also returns stations.

## Architecture

Standard Home Assistant integration pattern: **config entry → DataUpdateCoordinator → sensor platform**, with a thin domain layer under `api/` that isolates UBA-specific HTTP/parsing from HA concerns.

```
custom_components/Umweltbundesamt/
├── __init__.py            # async_setup_entry / async_unload_entry, forward to sensor
├── manifest.json          # domain, version, requirements, codeowners, iot_class=cloud_polling
├── const.py               # DOMAIN, BASE_URL, DEFAULT_SCAN_INTERVAL, level labels
├── config_flow.py         # ConfigFlow + OptionsFlow
├── coordinator.py         # UBADataUpdateCoordinator (hourly)
├── sensor.py              # dynamic sensor creation
├── strings.json           # canonical EN source (HA convention)
├── translations/
│   └── de.json            # German translation (EN is served from strings.json)
└── api/
    ├── __init__.py        # re-exports public symbols
    ├── client.py          # async aiohttp client
    ├── models.py          # Station, Component, Measurement dataclasses
    └── errors.py          # UBAApiError, UBATimeoutError
```

### Module boundaries

- **`api/client.py`** — Pure HTTP + parsing. Knows nothing about HA. Takes an `aiohttp.ClientSession`. Exposes:
  - `async fetch_stations() -> list[Station]`
  - `async fetch_components() -> dict[int, Component]`
  - `async fetch_current_airquality(station_id: int) -> Measurement | None`
  Raises `UBAApiError` / `UBATimeoutError`. Swappable in tests.
- **`coordinator.py`** — `DataUpdateCoordinator[Measurement]`. Calls the client, handles retry/translation to `UpdateFailed`, holds the cached component metadata.
- **`config_flow.py`** — HA-aware. Uses `api.client` to build the station dropdown, and `HomeAssistant.config.latitude/longitude` to pre-select the nearest active station.
- **`sensor.py`** — HA-aware. Builds entities from the first coordinator refresh; each entity only reads from `coordinator.data`.

Each file has a single responsibility and can be tested in isolation.

## User experience

### Installation

1. Add this repository to HACS (custom repository → integration), install, restart HA.
2. Settings → Devices & Services → Add Integration → "Umweltbundesamt".

### Config flow (single step)

- On entry, the flow calls `client.fetch_stations()` and filters to currently-active stations (no end date, or end date in the future).
- Computes Haversine distance from HA's configured home coordinates to each active station; the nearest is pre-selected.
- Presents a single selector:
  - **Station** (searchable dropdown): `"{code} — {name}, {city} ({distance_km:.0f} km)"`
- `unique_id` = station ID; prevents duplicate entries for the same station.
- Errors: `cannot_connect` (API unreachable), `no_active_stations` (empty list after filtering).

### Options flow

- Same station dropdown (no distance computation needed; pre-selected = current).
- Toggle: **Include air-quality index sensor** (default: on).
- Changing the station triggers a reload so entities re-register with new `unique_id`s.

### Device & entities

- One `DeviceInfo` per config entry, representing the station:
  - `identifiers = {(DOMAIN, str(station_id))}`
  - `name = "{station_name} ({station_city})"`
  - `manufacturer = "Umweltbundesamt"`
  - `model = station_type` (e.g. "Hintergrund städtisch")
  - `configuration_url = f"https://www.umweltbundesamt.de/daten/luft/luftdaten/stationen?lat={lat}&lng={lng}"`
- Per-component sensors:
  - `unique_id = f"uba_{station_id}_{component_code_lower}"` (e.g. `uba_282_pm10`).
  - `name = component.localized_name` (e.g. "Feinstaub (PM10)").
  - `native_unit_of_measurement` from component metadata (µg/m³ or mg/m³).
  - `device_class` mapped from component code: PM10/PM25→`PM10`/`PM25`, NO2→`NITROGEN_DIOXIDE`, O3→`OZONE`, SO2→`SULPHUR_DIOXIDE`, CO→`CO`. Unknown → no device class.
  - `state_class = MEASUREMENT` to enable HA long-term statistics.
- Air-quality-index sensor (when enabled):
  - `unique_id = f"uba_{station_id}_aqi"`.
  - State: integer `1..5` (or `None` when missing / flagged `incomplete`).
  - Attributes: `level_text` (localized: "Sehr gut"/"Very good" … "Sehr schlecht"/"Very bad"), `measurement_time` (ISO datetime), `station_code`, `station_city`.
  - No `device_class` (HA has no generic AQI device class suitable for this 1–5 scheme).

## Data flow

1. **Setup** (`async_setup_entry`):
   - Build shared `UBAClient` using HA's `async_get_clientsession`.
   - Fetch `/stations/json` + `/components/json` once; cache on the client instance.
   - Create `UBADataUpdateCoordinator(station_id, include_aqi)`, run `async_config_entry_first_refresh()`.
   - Forward to `sensor` platform; `sensor.async_setup_entry` builds entities from `coordinator.data.components.keys()`.
2. **Poll** (every 60 min with small jitter):
   - Call `/airquality/json` with `date_from/to = today & yesterday`, `time_from/to = 1..24`, to guarantee the window covers the latest published hour regardless of timezone edge cases.
   - Pick the newest row; normalise into `Measurement(timestamp, index, components={code: (value, unit, class_idx)})`.
   - `timestamp` is parsed from the row's `ymd + hour` fields; UBA publishes in Europe/Berlin local time, so the client attaches that tzinfo (via `zoneinfo.ZoneInfo("Europe/Berlin")`) and HA formats it to the user's locale as needed.
   - On parse/HTTP failure, raise `UpdateFailed`; HA marks entities unavailable until next successful poll.
3. **Station change via options**:
   - `async_reload_entry` tears down the coordinator + entities and rebuilds with the new station ID. Because `unique_id` and `DeviceInfo.identifiers` are station-scoped, the old device/entities are left as orphans in the HA registry (user can delete them from the UI). This is acceptable for an infrequent action; automatic cleanup is out of scope for v0.1.

## Error handling

| Failure | Behaviour |
|---|---|
| Network error during config flow | Show `cannot_connect` error, keep form open. |
| Station list empty or no active stations | Show `no_active_stations` abort. |
| Network / 5xx during poll | `UpdateFailed` → entities go unavailable, coordinator retries next interval. |
| `incomplete=1` or null values in a row | Return `None` for that component's value; sensor reports `unknown`. |
| API schema drift (unexpected shape) | `UBAApiError("unexpected response")`, `UpdateFailed`. Logged at `warning`. |

## Testing

All tests run without network access.

- **API client** (`tests/test_client.py`): `aioresponses` fixtures for station list, component list, and at least two `/airquality/json` shapes (fully populated / partially incomplete). Verifies parsing into models, timestamp handling, and error mapping.
- **Coordinator** (`tests/test_coordinator.py`): injects a fake client; asserts `UpdateFailed` on client errors, data cached on success.
- **Config flow** (`tests/test_config_flow.py`, `pytest-homeassistant-custom-component`): happy path (nearest pre-selected, entry created); `cannot_connect`; `no_active_stations`; duplicate station rejected; options flow changes station and triggers reload.
- **Sensors** (`tests/test_sensor.py`): entity creation given a fixture coordinator state; state, unit, device class, attributes for AQI sensor; entities go `unavailable` on `UpdateFailed`.

## Validation & release

- **flake8:** `.venv/bin/python -m flake8 custom_components` (uses existing `.flake8`, `max-line-length=120`).
- **hassfest + HACS action:** relies on existing CI workflows (`hassfest.yaml`, HACS validation). Project CLAUDE.md confirms these are already wired up.
- **Release:** creating a GitHub release triggers `.github/workflows/release.yml`, which rewrites `manifest.json`'s version to the tag and packages `custom_components/Umweltbundesamt/` into `Umweltbundesamt.zip`.
- **Initial version:** `0.1.0` (advisory; release tag is authoritative).

## Risks & open questions

- **Station-list endpoint shape** — verify on first implementation task (see API reference note). Affects `fetch_stations()` only.
- **Hourly publish lag** — UBA typically publishes ~60–90 min after the hour. Our 60-minute scan interval may momentarily return the same record; acceptable (no extra entity churn). If user complaints arise, add small post-:30 offset.
- **Index vs. per-component timestamps** — the index is computed from components at the same hour; we use a single `measurement_time` taken from the row. No separate per-component timestamp attribute.
- **Naming of German pollutant labels** — we use `component.localized_name` from the API, which is authoritative. HA device-class localization will override the sensor display name automatically for common pollutants; that's the intended behaviour.
