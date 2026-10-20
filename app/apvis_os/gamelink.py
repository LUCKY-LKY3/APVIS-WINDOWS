"""APVIS for Windows: which game is being played, and live stats for it (Home's game card).

`GameLink.sample()` is called every ~2 s from a background thread. It reads the foreground window (Win32 via
ctypes), decides whether it is a game, keeps play sessions per game in `<state dir>/games.json`, and reads
CPU/RAM (psutil) and the NVIDIA GPU (nvidia-smi). FPS is only measured when PresentMon is installed; otherwise
it is None and the UI says "not measured". Nothing here touches the network, and no number is ever made up.

The decision logic (`classify`, `friendly_name`, `parse_nvidia_smi`, `GameTracker`, `GameStore`) is pure so it
can be tested on Linux.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

HISTORY = 150                 # samples kept for the sparklines (~5 minutes at 2 s)
GRACE_S = 60                  # a game stays "active" this long after it loses focus (alt-tab)
CHECKPOINT_S = 60             # an open session is written down this often (survives a crash)
DAYS_KEPT = 14
SESSIONS_KEPT = 30
RECENT_SHOWN = 8
CREATE_NO_WINDOW = 0x08000000

# Folders that only hold games. The component after the marker is the game's install folder.
LIBRARY_MARKERS = (
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\riot games\\",
    "\\gog galaxy\\games\\",
    "\\gog games\\",
    "\\ubisoft game launcher\\games\\",
    "\\ea games\\",
    "\\origin games\\",
    "\\xboxgames\\",
)
# Launchers and tools that live inside those folders.
LIBRARY_EXCLUDED_DIRS = (
    "\\epic games\\launcher\\",
    "\\riot games\\riot client\\",
    "\\steamapps\\common\\steamworks shared\\",
    "\\steamapps\\common\\steam controller configs\\",
    "\\steamapps\\common\\wallpaper_engine\\",
    "\\steamapps\\common\\steamvr\\",
)

# Exe stems (lower case, no ".exe") that are never a game, even full screen.
EXCLUDED_EXES = frozenset("""
explorer applicationframehost searchhost searchapp startmenuexperiencehost shellexperiencehost lockapp
textinputhost systemsettings taskmgr mmc control regedit mstsc snippingtool screenclippinghost
chrome msedge msedgewebview2 firefox opera opera_gx brave vivaldi iexplore arc thorium librewolf waterfox
discord discordptb discordcanary slack teams ms-teams zoom whatsapp telegram signal skype
steam steamwebhelper steamservice gameoverlayui epicgameslauncher epicwebhelper riotclientservices riotclientux
riotclientuxrender leagueclient leagueclientux leagueclientuxrender battle.net agent upc ubisoftconnect
uplaywebcore eadesktop eabackgroundservice origin galaxyclient goggalaxy xboxapp xboxpcapp gamebar
gamebarftserver playnite.desktopapp playnite.fullscreenapp
obs64 obs32 obs streamlabs xsplit.core nvcontainer
msiafterburner rtss rtsshooksloader64 sunshine moonlight
python pythonw py apvis apvis-home qmlscene
windowsterminal wt cmd powershell pwsh conhost openconsole wsl bash mintty alacritty wezterm-gui
code code-insiders devenv notepad notepad++ sublime_text idea64 pycharm64 rider64 cursor windsurf zed
claude chatgpt
vlc mpc-hc64 mpc-hc mpc-be64 potplayermini64 potplayer wmplayer microsoft.media.player video.ui mpv kodi
plex spotify netflix
powerpnt winword excel onenote outlook acrord32 acrobat sumatrapdf photos microsoft.photos
unitycrashhandler64 unitycrashhandler32 crashreportclient vc_redist.x64 vc_redist.x86 dxsetup
easyanticheat_setup easyanticheat_eos_setup wallpaper32 wallpaper64 ui32 lively
""".split()) | {"streamlabs obs", "nvidia overlay", "nvidia app", "nvidia share"}
EXCLUDED_PREFIXES = ("apvis",)
DESKTOP_CLASSES = frozenset({"progman", "workerw", "shell_traywnd", "shell_secondarytraywnd"})

NVIDIA_FIELDS = ("name", "utilization.gpu", "temperature.gpu", "memory.used", "memory.total", "power.draw",
                 "clocks.gr", "fan.speed")
NVIDIA_SMI_CANDIDATES = (
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
)


def state_dir() -> Path:
    """APVIS_OS_STATE_DIR like the other stores; on Windows without it, %LOCALAPPDATA%\\APVIS-OS."""
    env = os.environ.get("APVIS_OS_STATE_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "APVIS-OS"
    return Path("/var/lib/apvis-os")


def store_path() -> Path:
    return state_dir() / "games.json"


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- detection (pure)

def _norm(path: str) -> str:
    return path.replace("/", "\\").lower()


def exe_stem(exe: str) -> str:
    name = _norm(exe).rsplit("\\", 1)[-1]
    return name[:-4] if name.endswith(".exe") else name


def library_folder(exe: str) -> tuple[str, str] | None:
    """(marker, install folder name as written) when the exe is inside a known game library."""
    low = _norm(exe)
    if any(bad in low for bad in LIBRARY_EXCLUDED_DIRS):
        return None
    for marker in LIBRARY_MARKERS:
        at = low.find(marker)
        if at < 0:
            continue
        rest = exe.replace("/", "\\")[at + len(marker):]
        folder = rest.split("\\", 1)[0]
        if folder and "\\" in rest:          # the exe must be inside a game's folder, not the library root
            return marker, folder
    return None


def is_excluded(exe: str) -> bool:
    stem = exe_stem(exe)
    return stem in EXCLUDED_EXES or stem.startswith(EXCLUDED_PREFIXES)


def covers_monitor(window: tuple[int, int, int, int], monitor: tuple[int, int, int, int], tolerance: int = 2) -> bool:
    """Full screen or borderless: the window rect (left, top, right, bottom) covers the whole monitor."""
    wl, wt, wr, wb = window
    ml, mt, mr, mb = monitor
    if mr <= ml or mb <= mt:
        return False
    return wl <= ml + tolerance and wt <= mt + tolerance and wr >= mr - tolerance and wb >= mb - tolerance


@dataclass
class Foreground:
    """What the foreground window is (read from Win32, or built by tests)."""
    pid: int
    exe: str
    title: str = ""
    class_name: str = ""
    fullscreen: bool = False
    minimized: bool = False
    create_time: float = 0.0


def classify(fg: Foreground | None) -> tuple[bool, str]:
    """(is a game, why). Library folders win; otherwise a full-screen window that isn't on the exclusion list."""
    if fg is None or not fg.exe:
        return False, "no window"
    if is_excluded(fg.exe):
        return False, "excluded"
    if fg.class_name.lower() in DESKTOP_CLASSES:
        return False, "desktop"
    if library_folder(fg.exe):
        return True, "library"
    if fg.minimized:
        return False, "minimized"
    if fg.fullscreen:
        if "\\windows\\" in _norm(fg.exe) and "\\windowsapps\\" not in _norm(fg.exe):
            return False, "system"          # C:\Windows\... full screen is the OS (screensaver, lock, OOBE)
        return True, "fullscreen"
    return False, "windowed"


