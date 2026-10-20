"""APVIS Apps Store: launch what is installed, install more from Debian or Flathub.

Installed apps are this computer's real desktop entries. The catalog below lists real
packages (Debian trixie, or Flathub when Debian has no build). Installing and removing
runs through /usr/local/lib/apvis-os/apvis-apps as root, which only accepts ids from
this catalog (its own root-owned copy, never the owner's update folder). Home checks
the owner's password before asking it to run.
"""

from __future__ import annotations

import configparser
import json
import re
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

HELPER = Path("/usr/local/lib/apvis-os/apvis-apps")
PREFS = Path.home() / ".local/state/apvis-os/apps.json"
MAX_PINNED = 6
MAX_RECENT = 12
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"
CATEGORIES = ("featured", "productivity", "development", "creativity", "media", "internet", "utilities", "apvis", "selfhosted", "installed")


@dataclass(frozen=True)
class CatalogApp:
    id: str
    name: str
    summary: str
    category: str               # one of CATEGORIES
    source: str                 # debian | flathub
    ref: str                    # Debian package or Flathub app id
    desktop: str = ""           # the desktop entry it installs (to open it afterwards)
    kind: str = "app"           # app | service
    featured: bool = False
    about: str = ""


def _c(id, name, summary, category, source, ref, desktop="", kind="app", featured=False, about=""):  # noqa: A002
    return CatalogApp(id, name, summary, category, source, ref, desktop or (ref if source == "flathub" else ""), kind, featured, about)


CATALOG: tuple[CatalogApp, ...] = (
    _c("firefox", "Firefox", "Web browser", "internet", "debian", "firefox-esr", "firefox-esr", featured=True,
       about="Mozilla's web browser (Extended Support Release, kept up to date by Debian security updates)."),
    _c("vscode", "Visual Studio Code", "Code editor", "development", "flathub", "com.visualstudio.code", featured=True,
       about="Microsoft's code editor with extensions for every language. From Flathub."),
    _c("vlc", "VLC", "Media player", "media", "debian", "vlc", "vlc", featured=True,
       about="Plays nearly every video and audio file, DVDs and network streams."),
    _c("libreoffice", "LibreOffice", "Office suite", "productivity", "debian", "libreoffice", "libreoffice-startcenter", featured=True,
       about="Documents, spreadsheets and presentations; opens Microsoft Office files."),
    _c("thunderbird", "Thunderbird", "Email and calendar", "productivity", "debian", "thunderbird", "thunderbird"),
    _c("obsidian", "Obsidian", "Notes and knowledge base", "productivity", "flathub", "md.obsidian.Obsidian"),
    _c("keepassxc", "KeePassXC", "Password manager", "productivity", "debian", "keepassxc", "org.keepassxc.KeePassXC"),
    _c("qpdfview", "qpdfview", "PDF viewer", "productivity", "debian", "qpdfview", "qpdfview"),
    _c("geany", "Geany", "Lightweight code editor", "development", "debian", "geany", "geany"),
    _c("thonny", "Thonny", "Python for beginners", "development", "debian", "thonny", "org.thonny.Thonny"),
    _c("github-desktop", "GitHub Desktop", "Git made simple", "development", "flathub", "io.github.shiftey.Desktop"),
    _c("git", "Git", "Version control (terminal)", "development", "debian", "git", kind="service"),
    _c("gimp", "GIMP", "Photo and image editor", "creativity", "debian", "gimp", "gimp"),
    _c("inkscape", "Inkscape", "Vector graphics", "creativity", "debian", "inkscape", "org.inkscape.Inkscape"),
    _c("krita", "Krita", "Digital painting", "creativity", "debian", "krita", "org.kde.krita"),
    _c("blender", "Blender", "3D modelling and animation", "creativity", "debian", "blender", "blender"),
    _c("kdenlive", "Kdenlive", "Video editor", "creativity", "debian", "kdenlive", "org.kde.kdenlive"),
    _c("audacity", "Audacity", "Audio editor", "creativity", "debian", "audacity", "audacity"),
    _c("obs", "OBS Studio", "Recording and streaming", "creativity", "debian", "obs-studio", "com.obsproject.Studio"),
    _c("mpv", "mpv", "Minimal video player", "media", "debian", "mpv", "mpv"),
    _c("spotify", "Spotify", "Music streaming", "media", "flathub", "com.spotify.Client"),
    _c("strawberry", "Strawberry", "Music library player", "media", "debian", "strawberry", "org.strawberrymusicplayer.strawberry"),
    _c("steam", "Steam", "Games", "media", "flathub", "com.valvesoftware.Steam"),
    _c("chromium", "Chromium", "Web browser", "internet", "debian", "chromium", "chromium"),
    _c("discord", "Discord", "Voice and chat", "internet", "flathub", "com.discordapp.Discord"),
    _c("telegram", "Telegram", "Messaging", "internet", "debian", "telegram-desktop", "org.telegram.desktop"),
    _c("transmission", "Transmission", "Torrent downloads", "internet", "debian", "transmission-qt", "transmission-qt"),
    _c("filezilla", "FileZilla", "FTP and SFTP transfers", "internet", "debian", "filezilla", "filezilla"),
    _c("gparted", "GParted", "Partition editor", "utilities", "debian", "gparted", "gparted"),
    _c("flameshot", "Flameshot", "Screenshots", "utilities", "debian", "flameshot", "org.flameshot.Flameshot"),
    _c("htop", "htop", "Process viewer (terminal)", "utilities", "debian", "htop", "htop"),
    _c("archiver", "LXQt Archiver", "Zip and unzip files", "utilities", "debian", "lxqt-archiver", "lxqt-archiver"),
    _c("baobab", "Disk Usage", "See what fills your disk", "utilities", "debian", "baobab", "org.gnome.baobab"),
    _c("syncthing", "Syncthing", "Sync folders between your devices", "selfhosted", "debian", "syncthing", "syncthing-ui", kind="service"),
    _c("openssh", "SSH server", "Log in to this computer from your network", "selfhosted", "debian", "openssh-server", kind="service"),
    _c("samba", "Samba", "Share folders with Windows PCs", "selfhosted", "debian", "samba", kind="service"),
    _c("cups", "Printing", "Printer support (CUPS)", "selfhosted", "debian", "cups", kind="service"),
    _c("docker", "Docker", "Run self-hosted apps in containers", "selfhosted", "debian", "docker.io", kind="service"),
    _c("nextcloud", "Nextcloud", "Sync with your Nextcloud", "selfhosted", "debian", "nextcloud-desktop", "com.nextcloud.desktopclient.nextcloud"),
)
CATALOG_BY_ID = {app.id: app for app in CATALOG}

