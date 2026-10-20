"""Renderer-independent Nucleus behaviour driven only by typed APVIS state.

The controller turns a :class:`NucleusMode` (from the shell projection) into
smoothly interpolated motion parameters. It carries no colour: colour is a
theme token owned by the QML theme, so the owner can change the accent without
changing behaviour. Nothing here can be driven by model text.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum, IntEnum
from pathlib import Path

from .projection import NucleusMode

EARTH_POINTS = Path("/usr/share/apvis-os/geo/earth-land-points.json")


@dataclass(frozen=True)
class MotionProfile:
    """Target motion for one mode; every value is a 0..1 (or signed) scalar."""

    energy: float
    activity: float
    core_intensity: float
    density: float
    rotation_speed: float
    orbit_speed: float
    turbulence: float
    pulse_strength: float
    breathing: float
    expansion: float
    instability: float


# Adapted from the frozen APVIS 7.0.1 ParticleStateController table
# (apvis/ui2/particles.py), with hue removed and V2's calm-idle rule applied.
_PROFILES: dict[NucleusMode, MotionProfile] = {
    NucleusMode.IDLE: MotionProfile(.30, .16, .44, .72, .12, .16, .10, .08, .45, 0, 0),
    NucleusMode.CONTINUITY_UNKNOWN: MotionProfile(.34, .20, .40, .66, .12, .16, .14, .10, .40, 0, .04),
    NucleusMode.ATTENTION: MotionProfile(.40, .18, .52, .70, .08, .10, .08, .20, .30, -.03, 0),
    NucleusMode.LISTENING: MotionProfile(.54, .58, .66, .82, .28, .36, .28, .30, .20, .08, .02),
    NucleusMode.RETRIEVAL: MotionProfile(.66, .70, .74, .88, .46, .58, .40, .34, .15, .04, .04),
    NucleusMode.WORKING: MotionProfile(.80, .86, .88, .94, .62, .78, .50, .42, .10, .08, .04),
    NucleusMode.SUCCESS: MotionProfile(.62, .40, .92, .86, .24, .26, .16, .60, .25, .16, 0),
    NucleusMode.ERROR: MotionProfile(.52, .48, .64, .70, .14, .20, .56, .36, .10, -.04, .55),
    NucleusMode.LOCAL_ONLY: MotionProfile(.30, .16, .40, .64, .12, .14, .10, .08, .45, -.06, 0),
    NucleusMode.RECOVERY: MotionProfile(.22, .10, .30, .50, .06, .08, .06, .04, .25, -.08, 0),
}


def motion_profile(mode: NucleusMode | str) -> MotionProfile:
    try:
        key = mode if isinstance(mode, NucleusMode) else NucleusMode(mode)
    except ValueError:
        key = NucleusMode.IDLE
    return _PROFILES[key]


class NucleusStateController:
    """Frame-rate independent easing toward the active mode's profile."""

    def __init__(self, mode: NucleusMode | str = NucleusMode.IDLE) -> None:
        self.mode = NucleusMode.IDLE
        self.set_mode(mode)
        self._values = asdict(motion_profile(self.mode))

    def set_mode(self, mode: NucleusMode | str) -> None:
        try:
            self.mode = mode if isinstance(mode, NucleusMode) else NucleusMode(mode)
        except ValueError:
            self.mode = NucleusMode.IDLE

    @property
    def values(self) -> dict[str, float]:
        return dict(self._values)

    def sample(self, delta_seconds: float, *, response_hz: float = 4.0) -> dict[str, float]:
        dt = max(0.0, min(float(delta_seconds), 0.25))
        alpha = 1.0 - math.exp(-max(0.1, response_hz) * dt)
        target = asdict(motion_profile(self.mode))
        for name, desired in target.items():
            self._values[name] += (desired - self._values[name]) * alpha
        return self.values


class QualityTier(IntEnum):
    MINIMAL = 0
    BALANCED = 1
    FULL = 2


@dataclass(frozen=True)
class QualityBudget:
    particles: int
    effect_scale: float


_BUDGETS = {
    QualityTier.FULL: QualityBudget(8000, 1.0),
    QualityTier.BALANCED: QualityBudget(4500, 0.75),
    QualityTier.MINIMAL: QualityBudget(1400, 0.5),
}


def quality_budget(tier: QualityTier) -> QualityBudget:
    return _BUDGETS[QualityTier(tier)]