_SUFFIX = re.compile(r"[-_. ]?(win64|win32|shipping|x64|x86|dx11|dx12|d3d11|d3d12|vulkan|retail|final|"
                     r"release|egs|64|32)$", re.I)


def prettify_exe(exe: str) -> str:
    stem = exe.replace("/", "\\").rsplit("\\", 1)[-1]
    if stem.lower().endswith(".exe"):
        stem = stem[:-4]
    previous = None
    while previous != stem and stem:
        previous = stem
        stem = _SUFFIX.sub("", stem)
    stem = stem or previous or ""
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)
    words = re.split(r"[\s_\-.]+", stem)
    return " ".join(w if not w.islower() else w.capitalize() for w in words if w).strip()


def parse_acf(text: str) -> dict[str, str]:
    """The flat "key" "value" pairs of a Steam appmanifest (nested blocks are skipped over, not parsed)."""
    out: dict[str, str] = {}
    depth = 0
    for line in text.splitlines():
        line = line.strip()
        if line == "{":
            depth += 1
            continue
        if line == "}":
            depth -= 1
            continue
        if depth != 1:
            continue
        m = re.match(r'^"([^"]+)"\s+"((?:[^"\\]|\\.)*)"$', line)
        if m:
            out[m.group(1).lower()] = m.group(2).replace("\\\\", "\\").replace('\\"', '"')
    return out