# APVIS's own apps are pages of Home (real, built in, nothing to install).
BUILTIN: tuple[dict[str, str], ...] = (
    {"id": "apvis-monitor", "name": "APVIS Monitor", "summary": "System intelligence", "glyph": "chip", "action": "page:system"},
    {"id": "apvis-automations", "name": "APVIS Automations", "summary": "Workflow engine", "glyph": "gear", "action": "page:missions"},
    {"id": "apvis-memory", "name": "APVIS Memory", "summary": "Notes and your vault", "glyph": "memory", "action": "page:notes"},
    {"id": "apvis-atlas", "name": "APVIS Atlas", "summary": "Live world and flights", "glyph": "atlas", "action": "page:atlas"},
    {"id": "apvis-devices", "name": "APVIS Devices", "summary": "This computer and what's connected", "glyph": "device", "action": "page:devices"},
    {"id": "apvis-browser", "name": "APVIS Browser", "summary": "Private web browser with Ask APVIS", "glyph": "atlas", "action": "launch:browser"},
    {"id": "apvis-terminal", "name": "APVIS Terminal", "summary": "Terminal with the APVIS greeting", "glyph": "terminal", "action": "launch:terminal"},
    {"id": "apvis-api", "name": "APVIS API", "summary": "Local AI endpoint for your apps", "glyph": "brain", "action": "settings:ai"},
    {"id": "apvis-settings", "name": "APVIS Settings", "summary": "Appearance, AI and updates", "glyph": "settings", "action": "page:settings"},
)

_FREEDESKTOP = (("Office", "productivity"), ("Development", "development"), ("Graphics", "creativity"),
                ("AudioVideo", "media"), ("Audio", "media"), ("Video", "media"), ("Game", "media"),
                ("Network", "internet"), ("WebBrowser", "internet"), ("Utility", "utilities"),
                ("System", "utilities"), ("Settings", "utilities"))


def app_dirs(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    return [home / ".local/share/applications", home / ".local/share/flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"), Path("/usr/local/share/applications"),
            Path("/usr/share/applications")]


def icon_path(name: str, home: Path | None = None) -> str:
    """A file for a desktop entry's Icon= value; the bare name when only the icon theme can find it."""
    if not name:
        return ""
    if name.startswith("/"):
        return name if Path(name).is_file() else ""
    home = home or Path.home()
    roots = [home / ".local/share/icons", home / ".local/share/flatpak/exports/share/icons",
             Path("/var/lib/flatpak/exports/share/icons"), Path("/usr/share/icons")]
    for root in roots:
        for size in ("scalable", "256x256", "128x128", "96x96", "64x64", "48x48"):
            for ext in (".svg", ".png"):
                candidate = root / "hicolor" / size / "apps" / (name + ext)
                if candidate.is_file():
                    return str(candidate)
    for ext in (".svg", ".png", ".xpm"):
        candidate = Path("/usr/share/pixmaps") / (name + ext)
        if candidate.is_file():
            return str(candidate)
    return name


