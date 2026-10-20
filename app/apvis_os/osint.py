"""OSIRIS world layers for the Atlas: public, key-free, sourced open data.

Each layer is fetched from its publisher only while the Atlas is on screen,
at a polite interval, and carries its source, licence note, fetch time and
any error. Nothing is invented: a layer that fails says so and shows nothing.

Layers: USGS earthquakes (M2.5+, 24 h), NASA EONET natural events (open),
GDACS disaster alerts (UN/EU), the ISS position (wheretheiss.at), NOAA SWPC
planetary K-index (space weather), TfL JamCams (official public London traffic
cameras), world news (GDELT + BBC World headlines) and markets (Yahoo Finance
public chart data, delayed; CoinGecko for crypto). Only official public feeds:
no private or unsecured cameras. BBC Technology and Science headlines serve
Ask's news catch-up (briefing.py), not the Atlas.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from typing import Any, Callable

from .common import utc_now

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) APVIS-OS/2.0 (+owner desktop OSIRIS world atlas)"
Fetch = Callable[[str], bytes]


def _fetch(url: str, timeout: float = 15) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- parsers

def parse_usgs(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for f in data.get("features", []):
        props, geom = f.get("properties") or {}, f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        mag = _num(props.get("mag"))
        if len(coords) < 2 or mag is None:
            continue
        items.append({"id": str(f.get("id", "")), "kind": "quake", "lat": coords[1], "lon": coords[0],
                      "title": f"M{mag:.1f} earthquake", "detail": str(props.get("place") or ""),
                      "mag": round(mag, 1), "depth_km": _num(coords[2]) if len(coords) > 2 else None,
                      "time_ms": int(props.get("time") or 0), "url": str(props.get("url") or ""),
                      "tsunami": bool(props.get("tsunami"))})
    return items


EONET_KINDS = {"wildfires": "fire", "severeStorms": "storm", "volcanoes": "volcano", "seaLakeIce": "ice",
               "floods": "flood", "earthquakes": "quake", "landslides": "landslide", "dustHaze": "dust",
               "snow": "snow", "tempExtremes": "heat", "drought": "drought", "waterColor": "water", "manmade": "manmade"}


def _point(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return float(coords[1]), float(coords[0])
    if geometry.get("type") == "Polygon" and coords and coords[0]:
        ring = coords[0]
        return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)
    return None


def parse_eonet(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for event in data.get("events", []):
        geometries = event.get("geometry") or []
        if not geometries:
            continue
        latest = geometries[-1]
        point = _point(latest)
        if point is None:
            continue
        category = ((event.get("categories") or [{}])[0]).get("id", "")
        track = [p for g in geometries[-12:] if (p := _point(g))]
        items.append({"id": str(event.get("id", "")), "kind": EONET_KINDS.get(category, "event"),
                      "lat": point[0], "lon": point[1], "title": str(event.get("title") or ""),
                      "detail": ((event.get("categories") or [{}])[0]).get("title", ""),
                      "time": str(latest.get("date") or ""), "url": str(event.get("link") or ""),
                      "track": [v for p in track for v in (round(p[0], 3), round(p[1], 3))]})
    return items


GDACS_KINDS = {"EQ": "quake", "TC": "cyclone", "FL": "flood", "VO": "volcano", "DR": "drought", "WF": "fire"}


GDACS_MAX_AGE_DAYS = 14


def _recent(stamp: str, days: float, now: float | None = None) -> bool:
    """True if an ISO time is within the last `days` (unknown times are kept)."""
    try:
        from datetime import datetime, timezone
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return ((now or time.time()) - when.timestamp()) <= days * 86400
    except (ValueError, AttributeError):
        return True


def parse_gdacs(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for f in data.get("features", []):
        props = f.get("properties") or {}
        if not _recent(str(props.get("todate") or props.get("fromdate") or ""), GDACS_MAX_AGE_DAYS):
            continue                  # finished long ago: not "now"
        point = _point(f.get("geometry") or {})
        if point is None:
            continue
        items.append({"id": f"{props.get('eventtype')}{props.get('eventid')}", "kind": GDACS_KINDS.get(props.get("eventtype"), "alert"),
                      "lat": point[0], "lon": point[1], "title": str(props.get("name") or props.get("eventname") or ""),
                      "detail": str(props.get("country") or ""), "alert": str(props.get("alertlevel") or "Green"),
                      "time": str(props.get("fromdate") or ""),
                      "url": str((props.get("url") or {}).get("report", "") if isinstance(props.get("url"), dict) else "")})
    return items


def parse_iss(data: dict[str, Any]) -> list[dict[str, Any]]:
    lat, lon = _num(data.get("latitude")), _num(data.get("longitude"))
    if lat is None or lon is None:
        return []
    return [{"id": "iss", "kind": "iss", "lat": lat, "lon": lon, "title": "International Space Station",
             "detail": f"{_num(data.get('altitude')) or 0:.0f} km up · {_num(data.get('velocity')) or 0:,.0f} km/h",
             "time_ms": int((data.get("timestamp") or 0) * 1000)}]


def kp_level(kp: float) -> str:
    return ("quiet" if kp < 4 else "unsettled" if kp < 5 else f"storm G{min(5, int(kp) - 4)}")


def parse_swpc(data: list[Any]) -> list[dict[str, Any]]:
    rows = [r for r in data if isinstance(r, dict) and _num(r.get("Kp")) is not None]
    if not rows:
        return []
    last = rows[-1]
    kp = float(last["Kp"])
    return [{"id": "kp", "kind": "space", "title": f"Kp {kp:.1f} · {kp_level(kp)}", "kp": kp,
             "level": kp_level(kp), "time": str(last.get("time_tag") or "")}]


def parse_jamcams(data: list[Any]) -> list[dict[str, Any]]:
    items = []
    for cam in data if isinstance(data, list) else []:
        props = {p.get("key"): p for p in cam.get("additionalProperties", []) if isinstance(p, dict)}
        lat, lon = _num(cam.get("lat")), _num(cam.get("lon"))
        image = str((props.get("imageUrl") or {}).get("value") or "")
        if lat is None or lon is None or not image.startswith("https://") or (props.get("available") or {}).get("value") == "false":
            continue
        items.append({"id": str(cam.get("id", "")), "kind": "camera", "lat": lat, "lon": lon,
                      "title": str(cam.get("commonName") or "Traffic camera"),
                      "detail": "Looking " + str((props.get("view") or {}).get("value") or "").lower(),
                      "image": image, "time": str((props.get("imageUrl") or {}).get("modified") or "")})
    return items


MARKETS = (("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow Jones"), ("^FTSE", "FTSE 100"), ("^GDAXI", "DAX"),
           ("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"), ("GC=F", "Gold"), ("CL=F", "Oil (WTI)"),
           ("GBPUSD=X", "GBP/USD"), ("EURUSD=X", "EUR/USD"), ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"))
CRYPTO = (("bitcoin", "Bitcoin"), ("ethereum", "Ethereum"))   # CoinGecko, only if Yahoo has no crypto quote


def fetch_markets(fetch: Callable[[str], bytes]) -> list[dict[str, Any]]:
    """Index, commodity and FX quotes (delayed) plus crypto; each row names its own source."""
    rows = []
    for symbol, name in MARKETS:
        try:
            data = json.loads(fetch("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol)
                                    + "?range=1d&interval=15m").decode("utf-8"))
            result = data["chart"]["result"][0]
            meta = result["meta"]
            price, prev = float(meta["regularMarketPrice"]), float(meta.get("chartPreviousClose") or 0)
            closes = [c for c in ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [] if c is not None]
            step = max(1, len(closes) // 40)
            series = [round(c, 4) for c in closes[::step]]
            rows.append({"id": symbol, "kind": "market", "title": name, "price": price,
                         "change_pct": round((price - prev) / prev * 100, 2) if prev else None,
                         "currency": str(meta.get("currency") or ""), "time_ms": int(meta.get("regularMarketTime") or 0) * 1000,
                         "previous": prev, "series": series, "source": "Yahoo Finance (delayed)"})
        except Exception:        # one quote failing never hides the others
            continue
    have = {r["title"] for r in rows}
    missing = [(c, n) for c, n in CRYPTO if n not in have]
    try:
        if not missing:
            raise LookupError
        ids = ",".join(c for c, _ in missing)
        data = json.loads(fetch(f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true"
                                "&include_last_updated_at=true").decode("utf-8"))
        for coin, name in missing:
            q = data.get(coin) or {}
            if "usd" in q:
                rows.append({"id": coin, "kind": "market", "title": name, "price": float(q["usd"]),
                             "change_pct": round(float(q.get("usd_24h_change") or 0), 2), "currency": "USD",
                             "time_ms": int(q.get("last_updated_at") or 0) * 1000, "source": "CoinGecko"})
    except Exception:
        pass
    if not rows:
        raise OSError("no market source answered")
    return rows


NEWS_QUERY = "(protest OR conflict OR election OR sanctions OR ceasefire OR coup) sourcelang:english"
# BBC News feeds by topic: (source name, section, feed). World feeds the Atlas news layer; Ask's news
# catch-up (briefing.py) also reads Technology and Science.
BBC_FEEDS = {
    "world": ("BBC World", "World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    "tech": ("BBC Technology", "Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    "science": ("BBC Science", "Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
}
# The newest BBC headlines per topic, as last fetched by anything in Home (the Atlas or Ask), so Ask's
# catch-up can reuse them: {topic: (time.monotonic() when fetched, rows)}.
_HEADLINES: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_HEADLINES_LOCK = threading.Lock()


def parse_bbc(data: bytes, topic: str = "world") -> list[dict[str, Any]]:
    from email.utils import parsedate_to_datetime
    source, section, _ = BBC_FEEDS[topic]
    rows = []
    for item in ElementTree.fromstring(data).iter("item"):
        when = ""
        try:
            when = parsedate_to_datetime(item.findtext("pubDate") or "").isoformat()
        except (TypeError, ValueError):
            pass
        title, link = (item.findtext("title") or "").strip(), (item.findtext("link") or "").strip()
        if "at_medium=" in link:                    # the feed's tracking tags: the plain article link is enough
            link = link.split("?", 1)[0]
        if title:
            rows.append({"id": link, "kind": "news", "title": title, "detail": f"BBC News · {section}", "time": when,
                         "url": link, "source": source, "topic": topic})
    return rows


def fetch_bbc(fetch: Callable[[str], bytes], topic: str) -> list[dict[str, Any]]:
    """One BBC feed, newest first; remembered for Ask's catch-up. Raises when it can't be read."""
    rows = sorted(parse_bbc(fetch(BBC_FEEDS[topic][2]), topic), key=lambda r: r.get("time") or "", reverse=True)
    with _HEADLINES_LOCK:
        _HEADLINES[topic] = (time.monotonic(), rows)
    return rows


def recent_headlines(topic: str, max_age: float) -> list[dict[str, Any]] | None:
    """The topic's headlines if something fetched them within max_age seconds, else None."""
    with _HEADLINES_LOCK:
        hit = _HEADLINES.get(topic)
    return list(hit[1]) if hit and time.monotonic() - hit[0] <= max_age else None


