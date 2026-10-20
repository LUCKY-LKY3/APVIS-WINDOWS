"""Pictures (owner, 2026-10-09; brought back from APVIS 7): "show me a picture of Paris" pops up a real photo.

Photos come from Wikimedia Commons (free, no account), always shown with their source, author and licence.
One of the best few matches is picked at random, so asking again shows another. Images are cached in the
state dir (at most MAX_CACHED). Only https://commons.wikimedia.org (search) and https://upload.wikimedia.org
and https://thumb.wikimedia.org (the image) are contacted; nothing about the owner is sent except the words of the request.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_CACHED = 12
USER_AGENT = "APVIS-OS/3 (personal desktop assistant; shows Wikimedia attribution)"
_BLOCKED = ("task", "memory", "setting", "log", "password", "api key", "my screen", "screen")
_PATTERNS = (
    re.compile(r"\bwhat (?:does|do) (.+?) look like\??$", re.I),
    re.compile(r"\b(?:show|find|pull up|bring up|display|get) (?:me )?(?:a |an |the |some )?(?:photo|picture|pic|image|visual)s? (?:of )?(?:a |an |the )?(.+?)\??$", re.I),
    re.compile(r"\b(?:pull up|bring up|show) (?:me )?(?:a |an |the )?(.+?) (?:photo|picture|pic|image)s?\??$", re.I),
    re.compile(r"^(?:a |an )?(?:photo|picture|pic|image)s? of (?:a |an |the )?(.+?)\??$", re.I),
)
# "What does a healthy diet / a good CV / the future look like?" asks for a description, not a photo (V4:
# these used to answer with a Commons picture instead of an answer).
_IDEA = re.compile(r"(?i)\b(?:it|this|that|they|them|he|she|my|your|our|their|good|great|typical|normal|ideal|healthy|"
                   r"average|perfect|successful|best|future|day|week|month|year|life|plan|routine|process|career|resume|"
                   r"cv|diet|budget|schedule|relationship|job|interview|essay|letter|code|output|result|answer|"
                   r"recession|world|economy|market|success)\b")


def visual_query(text: str) -> str | None:
    """The thing to picture, when the owner asks to see one; None otherwise."""
    cleaned = " ".join((text or "").strip().split())
    if not cleaned or any(word in cleaned.lower() for word in _BLOCKED):
        return None
    for i, pattern in enumerate(_PATTERNS):
        match = pattern.search(cleaned)
        if match:
            query = match.group(1).strip(" .?!,:;\"'")
            if i == 0 and _IDEA.search(query):
                return None
            return query[:100] if len(query) >= 2 else None
    return None


def _https(url: str, *hosts: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in hosts


def _plain(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def cache_dir() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "pictures"


def _get(url: str, limit: int, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("too large")
    return data


def find(query: str, *, fetch: Callable[[str, int, float], bytes] = _get, rng: random.Random | None = None,
         folder: Path | None = None, timeout: float = 8.0) -> dict[str, Any] | None:
    """A photo for `query`: {file, caption, credit, source, query}; None if nothing usable was found."""
    query = " ".join((query or "").split())[:100]
    if len(query) < 2:
        return None
    params = {"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap -map -plan -engraving -drawing -diagram", "gsrnamespace": 6,
              "gsrlimit": 8, "prop": "imageinfo|info", "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1280,
              "inprop": "url", "format": "json", "formatversion": 2}
    try:
        payload = json.loads(fetch(COMMONS_API + "?" + urllib.parse.urlencode(params), 4 * 1024 * 1024, timeout))
    except (urllib.error.URLError, OSError, ValueError, UnicodeError):
        return None
    candidates = []
    for page in (payload.get("query") or {}).get("pages") or []:
        info = ((page or {}).get("imageinfo") or [{}])[0] if isinstance(page, dict) else {}
        if not isinstance(info, dict) or str(info.get("mime")) not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        if int(info.get("width") or 0) < 640:
            continue                                     # skip icons, maps and small scans
        image = str(info.get("thumburl") or info.get("url") or "")
        source = str(page.get("canonicalurl") or page.get("fullurl") or "")
        if not (_https(image, "upload.wikimedia.org", "thumb.wikimedia.org") and _https(source, "commons.wikimedia.org")):
            continue
        meta = info.get("extmetadata") or {}
        caption = _plain(str((meta.get("ImageDescription") or {}).get("value") or "")) or \
            str(page.get("title") or query).removeprefix("File:").rsplit(".", 1)[0]
        artist = _plain(str((meta.get("Artist") or {}).get("value") or ""))
        licence = _plain(str((meta.get("LicenseShortName") or {}).get("value") or ""))
        credit = " · ".join(p for p in (artist[:80], licence) if p)
        candidates.append((page.get("index", 99), image, source, caption[:240], credit))
    candidates.sort(key=lambda c: c[0])
    pool = candidates[:4]
    (rng or random.Random()).shuffle(pool)
    folder = folder or cache_dir()
    for _, image, source, caption, credit in pool:
        name = hashlib.sha256(image.encode()).hexdigest()[:20] + Path(urlparse(image).path).suffix.lower()[:5]
        path = folder / name
        try:
            if not path.exists():
                data = fetch(image, MAX_IMAGE_BYTES, timeout)
                folder.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                _trim(folder, keep=path)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        return {"file": str(path), "caption": caption, "credit": credit, "source": source, "query": query}
    return None


def aircraft(registration: str, type_name: str = "", type_code: str = "", *,
             fetch: Callable[[str, int, float], bytes] = _get, folder: Path | None = None,
             timeout: float = 8.0) -> dict[str, Any] | None:
    """A photo for a plane picked on the Atlas (V4): this very airframe when Commons has one (by its
    registration), otherwise its type. The same plane always gets the same photo (no random pick).
    Adds "match": "this aircraft" | "type" so the UI can say which it is."""
    reg = re.sub(r"[^A-Za-z0-9-]", "", registration or "")[:10]
    name = " ".join(re.sub(r"[^A-Za-z0-9 .()-]", " ", type_name or "").split())[:60]
    code = re.sub(r"[^A-Za-z0-9]", "", type_code or "")[:6]
    tries: list[tuple[str, str]] = []
    if reg and name:
        tries.append((f"{reg} {name}", "this aircraft"))
    if reg:
        tries.append((f'"{reg}" aircraft', "this aircraft"))
    if name:
        tries.append((f"{name} aircraft", "type"))
    elif code:
        tries.append((f"{code} aircraft", "type"))
    for query, match in tries:
        got = find(query, fetch=fetch, rng=random.Random(query), folder=folder, timeout=timeout)
        if got:
            return {**got, "match": match}
    return None


def _trim(folder: Path, keep: Path) -> None:
    files = sorted((p for p in folder.iterdir() if p.is_file() and p != keep), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[MAX_CACHED - 1:]:
        old.unlink(missing_ok=True)