def steam_names(steamapps: Path) -> dict[str, str]:
    """installdir (lower case) -> store name, from appmanifest_*.acf in a steamapps folder."""
    names: dict[str, str] = {}
    try:
        manifests = list(steamapps.glob("appmanifest_*.acf"))
    except OSError:
        return names
    for manifest in manifests:
        try:
            data = parse_acf(manifest.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if data.get("installdir") and data.get("name"):
            names[data["installdir"].lower()] = data["name"]
    return names


_GENERIC_TITLES = {"", "default ime", "msctfime ui", "unity", "unreal", "game", "window", "main"}


def friendly_name(exe: str, title: str = "", steam: dict[str, str] | None = None) -> str:
    """Steam's name for the install folder, else the window title, else the install folder, else the exe."""
    lib = library_folder(exe)
    if lib and lib[0] == "\\steamapps\\common\\" and steam:
        found = steam.get(lib[1].lower())
        if found:
            return found
    clean = " ".join(title.split())
    if clean.lower() not in _GENERIC_TITLES and clean.lower() != exe_stem(exe):
        return clean[:60].rstrip()
    if lib:
        return lib[1]
    return prettify_exe(exe) or "Game"


def steamapps_for(exe: str) -> Path | None:
    low = _norm(exe)
    at = low.find("\\steamapps\\common\\")
    if at < 0:
        return None
    return Path(exe.replace("/", "\\")[: at + len("\\steamapps")])


# ---------------------------------------------------------------- GPU (nvidia-smi)

def _num(value: str, kind: type) -> Any:
    value = value.strip()
    if not value or value.startswith("[") or value.lower() in {"n/a", "not supported", "unknown error"}:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return round(number, 1) if kind is float else int(round(number))


def parse_nvidia_smi(text: str) -> dict[str, Any] | None:
    """The first GPU line of `--query-gpu=<NVIDIA_FIELDS> --format=csv,noheader,nounits`, or None."""
    for row in csv.reader(io.StringIO(text)):
        if len(row) < len(NVIDIA_FIELDS):
            continue
        cells = [c.strip() for c in row]
        name = cells[0]
        if not name or name.startswith("["):
            continue
        return {
            "name": name,
            "util": _num(cells[1], int),
            "temp": _num(cells[2], int),
            "vramUsed": _num(cells[3], int),
            "vramTotal": _num(cells[4], int),
            "power": _num(cells[5], float),
            "clock": _num(cells[6], int),
            "fan": _num(cells[7], int),
        }
    return None


def find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for candidate in NVIDIA_SMI_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return None


def read_gpu(tool: str | None, run: Callable[..., Any] = subprocess.run) -> dict[str, Any] | None:
    if not tool:
        return None
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 4}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    try:
        done = run([tool, "--query-gpu=" + ",".join(NVIDIA_FIELDS), "--format=csv,noheader,nounits"], **kwargs)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if getattr(done, "returncode", 1) != 0:
        return None
    return parse_nvidia_smi(done.stdout or "")


# ---------------------------------------------------------------- FPS (PresentMon, only if installed)

def find_presentmon() -> str | None:
    env = os.environ.get("APVIS_PRESENTMON")
    if env and os.path.isfile(env):
        return env
    for name in ("PresentMon", "PresentMon64", "PresentMon-x64"):
        found = shutil.which(name)
        if found:
            return found
    for root in (r"C:\Program Files\Intel\PresentMon\PresentMonCli", r"C:\Program Files\PresentMon"):
        try:
            hits = sorted(Path(root).glob("PresentMon*.exe"))
        except OSError:
            hits = []
        if hits:
            return str(hits[-1])
    return None


