"""Satellites for the Intelligence globe: CelesTrak GP elements, propagated here.

Orbital elements come from CelesTrak's public, key-free GP service, one group
at a time, at most every six hours per group (CelesTrak asks for that), cached
raw on disk under the state dir so a restart reuses them. Positions are worked
out locally in pure Python: two-body Kepler from the GP mean elements plus the
J2 secular drift of the node and perigee, then ECI -> Earth-fixed by GMST and
WGS-84 latitude/longitude/altitude. That is a few km off SGP4 within a day of
the epoch: plenty for a visual globe, not for conjunction work.

The world thread (osint.OsintFeed) owns one SatelliteCatalog: it refreshes the
elements when due and recomputes positions every ~10 s; the shell bridge asks
the same catalog for one object's details or its ground track on click.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .common import utc_now

GP_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=csv"

# (CelesTrak group, kind). The order is the de-duplication priority: an object
# listed in several groups keeps the kind of the first one.
GROUPS = (
    ("stations", "station"),
    ("gps-ops", "navigation"),
    ("galileo", "navigation"),
    ("glo-ops", "navigation"),
    ("beidou", "navigation"),
    ("weather", "weather"),
    ("science", "science"),
    ("geo", "geo"),
    ("visual", "bright"),
    ("starlink", "starlink"),
    ("cosmos-2251-debris", "debris"),
)
SAMPLED_KINDS = ("starlink", "debris")   # thinned to fit the cap; every other kind is kept whole
DEBRIS_SHARE = 0.25                      # of the room left after the kept kinds
CAP = 3000
REFRESH_S = 6 * 3600                     # CelesTrak: do not ask for the same group more often
RETRY_S = 1800                           # after a failed fetch
UPDATE_S = 10                            # positions are recomputed this often

MU = 398600.4418                         # km^3/s^2
RE = 6378.137                            # km, WGS-84 equatorial radius
J2 = 1.08262668e-3
FLAT = 1 / 298.257223563
E2 = FLAT * (2 - FLAT)
TWO_PI = 2 * math.pi
GEO_ALT = 35786.0


def cache_dir() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "osiris" / "celestrak"


def _epoch_s(stamp: str) -> float:
    """2026-10-19T12:34:56.123456 (UTC) -> Unix seconds."""
    return datetime.fromisoformat(stamp.strip().rstrip("Z")).replace(tzinfo=UTC).timestamp()


def parse_gp(data: bytes | str) -> list[dict[str, Any]]:
    """CelesTrak GP rows (CSV or JSON) -> element dicts; unusable rows are dropped."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    text = text.lstrip("﻿").strip()
    rows = json.loads(text) if text.startswith("[") else list(csv.DictReader(io.StringIO(text)))
    out = []
    for row in rows:
        try:
            el = {
                "norad": int(row["NORAD_CAT_ID"]),
                "name": str(row.get("OBJECT_NAME") or "").strip()[:32],
                "epoch": _epoch_s(str(row["EPOCH"])),
                "n": float(row["MEAN_MOTION"]),
                "e": float(row["ECCENTRICITY"]),
                "i": float(row["INCLINATION"]),
                "raan": float(row["RA_OF_ASC_NODE"]),
                "argp": float(row["ARG_OF_PERICENTER"]),
                "m": float(row["MEAN_ANOMALY"]),
                "ndot": float(row.get("MEAN_MOTION_DOT") or 0.0),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if el["n"] > 0 and 0 <= el["e"] < 1:
            out.append(el)
    return out


class Orbit:
    """Mean elements turned into the constants the propagator needs."""

    __slots__ = ("norad", "name", "kind", "epoch", "n_rev_day", "e", "i_deg", "a", "n", "ndot",
                 "cos_i", "sin_i", "raan0", "argp0", "m0", "raan_rate", "argp_rate", "sqrt_1me2")

    def __init__(self, el: dict[str, Any], kind: str) -> None:
        self.norad, self.name, self.kind, self.epoch = el["norad"], el["name"], kind, el["epoch"]
        self.n_rev_day, self.e, self.i_deg = el["n"], el["e"], el["i"]
        self.n = el["n"] * TWO_PI / 86400.0                 # rad/s
        self.ndot = el["ndot"] * TWO_PI / 86400.0 ** 2      # GP gives ndot/2 in rev/day^2: M gains ndot*dt^2
        self.a = (MU / self.n ** 2) ** (1 / 3)
        i = math.radians(el["i"])
        self.cos_i, self.sin_i = math.cos(i), math.sin(i)
        self.raan0, self.argp0, self.m0 = math.radians(el["raan"]), math.radians(el["argp"]), math.radians(el["m"])
        p = self.a * (1 - self.e ** 2)
        k = 1.5 * J2 * (RE / p) ** 2 * self.n
        self.raan_rate = -k * self.cos_i
        self.argp_rate = k * (2 - 2.5 * self.sin_i ** 2)
        self.sqrt_1me2 = math.sqrt(1 - self.e ** 2)

    @property
    def mean_alt(self) -> float:
        return self.a - RE

    def orbit_class(self) -> str:
        perigee, apogee = self.a * (1 - self.e) - RE, self.a * (1 + self.e) - RE
        if self.e > 0.25 or apogee - perigee > 10000:
            return "HEO"
        alt = self.mean_alt
        if alt < 2000:
            return "LEO"
        if abs(alt - GEO_ALT) <= 1000:
            return "GEO"
        return "MEO" if alt < GEO_ALT else "HEO"

    def state(self, t: float, gmst: float) -> tuple[float, float, float, float]:
        """(lat deg, lon deg, alt km, radius km) at Unix time t; gmst in radians."""
        dt = t - self.epoch
        e = self.e
        m = (self.m0 + self.n * dt + self.ndot * dt * dt) % TWO_PI
        ea = m if e < 0.8 else math.pi
        for _ in range(12):                                 # Newton on Kepler's equation
            d = (ea - e * math.sin(ea) - m) / (1 - e * math.cos(ea))
            ea -= d
            if abs(d) < 1e-10:
                break
        cos_e, sin_e = math.cos(ea), math.sin(ea)
        x, y = cos_e - e, self.sqrt_1me2 * sin_e
        r = self.a * (1 - e * cos_e)
        u = self.argp0 + self.argp_rate * dt + math.atan2(y, x)   # argument of latitude
        node = self.raan0 + self.raan_rate * dt - gmst              # Earth-fixed node longitude
        cos_u, sin_u = math.cos(u), math.sin(u)
        cos_n, sin_n = math.cos(node), math.sin(node)
        xe = r * (cos_n * cos_u - sin_n * sin_u * self.cos_i)
        ye = r * (sin_n * cos_u + cos_n * sin_u * self.cos_i)
        z = r * sin_u * self.sin_i
        p = math.hypot(xe, ye)
        lat = math.atan2(z, p * (1 - E2))
        for _ in range(2):                                  # WGS-84 geodetic latitude
            s = math.sin(lat)
            nn = RE / math.sqrt(1 - E2 * s * s)
            lat = math.atan2(z + E2 * nn * s, p)
        s, c = math.sin(lat), math.cos(lat)
        alt = p * c + z * s - RE * math.sqrt(1 - E2 * s * s)
        return math.degrees(lat), math.degrees(math.atan2(ye, xe)), alt, r

    def speed(self, r: float) -> float:
        return math.sqrt(MU * (2 / r - 1 / self.a))         # vis-viva, inertial km/s


def gmst(t: float) -> float:
    """Greenwich mean sidereal angle (radians) at Unix time t."""
    days = t / 86400.0 + 2440587.5 - 2451545.0
    return math.radians((280.46061837 + 360.98564736629 * days) % 360.0)


def _sample(items: list[Orbit], count: int) -> list[Orbit]:
    """Evenly spaced by NORAD id, so the same objects stay picked across refreshes."""
    items = sorted(items, key=lambda o: o.norad)
    if count >= len(items):
        return items
    if count <= 0:
        return []
    step = len(items) / count
    return [items[int(k * step)] for k in range(count)]


def select(by_group: dict[str, list[dict[str, Any]]], cap: int = CAP) -> list[Orbit]:
    """De-duplicate across groups, keep every non-sampled kind, thin starlink/debris to the cap."""
    seen: set[int] = set()
    kept: list[Orbit] = []
    pools: dict[str, list[Orbit]] = {kind: [] for kind in SAMPLED_KINDS}
    for group, kind in GROUPS:
        for el in by_group.get(group, []):
            if el["norad"] in seen:
                continue
            seen.add(el["norad"])
            orbit = Orbit(el, kind)
            (pools[kind] if kind in pools else kept).append(orbit)
    kept = kept[:cap]
    room = cap - len(kept)
    debris = min(len(pools["debris"]), int(room * DEBRIS_SHARE))
    starlink = min(len(pools["starlink"]), room - debris)
    debris = min(len(pools["debris"]), room - starlink)       # starlink short: debris takes the rest
    return kept + _sample(pools["starlink"], starlink) + _sample(pools["debris"], debris)


class SatelliteCatalog:
    name, source = "Satellites", "CelesTrak (GP elements)"
    licence = "CelesTrak public GP data; positions propagated locally (approximate)"

    def __init__(self, cache: Path | None = None, clock: Callable[[], float] = time.time,
                 cap: int = CAP, refresh_s: float = REFRESH_S, retry_s: float = RETRY_S) -> None:
        self.cache = cache if cache is not None else cache_dir()
        self._clock, self.cap, self.refresh_s, self.retry_s = clock, cap, refresh_s, retry_s
        self.by_group: dict[str, list[dict[str, Any]]] = {}
        self.next_fetch: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.orbits: list[Orbit] = []
        self.index: dict[int, Orbit] = {}
        self.fetched_at: str | None = None
        self.computed_at: str | None = None
        self.items: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}
        self.compute_ms = 0.0
        self._loaded = False

    # ---------------------------------------------------------------- elements
    def _path(self, group: str) -> Path:
        return self.cache / f"gp-{group}.csv"

    def _load_cache(self) -> None:
        """Once per run: reuse what is on disk; a fresh file also defers the next fetch."""
        self._loaded = True
        now = self._clock()
        for group, _ in GROUPS:
            path = self._path(group)
            try:
                rows = parse_gp(path.read_bytes())
                mtime = path.stat().st_mtime
            except (OSError, ValueError):
                continue
            if rows:
                self.by_group[group] = rows
                self.next_fetch[group] = mtime + self.refresh_s if mtime <= now else now + self.refresh_s

    def due_groups(self) -> list[str]:
        if not self._loaded:
            self._load_cache()
        now = self._clock()
        return [group for group, _ in GROUPS if now >= self.next_fetch.get(group, 0.0)]

    def refresh(self, fetch: Callable[[str], bytes]) -> bool:
        """Fetch the groups that are due; True if the elements changed."""
        due = self.due_groups()
        changed = not self.orbits and bool(self.by_group)      # cached elements loaded at start
        for group in due:
            now = self._clock()
            try:
                raw = fetch(GP_URL.format(group=group))
                rows = parse_gp(raw)
                if not rows:
                    raise ValueError("no elements")
            except Exception as exc:        # keep the cached elements; try again later
                self.errors[group] = ("CelesTrak could not be reached" if isinstance(exc, OSError)
                                      else "CelesTrak sent data APVIS could not read")
                self.next_fetch[group] = now + self.retry_s
                continue
            self.next_fetch[group] = now + self.refresh_s
            self.errors.pop(group, None)
            self.by_group[group] = rows
            self.fetched_at = utc_now()
            changed = True
            try:
                self.cache.mkdir(parents=True, exist_ok=True)
                tmp = self._path(group).with_suffix(".tmp")
                tmp.write_bytes(raw)
                os.replace(tmp, self._path(group))
            except OSError:
                pass
        if changed:
            self.orbits = select(self.by_group, self.cap)
            self.index = {o.norad: o for o in self.orbits}
        return changed

    # ---------------------------------------------------------------- positions
    def compute(self, t: float | None = None) -> list[dict[str, Any]]:
        """Recompute every selected object's position: the compact rows QML draws."""
        start = time.perf_counter()
        t = self._clock() if t is None else t
        g = gmst(t)
        items, counts = [], {}
        for o in self.orbits:
            try:
                lat, lon, alt, _ = o.state(t, g)
            except (ValueError, ZeroDivisionError, OverflowError):
                continue
            items.append({"id": o.norad, "n": o.name, "k": o.kind,
                          "lat": round(lat, 2), "lon": round(lon, 2), "alt": round(alt)})
            counts[o.kind] = counts.get(o.kind, 0) + 1
        self.items, self.counts = items, counts
        self.computed_at = utc_now()
        self.compute_ms = (time.perf_counter() - start) * 1000
        return items

    def snapshot(self) -> dict[str, Any]:
        """The `satellites` layer of the world snapshot (last computed positions)."""
        if self.items:
            status = "live"
        else:
            status = "unavailable" if self.errors else "waiting"
        error = None
        if self.errors:
            error = next(iter(self.errors.values())) + (" (showing cached elements)" if self.items else "")
        return {"name": self.name, "source": self.source, "licence": self.licence,
                "status": status, "fetched_at": self.fetched_at, "computed_at": self.computed_at,
                "error": error, "total": len(self.items), "counts": self.counts, "items": self.items}

    def info(self, norad: int, t: float | None = None) -> dict[str, Any]:
        """Full details of one object for the click card; {} when it is not in the catalog."""
        o = self.index.get(int(norad))
        if o is None:
            return {}
        t = self._clock() if t is None else t
        lat, lon, alt, r = o.state(t, gmst(t))
        return {"name": o.name, "kind": o.kind, "norad": o.norad, "altKm": round(alt, 1),
                "orbit": o.orbit_class(), "periodMin": round(1440.0 / o.n_rev_day, 1),
                "speedKms": round(o.speed(r), 2), "lat": round(lat, 3), "lon": round(lon, 3),
                "inclination": round(o.i_deg, 2)}

    def track(self, norad: int, points: int = 90, t: float | None = None) -> list[list[float]]:
        """Ground track [[lat, lon, altKm], ...] for one orbital period starting now."""
        o = self.index.get(int(norad))
        if o is None or points < 2:
            return []
        t = self._clock() if t is None else t
        period = 86400.0 / o.n_rev_day
        out = []
        for k in range(points):
            tk = t + period * k / (points - 1)
            lat, lon, alt, _ = o.state(tk, gmst(tk))
            out.append([round(lat, 2), round(lon, 2), round(alt)])
        return out
