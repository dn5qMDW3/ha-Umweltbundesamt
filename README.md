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

## Entities

For a station with UBA code `DEBE010` (Berlin Wedding), the integration creates one device and the following sensors:

| Entity | Description |
|---|---|
| `sensor.<station>_feinstaub_pm10` | PM10 concentration (µg/m³), `device_class: pm10` |
| `sensor.<station>_stickstoffdioxid` | NO₂ concentration (µg/m³), `device_class: nitrogen_dioxide` |
| `sensor.<station>_ozon` | O₃ concentration (µg/m³), `device_class: ozone` |
| `sensor.<station>_air_quality_index` | Overall 1–5 air-quality index with a localized `level_text` attribute |

The exact entity set depends on which components the chosen station reports; only components published by that station become sensors. All per-pollutant sensors use `state_class: measurement`, so Home Assistant records long-term statistics automatically.

## Data source

Data is provided by the Umweltbundesamt under their open-data terms: <https://www.umweltbundesamt.de/daten/luft/luftdaten>.
