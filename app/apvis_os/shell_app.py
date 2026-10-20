"""V2 desktop Home entry point and bounded ordinary-application launcher."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import threading
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .ask import AskConfig, AskService, Conversation
from .ollama import OllamaClient, OllamaError
from .aviation import AIRPORTS, Area, AviationFeed, airspace_stats, cache_path as aviation_cache
from .osint import OsintFeed
from .focus import FocusKind, FocusRecord, FocusStore
from .home_status import net_rates, quick_status, route_status, slow_status
from .telemetry import Telemetry
from .missions import MissionControl, ParseError, summary
from .vault import MemoryInbox, SensitiveContent, Vault, parse_memory_request
from .nucleus import (
    AdaptiveQuality,
    NucleusPreview,
    QualityTier,
    Renderer,
    build_particles,
    frame_stats,
    load_earth_points,
    motion_profile,
    quality_budget,
    read_preview,
    cpu_rendered,
    select_renderer,
)
from .projection import DisplayContext, NucleusMode, ShellProjector
from .search import SearchIndex
from .control import ControlCentre
from . import windows as window_list
from . import aisetup, appstore, backup, brain, devinfo, documents, health, hostinfo, lockscreen, miniterm, reminders, screen, semantic, updates, weather
from . import api as apvis_api
from . import guest as guest_mode
from .scheduler import SCHEDULER
from . import episodes as episodes_mod
from . import plans
from . import pictures
from .facts import measured_answer
from .continuity import continuity_answer, is_continuity_question

QML_HOME = Path("/usr/share/apvis-os/qml/Home.qml")
REDUCED_MOTION_FLAG = Path.home() / ".config/apvis/reduced-motion"
STARTUP_GRACE_S = 20.0
UI_PREFS = Path.home() / ".config/apvis/ui.json"          # accent colour and panel style
STYLES = ("glass", "hud")
# Models offered in Settings (owner's routing design: the fast model decides).
RECOMMENDED_MODELS = [
    {"name": "llama3.2:1b", "size": "1.3 GB", "role": "Fast answers, and decides which model answers"},
    {"name": "qwen2.5-coder:1.5b", "size": "1.0 GB", "role": "Code, terminal and PC help"},
    {"name": "qwen2.5-coder:7b", "size": "4.7 GB", "role": "Harder code questions (slower)"},
    {"name": "llama3.2:3b", "size": "2.0 GB", "role": "Smarter everyday answers (slower on the OptiPlex)"},
    {"name": "qwen2.5:0.5b", "size": "0.4 GB", "role": "Small talk, about twice as fast to start writing"},
    {"name": "moondream", "size": "1.7 GB", "role": "Answers about your screen (Win+Shift+S); slow on the OptiPlex CPU"},
]
INSTALL_HELPER = "/usr/local/lib/apvis-os/apvis-install"
INSTALL_HELPER_LIVE = Path("/run/live/medium/live/filesystem.squashfs")


def install_requested() -> bool:
    """Booted with the menu entry "Install APVIS OS" (apvis.install=1)."""
    try:
        return "apvis.install=1" in Path("/proc/cmdline").read_text().split()
    except OSError:
        return False
APPLICATIONS: dict[str, tuple[str, ...]] = {
    "files": ("/usr/bin/pcmanfm-qt",),
    "apps": ("/usr/bin/wofi", "--show", "drun", "--prompt", "Apps", "--style", "/etc/apvis-os/wofi/style.css"),
    # A new terminal greets with the APVIS mark and this computer's real details, then runs the shell.
    "terminal": ("/usr/bin/foot", "--title=APVIS Terminal", "sh", "-c",
                 'python3 -m apvis_os.hostinfo 2>/dev/null; exec "${SHELL:-/bin/bash}"'),
    "editor": ("/usr/bin/featherpad",),
    "browser": (sys.executable, "-m", "apvis_os.browser"),
    "network": ("/usr/bin/nm-connection-editor",),
    "displays": ("/usr/bin/wdisplays",),
    "sound": ("/usr/bin/pavucontrol-qt",),
}
ACCENTS = ("lacquer", "apvis", "emerald", "cyan-steel", "aqua", "emerald-steel", "emerald-silver", "cool-white")
# V3 M3 design directions: only for development previews (APVIS_ACCENT=v3a|v3b, art from APVIS_CORE_ART,
# fonts from APVIS_PREVIEW_FONTS); Settings never lists them and they are never saved.
PREVIEW_ACCENTS = ("v3b",)
# The interface font of each look (installed from Debian by the V3 update; missing fonts fall back quietly).
BODY_FONT = {"lacquer": "Inter", "v3b": "Inter"}
V3_LOOK_MARK = Path.home() / ".config/apvis/ui-v3-look"


def load_ui_prefs(path: Path | None = None) -> dict[str, str]:
    try:
        data = json.loads((path or UI_PREFS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {k: str(v) for k, v in data.items() if k in {"accent", "style"}}
    if isinstance(data.get("lockOnStart"), bool):
        out["lockOnStart"] = data["lockOnStart"]
    return out


def save_ui_prefs(prefs: dict[str, object], path: Path | None = None) -> None:
    target = path or UI_PREFS
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(prefs), encoding="utf-8")
    os.replace(tmp, target)


_DEFAULT_FONT: list = []


def apply_body_font(accent: str) -> None:
    """Use the look's interface font when it is installed (V3: Inter); otherwise the system font."""
    try:
        from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    except ImportError:
        return
    app = QGuiApplication.instance()
    if app is None:
        return
    if not _DEFAULT_FONT:
        _DEFAULT_FONT.append(QFont(app.font()))
    family = BODY_FONT.get(accent or "")
    if family and family in QFontDatabase.families():
        font = QFont(_DEFAULT_FONT[0])
        font.setFamily(family)
        app.setFont(font)
    else:
        app.setFont(_DEFAULT_FONT[0])


def product_version() -> str:
    """The installed APVIS version, from the image's release file (development runs say so)."""
    try:
        for line in Path("/usr/share/apvis-os/release").read_text(encoding="utf-8").splitlines():
            if line.startswith("product_version="):
                return "APVIS OS " + line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "development run (not an installed image)"


def launch_application(name: str, *args: str) -> None:
    """Launch one installed desktop tool; UI text never becomes a shell command."""
    command = APPLICATIONS.get(name)
    if command is None:
        raise ValueError("unknown application")
    if name == "browser":
        from .browser import available
        if not available():
            raise FileNotFoundError("APVIS Browser comes with the APVIS OS dev.26 image (it needs Qt WebEngine)")
        command = (*command, *args[:1])
    if not Path(command[0]).is_file():
        raise FileNotFoundError(f"{name} is unavailable")
    subprocess.Popen(command, close_fds=True, start_new_session=True)


