"""Weather at Indian load centres from Open-Meteo (ERA5 reanalysis archive: actual weather,
known with a ~5-day publication lag). Saved as published in raw/weather/.

    python -m research.weather fetch
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

import pandas as pd

from .config import DATA, ROOT

RAW = ROOT / "raw" / "weather"
CITIES = {  # load centres across the five regional grids
    "Delhi": (28.61, 77.21), "Lucknow": (26.85, 80.95), "Jaipur": (26.91, 75.79), "Ludhiana": (30.90, 75.85),
    "Mumbai": (19.08, 72.88), "Ahmedabad": (23.02, 72.57), "Chennai": (13.08, 80.27), "Hyderabad": (17.39, 78.49),
    "Kolkata": (22.57, 88.36),
}
VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum"
PUBLICATION_LAG_DAYS = 5   # ERA5 archive lags real time by about 5 days


def fetch(start="2022-01-01", end=None):
    end = end or (pd.Timestamp.today() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
    lat = ",".join(str(v[0]) for v in CITIES.values())
    lon = ",".join(str(v[1]) for v in CITIES.values())
    url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
           f"&start_date={start}&end_date={end}&daily={VARS}&timezone=Asia%2FKolkata")
    for wait in (0, 60, 180, 600):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research"}), timeout=180) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}; waiting")
    else:
        sys.exit("Open-Meteo kept refusing (rate limit); try later")
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"era5_{start}_{end}.json"
    path.write_bytes(body)
    answer = json.loads(body)
    rows = []
    for name, loc in zip(CITIES, answer):
        d = pd.DataFrame(loc["daily"])
        d["city"] = name
        rows.append(d)
    df = pd.concat(rows).rename(columns={"time": "date"})
    df.to_csv(DATA / "weather_daily.csv", index=False)
    print(f"saved {path.relative_to(ROOT)}; wrote data/weather_daily.csv {len(df)} rows, {df.date.min()} to {df.date.max()}"
          f" ({datetime.now():%H:%M})")


if __name__ == "__main__":
    {"fetch": fetch}[sys.argv[1]]()
