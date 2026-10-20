"""One local search across apps, pages, settings, vault notes, missions and home files (V2-05).

Everything is read from this machine; nothing is sent anywhere. Results carry a
kind and a key, and only a result this index produced can be opened, so the UI
cannot ask it to run an arbitrary command or path.
"""
from __future__ import annotations

import configparser
import os
import re
import shlex
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from urllib.request import url2pathname
from xml.etree import ElementTree

# Home surfaces and Settings sections that search can jump to.
PAGES = (
    ("home", "Home", "The core, system status, devices and live intelligence", ("core", "nucleus", "dashboard", "desktop")),
    ("missions", "Automation", "Missions: requests, approvals and history", ("tasks", "approve", "actions", "mission control")),
    ("atlas", "Intelligence", "The world atlas: quakes, disasters, flights, markets, news", ("atlas", "map", "globe", "flights", "osiris", "aviation", "planes", "news", "markets")),
    ("system", "System", "Live monitor: CPU, memory, cores, temperatures, programs", ("monitor", "task manager", "processes", "cpu", "temperature", "performance")),
    ("devices", "Devices", "This computer, displays, storage, network, local AI", ("hardware", "about", "specs", "disks", "storage", "gpu")),
    ("notes", "Memory", "What APVIS remembers, and what waits for review", ("vault", "notes", "inbox", "remember", "markdown")),
    ("settings", "Settings", "AI host, appearance and system", ("preferences", "config", "options")),
)
SETTINGS = (
    ("ollama", "Local AI address", "Where Ask finds Ollama on your network", ("ollama", "ai", "model", "llm", "optiplex", "server")),
    ("displays", "Displays", "Resolution, scale and arrangement", ("screen", "monitor", "resolution", "scale")),
    ("sound", "Sound", "Output, input and volume", ("volume", "speaker", "microphone", "audio")),
    ("network", "Network", "Wi-Fi and wired connections", ("wifi", "wi-fi", "internet", "ethernet")),
)
FILE_LIMIT = 4000
FILE_DEPTH = 5
FILE_TTL = 60.0


@dataclass(frozen=True)
class Hit:
    kind: str       # app | page | setting | note | mission | file | folder
    key: str
    title: str
    detail: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(query: str, title: str, extra: Iterable[str] = ()) -> float:
    """3 = title starts with it, 2 = a word starts with it, 1 = contained; extras score lower."""
    q, t = query.lower(), title.lower()
    if not q:
        return 0.0
    if t == q:
        return 3.5
    if t.startswith(q):
        return 3.0
    if any(word.startswith(q) for word in re.split(r"[\s._\-/]+", t)):
        return 2.0
    if q in t:
        return 1.0
    for word in extra:
        w = word.lower()
        if w.startswith(q) or q.startswith(w) and len(w) > 2:
            return 0.8
        if q in w:
            return 0.5
    return 0.0


@dataclass(frozen=True)
class App:
    name: str
    comment: str
    keywords: tuple[str, ...]
    argv: tuple[str, ...]