class FrameTimes:
    """Frame times from PresentMon CSV lines -> frames per second over the last second."""

    COLUMNS = ("msbetweenpresents", "frametime", "msbetweendisplaychange")

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._column: int | None = None
        self._frames: deque[tuple[float, float]] = deque(maxlen=2000)
        self._lock = threading.Lock()

    def feed(self, line: str) -> None:
        cells = next(csv.reader([line]), [])
        if not cells:
            return
        if self._column is None:
            lowered = [c.strip().lower() for c in cells]
            for name in self.COLUMNS:
                if name in lowered:
                    self._column = lowered.index(name)
                    return
            return
        if self._column >= len(cells):
            return
        try:
            ms = float(cells[self._column])
        except ValueError:
            return
        if ms > 0:
            with self._lock:
                self._frames.append((self._clock(), ms))

    def fps(self, window_s: float = 1.0, stale_s: float = 3.0) -> float | None:
        now = self._clock()
        with self._lock:
            recent = [ms for at, ms in self._frames if now - at <= window_s]
            newest = self._frames[-1][0] if self._frames else None
        if not recent or newest is None or now - newest > stale_s:
            return None
        return round(1000.0 / (sum(recent) / len(recent)), 1)


class FpsMeter:
    """Runs PresentMon for one process while a game is active. Off (fps None) when it isn't installed."""

    def __init__(self, tool: str | None) -> None:
        self.tool = tool
        self._proc: subprocess.Popen[str] | None = None
        self._pid = 0
        self._times = FrameTimes()

    def follow(self, pid: int | None) -> None:
        if not self.tool or pid == self._pid:
            return
        self.stop()
        if not pid:
            return
        self._pid = pid
        self._times = FrameTimes()
        kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL, "text": True}
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen([self.tool, "--process_id", str(pid), "--output_stdout",
                                           "--stop_existing_session", "--session_name", "apvis-gamelink",
                                           "--terminate_on_proc_exit"], **kwargs)
        except OSError:
            self._proc = None
            return
        times, proc = self._times, self._proc
        def pump() -> None:
            for line in proc.stdout or ():
                times.feed(line)
        threading.Thread(target=pump, name="apvis-game-fps", daemon=True).start()

    def fps(self) -> float | None:
        if self._proc is None:
            return None
        return self._times.fps()

    def stop(self) -> None:
        self._pid = 0
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None


# ---------------------------------------------------------------- sessions (pure, fake-clock friendly)

@dataclass
class ActiveGame:
    key: str              # lower-case exe path: totals stay together even when the window title changes
    name: str
    exe: str
    pid: int
    create_time: float
    start_ms: int
    last_focus_ms: int
    last_checkpoint_ms: int = 0


@dataclass
class Ended:
    key: str
    name: str
    exe: str
    start_ms: int
    end_ms: int


class GameTracker:
    """Which game is active. It survives alt-tab for GRACE_S, and ends as soon as its process exits."""

    def __init__(self, grace_s: int = GRACE_S) -> None:
        self.grace_ms = grace_s * 1000
        self.current: ActiveGame | None = None

    def step(self, now: int, fg: Foreground | None, alive: Callable[[ActiveGame], bool],
             name_for: Callable[[Foreground], str]) -> list[Ended]:
        ended: list[Ended] = []
        cur = self.current
        if cur is not None and fg is not None and fg.pid == cur.pid and fg.create_time == cur.create_time:
            cur.last_focus_ms = now                     # still the same game (even if it went windowed)
            return ended
        is_game, _why = classify(fg)
        if is_game and fg is not None:
            if cur is not None:
                ended.append(self._end(cur))
            self.current = ActiveGame(key=_norm(fg.exe), name=name_for(fg), exe=fg.exe, pid=fg.pid,
                                      create_time=fg.create_time, start_ms=now, last_focus_ms=now,
                                      last_checkpoint_ms=now)
            return ended
        if cur is not None and (not alive(cur) or now - cur.last_focus_ms > self.grace_ms):
            ended.append(self._end(cur))
            self.current = None
        return ended

    def _end(self, cur: ActiveGame) -> Ended:
        return Ended(cur.key, cur.name, cur.exe, cur.start_ms, max(cur.start_ms, cur.last_focus_ms))

    def close(self) -> list[Ended]:
        if self.current is None:
            return []
        out = [self._end(self.current)]
        self.current = None
        return out


