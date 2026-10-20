"""Health guard: APVIS keeps an eye on this computer and speaks up before things go wrong.

Checked every 15 s from real measurements (psutil, disk usage, hardware sensors):
  disk     free space on the system disk and home   (< 10 % warning, < 5 % critical)
  memory   available memory, sustained for a minute  (< 8 % warning, < 4 % critical)
  heat     hottest CPU sensor                        (>= 85 C warning, >= 95 C or the sensor's own critical)
Each alert says what was measured and offers a next step that only opens or explains
something; nothing is deleted or ended without the owner doing it.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ships in the image
    psutil = None  # type: ignore[assignment]

DISK_WARN, DISK_CRIT = 10.0, 5.0          # % free
MEM_WARN, MEM_CRIT = 8.0, 4.0             # % available
HEAT_WARN, HEAT_CRIT = 85.0, 95.0         # degrees C
MEM_SUSTAIN_S = 60.0
RENOTIFY_S = 30 * 60


@dataclass(frozen=True)
class Alert:
    id: str                    # disk:/, memory, heat
    level: str                 # warning | critical
    title: str
    detail: str
    action: str = ""           # an APVIS action key (page:system, ask:...) the owner can press
    action_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure(home: Path | None = None) -> dict[str, Any]:
    """One reading of everything the guard checks (missing parts are left out)."""
    out: dict[str, Any] = {"disks": {}}
    for label, path in (("system", Path("/")), ("home", home or Path.home())):
        try:
            usage = shutil.disk_usage(path)
            out["disks"][label] = {"path": str(path), "free_pct": 100 * usage.free / usage.total, "free": usage.free}
        except OSError:
            pass
    if psutil is not None:
        vm = psutil.virtual_memory()
        out["memory"] = {"available_pct": 100 * vm.available / vm.total, "available": vm.available}
        try:
            temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        except (OSError, RuntimeError):
            temps = {}
        hottest = None
        for name, entries in (temps or {}).items():
            for entry in entries:
                if entry.current and (hottest is None or entry.current > hottest["current"]):
                    hottest = {"sensor": f"{name} {entry.label}".strip(), "current": float(entry.current),
                               "critical": float(entry.critical) if entry.critical else None}
        if hottest:
            out["heat"] = hottest
    return out


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


class HealthGuard:
    """Turns readings into alerts, with a minute's patience for memory and no repeated nagging."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._low_memory_since: float | None = None
        self._notified: dict[str, float] = {}

    def check(self, reading: dict[str, Any]) -> list[Alert]:
        alerts: list[Alert] = []
        seen: set[str] = set()
        for label, disk in reading.get("disks", {}).items():
            free = disk["free_pct"]
            key = "disk:" + disk["path"]
            if free < DISK_WARN and key not in seen and not any(a.detail.endswith(f"({disk['path']})") for a in alerts):
                seen.add(key)
                where = "the system disk" if label == "system" else "your home folder's disk"
                alerts.append(Alert(key, "critical" if free < DISK_CRIT else "warning",
                                    f"Disk almost full: {free:.0f}% free",
                                    f"Only {_gb(disk['free'])} left on {where} ({disk['path']})",
                                    "ask:what is using my disk space", "What's using it?"))
        memory = reading.get("memory")
        if memory:
            if memory["available_pct"] < MEM_WARN:
                if self._low_memory_since is None:
                    self._low_memory_since = self._clock()
                if self._clock() - self._low_memory_since >= MEM_SUSTAIN_S:
                    alerts.append(Alert("memory", "critical" if memory["available_pct"] < MEM_CRIT else "warning",
                                        f"Memory running out: {memory['available_pct']:.0f}% free",
                                        f"Only {_gb(memory['available'])} available for more than a minute",
                                        "page:system", "See what's using it"))
            else:
                self._low_memory_since = None
        heat = reading.get("heat")
        if heat:
            critical = min(heat["critical"] or HEAT_CRIT, HEAT_CRIT)
            if heat["current"] >= min(HEAT_WARN, critical - 5):
                alerts.append(Alert("heat", "critical" if heat["current"] >= critical else "warning",
                                    f"Running hot: {heat['current']:.0f} °C",
                                    f"{heat['sensor'] or 'CPU'} is at {heat['current']:.0f} °C. Check the vents are clear; "
                                    "heavy AI answers and the core animation add heat.",
                                    "page:system", "See what's busy"))
        return alerts

    def to_notify(self, alerts: list[Alert]) -> list[Alert]:
        """New (or long-standing) alerts worth a desktop notification right now."""
        now = self._clock()
        fresh = [a for a in alerts if now - self._notified.get(a.id, -1e9) >= RENOTIFY_S]
        for alert in fresh:
            self._notified[alert.id] = now
        return fresh


def largest_folders(home: Path | None = None, *, limit: int = 6, budget_s: float = 4.0) -> list[tuple[str, int]]:
    """The biggest folders in the owner's home (sizes of their contents), measured within a time budget."""
    home = home or Path.home()
    deadline = time.monotonic() + budget_s
    sizes: list[tuple[str, int]] = []
    try:
        children = [p for p in home.iterdir() if p.is_dir() and not p.is_symlink()]
    except OSError:
        return []
    extra = [home / ".cache", home / ".local/share/Trash", home / ".ollama", home / ".local/share/flatpak"]
    for folder in children + [e for e in extra if e.is_dir() and e not in children]:
        total = 0
        for top, dirs, files in os.walk(folder, onerror=lambda e: None):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(top, d))]
            for name in files:
                try:
                    total += os.lstat(os.path.join(top, name)).st_size
                except OSError:
                    pass
            if time.monotonic() > deadline:
                break
        sizes.append((str(folder.relative_to(home)) if folder.is_relative_to(home) else str(folder), total))
        if time.monotonic() > deadline:
            break
    return sorted(sizes, key=lambda s: -s[1])[:limit]


def disk_answer(home: Path | None = None) -> str:
    home = home or Path.home()
    reading = measure(home)
    parts = []
    for label, disk in reading["disks"].items():
        parts.append(f"{'System disk' if label == 'system' else 'Home'}: {_gb(disk['free'])} free ({disk['free_pct']:.0f}%)")
    top = [(name, size) for name, size in largest_folders(home) if size >= 50 * 1024 ** 2]
    listing = "; ".join(f"{name} {_gb(size)}" for name, size in top) or "no folder in your home is over 50 MB"
    hints = []
    names = {name for name, _ in top}
    if ".local/share/Trash" in names:
        hints.append("emptying the Trash in Files frees that space")
    if ".cache" in names:
        hints.append(".cache holds app caches that are safe to clear")
    return (". ".join(dict.fromkeys(parts)) + f". Biggest folders in your home: {listing}." +
            (" Tip: " + "; ".join(hints) + "." if hints else ""))