def fetch_news(fetch: Callable[[str], bytes], topics: tuple[str, ...] = ("world",)) -> list[dict[str, Any]]:
    """Headlines, newest first. World (the Atlas layer): GDELT political news (last 24 h) and BBC World.
    "tech" and "science" add BBC Technology and BBC Science. Not placed on the map."""
    rows = []
    if "world" in topics:
        try:
            url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(NEWS_QUERY)
                   + "&mode=ArtList&maxrecords=40&format=json&timespan=24h&sort=DateDesc")
            for a in json.loads(fetch(url).decode("utf-8", "replace")).get("articles", []):
                rows.append({"id": str(a.get("url", "")), "kind": "news", "title": str(a.get("title") or "").strip(),
                             "detail": " · ".join(x for x in (str(a.get("domain") or ""), str(a.get("sourcecountry") or "")) if x),
                             "time": _gdelt_time(str(a.get("seendate") or "")), "url": str(a.get("url") or ""), "source": "GDELT",
                             "topic": "world"})
        except Exception:
            pass
    for topic in topics:
        try:
            rows += fetch_bbc(fetch, topic)
        except Exception:
            pass
    if not rows:
        raise OSError("no news source answered")
    rows.sort(key=lambda r: r.get("time") or "", reverse=True)
    return rows[:60]