def _category(categories: str) -> str:
    found = set(filter(None, categories.split(";")))
    for key, ours in _FREEDESKTOP:
        if key in found:
            return ours
    return "utilities"


def find(name: str) -> CatalogApp | None:
    """The catalog app someone means by name ("vlc", "Visual Studio Code", "vs code", "firefox-esr")."""
    key = re.sub(r"[^a-z0-9+]", "", (name or "").lower())
    if not key:
        return None
    for app in CATALOG:
        names = {app.id, app.name, app.ref, app.ref.rsplit(".", 1)[-1]}
        if key in {re.sub(r"[^a-z0-9+]", "", n.lower()) for n in names}:
            return app
    aliases = {"vscode": "vscode", "code": "vscode", "office": "libreoffice", "word": "libreoffice", "chrome": "chromium",
               "obsstudio": "obs", "passwordmanager": "keepassxc", "photoshop": "gimp", "torrent": "transmission"}
    return CATALOG_BY_ID.get(aliases.get(key, ""))


def installed_apps(dirs: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    """Visible desktop entries on this computer; Exec is split into argv, never run through a shell."""
    seen: dict[str, dict[str, Any]] = {}
    for directory in dirs or app_dirs():
        for entry in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
            if entry.stem in seen:
                continue
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
                argv = [a for a in shlex.split(section.get("Exec", "")) if not re.fullmatch(r"%[a-zA-Z]", a)]
            except ValueError:
                continue
            name = section.get("Name", "").strip()
            if not argv or not name:
                continue
            seen[entry.stem] = {"id": entry.stem, "name": name, "summary": (section.get("GenericName") or section.get("Comment") or "").strip(),
                                "icon": icon_path(section.get("Icon", "").strip()), "category": _category(section.get("Categories", "")),
                                "terminal": section.get("Terminal", "false").lower() == "true", "argv": argv,
                                "wmclass": section.get("StartupWMClass", "").strip()}
    return sorted(seen.values(), key=lambda a: a["name"].lower())


def is_installed(app: CatalogApp, root: Path = Path("/")) -> bool:
    if app.source == "flathub":
        return (root / "var/lib/flatpak/app" / app.ref / "current").exists()
    info = root / "var/lib/dpkg/info"
    return (info / f"{app.ref}.list").exists() or (info / f"{app.ref}:amd64.list").exists()


def can_install() -> dict[str, bool]:
    return {"debian": HELPER.is_file() and Path("/usr/bin/pkexec").is_file(),
            "flathub": HELPER.is_file() and Path("/usr/bin/flatpak").is_file()}


def load_prefs(path: Path | None = None) -> dict[str, list[str]]:
    """Recently used and pinned store items (keys like "i:foot", "c:vlc", "b:apvis-monitor")."""
    try:
        data = json.loads((path or PREFS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    ok = lambda v: isinstance(v, str) and re.fullmatch(r"[icbm]:[\w.+:-]{1,120}", v)  # noqa: E731
    return {"recent": [k for k in data.get("recent", []) if ok(k)][:MAX_RECENT],
            "pinned": [k for k in data.get("pinned", []) if ok(k)][:MAX_PINNED]}


def _save_prefs(prefs: dict[str, list[str]], path: Path | None = None) -> dict[str, list[str]]:
    target = path or PREFS
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(prefs), encoding="utf-8")
    tmp.replace(target)
    return prefs


def note_use(key: str, path: Path | None = None) -> dict[str, list[str]]:
    if not re.fullmatch(r"[icbm]:[\w.+:-]{1,120}", key or ""):
        raise ValueError("not a store item")
    prefs = load_prefs(path)
    prefs["recent"] = [key, *(k for k in prefs["recent"] if k != key)][:MAX_RECENT]
    return _save_prefs(prefs, path)


def toggle_pin(key: str, path: Path | None = None) -> dict[str, list[str]]:
    if not re.fullmatch(r"[icbm]:[\w.+:-]{1,120}", key or ""):
        raise ValueError("not a store item")
    prefs = load_prefs(path)
    if key in prefs["pinned"]:
        prefs["pinned"].remove(key)
    elif len(prefs["pinned"]) >= MAX_PINNED:
        raise ValueError(f"Home has room for {MAX_PINNED} pinned apps. Unpin one first.")
    else:
        prefs["pinned"].append(key)
    return _save_prefs(prefs, path)


def state(installed: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    installed = installed if installed is not None else installed_apps()
    ids = {a["id"] for a in installed}
    catalog = []
    for app in CATALOG:
        item = asdict(app)
        item["installed"] = is_installed(app)
        item["openable"] = item["installed"] and app.desktop in ids
        catalog.append(item)
    return {"installed": [{k: v for k, v in a.items() if k != "argv"} for a in installed], "catalog": catalog,
            "builtin": list(BUILTIN), "canInstall": can_install(), "prefs": load_prefs()}


def launch(desktop_id: str, installed: list[dict[str, Any]] | None = None,
           popen: Callable[..., Any] = subprocess.Popen) -> str:
    """Open one installed app by its desktop entry id; returns its name."""
    for app in installed if installed is not None else installed_apps():
        if app["id"] == desktop_id:
            argv = list(app["argv"])
            if app.get("terminal"):
                argv = ["/usr/bin/foot", "--title=" + app["name"], "--", *argv]
            popen(argv, close_fds=True, start_new_session=True, stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return app["name"]
    raise ValueError("that app is not installed")


def parse_progress(line: str) -> tuple[int, str] | None:
    """apt's status lines (APT::Status-Fd) -> (percent, message): downloads fill 0-50 %, installing 50-100 %."""
    parts = line.strip().split(":", 3)
    if len(parts) < 4 or parts[0] not in {"dlstatus", "pmstatus"}:
        return None
    try:
        pct = float(parts[2])
    except ValueError:
        return None
    base = 0 if parts[0] == "dlstatus" else 50
    return max(0, min(100, int(base + pct / 2))), parts[3].strip()


def run_job(action: str, app_id: str, on_progress: Callable[[int, str], None],
            popen: Callable[..., Any] = subprocess.Popen) -> tuple[bool, str]:
    """Install or remove one catalog app through the root helper; returns (ok, message)."""
    app = CATALOG_BY_ID.get(app_id)
    if app is None or action not in {"install", "remove"}:
        return False, "That app isn't in the APVIS catalog."
    if not can_install()[app.source]:
        return False, ("Installing apps needs the APVIS OS dev.25 image or newer (the next USB image)."
                       if not HELPER.is_file() else "Flatpak isn't installed on this computer.")
    proc = popen(["/usr/bin/pkexec", str(HELPER), action, app.id], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 stdin=subprocess.DEVNULL, text=True, bufsize=1)
    tail: list[str] = []
    for line in proc.stdout:
        progress = parse_progress(line)
        if progress:
            on_progress(*progress)
        elif line.strip():
            tail = (tail + [line.strip()])[-4:]
            if line.startswith("APVIS:"):
                on_progress(-1, line[6:].strip())
    code = proc.wait()
    verb = "installed" if action == "install" else "removed"
    if code == 0:
        return True, f"{app.name} is {verb}."
    if code in (126, 127):
        return False, "The system refused the request (polkit)."
    return False, f"{app.name} wasn't {verb}: " + (tail[-1] if tail else f"exit code {code}")


def helper_main(argv: list[str], run: Callable[..., Any] = subprocess.run) -> int:
    """Body of the root helper: one catalog id, one action, nothing else."""
    if len(argv) != 2 or argv[0] not in {"install", "remove"} or argv[1] not in CATALOG_BY_ID:
        print("usage: apvis-apps install|remove <catalog id>")
        return 2
    action, app = argv[0], CATALOG_BY_ID[argv[1]]
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8"}
    if app.source == "debian":
        lists = Path("/var/lib/apt/lists")
        fresh = any(p.stat().st_mtime > time.time() - 86400 for p in lists.glob("*_Packages"))
        if action == "install" and not fresh:
            print("APVIS: Refreshing the package list…", flush=True)
            run(["apt-get", "update", "-q"], env=env, check=False)
        verb = ["install", "-y", "-q"] if action == "install" else ["remove", "-y", "-q"]
        return run(["apt-get", *verb, "-o", "APT::Status-Fd=1", "-o", "Dpkg::Use-Pty=0", app.ref], env=env, check=False).returncode
    if action == "install":
        print("APVIS: Connecting to Flathub…", flush=True)
        run(["flatpak", "remote-add", "--system", "--if-not-exists", "flathub", FLATHUB], env=env, check=False)
        print(f"APVIS: Downloading {app.name} from Flathub (this can take a few minutes)…", flush=True)
        return run(["flatpak", "install", "--system", "-y", "--noninteractive", "flathub", app.ref], env=env, check=False).returncode
    return run(["flatpak", "uninstall", "--system", "-y", "--noninteractive", app.ref], env=env, check=False).returncode
