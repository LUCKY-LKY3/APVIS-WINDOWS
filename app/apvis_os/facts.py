"""Questions about this computer, answered by measuring it (System Graph, V2-11).

"What's my IP?", "what's using my CPU?", "how much memory is free?" are facts
the machine can report exactly; a language model would only guess. Each answer
names what was measured. Unsupported questions return None and go to Ask.
"""
from __future__ import annotations

import re
import socket
import time
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - psutil ships in the image
    psutil = None  # type: ignore[assignment]

_Q = r"(?i)^\s*(?:hey\s+apvis[,\s]*)?(?:please\s+)?"
_END = r"\s*[?.!]*\s*$"
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ip", re.compile(_Q + r"(?:what(?:'?s| is)\s+)?(?:my|the|this\s+computer'?s?)\s+(?:local\s+)?ip(?:\s+address)?" + _END)),
    ("cpu_top", re.compile(_Q + r"what(?:'?s| is)\s+(?:using|eating|hogging)\s+(?:my|the|all\s+(?:my|the))?\s*(?:cpu|processor)" + _END)),
    ("mem_top", re.compile(_Q + r"what(?:'?s| is)\s+(?:using|eating|hogging)\s+(?:my|the|all\s+(?:my|the))?\s*(?:memory|ram)" + _END)),
    ("memory", re.compile(_Q + r"(?:how\s+much\s+(?:free\s+)?(?:memory|ram)(?:\s+(?:do\s+i\s+have|is\s+(?:free|left|used)))?"
                          r"|(?:what(?:'?s| is)\s+)?(?:my\s+)?(?:memory|ram)\s+usage)" + _END)),
    ("uptime", re.compile(_Q + r"(?:how\s+long\s+(?:has\s+(?:this|the|my)\s+(?:computer|pc)\s+been\s+(?:on|up|running)|have\s+i\s+been\s+on)"
                          r"|(?:what(?:'?s| is)\s+(?:the|my)\s+)?uptime)" + _END)),
    ("battery", re.compile(_Q + r"(?:how\s+much\s+battery(?:\s+(?:do\s+i\s+have|is\s+left))?|(?:what(?:'?s| is)\s+)?(?:(?:my|the)\s+)?battery(?:\s+level)?)" + _END)),
    ("health", re.compile(_Q + r"(?:(?:analy[sz]e|check|scan)\s+(?:my|this|the)\s+(?:computer|pc|system)"
                          r"|how(?:'?s| is)\s+(?:my|this|the)\s+(?:computer|pc|system)(?:\s+doing)?"
                          r"|(?:run\s+(?:a\s+)?)?system\s+(?:check|health|status))" + _END)),
    ("disk_top", re.compile(_Q + r"(?:what(?:'?s| is)\s+(?:using|eating|taking(?:\s+up)?|filling)\s+(?:up\s+)?(?:all\s+)?(?:my|the)\s+(?:disk|storage|drive|space)(?:\s+space)?"
                            r"|why\s+is\s+my\s+(?:disk|storage|drive)\s+(?:so\s+)?full)" + _END)),
    ("hostname", re.compile(_Q + r"what(?:'?s| is)\s+(?:this|my)\s+computer(?:'s)?\s+(?:called|name)" + _END)),
]


def match(question: str) -> str | None:
    for key, pattern in PATTERNS:
        if pattern.match(question or ""):
            return key
    return None


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


def _top(field: str) -> list[tuple[str, float]]:
    """Top three process names by CPU or memory share (same-named processes summed)."""
    procs = list(psutil.process_iter(["name", "memory_percent"]))
    rows: list[tuple[str, float]] = []
    if field == "cpu_percent":
        # cpu_percent needs two readings; measure over a short window.
        for p in procs:
            try:
                p.cpu_percent(None)
            except (psutil.Error, OSError):
                pass
        psutil.cpu_percent(None)
        time.sleep(0.5)
        cores = max(1, psutil.cpu_count() or 1)
        for p in procs:
            try:
                rows.append((p.info["name"] or "?", p.cpu_percent(None) / cores))
            except (psutil.Error, OSError):
                continue
    else:
        rows = [(p.info["name"] or "?", p.info.get("memory_percent") or 0.0) for p in procs]
    merged: dict[str, float] = {}
    for name, value in rows:
        if name in {"System Idle Process", "idle"}:
            continue
        merged[name] = merged.get(name, 0.0) + value
    return sorted(merged.items(), key=lambda kv: -kv[1])[:3]


