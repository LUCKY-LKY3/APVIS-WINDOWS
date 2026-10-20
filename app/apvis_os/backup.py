"""Backup & restore of the owner's APVIS data (Settings -> Backup).

What is saved: the APVIS Vault (notes and memories), Home's look and settings, Ask's settings and
chat history, reminders, missions, the Apps Store's pins and recents, and the browser's history
(not its cookies). One .tar.gz file per backup, written to a USB drive or the home Backups folder.
Restoring first saves the current data (so a restore can be undone), then only writes files
inside the same known places; anything else in the archive is refused.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

HOME_ITEMS = ("APVIS Vault", ".config/apvis", ".local/state/apvis-os", ".local/share/apvis-os/browser/history.json")
STATE_SKIP = {"ai-setup.json", "ai-setup.request", "aviation", "cache", "osint"}
MAX_FILE = 50 * 1024 ** 2
PREFIX = "APVIS-Backup-"


def state_dir() -> Path:
    return Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))


def _files(home: Path, state: Path) -> list[tuple[Path, str]]:
    """(file on disk, name in the archive) for everything a backup holds."""
    out: list[tuple[Path, str]] = []

    def add_tree(base: Path, rel: str, prefix: str, skip: frozenset[str] | set[str] = frozenset()) -> None:
        path = base / rel if rel else base
        if path.is_file() and not path.is_symlink():
            if path.stat().st_size <= MAX_FILE:
                out.append((path, f"{prefix}/{rel}" if rel else prefix))
            return
        if not path.is_dir():
            return
        for top, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in skip and not os.path.islink(os.path.join(top, d))]
            for name in files:
                full = Path(top, name)
                if name in skip or full.is_symlink():
                    continue
                try:
                    if full.stat().st_size > MAX_FILE:
                        continue
                except OSError:
                    continue
                out.append((full, f"{prefix}/{full.relative_to(base).as_posix()}"))

    for item in HOME_ITEMS:
        add_tree(home, item, "home")
    if state.is_dir():
        for child in sorted(state.iterdir()):
            if child.name in STATE_SKIP or child.is_symlink():
                continue
            add_tree(state, child.name, "state", STATE_SKIP)
    return out


def create(target: Path, *, home: Path | None = None, state: Path | None = None, product: str = "",
           clock: Callable[[], float] = time.time) -> Path:
    """Write one backup into target/APVIS-Backups/; returns its path."""
    home, state = home or Path.home(), state or state_dir()
    files = _files(home, state)
    if not files:
        raise ValueError("There is nothing to back up yet.")
    folder = target / "APVIS-Backups"
    folder.mkdir(parents=True, exist_ok=True)
    size = sum(p.stat().st_size for p, _ in files)
    if shutil.disk_usage(folder).free < size * 1.2 + 10 * 1024 ** 2:
        raise OSError("There isn't enough free space on that drive.")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    final = folder / f"{PREFIX}{socket.gethostname()}-{stamp}.tar.gz"
    manifest = {"created": clock(), "product": product, "host": socket.gethostname(), "files": len(files), "bytes": size}
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".backup-", suffix=".part")
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            data = json.dumps(manifest, indent=1).encode("utf-8")
            info = tarfile.TarInfo("manifest.json")
            info.size, info.mtime = len(data), int(clock())
            tar.addfile(info, io.BytesIO(data))
            for path, name in files:
                tar.add(path, arcname=name, recursive=False)
        os.replace(tmp, final)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return final


def _allowed(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or ".." in parts:
        return False
    if parts[0] == "manifest.json" and len(parts) == 1:
        return True
    if parts[0] == "state":
        return len(parts) >= 2 and parts[1] not in STATE_SKIP
    if parts[0] == "home":
        rel = "/".join(parts[1:])
        return any(rel == item or rel.startswith(item + "/") for item in HOME_ITEMS)
    return False


def read_manifest(archive: Path) -> dict[str, Any]:
    with tarfile.open(archive, "r:gz") as tar:
        try:
            member = tar.getmember("manifest.json")
        except KeyError:
            raise ValueError("That file isn't an APVIS backup.") from None
        handle = tar.extractfile(member)
        return json.loads(handle.read().decode("utf-8")) if handle else {}


def restore(archive: Path, *, home: Path | None = None, state: Path | None = None, safety: Path | None = None) -> dict[str, Any]:
    """Put a backup back. The current data is saved first (safety backup); only known places are written."""
    home, state = home or Path.home(), state or state_dir()
    manifest = read_manifest(archive)
    safety_path = None
    try:
        safety_path = create(safety or home / ".local/share/apvis-os/backups", home=home, state=state, product="before restore")
    except ValueError:
        pass                                  # nothing there yet: nothing to save
    written = 0
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "manifest.json":
                continue
            if not member.isfile() or not _allowed(member.name):
                raise ValueError(f"The backup contains something APVIS won't restore: {member.name}")
            parts = PurePosixPath(member.name).parts
            dest = (home if parts[0] == "home" else state).joinpath(*parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            tmp = dest.with_name(dest.name + ".restoring")
            with open(tmp, "wb") as out:
                shutil.copyfileobj(source, out)
            os.replace(tmp, dest)
            written += 1
    return {"restored": written, "from": manifest.get("host", ""), "created": manifest.get("created"),
            "safety": str(safety_path) if safety_path else ""}


def targets(home: Path | None = None, mounts: Path = Path("/proc/mounts")) -> list[dict[str, Any]]:
    """Where a backup can go: plugged-in drives (/media, /run/media) and the home Backups folder."""
    home = home or Path.home()
    found: list[dict[str, Any]] = []
    try:
        lines = mounts.read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        point = fields[1].replace("\\040", " ")
        if point.startswith(("/media/", "/run/media/")) and os.access(point, os.W_OK):
            try:
                usage = shutil.disk_usage(point)
            except OSError:
                continue
            found.append({"path": point, "label": Path(point).name, "kind": "drive", "free": usage.free})
    backups = home / "Backups"
    try:
        free = shutil.disk_usage(home).free
    except OSError:
        free = 0
    found.append({"path": str(backups), "label": "Home ▸ Backups (this disk)", "kind": "home", "free": free})
    return found


def existing(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Backups already on those drives, newest first."""
    out = []
    for place in places:
        root = Path(place["path"])
        for folder in (root / "APVIS-Backups", root):
            for path in folder.glob(PREFIX + "*.tar.gz") if folder.is_dir() else []:
                try:
                    stat = path.stat()
                except OSError:
                    continue
                out.append({"path": str(path), "name": path.name, "size": stat.st_size, "time": stat.st_mtime, "where": place["label"]})
    seen, unique = set(), []
    for item in sorted(out, key=lambda i: -i["time"]):
        if item["path"] not in seen:
            seen.add(item["path"])
            unique.append(item)
    return unique[:12]