def _gdelt_time(stamp: str) -> str:
    """20260925T183000Z -> 2026-09-25T18:30:00Z"""
    if len(stamp) >= 15 and stamp[8] == "T":
        return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
    return ""


@dataclass(frozen=True)
class Layer:
    key: str
    name: str
    source: str
    licence: str
    url: str
    every_s: float
    parse: Callable[[Any], list[dict[str, Any]]]
    custom: Callable[[Callable[[str], bytes]], list[dict[str, Any]]] | None = None   # fetches several URLs itself


LAYERS = (
    Layer("quakes", "Earthquakes (M2.5+, 24 h)", "USGS", "US Government public domain",
          "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson", 300, parse_usgs),
    Layer("events", "Natural events", "NASA EONET", "NASA open data",
          "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30", 1800, parse_eonet),
    Layer("alerts", "Disaster alerts", "GDACS (UN / European Commission)", "GDACS, free with attribution",
          "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP", 900, parse_gdacs),
    Layer("iss", "ISS position", "wheretheiss.at", "free public API",
          "https://api.wheretheiss.at/v1/satellites/25544", 10, parse_iss),
    Layer("space", "Space weather", "NOAA SWPC", "US Government public domain",
          "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json", 900, parse_swpc),
    Layer("cameras", "Traffic cameras (London)", "TfL JamCams", "Powered by TfL Open Data",
          "https://api.tfl.gov.uk/Place/Type/JamCam", 3600, parse_jamcams),
    Layer("markets", "Markets", "Yahoo Finance (delayed) + CoinGecko", "public quote data, delayed",
          "", 300, lambda _: [], custom=fetch_markets),
    Layer("news", "World news", "GDELT + BBC World", "headlines link to their publishers",
          "", 1800, lambda _: [], custom=fetch_news),
)