class AdaptiveQuality:
    """Step down after sustained pressure, recover slowly (hysteresis).

    Recalibrated on the OptiPlex HD 4600 (3.0.10, 2026-10-10): the V3 core runs 54-58 fps there at every
    tier with p95 26-36 ms, because ~5% of frames miss one vsync to periodic UI work, which a lower tier
    cannot fix. The old p95 >22.2 ms "slow" mark (from APVIS 7) pushed Home to minimal on every start.
    Now slow = <45 fps or p95 >45 ms (frames really missing two vsyncs); good = >=54 fps and p95 <=34 ms;
    3 slow windows to step down, 8 good windows to step up.
    """

    def __init__(self, tier: QualityTier = QualityTier.FULL, *, ceiling: QualityTier = QualityTier.FULL) -> None:
        self.ceiling = QualityTier(ceiling)
        self.tier = QualityTier(min(tier, self.ceiling))
        self._slow = 0
        self._good = 0

    def report(self, fps: float, p95_ms: float) -> bool:
        slow = fps < 45.0 or p95_ms > 45.0
        good = fps >= 54.0 and p95_ms <= 34.0
        if slow:
            self._slow, self._good = self._slow + 1, 0
        elif good:
            self._good, self._slow = self._good + 1, 0
        else:
            self._slow, self._good = max(0, self._slow - 1), 0
        if self._slow >= 3 and self.tier > QualityTier.MINIMAL:
            self.tier, self._slow = QualityTier(self.tier - 1), 0
            return True
        if self._good >= 8 and self.tier < self.ceiling:
            self.tier, self._good = QualityTier(self.tier + 1), 0
            return True
        return False


def frame_stats(frame_ms: list[float]) -> tuple[float, float]:
    """Return (fps, p95 frame time) for one measurement window."""
    samples = sorted(t for t in frame_ms if t > 0)
    if not samples:
        return 0.0, 0.0
    fps = 1000.0 * len(samples) / sum(samples)
    p95 = samples[min(len(samples) - 1, math.ceil(0.95 * len(samples)) - 1)]
    return fps, p95


class NucleusShape(str, Enum):
    SPHERE = "sphere"      # default Nucleus
    APERTURE = "aperture"  # Answer Focus: particles part around a reading plane
    GLOBE = "globe"        # location: particles form the Earth with a real pin


class Renderer(str, Enum):
    SPHERE_3D = "sphere3d"  # Qt Quick 3D, needs a hardware/OpenGL scene graph
    CANVAS = "canvas"       # works on every backend, including Safe Graphics


def cpu_rendered(dri: str = "/dev/dri") -> bool:
    """True when Linux has no GPU render node, so Mesa falls back to llvmpipe.

    Every translucent full-screen layer is then filled by the CPU each frame;
    Home switches to a lighter look instead of dropping to 15 fps (dev.9 VM).
    Override with APVIS_GPU=1 / APVIS_GPU=0.
    """
    forced = os.environ.get("APVIS_GPU", "")
    if forced in {"0", "1"}:
        return forced == "0"
    if not sys.platform.startswith("linux"):
        return False
    try:
        return not any(name.startswith("renderD") for name in os.listdir(dri))
    except OSError:
        return True


def select_renderer(*, software_backend: bool, tier: QualityTier) -> Renderer:
    """Qt Quick 3D cannot draw on the software scene graph; Minimal stays 2D."""
    if software_backend or QualityTier(tier) == QualityTier.MINIMAL:
        return Renderer.CANVAS
    return Renderer.SPHERE_3D


@dataclass(frozen=True)
class NucleusParticle:
    """One particle's targets. Positions are on/in the unit sphere (y up, +z faces the viewer)."""

    sphere: tuple[float, float, float]
    globe: tuple[float, float, float]
    brightness: float
    spark: bool
    ocean: bool
    seed: float


def lat_lon_to_unit(lat: float, lon: float) -> tuple[float, float, float]:
    """Latitude/longitude in degrees to a unit vector; lon 0 faces the viewer."""
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo))


def globe_facing_rotation(lat: float, lon: float) -> tuple[float, float]:
    """(yaw, pitch) in radians that bring (lat, lon) to face the viewer.

    Renderers apply yaw about +y first, then pitch about +x; the QML shaders use
    the same convention so the pin and the particles agree.
    """
    return (-math.radians(lon), math.radians(lat))


