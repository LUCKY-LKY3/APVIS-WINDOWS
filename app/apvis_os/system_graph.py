"""Truthful, local System Graph observations with stable identity and freshness."""

from __future__ import annotations

import shutil
import socket
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .common import json_primitive, utc_now


class ObservationState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    STALE = "stale"


@dataclass(frozen=True)
class Observation:
    """A versioned JSON record; an interface list never proves connectivity."""

    schema_version: int
    entity_id: str
    property: str
    value: Any
    source: str
    observed_at: str
    max_age_seconds: int
    authority: str
    confidence: float
    state: ObservationState
    boot_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported observation schema_version")
        if not self.entity_id or not self.property or not self.source or not self.authority:
            raise ValueError("observation identity and provenance are required")
        if not isinstance(self.max_age_seconds, int) or self.max_age_seconds < 0:
            raise ValueError("max_age_seconds must be a non-negative integer")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(self.state, ObservationState):
            raise ValueError("state must be an ObservationState")
        json_primitive(self.value, "observation value")

    @property
    def subject(self) -> str:
        return f"{self.entity_id}.{self.property}"

    @property
    def available(self) -> bool:
        return self.state == ObservationState.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["subject"] = self.subject
        payload["available"] = self.available
        return payload


class SystemGraph:
    """Read-only host facts; absent kernel/OS sources are never guessed."""

    def __init__(self, boot_id_path: Path = Path("/proc/sys/kernel/random/boot_id")) -> None:
        self.boot_id_path = boot_id_path

    def _boot_id(self) -> str | None:
        try:
            value = self.boot_id_path.read_text(encoding="ascii").strip()
            return value or None
        except OSError:
            return None

    def _observation(self, property: str, value: Any, source: str, *, state: ObservationState, max_age_seconds: int, authority: str = "local-os", confidence: float = 1.0, detail: str | None = None) -> Observation:
        return Observation(1, "system", property, value, source, utc_now(), max_age_seconds, authority, confidence, state, self._boot_id(), detail)

    def _available(self, property: str, value: Any, source: str, *, max_age_seconds: int = 5, authority: str = "local-os", confidence: float = 1.0, detail: str | None = None) -> Observation:
        return self._observation(property, value, source, state=ObservationState.AVAILABLE, max_age_seconds=max_age_seconds, authority=authority, confidence=confidence, detail=detail)

    def _unavailable(self, property: str, source: str, detail: str) -> Observation:
        return self._observation(property, None, source, state=ObservationState.UNAVAILABLE, max_age_seconds=0, authority="none", confidence=0.0, detail=detail)

    def _error(self, property: str, source: str, detail: str) -> Observation:
        return self._observation(property, None, source, state=ObservationState.ERROR, max_age_seconds=0, authority="none", confidence=0.0, detail=detail)

    @staticmethod
    def _key_values(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        return values

    def identity(self) -> Observation:
        path = Path("/etc/os-release")
        if not path.is_file():
            return self._unavailable("identity", "etc-os-release", "/etc/os-release is unavailable")
        try:
            return self._available("identity", self._key_values(path), "etc-os-release", max_age_seconds=86_400)
        except OSError as exc:
            return self._error("identity", "etc-os-release", str(exc))

    def uptime(self) -> Observation:
        path = Path("/proc/uptime")
        if not path.is_file():
            return self._unavailable("uptime_seconds", "proc-uptime", "/proc/uptime is unavailable")
        try:
            return self._available("uptime_seconds", float(path.read_text(encoding="ascii").split()[0]), "proc-uptime", max_age_seconds=5)
        except (OSError, ValueError, IndexError) as exc:
            return self._error("uptime_seconds", "proc-uptime", str(exc))

    def memory(self) -> Observation:
        path = Path("/proc/meminfo")
        if not path.is_file():
            return self._unavailable("memory", "proc-meminfo", "/proc/meminfo is unavailable")
        try:
            values: dict[str, int] = {}
            for line in path.read_text(encoding="ascii").splitlines():
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
            data = {key: values[key] for key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree") if key in values}
            return self._available("memory", data, "proc-meminfo", max_age_seconds=5)
        except (OSError, ValueError, IndexError) as exc:
            return self._error("memory", "proc-meminfo", str(exc))

    def cpu(self) -> Observation:
        """Read CPU identity and load from procfs; never invent percentages."""
        cpuinfo = Path("/proc/cpuinfo")
        loadavg = Path("/proc/loadavg")
        if not cpuinfo.is_file() or not loadavg.is_file():
            return self._unavailable("cpu", "procfs", "CPU procfs sources are unavailable")
        try:
            model = None
            logical = 0
            for line in cpuinfo.read_text(encoding="ascii", errors="replace").splitlines():
                if line.startswith("model name") and model is None:
                    model = line.split(":", 1)[1].strip()
                if line.startswith("processor"):
                    logical += 1
            fields = loadavg.read_text(encoding="ascii").split()
            if not fields or logical <= 0:
                raise ValueError("incomplete CPU procfs data")
            return self._available("cpu", {"model": model or "unknown", "logical_processors": logical, "load_1m": float(fields[0])}, "proc-cpuinfo+proc-loadavg", max_age_seconds=5, confidence=0.95)
        except (OSError, ValueError, IndexError) as exc:
            return self._error("cpu", "procfs", str(exc))

    def graphics(self) -> Observation:
        """Enumerate DRM cards and their kernel driver when exposed."""
        drm = Path("/sys/class/drm")
        if not drm.is_dir():
            return self._unavailable("graphics", "sysfs-drm", "/sys/class/drm is unavailable")
        cards: list[dict[str, Any]] = []
        try:
            for card in sorted(drm.glob("card[0-9]*")):
                if not card.is_dir() or not card.name[4:].isdigit():
                    continue
                driver = None
                driver_link = card / "device" / "driver"
                if driver_link.is_symlink():
                    driver = driver_link.resolve().name
                cards.append({"card": card.name, "driver": driver})
            if not cards:
                return self._unavailable("graphics", "sysfs-drm", "no DRM cards are exposed")
            return self._available("graphics", {"cards": cards}, "sysfs-drm", max_age_seconds=30, confidence=0.9)
        except OSError as exc:
            return self._error("graphics", "sysfs-drm", str(exc))

    def processes(self) -> Observation:
        """Count visible numeric procfs entries without exposing command lines."""
        proc = Path("/proc")
        if not proc.is_dir():
            return self._unavailable("processes", "procfs", "/proc is unavailable")
        try:
            count = sum(1 for entry in proc.iterdir() if entry.name.isdigit())
            return self._available("processes", {"visible_count": count, "scope": "current-namespace"}, "procfs-process-directories", max_age_seconds=5, confidence=0.9)
        except OSError as exc:
            return self._error("processes", "procfs", str(exc))

    def storage(self) -> Observation:
        try:
            usage = shutil.disk_usage("/")
            return self._available("storage", {"path": "/", "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}, "shutil-disk-usage", max_age_seconds=30)
        except OSError as exc:
            return self._error("storage", "shutil-disk-usage", str(exc))

    def network(self) -> Observation:
        try:
            names = sorted(name for _, name in socket.if_nameindex())
            return self._available("network_interfaces", {"interfaces": names}, "socket-if-nameindex", max_age_seconds=10, confidence=0.8, detail="Interface enumeration does not establish link, address, DNS, or internet connectivity.")
        except OSError as exc:
            return self._error("network_interfaces", "socket-if-nameindex", str(exc))

    def snapshot(self) -> list[Observation]:
        return [self.identity(), self.uptime(), self.cpu(), self.memory(), self.storage(), self.network(), self.graphics(), self.processes()]
