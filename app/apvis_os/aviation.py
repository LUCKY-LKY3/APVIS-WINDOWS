"""OSIRIS aviation: live aircraft positions from a public ADS-B source, labelled honestly.

The source is ADSB.lol (https://www.adsb.lol), whose data is licensed ODbL 1.0
and whose API needs no account. Only the map area being viewed is sent. Every
snapshot carries its source, licence, fetch time and data age; stale or failed
data is labelled as such and never presented as live.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .common import utc_now

SOURCE_NAME = "ADSB.lol"
SOURCE_URL = "https://api.adsb.lol"
LICENCE = "ODbL 1.0"
ATTRIBUTION = "Flight data © ADSB.lol contributors, ODbL 1.0"
# Public, key-free ADS-B sources with the same readsb JSON, tried in order
# (owner, 2026-09-25: ADSB.lol was often down). The last one that answered is
# tried first next time; every snapshot names the source it came from.
SOURCES = (
    {"name": "adsb.fi", "licence": "adsb.fi open data (personal, non-commercial)",
     "attribution": "Flight data © adsb.fi community feeders (open data, non-commercial use)",
     "url": "https://opendata.adsb.fi/api/v2/lat/{lat:.3f}/lon/{lon:.3f}/dist/{radius}"},
    {"name": SOURCE_NAME, "licence": LICENCE, "attribution": ATTRIBUTION,
     "url": SOURCE_URL + "/v2/point/{lat:.3f}/{lon:.3f}/{radius}"},
)
USER_AGENT = "APVIS-OS/2.0 (+local owner desktop)"
MAX_POSITION_AGE_S = 60.0     # older positions are dropped
STALE_AFTER_S = 90.0          # a snapshot older than this is labelled stale
MIN_POLL_S = 10.0

# Well-known airport reference points (approximate, for orientation only).
AIRPORTS = [
    ("LHR", "London Heathrow", 51.470, -0.454), ("LGW", "London Gatwick", 51.148, -0.190),
    ("STN", "London Stansted", 51.885, 0.235), ("MAN", "Manchester", 53.354, -2.275),
    ("BHX", "Birmingham", 52.454, -1.748), ("BRS", "Bristol", 51.383, -2.719),
    ("EDI", "Edinburgh", 55.950, -3.373), ("GLA", "Glasgow", 55.872, -4.433),
    ("BFS", "Belfast International", 54.658, -6.216), ("DUB", "Dublin", 53.421, -6.270),
]


# ICAO type designators seen most over the UK, in words (the source only sends the code).
TYPE_NAMES = {
    "A319": "Airbus A319", "A320": "Airbus A320", "A20N": "Airbus A320neo", "A321": "Airbus A321",
    "A21N": "Airbus A321neo", "A332": "Airbus A330-200", "A333": "Airbus A330-300", "A339": "Airbus A330-900",
    "A343": "Airbus A340-300", "A346": "Airbus A340-600", "A359": "Airbus A350-900", "A35K": "Airbus A350-1000",
    "A388": "Airbus A380", "A400": "Airbus A400M", "BCS1": "Airbus A220-100", "BCS3": "Airbus A220-300",
    "B737": "Boeing 737-700", "B738": "Boeing 737-800", "B739": "Boeing 737-900", "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9", "B744": "Boeing 747-400", "B748": "Boeing 747-8", "B752": "Boeing 757-200",
    "B763": "Boeing 767-300", "B764": "Boeing 767-400", "B772": "Boeing 777-200", "B77L": "Boeing 777-200LR",
    "B77W": "Boeing 777-300ER", "B788": "Boeing 787-8", "B789": "Boeing 787-9", "B78X": "Boeing 787-10",
    "E170": "Embraer 170", "E175": "Embraer 175", "E190": "Embraer 190", "E195": "Embraer 195",
    "E290": "Embraer E190-E2", "E295": "Embraer E195-E2", "AT72": "ATR 72", "AT76": "ATR 72-600",
    "AT75": "ATR 72-500", "DH8D": "Dash 8 Q400", "CRJ9": "Bombardier CRJ900", "SF34": "Saab 340",
    "C172": "Cessna 172", "C152": "Cessna 152", "PA28": "Piper Cherokee", "SR22": "Cirrus SR22",
    "EC35": "Airbus H135", "EC45": "Airbus H145", "A139": "Leonardo AW139", "A169": "Leonardo AW169",
    "S92": "Sikorsky S-92", "C17": "Boeing C-17", "C130": "Lockheed C-130", "K35R": "Boeing KC-135",
    "EUFI": "Eurofighter Typhoon", "F35": "F-35 Lightning II", "GLF6": "Gulfstream G650", "CL35": "Challenger 350",
    "PC12": "Pilatus PC-12", "BE20": "King Air 200", "LJ45": "Learjet 45", "C68A": "Citation Latitude",
}
TRAIL_POINTS = 30          # positions kept per aircraft (one per update, ~7 minutes at 15 s)
TRAIL_FORGET_S = 180.0     # an aircraft not seen for this long loses its trail
ALTITUDE_BANDS = ("Ground", "Below 10,000 ft", "10–25,000 ft", "25–35,000 ft", "Above 35,000 ft")


@dataclass(frozen=True)
class Area:
    """Circle the source is asked for (nautical miles, the source's unit, max 250)."""
    lat: float = 54.5
    lon: float = -3.5
    radius_nm: int = 250

    def __post_init__(self) -> None:
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValueError("area centre is not a valid coordinate")
        if not 1 <= self.radius_nm <= 250:
            raise ValueError("radius must be between 1 and 250 nautical miles")


@dataclass(frozen=True)
class Aircraft:
    hex: str
    callsign: str
    registration: str
    type: str
    lat: float
    lon: float
    altitude_ft: int | None      # None when unknown; 0 with on_ground
    on_ground: bool
    speed_kt: float | None
    track_deg: float | None
    position_age_s: float
    squawk: str
    emergency: bool
    vertical_rate_fpm: int | None = None   # + climbing, - descending; None when not reported

    def to_row(self) -> list[Any]:
        """Compact row for the UI: [hex, callsign, reg, type, lat, lon, alt, ground, kt, track, age, emergency,
        vertical rate fpm, type name]."""
        return [self.hex, self.callsign, self.registration, self.type, round(self.lat, 4), round(self.lon, 4),
                self.altitude_ft, self.on_ground, None if self.speed_kt is None else round(self.speed_kt),
                None if self.track_deg is None else round(self.track_deg), round(self.position_age_s, 1), self.emergency,
                self.vertical_rate_fpm, TYPE_NAMES.get(self.type.upper(), "")]


@dataclass
class Snapshot:
    status: str                     # live | stale | unavailable | disabled
    aircraft: list[Aircraft] = field(default_factory=list)
    source: str = SOURCES[0]["name"]
    licence: str = SOURCES[0]["licence"]
    attribution: str = SOURCES[0]["attribution"]
    fetched_at: str | None = None   # when APVIS received it (UTC)
    fetched_mono: float | None = None
    source_time_ms: int | None = None
    area: Area = field(default_factory=Area)
    error: str | None = None
    dropped_old: int = 0

    def age_s(self, now: Callable[[], float] = time.monotonic) -> float | None:
        return None if self.fetched_mono is None else max(0.0, now() - self.fetched_mono)

    def to_dict(self, now: Callable[[], float] = time.monotonic) -> dict[str, Any]:
        age = self.age_s(now)
        status = self.status
        if status == "live" and age is not None and age > STALE_AFTER_S:
            status = "stale"
        return {"status": status, "count": len(self.aircraft), "source": self.source, "licence": self.licence,
                "attribution": self.attribution, "fetched_at": self.fetched_at,
                "age_s": None if age is None else round(age), "error": self.error, "dropped_old": self.dropped_old,
                "area": asdict(self.area), "aircraft": [a.to_row() for a in self.aircraft]}


def parse_aircraft(raw: dict[str, Any]) -> Aircraft | None:
    """One record from the readsb-style JSON; None if it has no usable, recent position."""
    try:
        lat, lon = float(raw["lat"]), float(raw["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    # ADS-B also carries surface vehicles and fixed obstacles (emitter category C*); they are not aircraft.
    if str(raw.get("category") or "").upper().startswith("C") or str(raw.get("t") or "").upper() in {"TWR", "GND", "SERV"}:
        return None
    age = float(raw.get("seen_pos", raw.get("seen", 0.0)) or 0.0)
    alt = raw.get("alt_baro")
    on_ground = alt == "ground"
    altitude = 0 if on_ground else (int(alt) if isinstance(alt, (int, float)) else None)
    track = raw.get("track", raw.get("true_heading"))
    speed = raw.get("gs")
    squawk = str(raw.get("squawk") or "")
    rate = raw.get("baro_rate", raw.get("geom_rate"))
    emergency_field = str(raw.get("emergency") or "none")
    return Aircraft(
        hex=str(raw.get("hex", "")).strip().lower()[:8],
        callsign="" if set(str(raw.get("flight") or "").strip()) <= {"0", "@"} else str(raw.get("flight")).strip()[:10],
        registration=str(raw.get("r") or "").strip()[:12],
        type=str(raw.get("t") or "").strip()[:6],
        lat=lat, lon=lon, altitude_ft=altitude, on_ground=on_ground,
        speed_kt=float(speed) if isinstance(speed, (int, float)) else None,
        track_deg=float(track) % 360 if isinstance(track, (int, float)) else None,
        position_age_s=age, squawk=squawk,
        emergency=emergency_field not in {"none", ""} or squawk in {"7500", "7600", "7700"},
        vertical_rate_fpm=int(rate) if isinstance(rate, (int, float)) and not on_ground else None,
    )


def plain_error(exc: Exception) -> str:
    """What went wrong, in words the owner can act on."""
    code = getattr(exc, "code", None)
    reason = str(getattr(exc, "reason", "") or exc).lower()
    if isinstance(code, int):
        if code == 429:
            return f"{SOURCE_NAME} asked APVIS to slow down; retrying shortly"
        return f"{SOURCE_NAME} returned an error (HTTP {code})"
    if "name resolution" in reason or "getaddrinfo" in reason or "nodename" in reason:
        return "no internet connection (could not look up the flight data server)"
    if "timed out" in reason:
        return f"{SOURCE_NAME} did not answer in time"
    if "refused" in reason or "unreachable" in reason:
        return f"cannot reach {SOURCE_NAME} (network unreachable)"
    if isinstance(exc, ValueError):
        return f"{SOURCE_NAME} sent data APVIS could not read"
    return f"{SOURCE_NAME} unreachable"


class AviationFeed:
    """Fetches, filters and caches snapshots with polite polling and backoff."""

    def __init__(self, area: Area | None = None, *, opener: Callable[..., Any] = urllib.request.urlopen,
                 monotonic: Callable[[], float] = time.monotonic, timeout: float = 8.0,
                 cache: Path | None = None) -> None:
        self.area = area or Area()
        self._open = opener
        self._now = monotonic
        self.timeout = timeout
        self.last = Snapshot("unavailable", area=self.area, error="not fetched yet")
        self.failures = 0
        self.next_allowed = 0.0
        self.cache = cache
        self.preferred = 0          # index into SOURCES of the last one that answered
        # Real past positions per aircraft, from earlier snapshots (never predicted).
        self.trails: dict[str, list[float]] = {}
        self.trail_seen: dict[str, float] = {}

    def url(self, source: dict[str, str] | None = None) -> str:
        source = source or SOURCES[self.preferred]
        return source["url"].format(lat=self.area.lat, lon=self.area.lon, radius=int(self.area.radius_nm))

    def backoff_s(self) -> float:
        return 0.0 if self.failures == 0 else min(300.0, 15.0 * 2 ** (self.failures - 1))

    def fetch(self) -> Snapshot:
        """One polite request. On failure the map is cleared (old positions are never shown as
        current) and only the time of the last good update is kept."""
        now = self._now()
        if now < self.next_allowed:
            return self.last
        self.next_allowed = now + MIN_POLL_S
        order = [self.preferred] + [i for i in range(len(SOURCES)) if i != self.preferred]
        payload, used, errors = None, None, []
        for index in order:
            source = SOURCES[index]
            request = urllib.request.Request(self.url(source), headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with self._open(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                rows = data.get("ac", data.get("aircraft")) if isinstance(data, dict) else None
                if not isinstance(rows, list):
                    raise ValueError("unexpected response shape")
                payload, used = {**data, "ac": rows}, index
                break
            except (urllib.error.URLError, OSError, ValueError) as exc:
                errors.append(plain_error(exc).replace(SOURCE_NAME, source["name"]))
        if payload is None:
            self.failures += 1
            self.next_allowed = self._now() + max(MIN_POLL_S, self.backoff_s())
            previous = self.last
            self.last = Snapshot("unavailable", aircraft=[], area=self.area, fetched_at=previous.fetched_at,
                                 fetched_mono=previous.fetched_mono, error="; ".join(errors))
            return self.last
        self.preferred = used
        source = SOURCES[used]
        aircraft, dropped = [], 0
        for raw in payload["ac"]:
            parsed = parse_aircraft(raw) if isinstance(raw, dict) else None
            if parsed is None:
                continue
            if parsed.position_age_s > MAX_POSITION_AGE_S:
                dropped += 1
                continue
            aircraft.append(parsed)
        aircraft.sort(key=lambda a: (a.callsign or "~", a.hex))
        self.failures = 0
        source_ms = payload.get("now")
        self.last = Snapshot("live", aircraft=aircraft, area=self.area, fetched_at=utc_now(), fetched_mono=self._now(),
                             source=source["name"], licence=source["licence"], attribution=source["attribution"],
                             source_time_ms=int(source_ms) if isinstance(source_ms, (int, float)) else None,
                             dropped_old=dropped)
        self._remember_positions(aircraft)
        self._write_cache()
        return self.last

    def _remember_positions(self, aircraft: list[Aircraft]) -> None:
        now = self._now()
        for a in aircraft:
            trail = self.trails.setdefault(a.hex, [])
            if not trail or abs(trail[-2] - a.lat) + abs(trail[-1] - a.lon) > 0.0005:
                trail += [round(a.lat, 4), round(a.lon, 4)]
                del trail[:-2 * TRAIL_POINTS]
            self.trail_seen[a.hex] = now
        for hex_id in [h for h, seen in self.trail_seen.items() if now - seen > TRAIL_FORGET_S]:
            self.trails.pop(hex_id, None)
            self.trail_seen.pop(hex_id, None)

    def rows(self) -> list[list[Any]]:
        """UI rows for the current snapshot, each with its trail [lat, lon, lat, lon, ...] appended."""
        return [a.to_row() + [self.trails.get(a.hex, [])[:-2]] for a in self.last.aircraft]

    def _write_cache(self) -> None:
        """Keep the last snapshot for apvisctl/diagnostics (owner-only file)."""
        if self.cache is None:
            return
        try:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            data = self.last.to_dict(self._now)
            data.pop("age_s", None)
            fd, tmp = tempfile.mkstemp(dir=self.cache.parent, prefix=".aviation.")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.cache)
        except OSError:
            pass


def cache_path() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "osiris" / "aviation-last.json"


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 3440.065 * math.asin(math.sqrt(a))


def airspace_stats(aircraft: list[Aircraft]) -> dict[str, Any]:
    """Counts for the Atlas side panel, all from the current snapshot."""
    bands = [0] * len(ALTITUDE_BANDS)
    climbing = descending = 0
    for a in aircraft:
        if a.on_ground:
            bands[0] += 1
        elif a.altitude_ft is not None:
            bands[1 if a.altitude_ft < 10000 else 2 if a.altitude_ft < 25000 else 3 if a.altitude_ft < 35000 else 4] += 1
        if a.vertical_rate_fpm is not None:
            climbing += a.vertical_rate_fpm > 300
            descending += a.vertical_rate_fpm < -300
    busiest = []
    for code, name, lat, lon in AIRPORTS:
        near = sum(1 for a in aircraft if (a.on_ground or (a.altitude_ft or 99999) < 10000)
                   and distance_nm(a.lat, a.lon, lat, lon) <= 25)
        if near:
            busiest.append([code, name, near])
    busiest.sort(key=lambda row: -row[2])
    airborne = [a for a in aircraft if not a.on_ground]
    highest = max((a for a in airborne if a.altitude_ft is not None), key=lambda a: a.altitude_ft, default=None)
    fastest = max((a for a in airborne if a.speed_kt is not None), key=lambda a: a.speed_kt, default=None)
    label = lambda a: a.callsign or a.registration or a.hex.upper()
    return {"bands": bands, "bandNames": list(ALTITUDE_BANDS), "busiest": busiest[:3],
            "highest": [label(highest), highest.altitude_ft] if highest else None,
            "fastest": [label(fastest), round(fastest.speed_kt)] if fastest else None,
            "climbing": climbing, "descending": descending,
            "emergencies": sum(1 for a in aircraft if a.emergency)}


def describe(aircraft: Aircraft) -> str:
    """Plain-language line for the text list and screen readers."""
    name = aircraft.callsign or aircraft.registration or aircraft.hex.upper()
    if aircraft.on_ground:
        height = "on the ground"
    elif aircraft.altitude_ft is None:
        height = "altitude unknown"
    else:
        height = f"{aircraft.altitude_ft:,} ft"
    speed = "" if aircraft.speed_kt is None else f", {aircraft.speed_kt:.0f} kt"
    heading = "" if aircraft.track_deg is None else f", heading {aircraft.track_deg:03.0f}°"
    kind = f" ({aircraft.type})" if aircraft.type else ""
    return f"{name}{kind}: {height}{speed}{heading}"
