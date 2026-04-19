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
