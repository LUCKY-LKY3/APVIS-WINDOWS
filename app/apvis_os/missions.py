"""Mission Control: typed actions the owner asks for, with approval before any change.

Only the owner's own words become actions, through a fixed parser into a
trusted catalogue; model output never does. Reading and opening things runs
straight away. Anything that changes files or settings, or powers the machine
down, waits for an approval bound to the exact action shown. Every run goes
through the Action Engine (audit log) and is checked afterwards; the mission is
a durable task record, so the Nucleus shows waiting approvals and failures.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .action_engine import ActionEngine, ActionResult, ActionSpec, PermissionClass
from .common import utc_now
from .task_state import TaskState, TaskStore
from .trash import move_to_trash
from .verification import VerificationResult

APPROVAL_TTL = timedelta(minutes=10)
FOLDERS = {
    "home": "", "home folder": "", "desktop": "Desktop", "documents": "Documents", "downloads": "Downloads",
    "pictures": "Pictures", "photos": "Pictures", "music": "Music", "videos": "Videos", "trash": ".local/share/Trash/files",
}
APP_ALIASES = {
    "terminal": ["/usr/bin/foot"], "files": ["/usr/bin/pcmanfm-qt"], "file manager": ["/usr/bin/pcmanfm-qt"],
    "sound settings": ["/usr/bin/pavucontrol-qt"], "network settings": ["/usr/bin/nm-connection-editor"],
    "display settings": ["/usr/bin/wdisplays"], "displays": ["/usr/bin/wdisplays"],
}
WLRCTL = "/usr/bin/wlrctl"           # V4 image: focuses an open window (wlr-foreign-toplevel)
CAPABILITIES = (
    "open apps and folders, switch to an open app, show disk space and system status, "
    "create folders, rename or move files and move them to Trash inside your home folder, "
    "set or mute the volume, turn Wi-Fi on or off, and shut down or restart"
)


@dataclass(frozen=True)
class ActionKind:
    name: str
    permission: PermissionClass
    needs_approval: bool
    title: str


KINDS = {k.name: k for k in (
    ActionKind("open_app", PermissionClass.LOCAL_SAFE_WRITE, False, "Open an app"),
    ActionKind("focus_app", PermissionClass.LOCAL_SAFE_WRITE, False, "Switch to an app"),
    ActionKind("open_folder", PermissionClass.LOCAL_SAFE_WRITE, False, "Open a folder"),
    ActionKind("disk_space", PermissionClass.READ, False, "Check disk space"),
    ActionKind("system_status", PermissionClass.READ, False, "Check system status"),
    ActionKind("create_folder", PermissionClass.LOCAL_SAFE_WRITE, True, "Create a folder"),
    ActionKind("move", PermissionClass.LOCAL_SAFE_WRITE, True, "Rename or move"),
    ActionKind("trash", PermissionClass.DESTRUCTIVE, True, "Move to Trash"),
    ActionKind("set_volume", PermissionClass.LOCAL_SAFE_WRITE, True, "Change the volume"),
    ActionKind("mute", PermissionClass.LOCAL_SAFE_WRITE, True, "Mute or unmute"),
    ActionKind("wifi", PermissionClass.LOCAL_SAFE_WRITE, True, "Turn Wi-Fi on or off"),
    ActionKind("power", PermissionClass.DESTRUCTIVE, True, "Shut down or restart"),
)}


@dataclass(frozen=True)
class ActionRequest:
    kind: str
    params: dict[str, Any]
    preview: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "params": self.params, "preview": self.preview}

    def token(self) -> str:
        """Approval is bound to exactly this action; any change needs a new approval."""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]


class ParseError(ValueError):
    """The request looks like an action but cannot be done safely as asked."""


def plan_token(steps: list[ActionRequest], source: str) -> str:
    """Approval for a plan is bound to every step (and who wrote it); any change needs a new approval."""
    payload = {"source": source, "steps": [step.to_dict() for step in steps]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


PLAN_SOURCES = {"owner": "your words", "recipe": "a built-in recipe", "model": "the local AI (check each step)"}
MAX_PLAN_STEPS = 30          # recipes can list many small moves; model plans are capped much lower (plans.py)


# ---------------------------------------------------------------- parsing

_LEAD = r"^\s*(?:(?:hey|ok|okay)\s+)?(?:apvis[,:]?\s+)?(?:please\s+|can you\s+|could you\s+|would you\s+)?"
_TAIL = r"\s*(?:for me|please|now)?\s*[.!?]*\s*$"


def _clean(name: str) -> str:
    return name.strip().strip("\"'").strip()


# V4 ("Ask ignores my questions"): many questions start with a command word ("remove duplicates from a
# list in python", "run me through DNS", "create a poem"). They used to become a Trash proposal, a
# "couldn't find an app" error, a failed model plan or the canned "I can't do that yet". These patterns
# tell such requests for an answer or some writing apart from requests to act on this computer.
_POLITE = re.compile(r"(?i)^\s*(?:(?:hey|ok|okay)\s+)?(?:apvis[,:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?")
_THINGS = re.compile(r"(?i)\w\.[a-z0-9]{1,5}\b|/|~|\b(?:files?|folders?|apps?|window|wi-?fi|volume|sound|audio|computer|pc|"
                     r"laptop|desktop|documents|downloads|pictures|photos|music|videos|trash|home\s+folder|bluetooth|screen|"
                     r"brightness)\b")
_ASKING_START = re.compile(r"(?i)^(?:how|why|what|what's|whats|which|when|where|who|whose|is|are|was|were|does|do|did|"
                           r"should|explain|define|describe|compare|tell\s+me)\b")
_ASKING_WORDS = re.compile(r"(?i)\b(?:vs\.?|versus|difference|meaning|tips|ideas|examples?|tutorial|guide|best\s+way|"
                           r"ways?\s+to|step\s+by\s+step)\b")
_CODEY = re.compile(r"(?i)(?:\b(?:python|javascript|typescript|java|rust|golang|sql|bash|powershell|regex|excel|spreadsheet|"
                    r"function|array|list|lists|string|strings|dict|dictionary|variable|loop|class|method|query|code|script|"
                    r"program|algorithm|json|csv|html|css|linux|process|dataframe|pandas|git)\b|c\+\+|c#)")
_FOR_ME = re.compile(r"(?i)^(?:run|send|set|start|update|play|make|get|give|show|walk|take|talk|fill|catch|bring)\s+me\b")
_WRITING = re.compile(r"(?i)^(?:create|make|start|set\s+up|write|draft|plan|change|play|run|format|update|open)\s+(?:me\s+)?"
                      r"(?:a|an|some|the|my|this|that)?\s*(?:[\w'-]+\s+){0,2}?(?:story|poem|joke|essay|letter|speech|summary|"
                      r"plan|budget|recipe|list|workout|routine|schedule|song|lyrics|name|title|bio|caption|tweet|post|"
                      r"cover\s+letter|resume|cv|quiz|game|riddle|outline|paragraph|sentence|haiku|description|review|"
                      r"itinerary|menu|checklist|table|business|diet|habit|conversation|discussion|debate)s?\b")


def is_question_like(text: str) -> bool:
    """True when words that start like a command ask for an answer or for writing, not for an action on this
    computer: "remove duplicates from a list in python", "run me through how DNS works", "make a list of
    snacks", "delete vs truncate in sql". Anything naming a file, folder, app or device setting stays an
    action ("delete my shopping list.txt", "can you shut down the pc?")."""
    core = _POLITE.sub("", text or "").strip()
    if not core:
        return False
    if _ASKING_START.match(core):
        return True
    if _THINGS.search(core):
        return False
    return bool(_ASKING_WORDS.search(core) or _CODEY.search(core) or _FOR_ME.match(core) or _WRITING.match(core))


# Words that begin a phrase rather than name a file ("move on to...", "run through the plan").
_NOT_A_NAME = {"on", "up", "out", "over", "away", "back", "ahead", "forward", "through", "around", "along", "in", "into",
               "it", "this", "that", "them", "these", "those", "me", "us", "you", "everything", "all", "something"}


def _names_a_file(spoken: str) -> bool:
    """Could these words be a file or folder name the owner means (when nothing by that name exists yet)?"""
    words = _clean(spoken).split()
    if not words:
        return False
    if re.search(r"\.[a-z0-9]{1,5}$", words[-1], re.I) or "/" in spoken or "~" in spoken:
        return True
    return len(words) <= 2 and words[0].lower() not in _NOT_A_NAME


class Planner:
    """Turn the owner's words into one typed ActionRequest (or None if not an action)."""

    def __init__(self, home: Path | None = None, app_dirs: list[Path] | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        self.app_dirs = app_dirs

    def folder(self, spoken: str) -> Path:
        key = _clean(spoken).lower().removeprefix("my ").removesuffix(" folder").strip()
        if key in FOLDERS:
            return self.home / FOLDERS[key]
        return self.inside_home(spoken)

    def inside_home(self, spoken: str, base: Path | None = None) -> Path:
        """Resolve a spoken path; it must stay inside the home folder."""
        raw = _clean(spoken)
        if not raw:
            raise ParseError("a file or folder name is needed")
        path = Path(os.path.expanduser(raw))
        if not path.is_absolute():
            path = (base or self.home) / path
        resolved = path.resolve()
        if resolved != self.home and self.home not in resolved.parents:
            raise ParseError("APVIS only changes files inside your home folder")
        if any(part.startswith(".") for part in resolved.relative_to(self.home).parts[:1]) and ".local/share/Trash" not in str(resolved):
            raise ParseError("APVIS does not change hidden settings folders")
        return resolved

    def _locate(self, name: str, where: str | None) -> Path:
        return self.inside_home(name, self.folder(where) if where else None)

    def plan(self, text: str) -> ActionRequest | None:
        t = text.strip()
        low = t.lower()
        m = re.match(r"^\s*(?:how much|what is the|what's the|check(?: the)?|show(?: me)?(?: the)?)\s*(?:free\s+)?(?:disk|storage|drive)\s*(?:space)?(?:\s+is)?(?:\s+(?:free|left|available))?" + _TAIL, low)
        if m or low.strip(" ?.") in {"disk space", "free space", "how much space do i have", "how much space is left"}:
            return ActionRequest("disk_space", {}, "Check free disk space")
        if re.match(r"^\s*(?:show|check|what is|what's|how is)\s+(?:the\s+|my\s+)?(?:system|computer|pc)(?:\s+status)?" + _TAIL, low):
            return ActionRequest("system_status", {}, "Check system status (CPU, memory, uptime)")
        if is_question_like(t):
            return None                     # a question that starts like a command: Ask answers it
        m = re.match(_LEAD + r"(shut\s*down|power\s*off|turn\s+off\s+the\s+(?:computer|pc)|restart|reboot)(?:\s+the\s+(?:computer|pc))?" + _TAIL, low)
        if m:
            reboot = m.group(1).startswith(("restart", "reboot"))
            return ActionRequest("power", {"action": "reboot" if reboot else "poweroff"},
                                 "Restart the computer" if reboot else "Shut down the computer")
        m = re.match(_LEAD + r"turn\s+(on|off)\s+(?:the\s+)?wi-?fi" + _TAIL, low) or \
            re.match(_LEAD + r"turn\s+(?:the\s+)?wi-?fi\s+(on|off)" + _TAIL, low) or \
            re.match(_LEAD + r"(enable|disable)\s+(?:the\s+)?wi-?fi" + _TAIL, low)
        if m:
            on = m.group(1) in {"on", "enable"}
            return ActionRequest("wifi", {"on": on}, f"Turn Wi-Fi {'on' if on else 'off'}")
        m = re.match(_LEAD + r"(?:set|change|turn)\s+(?:the\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*%?" + _TAIL, low)
        if m:
            level = int(m.group(1))
            if level > 100:
                raise ParseError("volume must be between 0 and 100%")
            return ActionRequest("set_volume", {"percent": level}, f"Set the volume to {level}%")
        m = re.match(_LEAD + r"(mute|unmute)(?:\s+(?:the\s+)?(?:sound|volume|audio))?" + _TAIL, low)
        if m:
            mute = m.group(1) == "mute"
            return ActionRequest("mute", {"mute": mute}, "Mute the sound" if mute else "Unmute the sound")
        m = re.match(_LEAD + r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?folder\s+(?:called\s+|named\s+)?(.+?)(?:\s+in\s+(?:my\s+)?(.+?))?" + _TAIL, t, re.I)
        if m:
            path = self._locate(m.group(1), m.group(2))
            return ActionRequest("create_folder", {"path": str(path)}, f"Create the folder {self.show(path)}")
        m = re.match(_LEAD + r"(?:delete|remove|trash|bin)\s+(.+?)(?:\s+(?:from|in)\s+(?:my\s+)?(.+?))?" + _TAIL, t, re.I)
        if m:
            path = self._locate(m.group(1), m.group(2))
            if path == self.home or path.parent == self.home and path.name in FOLDERS.values():
                raise ParseError("APVIS will not trash your home folder or its standard folders")
            if not path.exists() and not _names_a_file(m.group(1)):
                return None
            return ActionRequest("trash", {"path": str(path)}, f"Move {self.show(path)} to Trash (you can restore it)")
        m = re.match(_LEAD + r"rename\s+(.+?)\s+to\s+(.+?)(?:\s+in\s+(?:my\s+)?(.+?))?" + _TAIL, t, re.I)
        if m:
            src = self._locate(m.group(1), m.group(3))
            if not src.exists() and not _names_a_file(m.group(1)):
                return None
            dst = self.inside_home(m.group(2), src.parent)
            return ActionRequest("move", {"src": str(src), "dst": str(dst)}, f"Rename {self.show(src)} to {dst.name}")
        m = re.match(_LEAD + r"move\s+(.+?)\s+(?:from\s+(?:my\s+)?(.+?)\s+)?(?:to|into)\s+(?:my\s+)?(.+?)" + _TAIL, t, re.I)
        if m:
            src = self._locate(m.group(1), m.group(2))
            if not src.exists() and not _names_a_file(m.group(1)):
                return None                 # "move on to the next topic"
            dst = self.folder(m.group(3)) / src.name
            return ActionRequest("move", {"src": str(src), "dst": str(dst)}, f"Move {self.show(src)} to {self.show(dst.parent)}")
        # V4: "switch to Firefox" / "go to the terminal" / "show VLC": focus its window, or open it if none is open.
        m = re.match(_LEAD + r"(?:switch|swap|flip|change)\s+(?:over\s+|back\s+)?to\s+(?:the\s+|my\s+)?(.+?)(?:\s+(?:app|window))?" + _TAIL, t, re.I) or \
            re.match(_LEAD + r"(?:go|jump|get)\s+(?:back\s+)?to\s+(?:the\s+|my\s+)?(.+?)(?:\s+(?:app|window))?" + _TAIL, t, re.I) or \
            re.match(_LEAD + r"(?:show|bring\s+up|focus(?:\s+on)?)\s+(?:me\s+)?(?:the\s+|my\s+)?(.+?)(?:\s+(?:app|window))?" + _TAIL, t, re.I)
        if m:
            if _clean(m.group(1)).lower().removesuffix(" folder") in FOLDERS:
                path = self.folder(m.group(1))
                return ActionRequest("open_folder", {"path": str(path)}, f"Open {self.show(path)} in Files")
            entry = app_entry(m.group(1), self.app_dirs)
            if entry is not None:
                return ActionRequest("focus_app", {"app": entry["name"], "app_ids": entry["app_ids"], "argv": entry["argv"]},
                                     f"Switch to {entry['name']}")
            return None                     # "go to bed", "show me how": not an app
        m = re.match(_LEAD + r"(?:open|launch|start|run)\s+(?:the\s+|my\s+)?(.+?)" + _TAIL, t, re.I)
        if m:
            target = _clean(m.group(1))
            key = target.lower().removesuffix(" folder").strip()
            if key in FOLDERS or target.lower().endswith(" folder") or "/" in target:
                path = self.folder(target)
                return ActionRequest("open_folder", {"path": str(path)}, f"Open {self.show(path)} in Files")
            bare = re.sub(r"(?i)^(?:a|an|up)\s+", "", target)
            if find_app(target, self.app_dirs) is None and (bare == target or find_app(bare, self.app_dirs) is None):
                words = target.split()
                if len(words) > 3 or words[0].lower() in _NOT_A_NAME | {"a", "an", "some"}:
                    return None             # "run through the plan again", "start a fire": not an app name
                raise ParseError(f"I couldn't find an installed app called {target!r}")
            if find_app(target, self.app_dirs) is None:
                target = bare
            return ActionRequest("open_app", {"app": target}, f"Open {target}")
        return None

    def show(self, path: Path) -> str:
        """Owner-facing path: ~/Documents/Report.pdf."""
        try:
            rel = Path(path).resolve().relative_to(self.home)
        except ValueError:
            return str(path)
        return "~" if str(rel) == "." else f"~/{rel.as_posix()}"


# ---------------------------------------------------------------- executing

def _postcondition(check: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"postcondition": {"check": check, "passed": passed, "detail": detail}}


def _verify_postconditions(result: ActionResult) -> VerificationResult:
    checks = [item["postcondition"] for item in result.evidence if "postcondition" in item]
    if checks and all(check["passed"] for check in checks):
        return VerificationResult("postcondition", "passed", checks)
    return VerificationResult("postcondition", "failed", checks, "the result could not be confirmed")


def _run(command: list[str], timeout: float = 10) -> subprocess.CompletedProcess:
    if not Path(command[0]).is_file() and not shutil.which(command[0]):
        raise FileNotFoundError(f"{Path(command[0]).name} is not installed")
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def find_app(name: str, dirs: list[Path] | None = None) -> list[str] | None:
    """Find an installed app by its desktop-entry name; returns an argv (never a shell string)."""
    key = name.lower().strip()
    if key in APP_ALIASES:
        return APP_ALIASES[key]
    dirs = dirs or [Path.home() / ".local/share/applications", Path("/usr/share/applications")]
    best: tuple[int, list[str]] | None = None
    for directory in dirs:
        for entry in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                parser.read(entry, encoding="utf-8")
                section = parser["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
                continue
            if section.get("NoDisplay", "false").lower() == "true" or section.get("Hidden", "false").lower() == "true":
                continue
            names = {section.get("Name", "").lower(), entry.stem.lower(), section.get("GenericName", "").lower()}
            score = 2 if key in names else 1 if any(n.startswith(key) for n in names if n) else 0
            if score and (best is None or score > best[0]):
                argv = [a for a in shlex.split(section.get("Exec", "")) if not re.fullmatch(r"%[a-zA-Z]", a)]
                if argv:
                    best = (score, argv)
    return best[1] if best else None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", (text or "").lower())


def app_entry(spoken: str, dirs: list[Path] | None = None) -> dict[str, Any] | None:
    """The installed app the owner names ("firefox", "the terminal", "vs code"): its name, how to start it and
    the Wayland app ids its windows may carry (desktop id, StartupWMClass, program name). Names must match
    exactly (or be the app name's first word), so "go to bed" or "show me the news" never pick an app."""
    from . import appstore                          # the Apps Store's view of this computer's desktop entries

    cleaned = re.sub(r"(?i)\s+(?:app|application|window|program)$", "", _clean(spoken))
    cleaned = re.sub(r"(?i)^(?:the|my|a|an)\s+", "", cleaned)
    key = _norm(cleaned)
    if len(key) < 2:
        return None
    apps = appstore.installed_apps(dirs)
    alias = APP_ALIASES.get(cleaned.lower())
    catalog = appstore.find(cleaned)
    exact, loose = None, None
    for app in apps:
        program = Path(app["argv"][0]).name
        names = {_norm(app["name"]), _norm(app["id"]), _norm(app["id"].rsplit(".", 1)[-1]), _norm(program),
                 _norm(app.get("wmclass", ""))} - {""}
        if key in names or (alias and program == Path(alias[0]).name):
            exact = app
            break
        first = _norm(app["name"].split()[0])
        known = catalog is not None and (app["id"] == catalog.desktop or _norm(app["name"]) == _norm(catalog.name))
        if loose is None and ((len(key) >= 3 and key == first) or known):
            loose = app
    app = exact or loose
    if app is None:
        if not alias:
            return None
        program = Path(alias[0]).name
        return {"id": program, "name": cleaned.capitalize(), "argv": list(alias), "app_ids": [program]}
    ids = []
    for candidate in (app["id"], app.get("wmclass", ""), Path(app["argv"][0]).name):
        if candidate and candidate not in ids:
            ids.append(candidate)
    return {"id": app["id"], "name": app["name"], "argv": list(app["argv"]), "app_ids": ids}


class Executors:
    def __init__(self, home: Path, planner: Planner, launcher: Callable[[list[str]], Any] | None = None,
                 runner: Callable[..., subprocess.CompletedProcess] = _run) -> None:
        self.home, self.planner = home, planner
        self.launch = launcher or (lambda argv: subprocess.Popen(argv, close_fds=True, start_new_session=True,
                                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self.run = runner

    def open_app(self, spec: ActionSpec):
        argv = find_app(spec.inputs["app"], self.planner.app_dirs)
        if argv is None:
            raise FileNotFoundError(f"no installed app called {spec.inputs['app']!r}")
        process = self.launch(argv)
        time.sleep(0.5)
        alive = getattr(process, "poll", lambda: None)() is None
        return {"message": f"Opened {spec.inputs['app']}."}, [{"argv": argv}, _postcondition("process started", alive, argv[0])]

    def focus_app(self, spec: ActionSpec):
        """Bring the app's open window to the front (wlrctl, V4 image); if it has none, or wlrctl is missing or
        the compositor doesn't answer, open the app instead."""
        name, argv = spec.inputs["app"], list(spec.inputs["argv"])
        for app_id in spec.inputs.get("app_ids") or []:
            try:
                found = self.run([WLRCTL, "toplevel", "find", f"app_id:{app_id}"], timeout=3)
                if found.returncode != 0:
                    continue
                done = self.run([WLRCTL, "toplevel", "focus", f"app_id:{app_id}"], timeout=3)
            except (OSError, subprocess.SubprocessError):
                break                                   # no wlrctl here (before V4) or no compositor: open it
            if done.returncode == 0:
                return {"message": f"Switched to {name}."}, [{"app_id": app_id}, _postcondition("window focused", True, app_id)]
        process = self.launch(argv)
        time.sleep(0.5)
        alive = getattr(process, "poll", lambda: None)() is None
        return ({"message": f"{name} wasn't open, so I opened it."},
                [{"argv": argv}, _postcondition("process started", alive, argv[0])])

    def open_folder(self, spec: ActionSpec):
        path = Path(spec.inputs["path"])
        if not path.is_dir():
            raise FileNotFoundError(f"{self.planner.show(path)} does not exist")
        process = self.launch(["/usr/bin/pcmanfm-qt", str(path)])
        time.sleep(0.5)
        alive = getattr(process, "poll", lambda: None)() is None
        return {"message": f"Opened {self.planner.show(path)}."}, [_postcondition("file manager started", alive, str(path))]

    def disk_space(self, spec: ActionSpec):
        usage = shutil.disk_usage(self.home)
        gb = lambda n: n / 1e9  # noqa: E731
        message = f"Your home folder's drive has {gb(usage.free):.1f} GB free of {gb(usage.total):.1f} GB ({usage.used / usage.total:.0%} used)."
        return {"message": message}, [{"disk": usage._asdict()}, _postcondition("measured", True, "shutil.disk_usage")]

    def system_status(self, spec: ActionSpec):
        import psutil

        memory = psutil.virtual_memory()
        uptime = time.time() - psutil.boot_time()
        cpu = psutil.cpu_percent(interval=0.5)
        message = (f"CPU {cpu:.0f}% busy, memory {memory.used / 1e9:.1f} of {memory.total / 1e9:.1f} GB used, "
                   f"up for {int(uptime // 3600)} h {int(uptime % 3600 // 60)} min.")
        return {"message": message}, [{"cpu_percent": cpu, "memory_percent": memory.percent, "uptime_s": int(uptime)},
                                      _postcondition("measured", True, "psutil")]

    def create_folder(self, spec: ActionSpec):
        path = Path(spec.inputs["path"])
        if path.exists():
            raise FileExistsError(f"{self.planner.show(path)} already exists")
        path.mkdir(parents=True)
        return {"message": f"Created {self.planner.show(path)}."}, [_postcondition("folder exists", path.is_dir(), str(path))]

    def move(self, spec: ActionSpec):
        src, dst = Path(spec.inputs["src"]), Path(spec.inputs["dst"])
        if not src.exists():
            raise FileNotFoundError(f"{self.planner.show(src)} does not exist")
        if dst.exists():
            raise FileExistsError(f"{self.planner.show(dst)} already exists; nothing was overwritten")
        if not dst.parent.is_dir():
            raise FileNotFoundError(f"{self.planner.show(dst.parent)} does not exist")
        shutil.move(str(src), str(dst))
        return ({"message": f"Moved to {self.planner.show(dst)}."},
                [_postcondition("moved", dst.exists() and not src.exists(), f"{src} -> {dst}")])

    def trash(self, spec: ActionSpec):
        """freedesktop.org Trash: restorable from the file manager's Trash."""
        src = Path(spec.inputs["path"])
        if not src.exists():
            raise FileNotFoundError(f"{self.planner.show(src)} does not exist")
        target = move_to_trash(src, self.home)
        return ({"message": f"Moved {self.planner.show(src)} to Trash. You can restore it from Trash in Files."},
                [{"trashed_as": str(target)}, _postcondition("in Trash", target.exists() and not src.exists(), str(target))])

    def _volume(self) -> tuple[float, bool]:
        out = self.run(["/usr/bin/wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).stdout
        m = re.search(r"Volume:\s*([\d.]+)", out)
        if not m:
            raise RuntimeError("could not read the volume back")
        return float(m.group(1)), "MUTED" in out

    def set_volume(self, spec: ActionSpec):
        percent = int(spec.inputs["percent"])
        done = self.run(["/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent / 100:.2f}"])
        if done.returncode:
            raise RuntimeError(done.stderr.strip() or "wpctl failed")
        level, _ = self._volume()
        return {"message": f"Volume is now {round(level * 100)}%."}, [_postcondition("volume read back", abs(level * 100 - percent) < 1.5, f"{level:.2f}")]

    def mute(self, spec: ActionSpec):
        mute = bool(spec.inputs["mute"])
        done = self.run(["/usr/bin/wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if mute else "0"])
        if done.returncode:
            raise RuntimeError(done.stderr.strip() or "wpctl failed")
        _, muted = self._volume()
        return {"message": "Sound muted." if muted else "Sound unmuted."}, [_postcondition("mute read back", muted == mute, str(muted))]

    def wifi(self, spec: ActionSpec):
        on = bool(spec.inputs["on"])
        done = self.run(["/usr/bin/nmcli", "radio", "wifi", "on" if on else "off"])
        if done.returncode:
            raise RuntimeError(done.stderr.strip() or "nmcli failed")
        state = self.run(["/usr/bin/nmcli", "radio", "wifi"]).stdout.strip()
        return {"message": f"Wi-Fi is now {state}."}, [_postcondition("radio read back", state == ("enabled" if on else "disabled"), state)]

    def power(self, spec: ActionSpec):
        action = spec.inputs["action"]
        if action not in {"poweroff", "reboot"}:
            raise ValueError("unknown power action")
        done = self.run(["/usr/bin/systemctl", action], timeout=20)
        if done.returncode:
            raise PermissionError(done.stderr.strip() or f"systemctl {action} was refused")
        # The machine is going down; success cannot be observed from here.
        return {"message": "Restarting now." if action == "reboot" else "Shutting down now."}, [_postcondition("request accepted", True, action)]


# ---------------------------------------------------------------- missions

class MissionControl:
    def __init__(self, home: Path | None = None, store: TaskStore | None = None, engine: ActionEngine | None = None,
                 launcher: Callable[[list[str]], Any] | None = None, runner: Callable[..., subprocess.CompletedProcess] = _run,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), app_dirs: list[Path] | None = None) -> None:
        self.home = (home or Path.home()).resolve()
        self.planner = Planner(self.home, app_dirs)
        self.store = store or TaskStore()
        self.engine = engine or ActionEngine()
        self.clock = clock
        executors = Executors(self.home, self.planner, launcher, runner)
        for kind in KINDS.values():
            self.engine.register(f"mission.{kind.name}", kind.permission, getattr(executors, kind.name))
        try:
            self.engine.verification_registry.register("mission_postcondition", _verify_postconditions)
        except ValueError:
            pass  # shared registry already has it

    # -- records
    def _new_plan(self, text: str, steps: list[ActionRequest], source: str, title: str) -> TaskState:
        if not steps or len(steps) > MAX_PLAN_STEPS:
            raise ParseError("a plan needs between 1 and %d steps" % MAX_PLAN_STEPS)
        now = self.clock()
        needs = any(KINDS[s.kind].needs_approval for s in steps) or source == "model"
        worst = max((KINDS[s.kind].permission for s in steps), key=lambda p: list(PermissionClass).index(p))
        previews = [s.preview for s in steps]
        return TaskState(1, 0, f"mission-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}", text, title,
                         plan=previews, pending_steps=list(previews),
                         constraints=[f"permission:{worst.value}", f"approval:{'required' if needs else 'not required'}",
                                      f"source:{source}"],
                         observations=[{"plan": [s.to_dict() for s in steps], "source": source, "title": title,
                                        "approval_hash": plan_token(steps, source),
                                        "expires_at": (now + APPROVAL_TTL).isoformat().replace("+00:00", "Z")}],
                         replay_safety="unsafe" if needs else "safe")

    @staticmethod
    def _steps(state: TaskState) -> tuple[list[ActionRequest], str, str, str]:
        """(steps, approval hash, expiry, source) for one-step missions and plans alike."""
        record = state.observations[0]
        if "plan" in record:
            steps = [ActionRequest(d["kind"], d["params"], d["preview"]) for d in record["plan"]]
            return steps, record["approval_hash"], record["expires_at"], record.get("source", "owner")
        request, token, expires = MissionControl._request(state)
        return [request], token, expires, "owner"

    def propose_plan(self, text: str, steps: list[ActionRequest], source: str, title: str) -> TaskState:
        """A multi-step plan: waits for one approval if any step changes something (or a model wrote it),
        otherwise runs straight away."""
        for step in steps:
            if step.kind not in KINDS:
                raise ParseError(f"unknown action {step.kind!r}")
        state = self._new_plan(text, steps, source, title)
        if "approval:required" in state.constraints:
            state.final_status, state.current_step = "approval_required", title
            self.store.save(state)
            return state
        return self._execute_plan(state, steps)

    def _new(self, text: str, request: ActionRequest) -> TaskState:
        kind = KINDS[request.kind]
        now = self.clock()
        state = TaskState(1, 0, f"mission-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}", text, request.preview,
                          plan=[request.preview], pending_steps=[request.preview],
                          constraints=[f"permission:{kind.permission.value}", f"approval:{'required' if kind.needs_approval else 'not required'}"],
                          observations=[{"mission": request.to_dict(), "approval_hash": request.token(),
                                         "expires_at": (now + APPROVAL_TTL).isoformat().replace("+00:00", "Z")}],
                          replay_safety="unsafe" if kind.needs_approval else "safe")
        return state

    @staticmethod
    def _request(state: TaskState) -> tuple[ActionRequest, str, str]:
        record = state.observations[0]
        if "plan" in record:                       # a plan: its first step stands for it here
            first = record["plan"][0]
            return ActionRequest(first["kind"], first["params"], record.get("title", first["preview"])), \
                record["approval_hash"], record["expires_at"]
        mission = record["mission"]
        return ActionRequest(mission["kind"], mission["params"], mission["preview"]), record["approval_hash"], record["expires_at"]

    def propose(self, text: str) -> TaskState | None:
        """Plan an action from the owner's words; run it now if it changes nothing."""
        request = self.planner.plan(text)
        if request is None:
            return None
        state = self._new(text, request)
        if KINDS[request.kind].needs_approval:
            state.final_status = "approval_required"
            state.current_step = request.preview
            self.store.save(state)
            return state
        return self._execute(state, request)

    def approve(self, task_id: str, token: str) -> TaskState:
        state = self.store.load(task_id)
        if "plan" in state.observations[0]:
            return self._approve_plan(state, token)
        request, expected, expires = self._request(state)
        if state.final_status != "approval_required":
            done = {"completed": "already done", "cancelled": "cancelled", "failed": "already tried"}.get(state.final_status, state.final_status)
            raise ValueError(f"This was {done}, so nothing ran again")
        if token != expected or request.token() != expected:
            raise PermissionError("approval does not match the action that was shown")
        if self.clock() > datetime.fromisoformat(expires.replace("Z", "+00:00")):
            self._finish(state, "cancelled", error="approval expired; nothing was done")
            raise PermissionError("approval expired; nothing was done")
        state.verification.append({"approved_at": utc_now(), "approved_hash": token})
        return self._execute(state, request)

    def _approve_plan(self, state: TaskState, token: str) -> TaskState:
        steps, expected, expires, source = self._steps(state)
        if state.final_status != "approval_required":
            done = {"completed": "already done", "cancelled": "cancelled", "failed": "already tried"}.get(state.final_status, state.final_status)
            raise ValueError(f"This was {done}, so nothing ran again")
        if token != expected or plan_token(steps, source) != expected:
            raise PermissionError("approval does not match the plan that was shown")
        if self.clock() > datetime.fromisoformat(expires.replace("Z", "+00:00")):
            self._finish(state, "cancelled", error="approval expired; nothing was done")
            raise PermissionError("approval expired; nothing was done")
        state.verification.append({"approved_at": utc_now(), "approved_hash": token, "steps": len(steps)})
        return self._execute_plan(state, steps)

    def cancel(self, task_id: str) -> TaskState:
        state = self.store.load(task_id)
        if state.final_status == "running" and "plan" in state.observations[0]:
            # A plan stops before its next step; the step already running finishes (and is checked).
            state.observations[0]["cancel_requested"] = True
            self.store.save(state)
            return state
        if state.final_status != "approval_required":
            raise ValueError("Only actions still waiting for approval can be cancelled")
        return self._finish(state, "cancelled", error="cancelled by the owner before anything ran")

    def expire(self) -> list[str]:
        expired = []
        for state in self.recent(limit=50):
            if state.final_status == "approval_required":
                _, _, expires, _ = self._steps(state)
                if self.clock() > datetime.fromisoformat(expires.replace("Z", "+00:00")):
                    self._finish(state, "cancelled", error="approval expired; nothing was done")
                    expired.append(state.task_id)
        return expired

    def _finish(self, state: TaskState, status: str, *, error: str | None = None) -> TaskState:
        state.final_status = status
        state.current_step = None
        if error:
            state.errors.append({"at": utc_now(), "error": error})
        self.store.save(state)
        return state

    def _execute(self, state: TaskState, request: ActionRequest) -> TaskState:
        kind = KINDS[request.kind]
        state.final_status, state.current_step = "running", request.preview
        self.store.save(state)
        result = self.engine.execute(ActionSpec(state.task_id, f"mission.{kind.name}", kind.permission, request.params,
                                                verification=("mission_postcondition",)))
        state.tool_action_results.append(result.to_dict())
        state.completed_steps, state.pending_steps = [request.preview], []
        if result.status == "verified":
            return self._finish(state, "completed")
        if result.status == "failed":
            return self._finish(state, "failed", error=result.error or "action failed")
        # Ran but could not be confirmed: say so rather than claim success.
        state.uncertain_outcome = {"reason": result.error or "result not confirmed"}
        return self._finish(state, "failed", error=result.error or "the result could not be confirmed")

    def _execute_plan(self, state: TaskState, steps: list[ActionRequest]) -> TaskState:
        """Run the steps in order. Each is checked afterwards; the first failure stops the plan and the
        record says exactly which steps ran and which did not."""
        total = len(steps)
        messages = []
        state.final_status = "running"
        for number, step in enumerate(steps, 1):
            fresh = self.store.load(state.task_id) if (self.store.state_dir / f"{state.task_id}.json").exists() else state
            if fresh.observations[0].get("cancel_requested"):
                state.completed_steps, state.pending_steps = [s.preview for s in steps[:number - 1]], [s.preview for s in steps[number - 1:]]
                return self._finish(state, "cancelled",
                                    error=f"stopped by you after {number - 1} of {total} steps; the rest did not run")
            kind = KINDS[step.kind]
            state.current_step = f"Step {number} of {total}: {step.preview}"
            self.store.save(state)
            result = self.engine.execute(ActionSpec(state.task_id, f"mission.{kind.name}", kind.permission, step.params,
                                                    verification=("mission_postcondition",)))
            state.tool_action_results.append(result.to_dict())
            if result.status != "verified":
                state.completed_steps = [s.preview for s in steps[:number - 1]]
                state.pending_steps = [s.preview for s in steps[number - 1:]]
                reason = result.error or ("the result could not be confirmed" if result.status != "failed" else "action failed")
                if result.status != "failed":
                    state.uncertain_outcome = {"reason": reason, "step": number}
                not_run = total - number
                return self._finish(state, "failed", error=f"Step {number} of {total} ({step.preview}) did not work: {reason}. "
                                    + (f"{number - 1} step{'s' if number - 1 != 1 else ''} before it finished. " if number > 1 else "")
                                    + (f"{not_run} later step{'s' if not_run != 1 else ''} did not run." if not_run else ""))
            message = (result.result or {}).get("message", "") if hasattr(result, "result") else ""
            if message:
                messages.append(message)
            state.completed_steps.append(step.preview)
            state.pending_steps = [s.preview for s in steps[number:]]
        state.observations[0]["messages"] = messages
        return self._finish(state, "completed")

    def recent(self, limit: int = 12) -> list[TaskState]:
        missions = []
        for task_id in reversed(self.store.list_ids()):
            if task_id.startswith("mission-"):
                try:
                    missions.append(self.store.load(task_id))
                except (OSError, ValueError):
                    continue
            if len(missions) >= limit:
                break
        return missions

    def archive_finished(self) -> int:
        """Move finished mission records out of the active list (kept on disk, audit log untouched)."""
        archive = self.store.state_dir / "archive"
        moved = 0
        for state in self.recent(limit=500):
            if state.final_status in {"completed", "failed", "cancelled"}:
                archive.mkdir(parents=True, exist_ok=True)
                os.replace(self.store.state_dir / f"{state.task_id}.json", archive / f"{state.task_id}.json")
                moved += 1
        return moved


def summary(state: TaskState) -> dict[str, Any]:
    """Compact, UI-ready view of one mission."""
    if "plan" in state.observations[0]:
        return _plan_summary(state)
    request, token, expires = MissionControl._request(state)
    kind = KINDS[request.kind]
    last = state.tool_action_results[-1] if state.tool_action_results else {}
    message = (last.get("result") or {}).get("message", "")
    error = state.errors[-1]["error"] if state.errors else ""
    if state.final_status == "failed" and message:
        # It ran, but the check afterwards did not confirm the change.
        message, error = "", f"The change could not be confirmed. {message}"
    return {
        "id": state.task_id, "status": state.final_status, "preview": request.preview, "title": kind.title,
        "asked": state.original_objective, "needsApproval": kind.needs_approval,
        "permission": kind.permission.value, "token": token if state.final_status == "approval_required" else "",
        "expiresAt": expires, "message": message, "error": error, "updatedAt": state.updated_at,
        "verified": last.get("status") == "verified",
    }


def _plan_summary(state: TaskState) -> dict[str, Any]:
    steps, token, expires, source = MissionControl._steps(state)
    record = state.observations[0]
    needs = "approval:required" in state.constraints
    previews = [s.preview for s in steps]
    error = state.errors[-1]["error"] if state.errors else ""
    message = ""
    if state.final_status == "completed":
        done = record.get("messages") or []
        message = " ".join(done) if done else f"All {len(steps)} steps done."
    numbered = "\n".join(f"{i}. {p}" for i, p in enumerate(previews, 1))
    title = record.get("title") or f"Plan · {len(steps)} steps"
    return {
        "id": state.task_id, "status": state.final_status, "preview": f"{title}\n{numbered}", "title": title,
        "asked": state.original_objective, "needsApproval": needs, "steps": previews,
        "done": len(state.completed_steps), "current": state.current_step or "",
        "source": source, "sourceText": PLAN_SOURCES.get(source, source),
        "permission": next((c.split(":", 1)[1] for c in state.constraints if c.startswith("permission:")), ""),
        "token": token if state.final_status == "approval_required" else "",
        "expiresAt": expires, "message": message, "error": error, "updatedAt": state.updated_at,
        "verified": state.final_status == "completed",
    }
