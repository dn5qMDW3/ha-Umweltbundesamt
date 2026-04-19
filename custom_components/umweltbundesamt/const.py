"""Constants for the Umweltbundesamt integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "umweltbundesamt"
BASE_URL = "https://www.umweltbundesamt.de/api/air_data/v2"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=60)

CONF_STATION_ID = "station_id"
CONF_INCLUDE_AQI = "include_aqi"

DEFAULT_INCLUDE_AQI = True
