<div align="center">

<img src="custom_components/umweltbundesamt/brand/icon.png" alt="" width="128" height="128" />

# Umweltbundesamt for Home Assistant

Air-quality sensors from the German Federal Environment Agency's open-data API, straight in your Home Assistant dashboard.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=flat-square)](https://hacs.xyz/)
[![Release](https://img.shields.io/github/v/release/borisgrushenko/ha-Umweltbundesamt?style=flat-square)](https://github.com/borisgrushenko/ha-Umweltbundesamt/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.1%2B-03A9F4.svg?style=flat-square&logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![Quality Scale](https://img.shields.io/badge/quality%20scale-bronze-CD7F32.svg?style=flat-square)](https://developers.home-assistant.io/docs/integration_quality_scale/)
[![Hassfest](https://img.shields.io/github/actions/workflow/status/borisgrushenko/ha-Umweltbundesamt/hassfest.yaml?style=flat-square&label=hassfest)](https://github.com/borisgrushenko/ha-Umweltbundesamt/actions/workflows/hassfest.yaml)
[![HACS Validation](https://img.shields.io/github/actions/workflow/status/borisgrushenko/ha-Umweltbundesamt/hacs.yaml?style=flat-square&label=HACS%20validation)](https://github.com/borisgrushenko/ha-Umweltbundesamt/actions/workflows/hacs.yaml)

</div>

---

## Overview

The **Umweltbundesamt** (UBA) is Germany's Federal Environment Agency. It publishes hourly air-quality measurements from ~2 300 monitoring stations across Germany via a free, unauthenticated open-data API. This integration turns those measurements into first-class Home Assistant sensors — one device per station, one sensor per pollutant, plus an overall 1–5 air-quality index.

## Features

| | |
|---|---|
| **Auto-locate** | Picks the closest active UBA station using your HA home coordinates. Override any time via the options flow. |
| **Dynamic sensors** | One `SensorEntity` per pollutant the chosen station actually publishes — PM10, PM2.5, NO₂, O₃, SO₂, CO, and others as they appear. |
| **Air-quality index** | Dedicated `SensorDeviceClass.AQI` entity (1–5 scale) for a single "how healthy is the air" number. |
| **Long-term statistics** | Per-pollutant sensors use `state_class: measurement`; HA records statistics automatically for charting and energy-style dashboards. |
| **Bilingual** | English and German UI strings, with localized pollutant labels from the UBA API. |
| **Hourly polling** | Matches the UBA publishing cadence — one request per hour, no authentication, no API key. |
| **Zero setup cost** | `requirements: []` in the manifest — uses only libraries that ship with HA. |

## Installation

> [!TIP]
> This integration is not yet in the HACS default list. Add it as a **custom repository** of type **Integration** first; once it lands in the default list, this extra step will go away.

### Via HACS

1. In Home Assistant, open **HACS → ⋮ (top right) → Custom repositories**.
2. Paste `https://github.com/borisgrushenko/ha-Umweltbundesamt` and pick **Integration** as the category.
3. Open the newly-listed **Umweltbundesamt** entry and click **Download**.
4. Restart Home Assistant.
5. **Settings → Devices & Services → Add Integration → Umweltbundesamt**.

### Manual (without HACS)

<details>
<summary>Expand manual installation steps</summary>

1. Download the latest `umweltbundesamt.zip` from the [releases page](https://github.com/borisgrushenko/ha-Umweltbundesamt/releases).
2. Unzip into `<config>/custom_components/umweltbundesamt/` so that `manifest.json` sits directly inside that directory.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Umweltbundesamt**.

</details>

## Configuration

All configuration happens in the UI — no YAML required.

### Initial setup

When you add the integration, the config flow:

1. Fetches the full list of UBA stations.
2. Filters to stations currently reporting data.
3. Sorts by Haversine distance from your HA home location and preselects the nearest.
4. Lets you override the station via a searchable dropdown.
5. Offers a toggle for the overall air-quality-index sensor (default: on).

The selected station becomes the integration's single device; every pollutant it publishes becomes a child sensor.

### Changing the station later

**Settings → Devices & Services → Umweltbundesamt → Configure** re-opens the options flow with the current station preselected. You can pick a different station or toggle the AQI sensor at any time.

> [!NOTE]
> Changing stations rewrites the entry's unique identifier. Previously-created entities for the old station remain in the registry as orphans; remove them from **Settings → Devices & Services → Entities** if you want a clean slate.

## Entities

For a station with UBA code `DEBE010` (example), the integration creates one device plus sensors along these lines:

| Entity ID (example) | Description | Device class | State class |
|---|---|---|---|
| `sensor.<station>_pm10` | PM₁₀ concentration (µg/m³) | `pm10` | `measurement` |
| `sensor.<station>_pm25` | PM₂.₅ concentration (µg/m³) | `pm25` | `measurement` |
| `sensor.<station>_nitrogen_dioxide` | NO₂ concentration (µg/m³) | `nitrogen_dioxide` | `measurement` |
| `sensor.<station>_ozone` | O₃ concentration (µg/m³) | `ozone` | `measurement` |
| `sensor.<station>_sulphur_dioxide` | SO₂ concentration (µg/m³) | `sulphur_dioxide` | `measurement` |
| `sensor.<station>_carbon_monoxide` | CO concentration (mg/m³) | `carbon_monoxide` | `measurement` |
| `sensor.<station>_air_quality_index` | Overall index, 1 (very good) – 5 (very bad) | `aqi` | `measurement` |

> [!IMPORTANT]
> The exact entity set depends on which pollutants your chosen station actually publishes. Urban traffic stations typically report NO₂ + PM₁₀; rural background stations lean toward O₃ + PM₂.₅. All per-pollutant sensors carry `state_class: measurement`, so HA's long-term statistics kick in automatically.

Attributes exposed on the air-quality-index sensor:

| Attribute | Meaning |
|---|---|
| `measurement_time` | ISO-8601 timestamp for the start of the reporting hour (Europe/Berlin). |

## Polling cadence

The UBA API publishes hourly averages with a 60–90 minute lag after the hour ends. The coordinator polls every 60 minutes and always returns the newest available hour. On transient network or schema errors, entities go `unavailable` until the next successful poll.

## Development

<details>
<summary>Local development setup</summary>

### Prerequisites

- Python 3.12 or newer
- A clone of this repository

### Bootstrap

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install homeassistant pytest-homeassistant-custom-component \
                      aiohttp aioresponses flake8
```

### Run the test suite

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m flake8 custom_components tests
```

### Project layout

```
custom_components/umweltbundesamt/
├── __init__.py         # async_setup_entry, runtime_data wiring
├── manifest.json
├── const.py
├── config_flow.py      # User + options flows
├── coordinator.py      # DataUpdateCoordinator subclass
├── sensor.py           # Per-component + AQI entities
├── strings.json        # English translation source
├── translations/de.json
└── api/                # HA-agnostic aiohttp client
    ├── client.py
    ├── models.py
    └── errors.py
```

### Cutting a release

Bump `version` in `custom_components/umweltbundesamt/manifest.json`, commit, push to `main`. The `release.yaml` workflow creates the matching `v<version>` tag, builds `umweltbundesamt.zip`, and publishes a GitHub release automatically.

</details>

<details>
<summary>Starting a new HA integration?</summary>

The lessons learned building this repo are distilled into a reusable checklist: [`docs/creating-a-new-ha-integration.md`](docs/creating-a-new-ha-integration.md). Covers scaffolding, manifest + HACS requirements, config-flow patterns, `runtime_data`, entity conventions, translations, release CI, and the pitfalls we tripped on while shipping this integration.

</details>

## Data source & licensing

- Air-quality data © [Umweltbundesamt](https://www.umweltbundesamt.de/daten/luft/luftdaten), used under their [open-data terms](https://www.umweltbundesamt.de/daten/luft/luftdaten). This integration is not endorsed by or affiliated with the UBA.
- Icon: [Material Design Icons](https://pictogrammers.com/library/mdi/) — `air-filter`, Apache License 2.0.

## Contributing

Issues and pull requests are welcome. Before filing a bug, please include:

- Your Home Assistant version (**Settings → About**).
- The station ID you configured.
- The `home-assistant.log` excerpt around the failure (with **Debug logging** enabled for `custom_components.umweltbundesamt` if possible).