def desktop_apps(dirs: Iterable[Path]) -> list[App]:
    """Installed, visible desktop entries; Exec is split into argv, never run through a shell."""
    seen: dict[str, App] = {}
    for directory in dirs:
        for entry in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read(entry, encoding="utf-8")
                section = parser["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
                continue
            if section.get("Type", "Application") != "Application" or \
                    section.get("NoDisplay", "false").lower() == "true" or section.get("Hidden", "false").lower() == "true":
                continue
            try:
                argv = tuple(a for a in shlex.split(section.get("Exec", "")) if not re.fullmatch(r"%[a-zA-Z]", a))
            except ValueError:
                continue
            name = section.get("Name", "").strip()
            if not argv or not name or entry.stem in seen:
                continue
            words = tuple(w for w in re.split(r"[;,]", section.get("Keywords", "") + ";" + section.get("GenericName", "")) if w.strip())
            seen[entry.stem] = App(name, section.get("Comment", "").strip(), words, argv)
    return list(seen.values())


class SearchIndex:
    def __init__(self, home: Path | None = None, *, app_dirs: list[Path] | None = None,
                 notes: Callable[[], list[dict[str, Any]]] | None = None,
                 missions: Callable[[], list[dict[str, Any]]] | None = None, vault_root: Path | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        self.vault_root = (vault_root or self.home / "APVIS Vault").resolve()
        self.app_dirs = app_dirs or [self.home / ".local/share/applications", Path("/usr/share/applications")]
        self._notes = notes or (lambda: [])
        self._missions = missions or (lambda: [])
        self._apps: dict[str, App] = {}
        self._files: list[tuple[str, bool]] = []
        self._files_at = float("-inf")     # never scanned (monotonic time starts near 0 at boot)
        self._last: dict[tuple[str, str], Hit] = {}

    # ---- sources
    def _refresh_apps(self) -> None:
        self._apps = {"app:" + a.name: a for a in desktop_apps(self.app_dirs)}

    def _refresh_files(self) -> None:
        """Names under home only: hidden folders skipped, bounded depth and count."""
        found: list[tuple[str, bool]] = []
        for top, dirs, files in os.walk(self.home):
            rel_depth = len(Path(top).relative_to(self.home).parts)
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not Path(top, d).is_symlink())
            if rel_depth >= FILE_DEPTH:
                dirs[:] = []
            for d in dirs:
                found.append((str(Path(top, d)), True))
            for f in sorted(files):
                if not f.startswith("."):
                    found.append((str(Path(top, f)), False))
            if len(found) >= FILE_LIMIT:
                break
        self._files, self._files_at = found[:FILE_LIMIT], time.monotonic()

    def recent(self, limit: int = 8) -> list[Hit]:
        """Recently opened files from the freedesktop list (~/.local/share/recently-used.xbel), newest first."""
        xbel = self.home / ".local/share/recently-used.xbel"
        try:
            root = ElementTree.parse(xbel).getroot()
        except (OSError, ElementTree.ParseError):
            return []
        items = []
        for mark in root.iter("bookmark"):
            href = mark.get("href", "")
            if not href.startswith("file://"):
                continue
            path = Path(url2pathname(urlparse(href).path)).resolve()
            if path.is_relative_to(self.home) and path.exists() and not any(p.startswith(".") for p in path.relative_to(self.home).parts):
                items.append((mark.get("modified") or mark.get("visited") or "", len(items), path))
        items.sort(reverse=True)  # newest first; later entries win same-second ties
        hits = []
        for _, _, path in items[:limit]:
            rel = str(path.parent.relative_to(self.home)).replace("\\", "/")
            hits.append(Hit("folder" if path.is_dir() else "file", str(path), path.name,
                            "Recent · " + ("~" if rel == "." else "~/" + rel), 0.0))
        return hits

    def remember(self, path: Path, keep: int = 200) -> None:
        """Record an opened file in the freedesktop recent list (newest kept, atomically replaced)."""
        xbel = self.home / ".local/share/recently-used.xbel"
        try:
            tree = ElementTree.parse(xbel)
            root = tree.getroot()
        except (OSError, ElementTree.ParseError):
            root = ElementTree.Element("xbel", {"version": "1.0"})
            tree = ElementTree.ElementTree(root)
        href = Path(path).resolve().as_uri()
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for mark in list(root.iter("bookmark")):
            if mark.get("href") == href:
                root.remove(mark)
        root.append(ElementTree.Element("bookmark", {"href": href, "added": stamp, "modified": stamp, "visited": stamp}))
        marks = list(root.iter("bookmark"))
        for old in marks[:-keep]:
            root.remove(old)
        xbel.parent.mkdir(parents=True, exist_ok=True)
        tmp = xbel.with_name(xbel.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, xbel)

    # ---- query
    def query(self, text: str, limit: int = 12) -> list[Hit]:
        q = " ".join(text.split())[:80]
        if not q:
            hits = self.recent()
            self._last = {(h.kind, h.key): h for h in hits}
            return hits
        if not self._apps:
            self._refresh_apps()
        if time.monotonic() - self._files_at > FILE_TTL:
            self._refresh_files()
        hits: list[Hit] = []
        for key, title, detail, extra in PAGES:
            if s := _score(q, title, extra):
                hits.append(Hit("page", key, title, detail, s + 0.3))
        for key, title, detail, extra in SETTINGS:
            if s := _score(q, title, extra):
                hits.append(Hit("setting", key, title, "Settings · " + detail, s + 0.2))
        for key, app in self._apps.items():
            if s := _score(q, app.name, app.keywords):
                hits.append(Hit("app", key, app.name, app.comment or "Application", s + 0.25))
        for note in self._notes():
            if s := _score(q, str(note.get("title", "")), [str(t) for t in note.get("tags", [])] + str(note.get("excerpt", "")).split()):
                hits.append(Hit("note", str(note.get("path", "")), str(note.get("title", "")), "Memory · " + str(note.get("kind", "note")), s + 0.1))
        for mission in self._missions():
            label = str(mission.get("asked") or mission.get("preview") or "")
            if s := _score(q, label, str(mission.get("preview", "")).split()):
                hits.append(Hit("mission", str(mission.get("id", "")), label, "Mission · " + str(mission.get("status", "")), s))
        for path, is_dir in self._files:
            if s := _score(q, Path(path).name):
                rel = str(Path(path).parent.relative_to(self.home)).replace("\\", "/")
                depth = 0 if rel == "." else rel.count("/") + 1
                hits.append(Hit("folder" if is_dir else "file", path, Path(path).name,
                                "~" if rel == "." else "~/" + rel, s - 0.2 - 0.05 * depth))
        hits.sort(key=lambda h: (-h.score, len(h.title), h.title.lower()))
        hits = hits[:limit]
        self._last = {(h.kind, h.key): h for h in hits}
        return hits

    def resolve(self, kind: str, key: str) -> dict[str, Any]:
        """What opening a result means. Only results from the latest query resolve."""
        hit = self._last.get((kind, key))
        if hit is None:
            raise KeyError("That result is no longer listed; search again.")
        if kind == "app":
            return {"do": "run", "argv": list(self._apps[key].argv)}
        if kind in {"file", "folder"}:
            path = Path(key).resolve()
            if not path.is_relative_to(self.home) or not path.exists():
                raise KeyError("That file is gone or outside your home folder.")
            return {"do": "open", "path": str(path), "folder": path.is_dir()}
        if kind == "note":
            path = (self.vault_root / key).resolve()
            if not path.is_relative_to(self.vault_root) or not path.is_file():
                raise KeyError("That note is gone from your vault.")
            return {"do": "open", "path": str(path), "folder": False}
        if kind == "mission":
            return {"do": "page", "page": "missions", "mission": key}
        if kind == "setting":
            return {"do": "setting", "section": key}
        return {"do": "page", "page": "" if key == "home" else key}
