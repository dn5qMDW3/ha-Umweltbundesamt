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