def set_question_focus(label: str, store: FocusStore | None = None) -> None:
    """Set the explicit local Focus; this does not call a model or start research."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("Focus text is required")
    label = label.strip()
    focus_store = store or FocusStore()
    current = focus_store.get()
    focus_store.set(
        FocusRecord(uuid4().hex, FocusKind.QUESTION, label, label),
        expected_revision=current.revision,
    )


def nucleus_view(mode: str, preview: NucleusPreview | None) -> dict[str, object]:
    """What the Nucleus shows: motion from the real mode; shape only from a labelled preview."""
    try:
        typed = NucleusMode(mode)
    except ValueError:
        typed = NucleusMode.ATTENTION
    return {
        "mode": typed.value,
        "motion": asdict(motion_profile(typed)),
        "shape": preview.shape.value if preview else "sphere",
        "pin": preview.pin() if preview else None,
        "preview": preview is not None,
    }


def canvas_points(count: int) -> list[list[float]]:
    """Compact particle rows for the CPU (Safe Graphics) Nucleus."""
    try:
        earth = load_earth_points()
    except (OSError, ValueError):
        earth = []
    return [
        [*p.sphere, *p.globe, p.brightness, 1.0 if p.spark else 0.0, 1.0 if p.ocean else 0.0, p.seed]
        for p in build_particles(count, earth)
    ]


def pick_screen(screens: list, primary, wanted: str = "") -> object:
    """APVIS for Windows: the monitor to fill. APVIS_SCREEN=<number> (1 = first) chooses one; otherwise the first
    monitor that isn't the main one (the owner's second screen), or the main one when there is only one."""
    if wanted.strip().isdigit() and 1 <= int(wanted) <= len(screens):
        return screens[int(wanted) - 1]
    others = [s for s in screens if s is not primary]
    return others[0] if others else primary


def place_on_screen(window, app) -> None:
    screen = pick_screen(list(app.screens()), app.primaryScreen(), os.environ.get("APVIS_SCREEN", ""))
    if screen is None:
        return
    window.setScreen(screen)
    window.setGeometry(screen.geometry())
    window.showFullScreen()


def run(qml_path: Path = QML_HOME, *, windowed: bool = False, smoke_screenshot: Path | None = None,
        accent: str | None = None, reduced_motion: bool | None = None, smoke_delay_ms: int = 750,
        smoke_ask: str | None = None, smoke_page: str = "") -> int:
    from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow

    software_backend = os.environ.get("QT_QUICK_BACKEND") == "software" or os.environ.get("QSG_RHI_BACKEND") == "software"
    have_3d = False
    if not software_backend:
        try:
            from . import nucleus_qt  # noqa: F401  (registers ApvisNucleus.NucleusInstancing)
            have_3d = True
        except ImportError:
            have_3d = False
    frame_log = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "apvis-nucleus-frames.log"

    class ShellBridge(QObject):
        stateChanged = Signal()
        actionErrorChanged = Signal()
        renderChanged = Signal()
        askChanged = Signal()
        missionsChanged = Signal()
        atlasChanged = Signal()
        pageRequested = Signal(str)
        memoryChanged = Signal()
        settingsChanged = Signal()
        systemChanged = Signal()
        _systemUpdate = Signal("QVariantMap")  # measurements from the status thread
        _settingsUpdate = Signal("QVariantMap")
        controlChanged = Signal()
        frameInfoChanged = Signal()
        devChanged = Signal()
        updatesChanged = Signal()
        installerChanged = Signal()
        _installerUpdate = Signal("QVariantMap")
        _updatesUpdate = Signal("QVariantMap")
        _devUpdate = Signal("QVariantMap")
        _controlUpdate = Signal("QVariantMap")
        _atlasUpdate = Signal("QVariantMap", str)  # from the poller thread; delivered queued
        planePhotoChanged = Signal()
        _planePhotoUpdate = Signal("QVariantMap")   # an aircraft photo for the Atlas (worker thread)
        worldChanged = Signal()
        _worldUpdate = Signal(str)
        _askUpdate = Signal("QVariantMap")  # emitted from the Ask worker thread; delivered queued
        hostChanged = Signal()
        _hostUpdate = Signal("QVariantMap")
        powerRequested = Signal(str)          # Home shows the goodbye screen, then calls power()
        miniTerminalOutput = Signal("QVariantMap")   # the Home terminal card (from a worker thread)
        unlockResult = Signal(bool, str)
        appsChanged = Signal()
        _appsUpdate = Signal("QVariantMap")
        _homeCommand = Signal(str, str)       # from the local API thread (keyboard shortcuts, scripts)
        reminderDue = Signal(str, str)        # (text, "reminder"|"timer") when one comes due
        windowsChanged = Signal()
        _windowsUpdate = Signal("QVariantList")   # open app windows, read off the UI thread

        def __init__(self) -> None:
            super().__init__()
            self._guest = guest_mode.this_session_is_guest()     # V4: the Guest account looks around only
            self._projector = ShellProjector()
            self._state: dict[str, object] = {}
            self._nucleus: dict[str, object] = {}
            self._action_error = ""
            self._cpu_rendered = cpu_rendered()
            # Without a GPU start on the 2D Nucleus; the loop can still step up if frames allow.
            start = QualityTier.MINIMAL if self._cpu_rendered else QualityTier.FULL
            self._quality = AdaptiveQuality(start, ceiling=QualityTier.FULL if have_3d else QualityTier.MINIMAL)
            self._canvas_points = canvas_points(quality_budget(QualityTier.MINIMAL).particles)
            self._canvas_json = json.dumps([round(v, 4) for row in self._canvas_points for v in row])
            prefs = load_ui_prefs()
            # V3: the lacquer-and-brass look replaces V2 green once (the owner can switch back in Settings).
            if not V3_LOOK_MARK.exists() and not os.environ.get("APVIS_ACCENT") and accent is None:
                try:
                    if prefs.get("accent", "apvis") == "apvis":
                        prefs["accent"] = "lacquer"
                        save_ui_prefs({"accent": "lacquer", "style": prefs.get("style", "glass"),
                                       "lockOnStart": prefs.get("lockOnStart") is True})
                    V3_LOOK_MARK.parent.mkdir(parents=True, exist_ok=True)
                    V3_LOOK_MARK.write_text("1\n", encoding="utf-8")
                except OSError:
                    pass
            self._accent = accent if accent in ACCENTS else os.environ.get("APVIS_ACCENT") or prefs.get("accent", "lacquer")
            if self._accent not in ACCENTS and not (self._accent in PREVIEW_ACCENTS and os.environ.get("APVIS_ACCENT") == self._accent):
                self._accent = "lacquer"
            art = os.environ.get("APVIS_CORE_ART", "") if self._accent in PREVIEW_ACCENTS else ""
            self._art_dir = QUrl.fromLocalFile(str(Path(art).resolve()) + os.sep).toString() if art and Path(art).is_dir() else ""
            self._style = prefs.get("style", "glass") if prefs.get("style") in STYLES else "glass"
            self._lock_on_start = prefs.get("lockOnStart") is True
            self._home_intel = False
            self._world_thread: threading.Thread | None = None
            self._host: dict[str, object] = {}
            self._devices: dict[str, object] = {}
            self._hostUpdate.connect(self._apply_host)
            threading.Thread(target=lambda: self._hostUpdate.emit({"host": hostinfo.host_info()}),
                             name="apvis-host", daemon=True).start()
            env_reduced = os.environ.get("APVIS_REDUCED_MOTION", "") in {"1", "true", "yes"}
            saved_reduced = REDUCED_MOTION_FLAG.exists()
            self._reduced = (env_reduced or saved_reduced) if reduced_motion is None else reduced_motion
            self._frames: list[float] = []
            self._last_frame = 0.0
            self._window_start = time.perf_counter()
            # The first seconds after Home starts are busy (models, Atlas, app scan): their frames say nothing
            # about the GPU and used to push the tier down for the whole session.
            self._measure_from = time.perf_counter() + STARTUP_GRACE_S
            self._clock_start = time.perf_counter()
            self._clock = 0.0
            self._ask: dict[str, object] = {"state": "closed"}
            self._ask_generation = 0
            self._missions: list[dict[str, object]] = []
            self._search_results: list[dict[str, object]] = []
            self._display_context = DisplayContext.PRIVATE
            self._apps: dict[str, object] = {}
            self._apps_installed: list[dict[str, object]] = []
            self._appsUpdate.connect(self._apply_apps)
            self._homeCommand.connect(self._home_command)
            apvis_api.HOME_HOOKS["command"] = lambda kind, value: self._homeCommand.emit(kind, value)
            self._conversation = Conversation()   # follow-ups: the last exchanges, for 30 minutes, in memory only
            self._reminders = reminders.Reminders()
            self._health = health.HealthGuard()
            self._health_alerts: list[dict[str, object]] = []
            self._weather: dict[str, object] | None = None
            self._weather_busy = False
            self._app_focus = 0
            self._api_server = None
            try:
                if AskConfig.load().api_enabled:
                    self._api_server = apvis_api.start_background()
            except (OSError, ValueError):
                self._api_server = None
            self._search = SearchIndex(notes=lambda: self._notes, missions=lambda: self._missions, vault_root=Vault().root)
            self._mission_control: MissionControl | None = None
            self._inbox: list[dict[str, object]] = []
            self._system: dict[str, object] = {}
            self._telemetry = Telemetry()
            self._telemetry_data: dict[str, object] = {}
            self._system_page = False
            self._slow: dict[str, object] = {}
            self._route: dict[str, object] = {"reachable": False, "checking": True}
            self._systemUpdate.connect(self._apply_system)
            self._status_wake = threading.Event()
            self._stopping = False
            threading.Thread(target=self._status_loop, name="apvis-status", daemon=True).start()
            self._settings: dict[str, object] = {"ollamaUrl": "", "test": "", "testOk": False, "saved": ""}
            self._settingsUpdate.connect(self._apply_settings)
            # V3: meaning search for the vault. The index is kept current in the background, as background
            # work in the model scheduler (V3 M2): only when the computer is quiet, never beside an answer.
            self._indexer = semantic.Indexer(
                make_index=lambda: semantic.index_for(AskConfig.load()), vault=Vault,
                busy=lambda: self._ask.get("state") in ("thinking", "streaming"),
                on_status=lambda status: self._settingsUpdate.emit({"memory": self._memory_info(status=status)}),
                scheduler=SCHEDULER)
            self._ai_queue: dict[str, object] = {}
            # V3 M4: one-line summaries of Ask sessions (30 days), only while switched on.
            self._episode_list: list[dict[str, object]] = []
            self._episodes = episodes_mod.EpisodeRecorder(
                enabled=lambda: self._episodes_on(), chat=self._episode_chat, scheduler=SCHEDULER,
                on_change=lambda: self._settingsUpdate.emit({"episodesChanged": time.time()}))
            self._settings["episodes"] = {"enabled": self._episodes_on()}
            if self._settings["episodes"]["enabled"]:
                self._episodes.start()
            self._settings["memory"] = self._memory_info()
            try:
                if AskConfig.load().semantic_memory:
                    self._indexer.start()
            except (OSError, ValueError):
                pass
            self._control: dict[str, object] = {"state": {}, "message": "", "ok": True}
            self._control_centre = ControlCentre()
            self._frame_info: dict[str, object] = {}
            self._measuring = True
            self._developer = devinfo.enabled()
            self._dev_info: dict[str, object] = {}
            self._devUpdate.connect(self._apply_dev)
            self._updates: dict[str, object] = {**updates.status(), "state": "idle", "message": ""}
            self._update_offer: dict[str, object] | None = None
            self._updatesUpdate.connect(self._apply_updates)
            self._installer: dict[str, object] = {"live": INSTALL_HELPER_LIVE.exists(), "requested": install_requested(),
                                                  "state": "idle", "disks": [], "ollama": {}, "pct": 0, "message": ""}
            self._installerUpdate.connect(self._apply_installer)
            self._controlUpdate.connect(self._apply_control)
            try:
                self._settings["ollamaUrl"] = AskConfig.load().ollama_url
            except (OSError, ValueError) as exc:
                self._settings["test"] = f"Ask settings unreadable: {exc}"
            self._settings["version"] = product_version()
            self._notes: list[dict[str, object]] = []
            self._atlas: dict[str, object] = {"status": "off"}
            self._atlas_rows = "[]"
            self._atlas_visible = False
            self._atlas_thread: threading.Thread | None = None
            self._atlas_wake = threading.Event()
            # The world-feed thread has its own wake-up (V4 fix): it used to wait on _atlas_wake, which only the
            # flight poller clears, so with Atlas closed it spun flat out (one CPU core) for as long as Home ran.
            self._world_wake = threading.Event()
            self._atlasUpdate.connect(self._apply_atlas)
            self._plane_photo: dict[str, object] = {}
            self._plane_photos: dict[str, dict[str, object]] = {}   # hex -> found photo (this session)
            self._planePhotoUpdate.connect(self._apply_plane_photo)
            self._windows: list[dict[str, str]] = []
            self._windowsUpdate.connect(self._apply_windows)
            self._world_json = "{}"
            self._worldUpdate.connect(self._apply_world)
            self._atlas_area: Area | None = None      # set by the Atlas view; None = the default UK area
            self._area_changed = False
            coast_file = qml_path.parent.parent / "geo" / "atlas-uk-coast.json"
            try:
                coast = json.loads(coast_file.read_text(encoding="utf-8"))
                self._coast_json = json.dumps({"rings": coast["rings"], "source": coast["source"],
                                               "airports": [list(a) for a in AIRPORTS]})
            except (OSError, ValueError, KeyError):
                self._coast_json = json.dumps({"rings": [], "source": "", "airports": [list(a) for a in AIRPORTS]})
            try:
                dots = json.loads((qml_path.parent.parent / "geo" / "earth-land-points.json").read_text(encoding="utf-8"))
                self._earth_dots = json.dumps([v for p in dots["points"] for v in p])
            except (OSError, ValueError, KeyError):
                self._earth_dots = "[]"
            try:
                self._world_land = (qml_path.parent.parent / "geo" / "world-land.json").read_text(encoding="utf-8")
            except OSError:
                self._world_land = '{"rings": [], "source": ""}'
            try:
                self._world_borders = (qml_path.parent.parent / "geo" / "world-borders.json").read_text(encoding="utf-8")
            except OSError:
                self._world_borders = '{"lines": [], "source": ""}'
            self._askUpdate.connect(self._apply_ask)
            self.refresh()

        @Property("QVariantMap", notify=stateChanged)
        def state(self) -> dict[str, object]:
            return self._state

        @Property("QVariantMap", notify=stateChanged)
        def nucleus(self) -> dict[str, object]:
            return self._nucleus

        @Property("QVariantMap", notify=renderChanged)
        def render(self) -> dict[str, object]:
            renderer = select_renderer(software_backend=software_backend or not have_3d, tier=self._quality.tier)
            return {
                "renderer": renderer.value,
                "tier": self._quality.tier.name.lower(),
                "particles": quality_budget(self._quality.tier).particles if renderer == Renderer.SPHERE_3D else len(self._canvas_points),
                "software": software_backend,
                # Lite: freeze and cache the backdrop, drop decorative motion.
                "lite": software_backend or self._cpu_rendered or self._quality.tier == QualityTier.MINIMAL,
                "reducedMotion": self._reduced,
                "accent": self._accent,
                "artDir": self._art_dir,
                "style": self._style,
                "lockOnStart": self._lock_on_start,
            }

        @Property(str, constant=True)
        def canvasPoints(self) -> str:
            # One JSON string: QML parses it once; element-wise QVariantList
            # access from JavaScript was O(n^2) and took seconds.
            return self._canvas_json

        clockChanged = Signal()

        @Property(float, notify=clockChanged)
        def clock(self) -> float:
            return self._clock

        def advance_clock(self) -> None:
            self._clock = time.perf_counter() - self._clock_start
            self.clockChanged.emit()

        @Property(bool, constant=True)
        def guest(self) -> bool:
            """The Guest account (V4 login screen): Home looks the same, but nothing can be changed or kept."""
            return self._guest

        @Property(str, notify=actionErrorChanged)
        def actionError(self) -> str:
            return self._action_error

        def _error(self, message: str) -> None:
            self._action_error = message
            self.actionErrorChanged.emit()

        @Slot()
        def refresh(self) -> None:
            previous = ({k: v for k, v in self._state.items() if k != "generated_at"}, self._nucleus)
            try:
                self._state = self._projector.snapshot(self._display_context).to_dict()
            except (OSError, ValueError, TypeError) as exc:
                self._state = {
                    "schema_version": 1,
                    "nucleus_mode": "attention",
                    "status_text": "Local state unavailable",
                    "focus": None,
                    "task_counts": {},
                    "unreadable_task_count": 0,
                }
                self._error(f"Local state unavailable: {type(exc).__name__}")
            self._nucleus = nucleus_view(str(self._state.get("nucleus_mode", "idle")), read_preview())
            self._refresh_missions()
            self._refresh_system()
            self._refresh_memory()
            # Only notify QML on a real change; re-emitting identical state
            # restarts easing animations and costs frames.
            if previous != ({k: v for k, v in self._state.items() if k != "generated_at"}, self._nucleus):
                self.stateChanged.emit()

        @Slot(bool)
        def setFrameMeasuring(self, on: bool) -> None:
            """Home says whether the Nucleus is animating continuously. Pages and
            answers render only on change, so their gaps are not slow frames and
            must neither be shown as a frame rate nor lower the quality tier."""
            if on != self._measuring:
                self._measuring = on
                self.frame_gap()

        def frame_swapped(self) -> None:
            """Collect real frame times; every ~2 s feed the adaptive quality loop."""
            if not self._measuring:
                return
            now = time.perf_counter()
            if now < self._measure_from:
                return
            if self._last_frame:
                self._frames.append((now - self._last_frame) * 1000.0)
            self._last_frame = now
            if now - self._window_start < 2.0:
                return
            fps, p95 = frame_stats(self._frames)
            tier = self._quality.tier
            if len(self._frames) >= 5:
                self._frame_info = {"fps": round(fps), "p95": round(p95, 1), "tier": tier.name.lower()}
                self.frameInfoChanged.emit()
            changed = len(self._frames) >= 20 and self._quality.report(fps, p95)
            try:
                with frame_log.open("a", encoding="utf-8") as log:
                    log.write(f"{time.strftime('%H:%M:%S')} tier={tier.name.lower()} fps={fps:.1f} p95={p95:.1f}ms frames={len(self._frames)}\n")
            except OSError:
                pass
            self._frames.clear()
            self._window_start = now
            if changed:
                self.renderChanged.emit()

        def frame_gap(self) -> None:
            """Animation paused (hidden/reduced motion): do not count idle gaps as slow frames."""
            self._last_frame = 0.0
            self._frames.clear()
            self._window_start = time.perf_counter()

        @Property("QVariantMap", notify=askChanged)
        def ask(self) -> dict[str, object]:
            return self._ask

        @Property("QVariantMap", notify=systemChanged)
        def system(self) -> dict[str, object]:
            return {**self._system, **self._slow}

        @Property("QVariantMap", notify=systemChanged)
        def telemetry(self) -> dict[str, object]:
            return self._telemetry_data

        @Slot(bool)
        def setSystemPageVisible(self, visible: bool) -> None:
            """Per-core, process and sensor detail is only read while the System page is open."""
            self._system_page = bool(visible)
            if visible:
                self._refresh_system()

        @Property("QVariantMap", notify=systemChanged)
        def route(self) -> dict[str, object]:
            return self._route

        def _refresh_system(self) -> None:
            """Measurements are taken on the status thread; this only wakes it."""
            self._status_wake.set()

        @Slot("QVariantMap")
        def _apply_system(self, update: dict[str, object]) -> None:
            if "quick" in update:
                self._system = update["quick"]
            if "telemetry" in update:
                self._telemetry_data = update["telemetry"]
            if update.get("slow"):
                self._slow = update["slow"]
            if update.get("route"):
                self._route = update["route"]
            self.systemChanged.emit()

        def _status_loop(self) -> None:
            """All measurements off the UI thread: CPU/memory/net and telemetry every
            ~3 s, Wi-Fi/volume every 15 s, the AI host every 60 s (sooner if down)."""
            last_slow = last_route = last_boost = float("-inf")   # first checks run at once, even just after boot
            previous_net = None
            while not self._stopping:
                update: dict[str, object] = {}
                try:
                    quick = quick_status()
                    rates = net_rates(previous_net, quick.get("net"))
                    previous_net = quick.pop("net", None)
                    if rates is not None:
                        self._net_rates = rates
                    quick["netRates"] = getattr(self, "_net_rates", None)
                    quick["aiSetup"] = aisetup.read_status()      # first-start local AI (tiny file)
                    quick["health"] = self._health_alerts
                    quick["weather"] = self._weather
                    try:
                        for item in self._reminders.due_now():
                            self.reminderDue.emit(item.text, item.kind)
                            self.notify("Timer" if item.kind == "timer" else "Reminder", item.text)
                        quick["reminders"] = [{"text": r.text, "kind": r.kind, "due": r.due, "created": r.created}
                                              for r in self._reminders.pending()[:5]]
                    except (OSError, ValueError):
                        quick["reminders"] = []
                    update["quick"] = quick
                    # Per-core, process and sensor detail only while the System page shows (V4: reading every
                    # process every 3 s cost a few % of a core for a page that was usually closed).
                    update["telemetry"] = self._telemetry.sample(detail=self._system_page)
                except OSError:
                    update["quick"] = {"available": False}
                now = time.monotonic()
                if now - last_slow > 15:
                    update["slow"], last_slow = slow_status(), now
                    # Health guard: disk, memory and heat, with a notification the first time.
                    try:
                        alerts = self._health.check(health.measure())
                        for alert in self._health.to_notify(alerts):
                            self.notify(alert.title, alert.detail)
                        self._health_alerts = [a.to_dict() for a in alerts]
                        if isinstance(update.get("quick"), dict):
                            update["quick"]["health"] = self._health_alerts
                    except (OSError, ValueError, KeyError):
                        pass
                if now - last_route > 60 or not self._route.get("reachable") and now - last_route > 10:
                    update["route"], last_route = route_status(), now
                    route = update["route"]
                    if route.get("reachable") and route.get("model"):
                        self._warm_if_needed(route)
                if now - last_boost > 30:
                    last_boost = now
                    self._check_boost()
                    stale = not self._weather or time.time() - float(self._weather.get("at", 0)) > weather.REFRESH_S
                    if stale and not self._weather_busy:
                        self._refresh_weather()
                if self._stopping:
                    return
                try:
                    self._systemUpdate.emit(update)
                except RuntimeError:
                    return  # the bridge is gone (app shutting down)
                queue = self._queue_view()
                if queue != getattr(self, "_ai_queue", None):
                    self._ai_queue = queue
                    self._settingsUpdate.emit({"aiQueue": queue})
                self._status_wake.wait(3.0)
                self._status_wake.clear()

        @Property("QVariantList", constant=True)
        def recommendedModels(self) -> list[dict[str, str]]:
            return RECOMMENDED_MODELS

        @Property("QVariantMap", notify=settingsChanged)
        def settings(self) -> dict[str, object]:
            return self._settings

        @Slot("QVariantMap")
        def _apply_settings(self, update: dict[str, object]) -> None:
            self._settings = {**self._settings, **update}
            self.settingsChanged.emit()
            if "episodesChanged" in update:
                self._refresh_memory()

        # ---- Local AI models (Settings): recommended set, download with progress.
        @Slot()
        def refreshModels(self) -> None:
            def work() -> None:
                try:
                    config = AskConfig.load()
                    self._settingsUpdate.emit({"boost": self._boost_info(config), "api": self._api_info(config),
                                               "memory": self._memory_info(config),
                                               "episodes": {"enabled": config.episodes},
                                               "webSearch": {"enabled": config.web_search},
                                               "answerLength": config.answer_length,
                                               "weather": {"place": (weather.load().get("place") or {}).get("label", ""),
                                                           "reading": self._weather}})
                    client = OllamaClient(config.ollama_url, timeout=4)
                    installed = [m.name.removesuffix(":latest") for m in client.models()]
                    self._settingsUpdate.emit({"ollamaUp": True, "installedModels": installed})
                except (OllamaError, ValueError, OSError):
                    self._settingsUpdate.emit({"ollamaUp": False, "installedModels": []})

            threading.Thread(target=work, name="apvis-models", daemon=True).start()

        @Slot(str)
        @guest_mode.owner_only("Downloading AI models")
        def pullModel(self, name: str) -> None:
            if name not in {m["name"] for m in RECOMMENDED_MODELS}:
                self._apply_settings({"pullMessage": "Only the listed models can be downloaded here."})
                return
            self._apply_settings({"pulling": name, "pullPct": 0, "pullMessage": f"Starting {name}…"})

            def work() -> None:
                last = [0.0]

                def progress(status: str, done: int, total: int) -> None:
                    now = time.monotonic()
                    if now - last[0] > 0.3:
                        last[0] = now
                        pct = round(100 * done / total) if total else 0
                        self._settingsUpdate.emit({"pullPct": pct, "pullMessage": f"{name}: {status}" + (f" {pct}%" if total else "")})

                try:
                    OllamaClient(AskConfig.load().ollama_url, timeout=10).pull(name, progress)
                    self._settingsUpdate.emit({"pulling": "", "pullPct": 100, "pullMessage": f"{name} is ready."})
                except (OllamaError, ValueError, OSError) as exc:
                    self._settingsUpdate.emit({"pulling": "", "pullMessage": f"{name} did not download: {exc}"})
                self.refreshModels()
                threading.Thread(target=lambda: self._systemUpdate.emit({"route": route_status()}), daemon=True).start()

            threading.Thread(target=work, name="apvis-pull", daemon=True).start()

        @Slot()
        @guest_mode.owner_only("Setting up local AI")
        def setupLocalAI(self) -> None:
            """Install Ollama and the two recommended models in a visible terminal (the owner types their password)."""
            script = ("echo 'Installing Ollama (the official installer from ollama.com). It will ask for your password.'; "
                      "curl -fsSL https://ollama.com/install.sh | sh && "
                      "ollama pull llama3.2:1b && ollama pull qwen2.5-coder:1.5b && ollama pull qwen2.5:0.5b && "
                      "echo && echo 'Local AI is ready. You can close this window.' || "
                      "echo && echo 'Something went wrong above. Nothing else was changed.'")
            try:
                subprocess.Popen(["/usr/bin/foot", "--hold", "--title=APVIS · set up local AI", "sh", "-c", script],
                                 close_fds=True, start_new_session=True)
                self._apply_settings({"pullMessage": "Setting up local AI in the terminal window…"})
            except OSError as exc:
                self._apply_settings({"pullMessage": f"Couldn't open a terminal: {exc}"})

        @Slot(str)
        def testOllama(self, url: str) -> None:
            """Check an Ollama address without saving it (local/LAN addresses only)."""
            self._apply_settings({"test": "Testing…", "testOk": False, "saved": ""})

            def work() -> None:
                try:
                    client = OllamaClient(url, timeout=5)
                    version, models = client.version(), client.models()
                    names = ", ".join(m.name for m in models) or "no models installed"
                    self._settingsUpdate.emit({"test": f"Connected · Ollama {version} · {names}", "testOk": True})
                except (ValueError, OllamaError) as exc:
                    self._settingsUpdate.emit({"test": str(exc), "testOk": False})

            threading.Thread(target=work, name="apvis-settings", daemon=True).start()

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def saveOllama(self, url: str) -> None:
            try:
                config = AskConfig.load()
                config.ollama_url = url
                config.save()
                self._apply_settings({"ollamaUrl": config.ollama_url, "saved": "Saved. Ask now uses " + config.ollama_url})
                threading.Thread(target=lambda: self._systemUpdate.emit({"route": route_status()}), daemon=True).start()
            except (OSError, ValueError) as exc:
                self._apply_settings({"saved": f"Not saved: {exc}"})

        @Property("QVariantList", notify=memoryChanged)
        def inbox(self) -> list[dict[str, object]]:
            return self._inbox

        @Property("QVariantList", notify=memoryChanged)
        def notes(self) -> list[dict[str, object]]:
            return self._notes

        @Property(str, constant=True)
        def vaultPath(self) -> str:
            return str(Vault().root)

        # ---- V3 M2: one queue for local model work, and meaning search on the Memory page
        @staticmethod
        def _queue_view() -> dict[str, object]:
            snap = SCHEDULER.snapshot()
            running = snap["running"][0]["what"] if snap["running"] else ""
            return {"state": snap["state"], "running": running, "waiting": len(snap["waiting"]),
                    "overlaps": snap["overlaps"], "yields": snap["yields"], "jobs": snap["jobs"]}

        # ---- V3 M5: the local AI drafts plans (always approved on screen before anything runs)
        @staticmethod
        def _plan_chat(messages, schema):
            from .ask import resolve_model
            from .scheduler import LIVE
            config = AskConfig.load()
            service = AskService(config)
            boost = service.boost_client("general")
            if boost is not None:
                client, model, where = boost[0], boost[1], "boost"
            else:
                client = OllamaClient(config.ollama_url, timeout=5)
                installed = client.models()
                model = resolve_model("general", config.roles, installed) or resolve_model("fast", config.roles, installed)
                where = "local"
            if not model:
                raise OllamaError("no local model is installed")
            with SCHEDULER.slot(LIVE, "planning"):
                reply = "".join(client.chat_stream(model, messages, max_tokens=500, read_timeout=120.0, fmt=schema,
                                                   options=brain.load_options(where),
                                                   keep_alive=brain.keep_alive("general", where)))
            return reply, model

        # ---- V3 M4: episodes
        @staticmethod
        def _episodes_on() -> bool:
            if guest_mode.this_session_is_guest():
                return False                     # Guest: no session memory
            try:
                return AskConfig.load().episodes
            except (OSError, ValueError):
                return False

        @staticmethod
        def _episode_chat(messages, should_yield):
            """The fast local model writes a session's one-line summary (runs as background work)."""
            from .ask import resolve_model
            config = AskConfig.load()
            client = OllamaClient(config.ollama_url, timeout=5)
            model = resolve_model("fast", config.roles, client.models())
            if not model:
                return "", ""
            chat = episodes_mod.ollama_chat(client, model, brain.load_options("local"), brain.keep_alive("fast"))
            return chat(messages, should_yield)

        def _episode_views(self) -> list[dict[str, object]]:
            try:
                return [e.to_dict() for e in self._episodes.store.list()[:60]]
            except OSError:
                return []

        @Property("QVariantList", notify=memoryChanged)
        def episodes(self) -> list[dict[str, object]]:
            return self._episode_list

        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setEpisodes(self, on: bool) -> None:
            """Session memory on/off. Off stops recording and drops the session in progress; saved
            episodes stay until they expire or are forgotten."""
            try:
                config = AskConfig.load()
                config.episodes = bool(on)
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"episodesMessage": str(exc)})
                return
            if on:
                self._episodes.start()
                message = "On. Each Ask session gets a one-line summary, kept for 30 days."
            else:
                self._episodes.drop()
                self._episodes.stop()
                message = "Off. Nothing new is remembered; saved sessions stay until they expire or you forget them."
            self._apply_settings({"episodes": {"enabled": bool(on)}, "episodesMessage": message})
            self._refresh_memory()

        @Slot(str)
        @guest_mode.owner_only("Memory")
        def forgetEpisode(self, episode_id: str) -> None:
            try:
                self._episodes.store.forget(episode_id)
            except OSError as exc:
                self._error(f"Could not forget that session: {exc}")
            self._refresh_memory()

        @Slot()
        @guest_mode.owner_only("Memory")
        def forgetAllEpisodes(self) -> None:
            try:
                self._episodes.drop()
                self._episodes.store.forget_all()
            except OSError as exc:
                self._error(f"Could not forget the sessions: {exc}")
            self._refresh_memory()

        @Slot()
        def ownerTyping(self) -> None:
            """A key in the Ask bar: background model work (indexing) gives way straight away."""
            SCHEDULER.owner_active()

        @Slot(str)
        def searchMemory(self, query: str) -> None:
            """Memory page: search the whole vault (by meaning too, when it is switched on)."""
            query = (query or "").strip()[:300]
            if not query:
                self._apply_settings({"memorySearch": {}})
                return
            self._apply_settings({"memorySearch": {"query": query, "busy": True, "results": []}})

            def work() -> None:
                info: dict[str, object] = {}
                try:
                    vault = Vault()
                    hits = semantic.search(vault, query, limit=12, info=info)
                    results = [{"score": round(score, 3), **note.summary(vault.root)} for score, note in hits]
                    self._settingsUpdate.emit({"memorySearch": {"query": query, "busy": False, "results": results,
                                                                "mode": info.get("mode", "keyword")}})
                except (OSError, ValueError) as exc:
                    self._settingsUpdate.emit({"memorySearch": {"query": query, "busy": False, "results": [],
                                                                "error": str(exc)}})

            threading.Thread(target=work, name="apvis-memory-search", daemon=True).start()

        def _refresh_memory(self) -> None:
            try:
                vault = Vault()
                inbox = [{"id": p.proposal_id, "text": p.text, "kind": p.kind, "title": p.title, "reason": p.reason,
                          "source": p.source, "sensitivity": p.sensitivity, "similar": [s["title"] for s in p.similar],
                          "created": p.created} for p in MemoryInbox(vault).pending()]
                notes = [n.summary(vault.root) for n in vault.notes()[:50]]
            except (OSError, ValueError) as exc:
                inbox, notes = [], []
                self._error(f"Vault unavailable: {type(exc).__name__}")
            episodes = self._episode_views()
            if (inbox, notes, episodes) != (self._inbox, self._notes, self._episode_list):
                if notes != self._notes and self._indexer.running():
                    self._indexer.request()          # a note was added, accepted, edited or forgotten
                self._inbox, self._notes, self._episode_list = inbox, notes, episodes
                self.memoryChanged.emit()

        @Slot(str)
        @guest_mode.owner_only("Saving to memory")
        def acceptMemory(self, proposal_id: str) -> None:
            try:
                proposal = MemoryInbox().accept(proposal_id)
                if (self._ask.get("proposal") or {}).get("id") == proposal_id:
                    self._askUpdate.emit({"generation": self._ask_generation, "state": "memory",
                                          "proposal": {**self._ask["proposal"], "status": "accepted"},
                                          "answer": f"Saved to your vault: {Path(proposal.note_path).name}"})
            except (OSError, ValueError, KeyError) as exc:
                self._error(str(exc))
            self.refresh()

        @Slot(str)
        def rejectMemory(self, proposal_id: str) -> None:
            try:
                MemoryInbox().reject(proposal_id)
                if (self._ask.get("proposal") or {}).get("id") == proposal_id:
                    self._askUpdate.emit({"generation": self._ask_generation, "state": "memory",
                                          "proposal": {**self._ask["proposal"], "status": "rejected"},
                                          "answer": "Not saved. Nothing was written to your vault."})
            except (OSError, ValueError, KeyError) as exc:
                self._error(str(exc))
            self.refresh()

        # ---- Installer (V2-14): live media only; the root work runs in apvis-install via pkexec.
        @Property("QVariantMap", notify=installerChanged)
        def installer(self) -> dict[str, object]:
            return self._installer

        @Slot("QVariantMap")
        def _apply_installer(self, change: dict[str, object]) -> None:
            self._installer = {**self._installer, **change}
            self.installerChanged.emit()

        def _helper(self, args: list[str], stdin: str | None = None) -> subprocess.Popen:
            return subprocess.Popen(["/usr/bin/pkexec", INSTALL_HELPER] + args, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        @Slot()
        def installerDisks(self) -> None:
            self._apply_installer({"state": "scanning", "message": "Looking for disks…", "ollama": {}})

            def work() -> None:
                try:
                    out, _ = self._helper(["disks"]).communicate(timeout=60)
                    disks = json.loads(out)
                    if isinstance(disks, dict):          # the helper refused (not live media)
                        raise ValueError(disks.get("message", "installer unavailable"))
                    self._installerUpdate.emit({"state": "choose", "disks": disks,
                                                "message": "" if disks else "No internal disk big enough (16 GB) was found."})
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    self._installerUpdate.emit({"state": "error", "message": f"Couldn't list disks: {exc}"})

            threading.Thread(target=work, name="apvis-install-disks", daemon=True).start()

        @Slot(str)
        def installerScan(self, disk: str) -> None:
            self._apply_installer({"ollama": {"scanning": True}})

            def work() -> None:
                try:
                    out, _ = self._helper(["scan", disk]).communicate(timeout=300)
                    self._installerUpdate.emit({"ollama": json.loads(out) or {"none": True}})
                except (OSError, ValueError, subprocess.SubprocessError):
                    self._installerUpdate.emit({"ollama": {"none": True, "error": True}})

            threading.Thread(target=work, name="apvis-install-scan", daemon=True).start()

        @Slot(str, str, bool)
        def installerStart(self, disk: str, password: str, restore_ollama: bool, setup_ai: bool = False) -> None:
            self._apply_installer({"state": "installing", "pct": 1, "message": "Starting…"})

            def work() -> None:
                result: dict[str, object] = {"done": True, "ok": False, "message": "The installer stopped unexpectedly."}
                try:
                    proc = self._helper(["install", disk] + (["--restore-ollama"] if restore_ollama else [])
                                        + (["--setup-ai"] if setup_ai else []))
                    assert proc.stdin is not None and proc.stdout is not None
                    proc.stdin.write(password + "\n")   # stdin only: never on a command line or in a log
                    proc.stdin.close()
                    for line in proc.stdout:
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        if data.get("done"):
                            result = data
                        else:
                            self._installerUpdate.emit({"pct": data.get("pct", 0), "message": data.get("message", "")})
                    proc.wait()
                except OSError as exc:
                    result = {"ok": False, "message": f"Install stopped: {exc}"}
                self._installerUpdate.emit({"state": "done" if result.get("ok") else "error", "pct": 100 if result.get("ok") else 0,
                                            "message": result.get("message", "")})

            threading.Thread(target=work, name="apvis-install", daemon=True).start()

        @Slot()
        def restartComputer(self) -> None:
            self._control_job(lambda: self._control_centre.power("reboot"))

        # ---- APVIS layer updates (V2-20): check, install (verified), roll back.
        @Property("QVariantMap", notify=updatesChanged)
        def updates(self) -> dict[str, object]:
            return self._updates

        @Slot("QVariantMap")
        def _apply_updates(self, change: dict[str, object]) -> None:
            self._updates = {**self._updates, **updates.status(), **change}
            self.updatesChanged.emit()
            if change.get("restart"):
                # The launcher restarts Home on this code and loads the new layer.
                QTimer.singleShot(1500, lambda: QGuiApplication.exit(updates.RESTART_EXIT_CODE))

        @Slot()
        def checkUpdates(self) -> None:
            self._apply_updates({"state": "checking", "message": "Checking for updates…"})

            def work() -> None:
                offer = updates.check()
                self._update_offer = offer if offer["status"] == "available" else None
                self._updatesUpdate.emit({"state": offer["status"], "message": offer["message"],
                                          "latest": offer.get("latest", ""), "notes": offer.get("notes", "")})

            threading.Thread(target=work, name="apvis-update-check", daemon=True).start()

        @Slot()
        @guest_mode.owner_only("Updates")
        def installUpdate(self) -> None:
            offer = self._update_offer
            if not offer:
                self._apply_updates({"state": "error", "message": "Check for updates first."})
                return
            self._apply_updates({"state": "installing", "message": f"Downloading and verifying {offer['latest']}…"})

            def work() -> None:
                try:
                    result = updates.install(offer)
                    self._updatesUpdate.emit({"state": "installed", "message": result["message"], "restart": True})
                except (updates.UpdateError, OSError) as exc:
                    self._updatesUpdate.emit({"state": "error", "message": str(exc)})

            threading.Thread(target=work, name="apvis-update-install", daemon=True).start()

        @Slot()
        @guest_mode.owner_only("Updates")
        def rollbackUpdate(self) -> None:
            try:
                result = updates.rollback("rolled back by the owner")
            except OSError as exc:
                result = {"ok": False, "message": f"Rollback failed: {exc}"}
            self._apply_updates({"state": "rolledback" if result["ok"] else "error", "message": result["message"],
                                 "restart": result["ok"]})

        # ---- Developer Mode (V2-19): off unless the owner turns it on.
        @Property(bool, notify=devChanged)
        def developerMode(self) -> bool:
            return self._developer

        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setReducedMotion(self, on: bool) -> None:
            """Accessibility (V2-17): calm, still visuals; remembered across restarts."""
            try:
                if on:
                    REDUCED_MOTION_FLAG.parent.mkdir(parents=True, exist_ok=True)
                    REDUCED_MOTION_FLAG.touch()
                else:
                    REDUCED_MOTION_FLAG.unlink(missing_ok=True)
            except OSError as exc:
                self._error(f"Reduce motion unchanged: {exc}")
                return
            self._reduced = on
            self.frame_gap()
            self.renderChanged.emit()

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def setAccent(self, name: str) -> None:
            """Appearance: the accent colour, remembered across restarts."""
            if name not in ACCENTS:
                return
            try:
                save_ui_prefs({"accent": name, "style": self._style, "lockOnStart": self._lock_on_start})
            except OSError as exc:
                self._error(f"Accent unchanged: {exc}")
                return
            self._accent = name
            apply_body_font(name)
            self.renderChanged.emit()

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def setStyle(self, name: str) -> None:
            """Appearance: rounded glass panels (default) or chamfered HUD panels."""
            if name not in STYLES:
                return
            try:
                save_ui_prefs({"accent": self._accent, "style": name, "lockOnStart": self._lock_on_start})
            except OSError as exc:
                self._error(f"Style unchanged: {exc}")
                return
            self._style = name
            self.renderChanged.emit()

        # ---- APVIS API: warm-up, gaming PC boost, the local endpoint
        def _warm_if_needed(self, route: dict[str, object]) -> None:
            """Keep the fast model loaded with Ask's own settings and its system prompt cached
            (after a restart of Ollama, or the first time it is seen)."""
            if getattr(self, "_warming", False):
                return
            model = str(route["model"])
            try:
                loaded = OllamaClient(str(route["endpoint"]), timeout=2).loaded()
            except (OllamaError, OSError, ValueError):
                return
            if getattr(self, "_preloaded", None) == model and any(n.removesuffix(":latest") == model.removesuffix(":latest") for n in loaded):
                return
            self._warming = True

            def work() -> None:
                try:
                    self._preloaded = AskService().warm(model)
                except (OSError, ValueError):
                    self._preloaded = None
                finally:
                    self._warming = False

            threading.Thread(target=work, name="apvis-warm", daemon=True).start()

        def _boost_info(self, config: AskConfig, state: dict[str, object] | None = None) -> dict[str, object]:
            state = state if state is not None else (brain.BOOST.snapshot() if config.boost_url else {})
            models = list(state.get("models", [])) if state.get("url") == config.boost_url else []
            reachable = state.get("reachable") if state.get("url") == config.boost_url else None
            return {"url": config.boost_url, "enabled": config.boost_enabled, "mac": config.boost_mac,
                    "reachable": reachable, "models": models, "fast": brain.pick_boost_model("fast", models) or "",
                    "code": brain.pick_boost_model("code", models) or ""}

        def _api_info(self, config: AskConfig) -> dict[str, object]:
            return {"enabled": config.api_enabled, "running": self._api_server is not None,
                    "url": f"http://{apvis_api.HOST}:{apvis_api.PORT}"}

        def _check_boost(self) -> None:
            try:
                config = AskConfig.load()
            except (OSError, ValueError):
                return
            if not (config.boost_enabled and config.boost_url):
                return

            def work() -> None:
                state = brain.BOOST.check(config.boost_url)
                self._settingsUpdate.emit({"boost": self._boost_info(config, state)})

            threading.Thread(target=work, name="apvis-boost", daemon=True).start()

        @Slot(str, bool)
        @guest_mode.owner_only("Settings")
        def setBoost(self, url: str, enabled: bool) -> None:
            try:
                config = AskConfig.load()
                config.boost_url, config.boost_enabled = (url or "").strip(), bool(enabled)
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": str(exc)})
                return
            self._apply_settings({"boost": self._boost_info(config), "boostMessage":
                                  ("Gaming PC boost is on. Checking it now…" if config.boost_enabled else
                                   "Saved. Ask uses this computer only." if not config.boost_url else "Saved. Gaming PC boost is off.")})
            self._check_boost()

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def setBoostMac(self, mac: str) -> None:
            try:
                config = AskConfig.load()
                config.boost_mac = (mac or "").strip()
                config.save()
                self._apply_settings({"boost": self._boost_info(config), "boostMessage": "Saved the gaming PC's network address."})
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": str(exc)})

        @Slot()
        def findBoost(self) -> None:
            self._apply_settings({"boostMessage": "Looking for Ollama on your home network…", "boostFound": []})

            def work() -> None:
                found = brain.find_ollama_on_lan()
                self._settingsUpdate.emit({"boostFound": found, "boostMessage":
                                           f"Found {len(found)}: " + ", ".join(found) if found else
                                           "No computer on your network answers as Ollama. On the gaming PC, start Ollama with "
                                           "OLLAMA_HOST=0.0.0.0 so other computers can reach it."})

            threading.Thread(target=work, name="apvis-find", daemon=True).start()

        @Slot()
        @guest_mode.owner_only("Waking the gaming PC")
        def wakeBoost(self) -> None:
            try:
                brain.wake_on_lan(AskConfig.load().boost_mac)
                self._apply_settings({"boostMessage": "Wake-up sent. The gaming PC takes about half a minute to start; "
                                                      "Ask uses it as soon as it answers."})
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": f"Couldn't send the wake-up: {exc}"})

        # ---- V3 M1: search the vault by meaning
        def _memory_info(self, config: AskConfig | None = None, status: dict[str, object] | None = None) -> dict[str, object]:
            try:
                config = config or AskConfig.load()
            except (OSError, ValueError):
                return {"enabled": False}
            status = status if status is not None else self._indexer.last
            return {"enabled": config.semantic_memory, "model": status.get("model", ""), "state": status.get("state", ""),
                    "notes": status.get("notes", 0), "chunks": status.get("chunks", 0),
                    "embedded": status.get("embedded", 0), "seconds": status.get("seconds", 0),
                    "message": status.get("message", "")}

        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setSemanticMemory(self, on: bool) -> None:
            """Switch meaning search on (downloading the embedding model through Ollama if needed) or off.
            Off keeps the index file, so switching back on is instant; the notes are never touched."""
            try:
                config = AskConfig.load()
                config.semantic_memory = bool(on)
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"memoryMessage": str(exc)})
                return
            if not on:
                self._indexer.stop()
                self._apply_settings({"memory": self._memory_info(config), "memoryMessage":
                                      "Off. Your vault is searched by words only."})
                return
            self._apply_settings({"memory": self._memory_info(config), "memoryMessage": "Checking for an embedding model…"})

            def work() -> None:
                client = OllamaClient(config.ollama_url, timeout=10)
                try:
                    installed = [m.name for m in client.models()]
                except OllamaError as exc:
                    self._settingsUpdate.emit({"memoryMessage": f"Local AI isn't running, so meaning search waits: {exc}"})
                    return
                if semantic.pick_model(installed) is None:
                    for name in semantic.MODELS:
                        def progress(status: str, done: int, total: int, name: str = name) -> None:
                            pct = f" {round(100 * done / total)}%" if total else ""
                            self._settingsUpdate.emit({"memoryMessage": f"Downloading {name}: {status}{pct}"})
                        try:
                            client.pull(name, progress)
                            break
                        except OllamaError as exc:
                            self._settingsUpdate.emit({"memoryMessage": f"{name} did not download: {exc}"})
                    else:
                        return
                self._settingsUpdate.emit({"memoryMessage": "Reading your notes for meaning. Ask works as usual meanwhile."})
                self._indexer.start()

            threading.Thread(target=work, name="apvis-semantic", daemon=True).start()

        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setApiEnabled(self, on: bool) -> None:
            try:
                config = AskConfig.load()
                config.api_enabled = bool(on)
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": str(exc)})
                return
            if on and self._api_server is None:
                self._api_server = apvis_api.start_background()
            elif not on and self._api_server is not None:
                server, self._api_server = self._api_server, None
                threading.Thread(target=server.shutdown, daemon=True).start()
            self._apply_settings({"api": self._api_info(config)})

        @Slot(str, str)
        def _home_command(self, kind: str, value: str) -> None:
            """Commands from the local API (e.g. Win+Space opens the Apps Store), run on the UI thread."""
            if kind == "page":
                self.pageRequested.emit(value)
            elif kind == "ask":
                self.pageRequested.emit("")
                self.askQuestion(value)
            elif kind == "screen":
                self.pageRequested.emit("")
                self._screen_question(value)
            elif kind == "power":
                action, _, delay = value.partition(":")
                if not guest_mode.power_allowed(action, self._guest):
                    return
                QTimer.singleShot(int(delay or 0) * 1000, lambda: self.powerRequested.emit(action))
            elif kind == "restart":
                self.restartHome()           # same as Settings > Updates after an install: the launcher restarts Home

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def setAnswerLength(self, length: str) -> None:
            try:
                config = AskConfig.load()
                config.answer_length = length
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": str(exc)})
                return
            self._preloaded = None            # the system prompt changed: warm the cache with the new one
            self._apply_settings({"answerLength": config.answer_length})

        # ---- V4: web search when Ask is unsure (owner's choice, 2026-10-19; only the search words are sent)
        @staticmethod
        def _web_search_on() -> bool:
            try:
                return AskConfig.load().web_search
            except (OSError, ValueError):
                return False

        @Slot(bool)
        def setWebSearch(self, on: bool) -> None:
            try:
                config = AskConfig.load()
                config.web_search = bool(on)
                config.save()
            except (OSError, ValueError) as exc:
                self._apply_settings({"boostMessage": str(exc)})
                return
            self._apply_settings({"webSearch": {"enabled": config.web_search}})

        # ---- Weather (Settings -> Appearance -> Weather; off until a town is set)
        def _refresh_weather(self, place: dict[str, object] | None = None) -> None:
            place = place or weather.load().get("place")
            if not place:
                return
            self._weather_busy = True

            def work() -> None:
                try:
                    self._weather = weather.fetch_now(place)
                    self._settingsUpdate.emit({"weather": {"place": place.get("label", ""), "reading": self._weather}})
                except (OSError, ValueError, KeyError) as exc:
                    self._settingsUpdate.emit({"weatherMessage": f"Weather didn't load: {exc}"})
                finally:
                    self._weather_busy = False
                self._status_wake.set()

            threading.Thread(target=work, name="apvis-weather", daemon=True).start()

        @Slot(str)
        @guest_mode.owner_only("Settings")
        def setWeatherTown(self, town: str) -> None:
            if not town.strip():
                weather.save({})
                self._weather = None
                self._apply_settings({"weather": {}, "weatherMessage": "Weather is off."})
                self._status_wake.set()
                return
            self._apply_settings({"weatherMessage": f"Looking up {town.strip()}…"})

            def work() -> None:
                try:
                    place = weather.geocode(town)
                    weather.save({"place": place})
                    self._settingsUpdate.emit({"weatherMessage": f"Weather for {place['label']}.", "weather": {"place": place["label"]}})
                    self._refresh_weather(place)
                except (OSError, ValueError, KeyError) as exc:
                    self._settingsUpdate.emit({"weatherMessage": str(exc)})

            threading.Thread(target=work, name="apvis-weather-town", daemon=True).start()

        # ---- Backup & restore (Settings -> Backup)
        def _backup_state(self) -> dict[str, object]:
            places = backup.targets()
            return {"targets": places, "found": backup.existing(places)}

        @Slot()
        def refreshBackups(self) -> None:
            threading.Thread(target=lambda: self._settingsUpdate.emit({"backup": self._backup_state()}),
                             name="apvis-backups", daemon=True).start()

        @Slot(str)
        @guest_mode.owner_only("Backups")
        def backupTo(self, place: str) -> None:
            if place not in {t["path"] for t in backup.targets()}:
                self._apply_settings({"backupMessage": "That drive isn't available any more."})
                return
            self._apply_settings({"backupMessage": "Backing up your APVIS data…", "backupBusy": True})

            def work() -> None:
                try:
                    out = backup.create(Path(place), product=product_version())
                    message = f"Saved {out.name} ({out.stat().st_size / 1048576:.1f} MB) to {place}."
                except (OSError, ValueError, tarfile.TarError) as exc:
                    message = f"Backup didn't finish: {exc}"
                self._settingsUpdate.emit({"backupMessage": message, "backupBusy": False, "backup": self._backup_state()})

            threading.Thread(target=work, name="apvis-backup", daemon=True).start()

        @Slot(str)
        @guest_mode.owner_only("Backups")
        def restoreBackup(self, archive: str) -> None:
            if archive not in {f["path"] for f in backup.existing(backup.targets())}:
                self._apply_settings({"backupMessage": "That backup isn't available any more."})
                return
            self._apply_settings({"backupMessage": "Restoring…", "backupBusy": True})

            def work() -> None:
                try:
                    out = backup.restore(Path(archive))
                    message = (f"Restored {out['restored']} files. Your data from before was saved first"
                               + (f" ({Path(out['safety']).name})" if out["safety"] else "") + ". Restart Home to see everything.")
                    done = True
                except (OSError, ValueError, tarfile.TarError) as exc:
                    message, done = f"Restore didn't finish: {exc}", False
                self._settingsUpdate.emit({"backupMessage": message, "backupBusy": False, "backupRestored": done,
                                           "backup": self._backup_state()})

            threading.Thread(target=work, name="apvis-restore", daemon=True).start()

        @Slot()
        def restartHome(self) -> None:
            QTimer.singleShot(300, lambda: QGuiApplication.exit(updates.RESTART_EXIT_CODE))

        @Slot(str)
        def noteApp(self, key: str) -> None:
            """The Apps Store remembers what the owner opens (Recently used)."""
            try:
                self._apply_apps({"prefs": appstore.note_use(key)})
            except (OSError, ValueError):
                pass

        @Slot(str)
        def togglePin(self, key: str) -> None:
            try:
                prefs = appstore.toggle_pin(key)
                self._apply_apps({"prefs": prefs, "message": "Pinned to Home." if key in prefs["pinned"] else "Unpinned from Home."})
            except (OSError, ValueError) as exc:
                self._apply_apps({"message": str(exc)})

        # ---- Apps Store (page 09): installed apps, the catalog, installs through the root helper
        @Property("QVariantMap", notify=appsChanged)
        def apps(self) -> dict[str, object]:
            return self._apps

        @Slot("QVariantMap")
        def _apply_apps(self, update: dict[str, object]) -> None:
            self._apps = {**self._apps, **update}
            self.appsChanged.emit()

        @Slot()
        def refreshApps(self) -> None:
            def work() -> None:
                installed = appstore.installed_apps()
                self._apps_installed = installed
                self._appsUpdate.emit(appstore.state(installed))

            threading.Thread(target=work, name="apvis-apps", daemon=True).start()

        @Slot(str)
        def launchApp(self, desktop_id: str) -> None:
            try:
                name = appstore.launch(desktop_id, self._apps_installed or None)
                self._apply_apps({"message": f"Opening {name}…"})
            except (OSError, ValueError) as exc:
                self._apply_apps({"message": str(exc)})

        @Slot(str, str, str)
        @guest_mode.owner_only("Installing apps")
        def appJob(self, action: str, app_id: str, password: str) -> None:
            """Install or remove one catalog app: the owner's password first, then the root helper."""
            if (self._apps.get("job") or {}).get("state") in {"checking", "running"}:
                return
            self._apply_apps({"job": {"id": app_id, "action": action, "state": "checking", "pct": -1, "message": "Checking your password…"}})

            def work() -> None:
                ok, why = lockscreen.check_password(password)
                if not ok:
                    self._appsUpdate.emit({"job": {"id": app_id, "action": action, "state": "error", "pct": -1,
                                                   "message": why or "That password isn't right."}})
                    return
                self._appsUpdate.emit({"job": {"id": app_id, "action": action, "state": "running", "pct": 0, "message": "Starting…"}})
                last = [0.0]

                def progress(pct: int, message: str) -> None:
                    now = time.monotonic()
                    if now - last[0] > 0.25:
                        last[0] = now
                        self._appsUpdate.emit({"job": {"id": app_id, "action": action, "state": "running", "pct": pct, "message": message}})

                try:
                    ok, message = appstore.run_job(action, app_id, progress)
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    ok, message = False, f"Couldn't start: {exc}"
                installed = appstore.installed_apps()
                self._apps_installed = installed
                self._appsUpdate.emit({**appstore.state(installed), "job": {"id": app_id, "action": action,
                                       "state": "done" if ok else "error", "pct": 100 if ok else -1, "message": message}})

            threading.Thread(target=work, name="apvis-app-job", daemon=True).start()

        # ---- this computer (terminal card, Devices page)
        @Property("QVariantMap", notify=hostChanged)
        def host(self) -> dict[str, object]:
            return self._host

        @Property("QVariantMap", notify=hostChanged)
        def devices(self) -> dict[str, object]:
            return self._devices

        @Slot("QVariantMap")
        def _apply_host(self, update: dict[str, object]) -> None:
            if "host" in update:
                self._host = update["host"]
            if "devices" in update:
                self._devices = update["devices"]
            self.hostChanged.emit()

        @Slot()
        def refreshDevices(self) -> None:
            threading.Thread(target=lambda: self._hostUpdate.emit({"devices": hostinfo.devices()}),
                             name="apvis-devices", daemon=True).start()

        @Slot(int)
        def endProcess(self, pid: int) -> None:
            """System page: end one of the owner's own programs (never Home itself)."""
            try:
                import getpass
                import psutil
                if pid == os.getpid():
                    raise ValueError("that is APVIS Home itself")
                proc = psutil.Process(pid)
                if proc.username().split("\\")[-1] != getpass.getuser():
                    raise PermissionError("only your own programs can be ended here")
                name = proc.name()
                proc.terminate()
                self._error("")
                self.notify("Program ended", name)
            except Exception as exc:  # gone, denied, or refused above
                self._error(f"Could not end that program: {exc}")

        # ---- the lock screen
        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setLockOnStart(self, on: bool) -> None:
            try:
                save_ui_prefs({"accent": self._accent, "style": self._style, "lockOnStart": bool(on)})
            except OSError as exc:
                self._error(f"Setting unchanged: {exc}")
                return
            self._lock_on_start = bool(on)
            self.renderChanged.emit()

        @Slot(bool)
        def setLockChrome(self, locked: bool) -> None:
            """When Home locks, bring it in front of open apps (Wayland apps can't raise themselves, so this asks
            the compositor through wlrctl). Best effort: without wlrctl nothing happens."""
            if not locked:
                return
            wlrctl = Path("/usr/bin/wlrctl")
            if not wlrctl.is_file():
                return
            try:
                subprocess.run([str(wlrctl), "toplevel", "focus", "app_id:apvis-home"], timeout=3, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass

        @Slot(str)
        def unlock(self, password: str) -> None:
            def work() -> None:
                ok, message = lockscreen.check_password(password)
                self.unlockResult.emit(ok, message)
            threading.Thread(target=work, name="apvis-unlock", daemon=True).start()

        # ---- the Home mini terminal (fixed commands, never a shell)
        @Slot(str)
        def miniTerminal(self, line: str) -> None:
            def work() -> None:
                try:
                    result = miniterm.run(line)
                except Exception as exc:  # a measurement failed: say so in the card
                    result = {"lines": [{"t": f"That didn't work: {exc}", "c": "warn"}]}
                result["command"] = line
                self.miniTerminalOutput.emit(result)
            threading.Thread(target=work, name="apvis-miniterm", daemon=True).start()

        # ---- power with a goodbye screen
        @Slot(str)
        def requestPower(self, action: str) -> None:
            if action in {"suspend", "reboot", "poweroff", "logout"} and guest_mode.power_allowed(action, self._guest):
                self.powerRequested.emit(action)

        # ---- world intelligence for the Home card
        @Slot(bool)
        def setHomeIntel(self, wanted: bool) -> None:
            """The Home Live Intelligence card wants the light world feeds while Home shows."""
            self._home_intel = bool(wanted)
            self._atlas_wake.set()
            self._world_wake.set()
            if wanted:
                self._ensure_world_thread()

        def _ensure_world_thread(self) -> None:
            if self._world_thread is not None and self._world_thread.is_alive():
                return

            def world() -> None:
                osint = OsintFeed()
                while (self._atlas_visible or self._home_intel) and not self._stopping:
                    osint.poll(lambda: self._worldUpdate.emit(json.dumps(osint.snapshot())))
                    self._world_wake.wait(5.0)
                    self._world_wake.clear()

            self._world_thread = threading.Thread(target=world, name="apvis-osint", daemon=True)
            self._world_thread.start()

        @Slot(bool)
        @guest_mode.owner_only("Settings")
        def setDeveloperMode(self, on: bool) -> None:
            try:
                self._developer = devinfo.set_enabled(on)
            except OSError as exc:
                self._error(f"Developer mode unchanged: {exc}")
            self.devChanged.emit()

        @Property("QVariantMap", notify=devChanged)
        def devInfo(self) -> dict[str, object]:
            return self._dev_info

        @Slot("QVariantMap")
        def _apply_dev(self, info: dict[str, object]) -> None:
            self._dev_info = info
            self.devChanged.emit()

        @Slot()
        def refreshDev(self) -> None:
            if not self._developer:
                return
            render, frames, atlas = self.render, dict(self._frame_info), dict(self._atlas)
            route, missions = dict(self._route or {}), list(self._missions)
            notes, inbox = len(self._notes), len(self._inbox)

            def work() -> None:
                self._devUpdate.emit(devinfo.collect(render, frames, atlas, route, missions, notes, inbox))

            threading.Thread(target=work, name="apvis-dev", daemon=True).start()

        @Property("QVariantMap", notify=frameInfoChanged)
        def frameInfo(self) -> dict[str, object]:
            """Measured frame rate of the last ~2 s window (for Settings and developers)."""
            return self._frame_info

        # ---- Control Centre: owner-pressed controls run at once and are read back.
        @Property("QVariantMap", notify=controlChanged)
        def control(self) -> dict[str, object]:
            return self._control

        @Slot("QVariantMap")
        def _apply_control(self, update: dict[str, object]) -> None:
            self._control = {**self._control, **update}
            self.controlChanged.emit()

        def _control_job(self, job) -> None:
            def work() -> None:
                try:
                    result = job()
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    result = {"ok": False, "message": f"Unavailable: {exc}"}
                self._controlUpdate.emit(result)
            threading.Thread(target=work, name="apvis-control", daemon=True).start()

        @Slot()
        def refreshControl(self) -> None:
            self._control_job(lambda: {"state": self._control_centre.state()})  # keeps the last result message

        @Slot(int)
        def setVolume(self, percent: int) -> None:
            self._control_job(lambda: self._control_centre.set_volume(percent))

        @Slot(bool)
        def setMuted(self, muted: bool) -> None:
            self._control_job(lambda: self._control_centre.set_muted(muted))

        @Slot(str)
        def mediaControl(self, action: str) -> None:
            """Control Centre: play/pause, next, previous for whatever is playing."""
            self._control_job(lambda: self._control_centre.media_command(action))

        @Slot(bool)
        @guest_mode.owner_only("Remote access")
        def setRemoteAccess(self, on: bool) -> None:
            self._control_job(lambda: self._control_centre.set_remote(on))

        @Slot(int, int)
        @guest_mode.owner_only("Settings")
        def setPowerTimers(self, screen_off_min: int, sleep_min: int) -> None:
            self._control_job(lambda: self._control_centre.set_power_timers(screen_off_min, sleep_min))

        @Slot(str)
        def power(self, action: str) -> None:
            if not guest_mode.power_allowed(action, self._guest):
                self._error(guest_mode.refusal("Restart, sleep and shut down"))
                return

            def job():
                result = self._control_centre.power(action)
                if not result.get("ok", True) and action in {"poweroff", "reboot", "suspend"}:
                    self._askUpdate.emit({"generation": self._ask_generation, "state": "error",
                                          "error": result.get("message", "The system refused.")})
                return result
            self._control_job(job)

        @Slot(bool)
        @guest_mode.owner_only("Wi-Fi")
        def setWifi(self, on: bool) -> None:
            self._control_job(lambda: self._control_centre.set_wifi(on))

        @Slot(bool)
        def setDoNotDisturb(self, on: bool) -> None:
            """Toggle mako's do-not-disturb mode and report what actually took effect."""
            makoctl = "/usr/bin/makoctl"
            try:
                subprocess.run([makoctl, "mode", "-a" if on else "-r", "do-not-disturb"],
                               capture_output=True, timeout=3, check=True)
                modes = subprocess.run([makoctl, "mode"], capture_output=True, text=True, timeout=3, check=True).stdout.split()
                active = "do-not-disturb" in modes
                note = ("On. Only approvals will pop up." if active else "Off. Notifications show normally.")                     if active == on else "The notification service did not change mode."
                self._apply_settings({"dnd": active, "dndNote": note})
            except (OSError, subprocess.SubprocessError) as exc:
                self._apply_settings({"dndNote": f"Notifications unavailable: {type(exc).__name__}"})

        @Slot(bool)
        def setSharedDisplay(self, shared: bool) -> None:
            """A second screen the owner has not confirmed: project without private context (V2-13)."""
            context = DisplayContext.SHARED if shared else DisplayContext.PRIVATE
            if context != self._display_context:
                self._display_context = context
                self.refresh()

        @Slot(str, str)
        def notify(self, title: str, body: str) -> None:
            """A desktop notification (mako) for things that need the owner while Home is not in front."""
            if Path("/usr/bin/notify-send").is_file():
                subprocess.Popen(["/usr/bin/notify-send", "--app-name=APVIS", "--urgency=critical",
                                  title[:80], body[:200]], close_fds=True, start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        @Slot(str)
        @guest_mode.owner_only("Memory")
        def forgetMemory(self, rel_path: str) -> None:
            """Forget one remembered item: its file goes to the Trash (restorable in Files)."""
            try:
                Vault().forget(rel_path)
                self._error("")
            except (OSError, ValueError) as exc:
                self._error(f"Could not forget that: {exc}")
            self.refresh()

        @Slot(str)
        def openNote(self, rel_path: str) -> None:
            """Open one vault note in the text editor (paths outside the vault are refused)."""
            root = Vault().root
            path = (root / rel_path).resolve()
            try:
                if not path.is_relative_to(root) or not path.is_file():
                    raise OSError("that note is not in your vault")
                opener = ["/usr/bin/gio", "open", str(path)] if Path("/usr/bin/gio").is_file() else ["/usr/bin/pcmanfm-qt", str(path.parent)]
                subprocess.Popen(opener, close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._error("")
            except OSError as exc:
                self._error(f"Could not open the note: {exc}")

        @Slot()
        @guest_mode.owner_only("Notes")
        def newNote(self) -> None:
            """Create: a new, empty note in the vault, opened in the text editor."""
            try:
                path = Vault().write("Note " + time.strftime("%d %b %Y %H.%M"), "", kind="note")
                self.openNote(str(path.relative_to(Vault().root)))
            except (OSError, ValueError) as exc:
                self._error(f"Could not create a note: {exc}")
            self.refresh()

        @Slot()
        def openVault(self) -> None:
            try:
                root = Vault().ensure()
                subprocess.Popen(["/usr/bin/pcmanfm-qt", str(root)], close_fds=True, start_new_session=True)
                self._error("")
            except OSError as exc:
                self._error(f"Could not open the vault: {exc}")
            self.refresh()

        def _memory_request(self, generation: int, question: str) -> bool:
            """Remember/recall/decision requests; True if handled (never reaches a model or Mission Control)."""
            parsed = parse_memory_request(question)
            if parsed is None:
                return False
            kind, data = parsed
            try:
                if kind == "recall":
                    info: dict[str, object] = {}
                    hits = semantic.search(Vault(), data["query"], limit=6, info=info)
                    if hits:
                        lines = []
                        for _, note in hits:
                            excerpt = note.summary(Vault().root)["excerpt"]
                            lines.append(f"• {note.title} ({note.kind}, {note.updated[:10] or 'undated'})"
                                         + (f"\n  {excerpt}" if excerpt else ""))
                        answer = "From your vault:\n\n" + "\n".join(lines)
                    else:
                        answer = f"Nothing in your vault mentions {data['query']!r} yet."
                    self._askUpdate.emit({"generation": generation, "state": "done", "answer": answer,
                                          "meta": "your vault · " + ("searched by meaning" if info.get("mode") == "hybrid" else "searched")
                                                  + " on this device"})
                    return True
                if self._guest:
                    self._askUpdate.emit({"generation": generation, "state": "done", "meta": "guest",
                                          "answer": "Guest keeps nothing, so I can't remember that. Sign in as APVIS to save it."})
                    return True
                proposal = MemoryInbox().propose(data["text"], kind="decision" if kind == "decision" else "note",
                                                 reason=data.get("reason", ""), asked=question)
                view = {"id": proposal.proposal_id, "text": proposal.text, "kind": proposal.kind,
                        "title": proposal.title, "reason": proposal.reason, "similar": [s["title"] for s in proposal.similar],
                        "status": "pending"}
                self._askUpdate.emit({"generation": generation, "state": "memory", "proposal": view, "answer": ""})
            except SensitiveContent as exc:
                self._askUpdate.emit({"generation": generation, "state": "error", "error": str(exc)})
            except (OSError, ValueError) as exc:
                self._askUpdate.emit({"generation": generation, "state": "error", "error": f"Vault unavailable: {exc}"})
            return True

        @Property("QVariantMap", notify=atlasChanged)
        def atlas(self) -> dict[str, object]:
            return self._atlas

        @Property(str, notify=atlasChanged)
        def atlasAircraft(self) -> str:
            # One JSON string per update; element-wise list access from QML is slow.
            return self._atlas_rows

        @Property(str, constant=True)
        def atlasMap(self) -> str:
            return self._coast_json

        @Property(str, constant=True)
        def earthDots(self) -> str:
            """Flat [lat, lon, ...] land sample points (Natural Earth) for the dot-matrix world."""
            return self._earth_dots

        @Property(str, constant=True)
        def worldLand(self) -> str:
            return self._world_land

        @Property(str, constant=True)
        def worldBorders(self) -> str:
            return self._world_borders

        @Property(str, notify=worldChanged)
        def atlasWorld(self) -> str:
            """World OSINT layers as one JSON string (see apvis_os.osint)."""
            return self._world_json

        @Slot(str)
        def _apply_world(self, data: str) -> None:
            self._world_json = data
            self.worldChanged.emit()

        @Slot(float, float)
        def setAtlasArea(self, lat: float, lon: float) -> None:
            """Aircraft follow the area on screen (the sources answer within 250 NM of a point)."""
            try:
                area = Area(round(lat, 2), round(lon, 2), 250)
            except ValueError:
                return
            if self._atlas_area is None or abs(area.lat - self._atlas_area.lat) + abs(area.lon - self._atlas_area.lon) > 1.0:
                self._atlas_area, self._area_changed = area, True
                self._atlas_wake.set()

        @Slot("QVariantMap", str)
        def _apply_atlas(self, info: dict[str, object], rows: str) -> None:
            self._atlas, self._atlas_rows = info, rows
            self.atlasChanged.emit()

        @Slot(bool)
        def setAtlasVisible(self, visible: bool) -> None:
            """The live feed runs only while Atlas is on screen."""
            self._atlas_visible = bool(visible)
            self._atlas_wake.set()  # lets a waiting poller notice promptly
            self._world_wake.set()
            if not visible:
                return
            self._ensure_world_thread()
            if self._atlas_thread is not None and self._atlas_thread.is_alive():
                return
            if self._atlas.get("status") == "off":
                self._atlas = {"status": "loading"}
                self.atlasChanged.emit()

            def poll() -> None:
                feed = AviationFeed(cache=aviation_cache())
                while self._atlas_visible:
                    if self._area_changed and self._atlas_area is not None:
                        feed.area, self._area_changed = self._atlas_area, False
                        feed.next_allowed = 0.0       # new area: fetch now (the Atlas debounces panning)
                    snapshot = feed.fetch()
                    data = snapshot.to_dict()
                    data.pop("aircraft")
                    data["stats"] = airspace_stats(snapshot.aircraft)
                    rows = json.dumps(feed.rows())
                    self._atlasUpdate.emit(data, rows)
                    # 15 s between updates, or the source's backoff; age labels refresh meanwhile.
                    wait_until = time.monotonic() + max(15.0, feed.backoff_s())
                    while self._atlas_visible and time.monotonic() < wait_until and not self._area_changed:
                        self._atlas_wake.wait(5.0)
                        self._atlas_wake.clear()
                        data = feed.last.to_dict()
                        data.pop("aircraft")
                        data["stats"] = airspace_stats(feed.last.aircraft)
                        self._atlasUpdate.emit(data, rows)

            self._atlas_thread = threading.Thread(target=poll, name="apvis-atlas", daemon=True)
            self._atlas_thread.start()

        @Property("QVariantMap", notify=planePhotoChanged)
        def planePhoto(self) -> dict[str, object]:
            """{hex, state: loading|ready|none, url, caption, credit, source, match} for the focused plane."""
            return self._plane_photo

        @Slot("QVariantMap")
        def _apply_plane_photo(self, photo: dict[str, object]) -> None:
            if photo.get("hex") == self._plane_photo.get("hex"):
                self._plane_photo = photo
                self.planePhotoChanged.emit()

        # ---- open app windows (the APVIS logo's menu, V4)
        @Property("QVariantList", notify=windowsChanged)
        def openWindows(self) -> list[dict[str, str]]:
            return self._windows

        @Property(bool, constant=True)
        def windowsAvailable(self) -> bool:
            return window_list.available()

        @Slot("QVariantList")
        def _apply_windows(self, found: list[dict[str, str]]) -> None:
            self._windows = list(found)
            self.windowsChanged.emit()

        @Slot()
        def refreshWindows(self) -> None:
            threading.Thread(target=lambda: self._windowsUpdate.emit(window_list.list_windows()),
                             name="apvis-windows", daemon=True).start()

        @Slot(int)
        def focusWindow(self, index: int) -> None:
            if 0 <= index < len(self._windows):
                chosen = dict(self._windows[index])
                threading.Thread(target=lambda: window_list.focus(chosen), name="apvis-focus", daemon=True).start()

        @Slot(str, str, str, str)
        def findPlanePhoto(self, hex_id: str, registration: str, type_name: str, type_code: str) -> None:
            """A Wikimedia Commons photo of this airframe or its type (V4 step 3), fetched off the UI thread."""
            hex_id = (hex_id or "").strip().lower()
            if not hex_id or self._plane_photo.get("hex") == hex_id and self._plane_photo.get("state") != "none":
                return
            if hex_id in self._plane_photos:
                self._plane_photo = self._plane_photos[hex_id]
                self.planePhotoChanged.emit()
                return
            self._plane_photo = {"hex": hex_id, "state": "loading"}
            self.planePhotoChanged.emit()

            def work() -> None:
                try:
                    found = pictures.aircraft(registration, type_name, type_code)
                except Exception:                     # a photo is a nicety: never let it break Atlas
                    found = None
                photo: dict[str, object] = {"hex": hex_id, "state": "none"}
                if found:
                    photo = {"hex": hex_id, "state": "ready", "url": QUrl.fromLocalFile(found["file"]).toString(),
                             "caption": found["caption"], "credit": found["credit"], "source": found["source"],
                             "match": found.get("match", "type")}
                    self._plane_photos[hex_id] = photo
                self._planePhotoUpdate.emit(photo)

            threading.Thread(target=work, name="apvis-plane-photo", daemon=True).start()

        @Slot(str, str)
        def focusFlight(self, callsign: str, hex_id: str) -> None:
            label = (callsign or hex_id or "").strip()
            if not label:
                return
            try:
                store = FocusStore()
                current = store.get()
                store.set(FocusRecord(uuid4().hex, FocusKind.FLIGHT, f"flight:{hex_id or label}", f"Flight {label}"),
                          expected_revision=current.revision)
                self._error("")
                self.refresh()
            except (OSError, ValueError) as exc:
                self._error(str(exc))

        @Property("QVariantList", notify=missionsChanged)
        def missions(self) -> list[dict[str, object]]:
            return self._missions

        def _missions_api(self) -> MissionControl:
            if self._mission_control is None:
                self._mission_control = MissionControl()
            return self._mission_control

        def _refresh_missions(self) -> None:
            try:
                api = self._missions_api()
                api.expire()
                missions = [summary(state) for state in api.recent(limit=12)]
            except (OSError, ValueError, KeyError) as exc:
                missions = []
                self._error(f"Missions unavailable: {type(exc).__name__}")
            if missions != self._missions:
                self._missions = missions
                self.missionsChanged.emit()

        def _show_mission(self, generation: int, state) -> None:
            view = summary(state)
            self._askUpdate.emit({"generation": generation, "state": "mission", "mission": view,
                                  "question": view["asked"], "answer": view["message"] or view["error"]})

        @Slot(str, str)
        @guest_mode.owner_only("Running tasks")
        def approveMission(self, task_id: str, token: str) -> None:
            generation = self._ask_generation

            def work() -> None:
                try:
                    state = self._missions_api().approve(task_id, token)
                    self._show_mission(generation, state)
                except (OSError, ValueError, PermissionError, KeyError) as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "error": str(exc)})

            threading.Thread(target=work, name="apvis-mission", daemon=True).start()

        @Slot(str)
        def cancelMission(self, task_id: str) -> None:
            try:
                state = self._missions_api().cancel(task_id)
                if (self._ask.get("mission") or {}).get("id") == task_id:
                    self._show_mission(self._ask_generation, state)
            except (OSError, ValueError, KeyError) as exc:
                self._error(str(exc))
            self.refresh()

        @Slot()
        def archiveMissions(self) -> None:
            try:
                self._missions_api().archive_finished()
            except OSError as exc:
                self._error(str(exc))
            self.refresh()

        @Slot("QVariantMap")
        def _apply_ask(self, update: dict[str, object]) -> None:
            if update.get("generation") != self._ask_generation:
                return  # a newer question (or Close) superseded this one
            self._ask = {**self._ask, **update}
            self.askChanged.emit()
            if update.get("state") in {"mission", "error", "memory"}:
                self.refresh()  # missions list and approval count follow the action

        @Slot(str)
        def askQuestion(self, question: str) -> None:
            question = (question or "").strip()
            if not question:
                return
            # Surfaces are opened directly, not planned as actions.
            if re.match(r"(?i)^\s*(?:please\s+)?(?:open|show|go to)\s+(?:me\s+)?(?:the\s+)?"
                        r"(?:atlas|flights?|planes|aircraft|airspace|live flights)(?:\s+over\s+the\s+uk)?\s*[.!?]*$", question):
                self.closeAnswer()
                self.pageRequested.emit("atlas")
                return
            # "open bbc.co.uk" opens APVIS Browser; so does "search the web for X" while Ask's web search is off
            # (when it's on, Ask answers from the results and shows the links).
            site_match = re.match(r"(?i)^\s*(?:please\s+)?(?:open|go to|visit|browse(?:\s+to)?)\s+((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?)\s*[.!?]*$", question)
            web_match = None if self._web_search_on() else re.match(r"(?i)^\s*(?:please\s+)?(?:search\s+(?:the\s+web|online|the\s+internet)\s+for|google|look\s+up\s+online)\s+(.+?)\s*[.!?]*$", question)
            if site_match or web_match:
                try:
                    launch_application("browser", site_match.group(1) if site_match else web_match.group(1))
                    self.closeAnswer()
                    self._error("")
                except (OSError, ValueError) as exc:
                    self._error(str(exc))
                return
            # "install VLC" opens the Apps Store at VLC: installing asks for the owner's password there.
            wanted = re.match(r"(?i)^\s*(?:please\s+)?(?:can you\s+|could you\s+)?(?:install|get me|get|download|uninstall)\s+"
                              r"(?:the\s+)?(.+?)(?:\s+app)?(?:\s+for me)?\s*[.!?]*$", question)
            app = appstore.find(wanted.group(1)) if wanted else None
            if app is not None:
                self.closeAnswer()
                self._app_focus += 1
                self._apply_apps({"focus": {"id": app.id, "n": self._app_focus}})
                self.pageRequested.emit("apps")
                return
            SCHEDULER.owner_active()          # background model work stops at its next step
            self._ask_generation += 1
            generation = self._ask_generation
            self._ask = {"state": "thinking", "question": question, "answer": "", "meta": "Asking local model…",
                         "generation": generation}
            self.askChanged.emit()

            def cancelled() -> bool:
                return generation != self._ask_generation

            def work() -> None:
                if is_continuity_question(question):
                    # Answered from recorded local state; no model involved.
                    if self._display_context != DisplayContext.PRIVATE:
                        answer = "That is private, and a second screen is connected. Confirm your screens first."
                    else:
                        recent = episodes_mod.recent_lines(self._episodes.store) if self._episodes_on() else []
                        answer = continuity_answer(self._state.get("focus"), self._missions, self._notes, episodes=recent)
                    self._askUpdate.emit({"generation": generation, "state": "done", "answer": answer,
                                          "meta": "your records on this computer (Focus, Mission Control, vault) · no model used",
                                          "model": ""})
                    return
                if weather.is_question(question):
                    self._askUpdate.emit({"generation": generation, "state": "done", "model": "",
                                          "answer": weather.answer(question, self._weather),
                                          "meta": "Open-Meteo weather for your town · no model used"})
                    return
                try:
                    said = reminders.answer(question, self._reminders)
                except (OSError, ValueError) as exc:
                    said = str(exc)
                if said is not None:
                    self._askUpdate.emit({"generation": generation, "state": "done", "answer": said, "model": "",
                                          "meta": "reminders · kept on this computer · no model used"})
                    self._status_wake.set()           # the Active Task card shows it straight away
                    return
                # "Show me a picture of Paris": a real photo from Wikimedia Commons, credited (owner, from APVIS 7).
                wanted_picture = pictures.visual_query(question)
                if wanted_picture:
                    self._askUpdate.emit({"generation": generation, "state": "thinking", "meta": f"Finding a picture of {wanted_picture}…"})
                    found = pictures.find(wanted_picture)
                    if cancelled():
                        return
                    if found:
                        self._askUpdate.emit({"generation": generation, "state": "done", "model": "",
                                              "answer": found["caption"], "picture": {**found, "url": QUrl.fromLocalFile(found["file"]).toString()},
                                              "meta": "Wikimedia Commons" + (f" · {found['credit']}" if found["credit"] else "")})
                    else:
                        self._askUpdate.emit({"generation": generation, "state": "done", "model": "",
                                              "answer": f"I couldn't find a picture of {wanted_picture} (Wikimedia Commons, or no internet).",
                                              "meta": "pictures · no model used"})
                    return
                facts = measured_answer(question)
                if facts is not None:
                    self._askUpdate.emit({"generation": generation, "state": "done", "model": "", **facts})
                    return
                if self._memory_request(generation, question):
                    return
                # V3 M5: several actions in one request, or a recipe, become one plan (approved once).
                try:
                    plan = plans.propose(self._missions_api().planner, question)
                    if plan is not None:
                        title = plan.title + (f" ({plan.note})" if plan.note else "")
                        self._show_mission(generation, self._missions_api().propose_plan(question, plan.steps, plan.source, title))
                        return
                except ParseError as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "", "error": f"{exc}."})
                    return
                except (OSError, ValueError, KeyError) as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "",
                                          "error": f"Mission Control unavailable: {exc}"})
                    return
                try:
                    mission = self._missions_api().propose(question)
                except ParseError as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "", "error": f"{exc}."})
                    return
                except (OSError, ValueError, KeyError) as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "",
                                          "error": f"Mission Control unavailable: {exc}"})
                    return
                if mission is not None:
                    self._show_mission(generation, mission)
                    return
                # V3 M5: a multi-part action request nothing above understood -> the local AI drafts a plan,
                # code checks every step, and it waits for the owner's approval like any other.
                if plans.wants_model_plan(question):
                    self._askUpdate.emit({"generation": generation, "state": "thinking", "meta": "Planning the steps…"})
                    try:
                        plan = plans.model_plan(self._missions_api().planner, question, self._plan_chat)
                        title = plan.title
                        self._show_mission(generation, self._missions_api().propose_plan(question, plan.steps, plan.source, title))
                        return
                    except (ParseError, OllamaError, OSError, ValueError) as exc:
                        if cancelled():
                            return
                        self._askUpdate.emit({"generation": generation, "state": "done", "model": "",
                                              "answer": f"I couldn't make a safe plan for that ({exc}). "
                                                        "Try asking for one step at a time.",
                                              "meta": "Mission Control · nothing was changed"})
                        return
                last = [0.0]

                def on_text(text: str) -> None:
                    now = time.perf_counter()
                    if now - last[0] >= 0.08:  # bound redraws while the model streams
                        last[0] = now
                        self._askUpdate.emit({"generation": generation, "state": "streaming", "answer": text})

                # Follow-ups: this chat's last exchanges (kept in memory for 30 min, also after the answer closes).
                history = self._conversation.messages()
                # "summarise report.docx": the file (inside home) becomes the chat's context.
                doc_note = ""
                wanted_doc = documents.match(question)
                if wanted_doc:
                    try:
                        path = documents.find(wanted_doc["name"], wanted_doc["where"])
                        text = documents.extract(path)
                    except documents.DocumentError as exc:
                        self._askUpdate.emit({"generation": generation, "state": "done", "answer": str(exc), "model": "",
                                              "meta": "your files · no model used"})
                        return
                    from .browser import PAGE_TEXT_BOOST, PAGE_TEXT_LOCAL
                    limit = PAGE_TEXT_BOOST if AskService().boost_client("general") else PAGE_TEXT_LOCAL
                    history = documents.context(path, text, limit)
                    doc_note = f" · read {path.name}" + (" (first part)" if len(text) > limit else "")
                try:
                    result = AskService().ask(question, on_text=on_text, cancelled=cancelled, history=history, web=True)
                    if result.status == "completed" and not cancelled() and result.answer:
                        if result.source != "instant":
                            self._episodes.add_turn(question, result.answer)
                        self._conversation.remember(history, question, result.answer)
                except (OSError, ValueError) as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "",
                                          "error": f"Ask unavailable: {exc}"})
                    return
                if result.status == "completed":
                    if result.source == "instant":
                        meta = f"APVIS · instant · {max(1, round((result.total_s or 0) * 1000))} ms"
                    elif result.source == "remembered":
                        meta = f"{result.model} · remembered answer · instant"
                    else:
                        where = {"gaming-pc": " · gaming PC", "local": " · local"}.get(result.source, "")  # web/news: in via
                        meta = f"{result.model}{where} · {result.total_s:.1f} s"
                        if result.first_token_s is not None and (result.total_s or 0) >= 2:
                            meta += f" · first words {result.first_token_s:.1f} s"
                        if result.tokens_per_s:
                            meta += f" · {result.tokens_per_s:.0f} tok/s"
                    if doc_note:
                        meta += doc_note
                    elif result.history_used:
                        meta += " · follow-up"
                    if result.routed_by and result.routed_by != result.model:
                        meta += f" · picked by {result.routed_by} ({ {'code': 'code question', 'deep': 'needs deep thinking'}.get(result.role, result.role)})"
                    if result.notes_used:
                        meta += " · used your notes: " + ", ".join(result.notes_used)
                    if result.via:
                        meta += " · " + result.via
                    self._askUpdate.emit({"generation": generation, "state": "done", "answer": result.answer or "(empty answer)",
                                          "meta": meta, "model": result.model})
                elif result.status != "cancelled":
                    hint = " Check that Ollama is running." if result.status == "unavailable" else ""
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "",
                                          "error": f"{result.error}.{hint}"})

            threading.Thread(target=work, name="apvis-ask", daemon=True).start()

        def _screen_question(self, capture: str) -> None:
            """Win+Shift+S: answer about the captured area (vision model, else the text in it); the capture is then deleted."""
            path = screen.valid_capture(capture)
            if path is None:
                return
            question = "What's in this part of my screen? Describe it briefly and point out anything important."
            self._ask_generation += 1
            generation = self._ask_generation
            self._ask = {"state": "thinking", "question": "What's on my screen?", "answer": "", "meta": "Looking at your screen…",
                         "generation": generation}
            self.askChanged.emit()

            def work() -> None:
                import base64
                try:
                    data = path.read_bytes()
                    last = [0.0]

                    def on_text(text: str) -> None:
                        now = time.perf_counter()
                        if now - last[0] >= 0.08:
                            last[0] = now
                            self._askUpdate.emit({"generation": generation, "state": "streaming", "answer": text})

                    cancelled = lambda: generation != self._ask_generation  # noqa: E731
                    service = AskService()
                    result = service.ask(question, images=[base64.b64encode(data).decode("ascii")], on_text=on_text, cancelled=cancelled)
                    how = "looked at it"
                    if result.status != "completed":
                        text = screen.ocr(path)             # no vision model: read the words in the area instead
                        if not text:
                            self._askUpdate.emit({"generation": generation, "state": "done", "model": "",
                                                  "answer": "I couldn't read that area. Install a vision model (moondream) in Settings -> Local AI, "
                                                            "or select an area with text in it.", "meta": "screen · no model used"})
                            return
                        result = service.ask("Here is the text from part of my screen. What is it about? Point out anything important.",
                                             history=[{"role": "user", "content": "Text on my screen:\n\n" + text[:4000]},
                                                      {"role": "assistant", "content": "I've read it."}], on_text=on_text, cancelled=cancelled)
                        how = "read the text in it"
                    if result.status == "completed":
                        where = "gaming PC" if result.source == "gaming-pc" else "local"
                        self._askUpdate.emit({"generation": generation, "state": "done", "answer": result.answer, "model": result.model,
                                              "meta": f"{result.model} · {where} · {how} · {result.total_s:.1f} s"})
                    elif result.status != "cancelled":
                        self._askUpdate.emit({"generation": generation, "state": "error", "meta": "", "error": f"{result.error}."})
                except (OSError, ValueError) as exc:
                    self._askUpdate.emit({"generation": generation, "state": "error", "meta": "", "error": f"Screen question failed: {exc}"})
                finally:
                    path.unlink(missing_ok=True)

            threading.Thread(target=work, name="apvis-screen", daemon=True).start()

        @Slot()
        def closeAnswer(self) -> None:
            self._ask_generation += 1  # also cancels a running stream; the chat resumes if Ask reopens within 30 min
            self._ask = {"state": "closed"}
            self.askChanged.emit()

        searchChanged = Signal()

        @Property("QVariantList", notify=searchChanged)
        def searchResults(self) -> list[dict[str, object]]:
            return self._search_results

        @Slot(str)
        def search(self, text: str) -> None:
            try:
                results = [h.to_dict() for h in self._search.query(text)]
            except OSError as exc:
                results = []
                self._error(f"Search unavailable: {type(exc).__name__}")
            if results != self._search_results:
                self._search_results = results
                self.searchChanged.emit()

        @Slot(str, str)
        def openResult(self, kind: str, key: str) -> None:
            """Open a search result; only results the index just listed resolve."""
            try:
                target = self._search.resolve(kind, key)
                if target["do"] == "run":
                    subprocess.Popen(target["argv"], close_fds=True, start_new_session=True,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif target["do"] == "open":
                    path = target["path"]
                    try:
                        self._search.remember(Path(path))
                    except OSError:
                        pass  # the recent list is a convenience; opening still proceeds
                    if target["folder"] or not Path("/usr/bin/gio").is_file():
                        folder = path if target["folder"] else str(Path(path).parent)
                        subprocess.Popen(["/usr/bin/pcmanfm-qt", folder], close_fds=True, start_new_session=True)
                    else:
                        subprocess.Popen(["/usr/bin/gio", "open", path], close_fds=True, start_new_session=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif target["do"] == "setting":
                    if target["section"] in APPLICATIONS:
                        launch_application(target["section"])
                    else:
                        self.pageRequested.emit("settings")
                else:
                    self.pageRequested.emit(target["page"])
                self._error("")
            except (OSError, KeyError, ValueError) as exc:
                self._error(str(exc).strip("'\""))

        @Slot(str)
        def launch(self, name: str) -> None:
            try:
                launch_application(name)
                self._error("")
            except (OSError, ValueError) as exc:
                self._error(str(exc))

        @Slot(str)
        def setFocus(self, label: str) -> None:
            try:
                set_question_focus(label)
                self._error("")
                self.refresh()
            except (OSError, ValueError) as exc:
                self._error(str(exc))

        @Slot()
        def clearFocus(self) -> None:
            try:
                store = FocusStore()
                current = store.get()
                store.clear(expected_revision=current.revision)
                self._error("")
                self.refresh()
            except (OSError, ValueError) as exc:
                self._error(str(exc))

    if not qml_path.is_file():
        raise FileNotFoundError(f"V2 Home QML unavailable: {qml_path}")
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    if sys.platform == "win32" and not os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        # Development previews on Windows: use the same non-native style as the
        # image (the native Windows style ignores APVIS's control styling).
        from PySide6.QtQuickControls2 import QQuickStyle
        QQuickStyle.setStyle("Fusion")
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("APVIS OS V2")
    # Wayland app_id; the labwc window rule for Home matches this identifier.
    app.setDesktopFileName("apvis-home")
    bridge = ShellBridge()
    engine = QQmlApplicationEngine()
    try:
        from PySide6.QtCore import QSize, Qt
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtQuick import QQuickImageProvider

        class AppIconProvider(QQuickImageProvider):
            """image://appicon/<file or theme name>: app icons for the Apps Store (empty when missing)."""

            def __init__(self) -> None:
                super().__init__(QQuickImageProvider.ImageType.Pixmap)

            def requestPixmap(self, name: str, size: QSize, requested: QSize) -> QPixmap:  # noqa: N802
                from urllib.parse import unquote
                name = unquote(name)
                side = max(requested.width(), requested.height(), 16) if requested.isValid() else 64
                icon = QIcon(name) if name.startswith("/") else QIcon.fromTheme(name)
                pixmap = icon.pixmap(side, side) if not icon.isNull() else QPixmap()
                if pixmap.isNull():
                    pixmap = QPixmap(1, 1)
                    pixmap.fill(Qt.GlobalColor.transparent)
                return pixmap

        engine.addImageProvider("appicon", AppIconProvider())
    except ImportError:
        pass
    # V3 look fonts (Inter, EB Garamond; SIL Open Font License, texts beside them) ship with the APVIS layer,
    # so an update brings them without system packages. APVIS_PREVIEW_FONTS adds a folder for design previews.
    from PySide6.QtGui import QFontDatabase
    for folder in (qml_path.resolve().parent / "fonts", Path(os.environ.get("APVIS_PREVIEW_FONTS", "") or "/nonexistent")):
        if folder.is_dir():
            for font in sorted(folder.rglob("*.[ot]tf")):
                QFontDatabase.addApplicationFont(str(font))
    apply_body_font(bridge.render.get("accent", "") if isinstance(bridge.render, dict) else "")
    engine.rootContext().setContextProperty("shell", bridge)
    engine.rootContext().setContextProperty("previewWindowed", windowed)
    engine.rootContext().setContextProperty("previewPage", smoke_page)
    # Development previews: window size ("1920x1080") and skipping the start-up sequence.
    size = re.fullmatch(r"(\d{3,4})x(\d{3,4})", os.environ.get("APVIS_PREVIEW_SIZE", ""))
    engine.rootContext().setContextProperty("previewSize", {"width": int(size.group(1)) if size else 0,
                                                            "height": int(size.group(2)) if size else 0})
    engine.rootContext().setContextProperty("previewNoIntro", os.environ.get("APVIS_NO_INTRO", "") == "1")
    # APVIS for Windows (desktop app): full screen on its own monitor instead of being the desktop itself.
    desktop_app = not windowed and (sys.platform == "win32" or os.environ.get("APVIS_DESKTOP_APP") == "1")
    engine.rootContext().setContextProperty("desktopApp", desktop_app)
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    if not engine.rootObjects():
        return 2
    window = engine.rootObjects()[0]
    if desktop_app and isinstance(window, QQuickWindow):
        place_on_screen(window, app)
    if isinstance(window, QQuickWindow):
        window.frameSwapped.connect(bridge.frame_swapped)
        window.visibilityChanged.connect(lambda *_: bridge.frame_gap())
    if isinstance(window, QQuickWindow):
        # The software scene graph only renders on request, which also stalls
        # QML animation timers. A plain Qt timer (event loop, not the render
        # loop) advances the CPU Nucleus clock at ~30 fps while it is shown.
        from PySide6.QtGui import QWindow

        def tick() -> None:
            if bridge._reduced or bridge.render["renderer"] != Renderer.CANVAS.value or not bridge.render.get("software"):
                return  # still visuals, or a GPU: the orb is paced by its own FrameAnimation (vsync)
            if window.visibility() in (QWindow.Visibility.Hidden, QWindow.Visibility.Minimized):
                return
            # Without a GPU every frame is filled by the CPU: pace the lite
            # Nucleus at ~20 fps instead of ~30 (dev.10 VM: 25 fps at 3 cores).
            interval = 50 if bridge.render.get("lite") else 33
            if ticker.interval() != interval:
                ticker.setInterval(interval)
            bridge.advance_clock()
            window.update()

        ticker = QTimer(app)
        ticker.setInterval(33)
        ticker.timeout.connect(tick)
        ticker.start()
        engine._software_ticker = ticker
    timer = QTimer(app)
    timer.setInterval(2500)
    timer.timeout.connect(bridge.refresh)
    timer.start()
    def stop_threads() -> None:
        bridge._stopping = True
        bridge._indexer.stop()
        bridge._atlas_visible = False
        bridge._status_wake.set()
        bridge._atlas_wake.set()
        bridge._world_wake.set()
    app.aboutToQuit.connect(stop_threads)
    engine._shell_bridge = bridge  # Keep context property alive.
    engine._shell_timer = timer
    if smoke_ask:
        bridge.askQuestion(smoke_ask)
    captured = {"ok": False}
    if smoke_screenshot is not None:
        smoke_screenshot.parent.mkdir(parents=True, exist_ok=True)
        if not isinstance(window, QQuickWindow):
            raise RuntimeError("V2 Home root is not a QQuickWindow")

        def capture() -> None:
            image = window.grabWindow()
            captured["ok"] = not image.isNull() and image.save(str(smoke_screenshot))

        QTimer.singleShot(smoke_delay_ms, capture)
        QTimer.singleShot(smoke_delay_ms + 650, app.quit)
    status = int(app.exec())
    return 3 if smoke_screenshot is not None and not captured["ok"] else status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APVIS OS V2 Home shell")
    parser.add_argument("--qml", type=Path, default=QML_HOME)
    parser.add_argument("--windowed", action="store_true", help="run as a regular window for development")
    parser.add_argument("--smoke-screenshot", type=Path, help="capture one bounded local Qt render, then exit")
    parser.add_argument("--smoke-delay-ms", type=int, default=750, help="delay before the smoke capture")
    parser.add_argument("--accent", choices=ACCENTS, help="colour accent (default: APVIS_ACCENT or emerald-silver)")
    parser.add_argument("--reduced-motion", action="store_true", help="freeze Nucleus motion")
    parser.add_argument("--smoke-ask", help="ask this question at start (smoke tests)")
    parser.add_argument("--smoke-page", default="", choices=["", "atlas", "atlas-home", "notes", "settings"], help="open this page at start (smoke tests)")
    args = parser.parse_args(argv)
    return run(args.qml, windowed=args.windowed, smoke_screenshot=args.smoke_screenshot, accent=args.accent,
               reduced_motion=True if args.reduced_motion else None, smoke_delay_ms=args.smoke_delay_ms,
               smoke_ask=args.smoke_ask, smoke_page=args.smoke_page)


if __name__ == "__main__":
    raise SystemExit(main())