def build_particles(count: int, earth_points: list[tuple[float, float]], *, seed: int = 7) -> list[NucleusParticle]:
    """Deterministic layered sphere + globe targets for ``count`` particles."""
    if count < 1:
        raise ValueError("count must be positive")
    rng = _Lcg(seed)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    land = list(earth_points)
    land_count = min(len(land), int(count * 0.78))
    step = len(land) / land_count if land_count else 1.0
    particles = []
    for i in range(count):
        # Sphere: Fibonacci directions with three depth layers (shell/mid/core).
        z = 1.0 - (2.0 * i + 1.0) / count
        ring = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden * i + rng.next() * 0.35
        direction = (ring * math.cos(theta), z, ring * math.sin(theta))
        # Mostly a thin shell: projected, it is densest at the edge, which is what
        # makes it read as a sphere rather than a disc. A sparse dim mid layer and a
        # small bright core give it inner depth.
        layer = rng.next()
        if layer < 0.74:
            radius, brightness = 0.92 + rng.next() * 0.08, 0.55 + rng.next() * 0.30
        elif layer < 0.90:
            radius, brightness = 0.55 + rng.next() * 0.30, 0.25 + rng.next() * 0.20
        else:
            radius, brightness = 0.08 + rng.next() * 0.30, 0.70 + rng.next() * 0.30
        sphere = tuple(c * radius for c in direction)
        # Globe: land points first (evenly subsampled), the rest sparse ocean.
        if i < land_count:
            lat, lon = land[int(i * step)]
            globe, ocean = lat_lon_to_unit(lat, lon), False
        else:
            k = i - land_count
            m = max(1, count - land_count)
            oz = 1.0 - (2.0 * k + 1.0) / m
            oring = math.sqrt(max(0.0, 1.0 - oz * oz))
            globe, ocean = (oring * math.cos(golden * k), oz, oring * math.sin(golden * k)), True
        particles.append(NucleusParticle(
            sphere=sphere, globe=globe, brightness=round(brightness, 3),
            spark=rng.next() < 0.015, ocean=ocean, seed=round(rng.next(), 4),
        ))
    return particles


class _Lcg:
    """Tiny deterministic generator so every renderer gets identical particles."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0x7FFFFFFF or 1

    def next(self) -> float:
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state / 0x7FFFFFFF


@dataclass(frozen=True)
class NucleusPreview:
    """Developer-only shape preview. Always labelled as a preview; expires."""

    shape: NucleusShape
    expires_at: float
    lat: float | None = None
    lon: float | None = None
    label: str | None = None

    def pin(self) -> dict[str, object] | None:
        if self.shape != NucleusShape.GLOBE or self.lat is None or self.lon is None:
            return None
        return {"lat": self.lat, "lon": self.lon, "label": self.label or f"{self.lat:.2f}, {self.lon:.2f}",
                "source": "coordinates entered with apvisctl"}


def preview_path() -> Path:
    import os

    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os")) / "nucleus" / "preview.json"


def write_preview(shape: NucleusShape | str, *, seconds: int = 120, lat: float | None = None,
                  lon: float | None = None, label: str | None = None, now: float | None = None,
                  path: Path | None = None) -> NucleusPreview:
    import time

    shape = NucleusShape(shape)
    if not 5 <= int(seconds) <= 3600:
        raise ValueError("preview seconds must be between 5 and 3600")
    if shape == NucleusShape.GLOBE and (lat is None or lon is None):
        raise ValueError("a globe preview needs --lat and --lon")
    if lat is not None and not -90 <= lat <= 90 or lon is not None and not -180 <= lon <= 180:
        raise ValueError("latitude/longitude out of range")
    if label is not None and (not label.strip() or len(label) > 80):
        raise ValueError("label must be 1-80 characters")
    preview = NucleusPreview(shape, (now if now is not None else time.time()) + int(seconds), lat, lon,
                             label.strip() if label else None)
    target = path or preview_path()
    target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    payload = {"schema_version": 1, "shape": shape.value, "expires_at": preview.expires_at,
               "lat": lat, "lon": lon, "label": preview.label}
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(target)
    return preview


def read_preview(*, now: float | None = None, path: Path | None = None) -> NucleusPreview | None:
    """Return the active preview, or None if absent, malformed or expired."""
    import time

    target = path or preview_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1:
            return None
        preview = NucleusPreview(NucleusShape(raw["shape"]), float(raw["expires_at"]),
                                 raw.get("lat"), raw.get("lon"), raw.get("label"))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if preview.expires_at <= (now if now is not None else time.time()):
        return None
    return preview


def clear_preview(*, path: Path | None = None) -> None:
    (path or preview_path()).unlink(missing_ok=True)


def load_earth_points(path: Path = EARTH_POINTS) -> list[tuple[float, float]]:
    """Land sample points as (lat, lon) degrees from the shipped Natural Earth file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or not isinstance(raw.get("points"), list):
        raise ValueError("unsupported earth points file")
    points = []
    for item in raw["points"]:
        lat, lon = float(item[0]), float(item[1])
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            raise ValueError("earth point out of range")
        points.append((lat, lon))
    return points