def split_by_day(start_ms: int, end_ms: int) -> dict[str, int]:
    """Seconds of [start, end) on each local calendar day ("YYYY-MM-DD")."""
    out: dict[str, int] = {}
    if end_ms <= start_ms:
        return out
    at = datetime.fromtimestamp(start_ms / 1000)
    end = datetime.fromtimestamp(end_ms / 1000)
    while at < end:
        midnight = datetime(at.year, at.month, at.day) + timedelta(days=1)
        stop = min(midnight, end)
        seconds = int((stop - at).total_seconds())   # floored, like the session total
        if seconds:
            day = at.strftime("%Y-%m-%d")
            out[day] = out.get(day, 0) + seconds
        at = stop
    return out


def _empty() -> dict[str, Any]:
    return {"version": 1, "games": {}, "days": {}, "sessions": [], "open": None}


class GameStore:
    """games.json: totals per game, seconds per day (14 days), the last sessions, and the open session."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or store_path()
        self._lock = threading.Lock()
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty()
        if not isinstance(data, dict):
            return _empty()
        base = _empty()
        for key in ("games", "days"):
            if isinstance(data.get(key), dict):
                base[key] = data[key]
        if isinstance(data.get("sessions"), list):
            base["sessions"] = [s for s in data["sessions"] if isinstance(s, dict)]
        if isinstance(data.get("open"), dict):
            base["open"] = data["open"]
        return base

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".games.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.data, handle, indent=1)
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    def record(self, session: Ended, today: str | None = None) -> None:
        seconds = max(0, (session.end_ms - session.start_ms) // 1000)
        if seconds < 1:
            return
        games = self.data["games"]
        game = games.setdefault(session.key, {"name": session.name, "exe": session.exe, "totalSeconds": 0,
                                              "lastPlayedMs": 0, "sessions": 0})
        game["name"] = session.name
        game["exe"] = session.exe
        game["totalSeconds"] = int(game.get("totalSeconds", 0)) + seconds
        game["lastPlayedMs"] = max(int(game.get("lastPlayedMs", 0)), session.end_ms)
        game["sessions"] = int(game.get("sessions", 0)) + 1
        for day, secs in split_by_day(session.start_ms, session.end_ms).items():
            per_day = self.data["days"].setdefault(day, {})
            per_day[session.key] = int(per_day.get(session.key, 0)) + secs
        self.data["sessions"] = (self.data["sessions"] + [{
            "name": session.name, "exe": session.exe, "startMs": session.start_ms, "endMs": session.end_ms,
            "seconds": seconds}])[-SESSIONS_KEPT:]
        self._prune(today or datetime.fromtimestamp(session.end_ms / 1000).strftime("%Y-%m-%d"))

    def _prune(self, today: str) -> None:
        try:
            cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=DAYS_KEPT)).strftime("%Y-%m-%d")
        except ValueError:
            return
        self.data["days"] = {d: v for d, v in self.data["days"].items() if d > cutoff}

    def set_open(self, cur: ActiveGame | None, now: int) -> None:
        self.data["open"] = None if cur is None else {
            "key": cur.key, "name": cur.name, "exe": cur.exe, "startMs": cur.start_ms, "lastMs": now}

    def recover(self) -> Ended | None:
        """A session left open by a crash or power cut is counted up to its last checkpoint."""
        open_ = self.data.get("open")
        self.data["open"] = None
        if not open_:
            return None
        try:
            session = Ended(str(open_["key"]), str(open_["name"]), str(open_["exe"]), int(open_["startMs"]),
                            int(open_["lastMs"]))
        except (KeyError, TypeError, ValueError):
            return None
        self.record(session)
        return session

    def today(self, day: str, live: ActiveGame | None = None, now: int = 0) -> list[dict[str, Any]]:
        totals = dict(self.data["days"].get(day, {}))
        names = {k: g.get("name", k) for k, g in self.data["games"].items()}
        if live is not None:
            names[live.key] = live.name
            secs = split_by_day(live.start_ms, max(live.start_ms, now)).get(day, 0)
            totals[live.key] = int(totals.get(live.key, 0)) + secs
        rows = [{"name": names.get(k, k), "seconds": int(s)} for k, s in totals.items() if s > 0]
        return sorted(rows, key=lambda r: -r["seconds"])

    def recent(self, live: ActiveGame | None = None, now: int = 0) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for key, game in self.data["games"].items():
            rows[key] = {"name": game.get("name", key), "lastPlayedMs": int(game.get("lastPlayedMs", 0)),
                         "totalSeconds": int(game.get("totalSeconds", 0))}
        if live is not None:
            row = rows.setdefault(live.key, {"name": live.name, "lastPlayedMs": 0, "totalSeconds": 0})
            row["name"] = live.name
            row["lastPlayedMs"] = now
            row["totalSeconds"] += max(0, (now - live.start_ms) // 1000)
        return sorted(rows.values(), key=lambda r: -r["lastPlayedMs"])[:RECENT_SHOWN]


# ---------------------------------------------------------------- Win32 (ctypes)

def _win32_foreground() -> Foreground | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(1, length + 1))
    user32.GetWindowTextW(hwnd, buf, len(buf))
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    rect = wintypes.RECT()
    fullscreen = False
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        monitor = user32.MonitorFromWindow(hwnd, 2)       # MONITOR_DEFAULTTONEAREST
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            m = info.rcMonitor
            fullscreen = covers_monitor((rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom))
    exe, created = _process_exe(pid.value)
    return Foreground(pid=pid.value, exe=exe, title=buf.value, class_name=cls.value, fullscreen=fullscreen,
                      minimized=bool(user32.IsIconic(hwnd)), create_time=created)


def _process_exe(pid: int) -> tuple[str, float]:
    import psutil

    exe, created = "", 0.0
    try:
        proc = psutil.Process(pid)
        created = proc.create_time()
        exe = proc.exe()
    except (psutil.Error, OSError):
        pass
    if not exe and sys.platform == "win32":          # elevated/protected games: the limited query still works
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                        ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            try:
                size = wintypes.DWORD(1024)
                buf = ctypes.create_unicode_buffer(1024)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    exe = buf.value
            finally:
                kernel32.CloseHandle(handle)
    return exe, created


def _alive(game: ActiveGame) -> bool:
    import psutil

    try:
        proc = psutil.Process(game.pid)
        return proc.is_running() and (not game.create_time or abs(proc.create_time() - game.create_time) < 1.0)
    except (psutil.Error, OSError):
        return False


# ---------------------------------------------------------------- GameLink

class CpuMeter:
    """Whole-machine CPU % from our own cpu_times deltas (psutil.cpu_percent(None) is shared with Home)."""

    def __init__(self) -> None:
        self._last: tuple[float, float] | None = None

    def read(self) -> float:
        import psutil

        t = psutil.cpu_times()
        idle = t.idle + getattr(t, "iowait", 0.0)
        total = sum(t)
        last, self._last = self._last, (idle, total)
        if last is None or total <= last[1]:
            return round(psutil.cpu_percent(interval=None), 1)
        busy = 1.0 - (idle - last[0]) / (total - last[1])
        return round(max(0.0, min(100.0, busy * 100.0)), 1)


class GameLink:
    """One object per Home; `sample()` every ~2 s from one thread."""

    def __init__(self, store: GameStore | None = None, *, clock: Callable[[], int] = now_ms,
                 foreground: Callable[[], Foreground | None] | None = None,
                 alive: Callable[[ActiveGame], bool] = _alive,
                 gpu: Callable[[], dict[str, Any] | None] | None = None,
                 fps: FpsMeter | None = None) -> None:
        self.available = sys.platform == "win32"
        self.store = store or GameStore()
        self._clock = clock
        self._foreground = foreground or (_win32_foreground if self.available else (lambda: None))
        self._alive = alive
        tool = find_nvidia_smi()
        self._gpu = gpu or (lambda: read_gpu(tool))
        self._fps = fps or FpsMeter(find_presentmon() if self.available else None)
        self.tracker = GameTracker()
        self._cpu = CpuMeter()
        self._proc: Any = None
        self._proc_pid = 0
        self._steam: dict[str, dict[str, str]] = {}
        self.history: dict[str, deque[Any]] = {k: deque(maxlen=HISTORY) for k in ("cpu", "gpu", "gpuTemp")}
        if self.store.recover():
            self.store.save()

    def _name_for(self, fg: Foreground) -> str:
        steam: dict[str, str] | None = None
        apps = steamapps_for(fg.exe)
        if apps is not None:
            key = str(apps).lower()
            if key not in self._steam:
                self._steam[key] = steam_names(apps)
            steam = self._steam[key]
        return friendly_name(fg.exe, fg.title, steam)

    def _proc_stats(self, game: ActiveGame | None) -> tuple[float | None, int | None]:
        import psutil

        if game is None:
            self._proc, self._proc_pid = None, 0
            return None, None
        try:
            if self._proc_pid != game.pid:
                self._proc, self._proc_pid = psutil.Process(game.pid), game.pid
                self._proc.cpu_percent(None)                # primes; the next sample has a real number
                return None, int(self._proc.memory_info().rss // (1024 * 1024))
            cpu = self._proc.cpu_percent(None) / max(1, psutil.cpu_count() or 1)
            return round(cpu, 1), int(self._proc.memory_info().rss // (1024 * 1024))
        except (psutil.Error, OSError):
            return None, None

    def sample(self) -> dict[str, Any]:
        import psutil

        now = self._clock()
        try:
            fg = self._foreground()
        except Exception:                      # a Win32 hiccup must not stop the card
            fg = None
        ended = self.tracker.step(now, fg, self._alive, self._name_for)
        for session in ended:
            self.store.record(session)
        cur = self.tracker.current
        dirty = bool(ended)
        if cur is not None and (ended or now - cur.last_checkpoint_ms >= CHECKPOINT_S * 1000 or cur.start_ms == now):
            cur.last_checkpoint_ms = now
            dirty = True
        if dirty:
            self.store.set_open(cur, now)
            try:
                self.store.save()
            except OSError:
                pass
        cpu = self._cpu.read()
        ram = round(psutil.virtual_memory().percent, 1)
        proc_cpu, proc_ram = self._proc_stats(cur)
        gpu = self._gpu()
        self._fps.follow(cur.pid if cur else None)
        self.history["cpu"].append(cpu)
        self.history["gpu"].append(gpu.get("util") if gpu else None)
        self.history["gpuTemp"].append(gpu.get("temp") if gpu else None)
        day = datetime.fromtimestamp(now / 1000).strftime("%Y-%m-%d")
        return {
            "available": self.available,
            "active": cur is not None,
            "name": cur.name if cur else "",
            "exe": cur.exe if cur else "",
            "since_ms": cur.start_ms if cur else None,
            "sessionSeconds": max(0, (now - cur.start_ms) // 1000) if cur else 0,
            "cpu": cpu,
            "ram": ram,
            "procCpu": proc_cpu,
            "procRamMb": proc_ram,
            "gpu": gpu,
            "fps": self._fps.fps() if cur else None,
            "history": {k: list(v) for k, v in self.history.items()},
            "today": self.store.today(day, cur, now),
            "recent": self.store.recent(cur, now),
        }

    def close(self) -> None:
        """Ends the open session (Home is quitting) and stops PresentMon."""
        self._fps.stop()
        for session in self.tracker.close():
            self.store.record(session)
        self.store.set_open(None, self._clock())
        try:
            self.store.save()
        except OSError:
            pass
