"""Live system telemetry for the HUD: short histories and detail, all measured.

Everything here comes from psutil on this machine. Nothing is simulated: if a
reading is unavailable (no sensors, no permission), it is reported as missing
and the HUD shows a dash rather than an invented value.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

HISTORY = 120          # samples kept per series (at ~2.5 s = about 5 minutes)


class Telemetry:
    def __init__(self, history: int = HISTORY) -> None:
        self.series: dict[str, deque[float]] = {k: deque(maxlen=history) for k in ("cpu", "memory", "down", "up", "read", "write")}
        self._last_net: tuple[float, int, int] | None = None
        self._last_disk: tuple[float, int, int] | None = None
        self._proc_primed = False
        try:
            import psutil  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    @staticmethod
    def _rate(prev: tuple[float, int, int] | None, now: tuple[float, int, int]) -> tuple[float, float] | None:
        if prev is None or now[0] - prev[0] <= 0.2:
            return None
        dt = now[0] - prev[0]
        return max(0.0, (now[1] - prev[1]) / dt), max(0.0, (now[2] - prev[2]) / dt)

    def sample(self, detail: bool = False) -> dict[str, Any]:
        """One reading; `detail` adds per-core, processes, sensors and disks (for the System page)."""
        if not self.available:
            return {"available": False}
        import psutil

        now = time.monotonic()
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        self.series["cpu"].append(round(cpu, 1))
        self.series["memory"].append(round(memory.percent, 1))
        out: dict[str, Any] = {"available": True}
        try:
            net = psutil.net_io_counters()
            reading = (now, int(net.bytes_recv), int(net.bytes_sent))
            rate = self._rate(self._last_net, reading)
            self._last_net = reading
            if rate:
                self.series["down"].append(round(rate[0]))
                self.series["up"].append(round(rate[1]))
        except (AttributeError, OSError):
            pass
        try:
            disk = psutil.disk_io_counters()
            if disk is not None:
                reading = (now, int(disk.read_bytes), int(disk.write_bytes))
                rate = self._rate(self._last_disk, reading)
                self._last_disk = reading
                if rate:
                    self.series["read"].append(round(rate[0]))
                    self.series["write"].append(round(rate[1]))
        except (AttributeError, OSError):
            pass
        out["history"] = {k: list(v) for k, v in self.series.items()}
        out["memoryUsedGb"] = round(memory.used / 1e9, 1)
        out["memoryTotalGb"] = round(memory.total / 1e9, 1)
        try:
            out["load"] = [round(x, 2) for x in psutil.getloadavg()]
        except (AttributeError, OSError):
            out["load"] = None
        if not detail:
            return out
        out["cores"] = [round(x) for x in psutil.cpu_percent(interval=None, percpu=True)]
        try:
            freq = psutil.cpu_freq()
            out["freqMhz"] = round(freq.current) if freq else None
        except (AttributeError, OSError, NotImplementedError):
            out["freqMhz"] = None
        # Processes by CPU (the first call only primes psutil's counters).
        procs = []
        cores = max(1, psutil.cpu_count() or 1)
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent", "username"]):
            try:
                info = p.info
                if (info.get("name") or "") in {"System Idle Process", "idle", "Idle"}:
                    continue
                procs.append({"pid": p.pid, "name": (info.get("name") or "?")[:24], "cpu": round((info.get("cpu_percent") or 0.0) / cores, 1),
                              "mem": round(info.get("memory_percent") or 0.0, 1), "user": (info.get("username") or "").split("\\")[-1]})
            except (psutil.Error, OSError):
                continue
        out["processes"] = sorted(procs, key=lambda x: (-x["cpu"], -x["mem"]))[:16] if self._proc_primed else []
        self._proc_primed = True
        out["processCount"] = len(procs)
        temps = []
        try:
            for chip, entries in (psutil.sensors_temperatures() or {}).items():
                for e in entries[:4]:
                    if e.current and 0 < e.current < 130:
                        temps.append({"label": (e.label or chip)[:16], "c": round(e.current)})
        except (AttributeError, OSError):
            pass
        out["temps"] = temps[:6]
        disks = []
        try:
            for part in psutil.disk_partitions(all=False)[:4]:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except OSError:
                    continue
                disks.append({"mount": part.mountpoint[:18], "pct": round(usage.percent), "totalGb": round(usage.total / 1e9)})
        except OSError:
            pass
        out["disks"] = disks
        return out
