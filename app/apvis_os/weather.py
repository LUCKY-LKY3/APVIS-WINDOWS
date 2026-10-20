"""Local weather for the owner's town (Open-Meteo: free, no account, no key).

Off until the owner types a town in Settings; then the top bar shows the temperature and
"what's the weather?" is answered from the latest reading (with its age), never guessed.
Refreshed every 30 minutes while Home runs.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
FORECAST = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto"
            "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&forecast_days=2")
REFRESH_S = 30 * 60
USER_AGENT = "APVIS-OS/2.0 (weather on the owner's desktop)"

# WMO weather codes (Open-Meteo) -> words and a small symbol.
CODES: dict[int, tuple[str, str]] = {
    0: ("clear", "☀"), 1: ("mostly clear", "🌤"), 2: ("partly cloudy", "⛅"), 3: ("overcast", "☁"),
    45: ("foggy", "🌫"), 48: ("freezing fog", "🌫"), 51: ("light drizzle", "🌦"), 53: ("drizzle", "🌦"), 55: ("heavy drizzle", "🌧"),
    56: ("freezing drizzle", "🌧"), 57: ("freezing drizzle", "🌧"), 61: ("light rain", "🌦"), 63: ("rain", "🌧"), 65: ("heavy rain", "🌧"),
    66: ("freezing rain", "🌧"), 67: ("freezing rain", "🌧"), 71: ("light snow", "🌨"), 73: ("snow", "🌨"), 75: ("heavy snow", "❄"),
    77: ("snow grains", "🌨"), 80: ("light showers", "🌦"), 81: ("showers", "🌧"), 82: ("heavy showers", "⛈"),
    85: ("snow showers", "🌨"), 86: ("heavy snow showers", "❄"), 95: ("thunderstorms", "⛈"), 96: ("thunderstorms with hail", "⛈"),
    99: ("thunderstorms with hail", "⛈"),
}

_ASK = re.compile(r"(?i)^\s*(?:hey\s+apvis[,\s]*)?(?:what(?:'?s| is)\s+the\s+weather(?:\s+like)?(?:\s+(?:today|now|outside|tomorrow))?"
                  r"|how(?:'?s| is)\s+the\s+weather(?:\s+(?:today|now|outside|tomorrow))?|weather(?:\s+(?:today|now|tomorrow))?"
                  r"|is\s+it\s+(?:going\s+to\s+)?(?:rain|raining|cold|hot|sunny)(?:\s+(?:today|now|outside|tomorrow))?"
                  r"|do\s+i\s+need\s+(?:an?\s+)?(?:umbrella|coat|jacket)(?:\s+today)?)\s*[?.!]*\s*$")


def config_path() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "weather.json"


def _get(url: str, timeout: float = 10) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        return json.load(response)


def geocode(town: str, fetch: Callable[[str], dict[str, Any]] = _get) -> dict[str, Any]:
    town = (town or "").strip()
    if not town or len(town) > 80:
        raise ValueError("Type a town or city, e.g. London")
    results = fetch(GEOCODE + urllib.parse.quote(town)).get("results") or []
    if not results:
        raise ValueError(f"Couldn't find a place called {town!r}")
    r = results[0]
    label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country_code")) if x)
    return {"town": town, "label": label, "lat": round(float(r["latitude"]), 4), "lon": round(float(r["longitude"]), 4)}


def load(path: Path | None = None) -> dict[str, Any]:
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, target)


def fetch_now(place: dict[str, Any], fetch: Callable[[str], dict[str, Any]] = _get, clock: Callable[[], float] = time.time) -> dict[str, Any]:
    data = fetch(FORECAST.format(lat=place["lat"], lon=place["lon"]))
    current, daily = data.get("current") or {}, data.get("daily") or {}
    code = int(current.get("weather_code", -1))
    words, symbol = CODES.get(code, ("unsettled", "☁"))

    def day(i: int) -> dict[str, Any]:
        try:
            dcode = int(daily["weather_code"][i])
            return {"max": round(daily["temperature_2m_max"][i]), "min": round(daily["temperature_2m_min"][i]),
                    "rain": daily.get("precipitation_probability_max", [None, None])[i], "words": CODES.get(dcode, ("unsettled", ""))[0]}
        except (KeyError, IndexError, TypeError, ValueError):
            return {}

    return {"label": place.get("label", ""), "temp": round(current.get("temperature_2m", 0)), "feels": round(current.get("apparent_temperature", 0)),
            "wind": round(current.get("wind_speed_10m", 0)), "words": words, "symbol": symbol if current.get("is_day", 1) or code > 3 else "☾",
            "today": day(0), "tomorrow": day(1), "at": clock()}


def is_question(text: str) -> bool:
    return bool(_ASK.match(text or ""))


def answer(text: str, reading: dict[str, Any] | None, clock: Callable[[], float] = time.time) -> str:
    if not reading:
        return "Weather is off. Type your town in Settings, then Appearance, then Weather, and APVIS will show it here."
    age = int((clock() - reading.get("at", 0)) / 60)
    when = "just now" if age < 2 else f"{age} min ago"
    tomorrow = "tomorrow" in text.lower()
    if tomorrow and reading.get("tomorrow"):
        t = reading["tomorrow"]
        rain = f", {t['rain']}% chance of rain" if t.get("rain") is not None else ""
        return f"Tomorrow in {reading['label']}: {t['words']}, {t['min']}–{t['max']}°C{rain}."
    today = reading.get("today") or {}
    rain = f" {today['rain']}% chance of rain today." if today.get("rain") is not None else ""
    advice = ""
    low = text.lower()
    if ("umbrella" in low or "rain" in low) and today.get("rain") is not None:
        advice = " Take an umbrella." if today["rain"] >= 40 else " You probably won't need an umbrella."
    elif ("coat" in low or "jacket" in low or "cold" in low):
        advice = " A coat would be a good idea." if reading["feels"] < 12 else " A light layer is enough."
    return (f"{reading['symbol']} {reading['temp']}°C and {reading['words']} in {reading['label']} (feels like {reading['feels']}°C, "
            f"wind {reading['wind']} km/h).{rain}{advice} Measured {when} (Open-Meteo).")