@dataclass
class LayerState:
    status: str = "waiting"          # waiting | live | unavailable
    items: list[dict[str, Any]] = field(default_factory=list)
    fetched_at: str | None = None
    fetched_mono: float | None = None
    error: str | None = None
    next_due: float = 0.0


class OsintFeed:
    def __init__(self, fetch: Fetch = _fetch, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._fetch, self._now = fetch, monotonic
        self.states = {layer.key: LayerState() for layer in LAYERS}

    def poll(self, on_change: Callable[[], None] | None = None) -> bool:
        """Fetch every layer that is due; True if anything changed.

        on_change runs after each layer that changed, so a slow source (GDELT)
        never holds back the layers that already answered."""
        changed = False
        for layer in LAYERS:
            state = self.states[layer.key]
            if self._now() < state.next_due:
                continue
            state.next_due = self._now() + layer.every_s
            try:
                state.items = (layer.custom(self._fetch) if layer.custom
                               else layer.parse(json.loads(self._fetch(layer.url).decode("utf-8"))))
                state.status, state.error = "live", None
                state.fetched_at, state.fetched_mono = utc_now(), self._now()
            except Exception as exc:     # network, HTTP, bad JSON: the layer says it is unavailable
                state.status, state.items = "unavailable", []
                state.error = (f"{layer.source} could not be reached" if isinstance(exc, OSError)
                               else f"{layer.source} sent data APVIS could not read")
                state.next_due = self._now() + min(layer.every_s, 120)
            changed = True
            if on_change is not None:
                on_change()
        return changed

    def snapshot(self) -> dict[str, Any]:
        out = {}
        for layer in LAYERS:
            state = self.states[layer.key]
            age = None if state.fetched_mono is None else round(self._now() - state.fetched_mono)
            out[layer.key] = {"name": layer.name, "source": layer.source, "licence": layer.licence,
                              "status": state.status, "fetched_at": state.fetched_at, "age_s": age,
                              "error": state.error, "items": state.items}
        return out