def answer(key: str) -> str:
    if key == "disk_top":
        from .health import disk_answer
        return disk_answer()
    if psutil is None:
        return "System measurements are unavailable on this computer."
    if key == "ip":
        found = []
        for name, addrs in psutil.net_if_addrs().items():
            if name == "lo" or name.startswith(("docker", "veth", "virbr")):
                continue
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    found.append(f"{a.address} ({name})")
        return ("Your local IP: " + ", ".join(found) + ". This is the address on your home network, not your public one.") \
            if found else "No network address right now: this computer is not connected."
    if key in {"cpu_top", "mem_top"}:
        field = "cpu_percent" if key == "cpu_top" else "memory_percent"
        top = _top(field)
        total = psutil.cpu_percent(interval=None) if key == "cpu_top" else psutil.virtual_memory().percent
        what = "CPU" if key == "cpu_top" else "memory"
        listing = "; ".join(f"{name} {value:.0f}%" for name, value in top if value >= 0.5) or "nothing stands out"
        return f"Total {what} use is {total:.0f}%. Biggest users: {listing}."
    if key == "memory":
        vm = psutil.virtual_memory()
        return f"{_gb(vm.available)} of {_gb(vm.total)} memory is available ({vm.percent:.0f}% in use)."
    if key == "uptime":
        seconds = int(time.time() - psutil.boot_time())
        h, m = seconds // 3600, seconds % 3600 // 60
        return f"This computer has been on for {h} h {m} min."
    if key == "battery":
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if battery is None:
            return "This computer has no battery; it runs on mains power."
        state = "charging" if battery.power_plugged else "on battery"
        return f"Battery is at {battery.percent:.0f}% ({state})."
    if key == "hostname":
        return f"This computer is called {socket.gethostname()}."
    if key == "health":
        return health_report()
    raise KeyError(key)


def measured_answer(question: str) -> dict[str, Any] | None:
    key = match(question)
    if key is None:
        return None
    return {"answer": answer(key), "meta": "a measurement on this computer just now · no model used"}


def health_report() -> str:
    """The "Analyse" check: CPU (with its biggest user), memory, disk, uptime and
    the hottest sensor, then a verdict. Every number is measured now."""
    top = _top("cpu_percent")
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    parts, issues = [], []
    busiest = f" (most: {top[0][0]} {top[0][1]:.0f}%)" if top and top[0][1] >= 1 else ""
    parts.append(f"CPU {cpu:.0f}%{busiest}")
    parts.append(f"memory {vm.percent:.0f}% used ({_gb(vm.available)} free)")
    try:
        import shutil
        from pathlib import Path
        du = shutil.disk_usage(Path.home())
        disk = 100 * du.used / du.total
        parts.append(f"disk {disk:.0f}% full ({du.free / 1e9:.0f} GB free)")
        if disk >= 90:
            issues.append("the disk is nearly full")
    except OSError:
        pass
    seconds = int(time.time() - psutil.boot_time())
    parts.append(f"on for {seconds // 3600} h {seconds % 3600 // 60} min")
    hottest = None
    try:
        for entries in (psutil.sensors_temperatures() or {}).values():
            for e in entries:
                if e.current and 0 < e.current < 130 and (hottest is None or e.current > hottest):
                    hottest = e.current
    except (AttributeError, OSError):
        pass
    if hottest is not None:
        parts.append(f"hottest sensor {hottest:.0f} °C")
        if hottest >= 85:
            issues.append("it is running hot")
    if cpu >= 85:
        issues.append("the CPU is very busy")
    if vm.percent >= 90:
        issues.append("memory is nearly full")
    verdict = "Everything looks healthy." if not issues else "Worth a look: " + ", ".join(issues) + "."
    return "System check: " + "; ".join(parts) + ". " + verdict
