"""APVIS layer updates (V2-20): check, verify, stage, switch, roll back.

An update bundle replaces only the APVIS layer (the QML UI and the apvis_os
Python package) without a new ISO. Bundles come from the owner's public
release channel and are trusted only if their ed25519 signature verifies
against the key shipped in the image, and every file matches the manifest.
Updates install next to the image (the image is never modified); the file
`current` names the active one, the previous one is kept, and the launcher rolls
back automatically if an updated Home fails to start.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

# Public, files-only channel: latest.json names the newest signed bundle.
CHANNEL = "https://raw.githubusercontent.com/LUCKY-LKY3/apvis-updates/main/"
RELEASES_URL = CHANNEL + "latest.json"
SOURCE_NAME = "APVIS updates (github.com/LUCKY-LKY3/apvis-updates, signed)"
PUBLIC_KEY = Path("/usr/share/apvis-os/update.pub")
BASE_RELEASE = Path("/usr/share/apvis-os/release")
SIGNIFY = "/usr/bin/signify-openbsd"
USER_AGENT = "APVIS-OS/2.0 (+owner desktop update check)"
KEEP = 2                          # installed versions kept besides the image
RESTART_EXIT_CODE = 75            # Home exits with this to be restarted by the launcher

Fetch = Callable[[str], bytes]
Verify = Callable[[Path, Path], None]


class UpdateError(RuntimeError):
    """Refused or failed; the message is shown to the owner as is."""


def version_key(version: str) -> tuple[int, ...]:
    """Comparable key; words are ignored. A final release sorts above its own pre-releases (V3 M1):
    '3.0.0-dev.5' -> (3, 0, 0, 0, 5) and '3.0.0' -> (3, 0, 0, 1), so 3.0.0 > 3.0.0-dev.5 > 2.0.0-dev.28.1.
    The first three numbers are the release; anything after a '-' marks a pre-release."""
    text = (version or "").strip()
    if not re.search(r"\d", text):
        return ()
    release, dash, rest = text.partition("-")
    main = [int(n) for n in re.findall(r"\d+", release)]
    if len(main) > 3:                       # '2.0.0.1' style: extra numbers count as a final release's parts
        main, extra = main[:3], main[3:]
    else:
        extra = []
    main += [0] * (3 - len(main))
    if dash:
        return (*main, 0, *extra, *(int(n) for n in re.findall(r"\d+", rest)))
    return (*main, 1, *extra)


def root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".local/share/apvis-os/updates"


def base_version(release: Path = BASE_RELEASE) -> str:
    try:
        for line in release.read_text(encoding="utf-8").splitlines():
            if line.startswith("product_version="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "0"


def _manifest(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


def current(home: Path | None = None) -> dict[str, Any] | None:
    """The active update, or None when running the image's own APVIS layer."""
    try:
        name = (root(home) / "current").read_text(encoding="utf-8").strip()
        folder = root(home) / name
        if not name or "/" in name or "\\" in name or not folder.is_dir():
            return None
        return {"version": _manifest(folder)["version"], "path": str(folder)}
    except (OSError, ValueError, KeyError):
        return None


def installed_version(home: Path | None = None, release: Path = BASE_RELEASE) -> str:
    active = current(home)
    return active["version"] if active else base_version(release)


def history(home: Path | None = None) -> list[dict[str, Any]]:
    try:
        return json.loads((root(home) / "history.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _record(home: Path | None, event: str, version: str, detail: str = "") -> None:
    rows = history(home)[-49:] + [{"event": event, "version": version, "detail": detail,
                                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}]
    path = root(home) / "history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".history.tmp")
    tmp.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def check(fetch: Fetch = _fetch, home: Path | None = None, release: Path = BASE_RELEASE) -> dict[str, Any]:
    """Read-only: is a newer signed bundle published?"""
    installed = installed_version(home, release)
    try:
        info = json.loads(fetch(RELEASES_URL).decode("utf-8"))
        latest = str(info.get("version", "")).lstrip("v")
        name = str(info.get("bundle", ""))
        if "/" in name or "\\" in name:
            raise ValueError("bad bundle name")
        assets = {name: CHANNEL + name, name + ".sig": CHANNEL + name + ".sig"} if name else {}
    except Exception as exc:  # network, HTTP, JSON: all mean "couldn't check"
        return {"status": "error", "installed": installed, "message": f"Couldn't check: {_plain(exc)}"}
    bundle = next((n for n in assets if n.endswith(".tar.xz")), None)
    if not latest or bundle is None or f"{bundle}.sig" not in assets:
        return {"status": "error", "installed": installed, "message": "Couldn't check: the release has no signed bundle"}
    if version_key(latest) <= version_key(installed):
        return {"status": "current", "installed": installed, "latest": latest, "message": f"Up to date ({installed})"}
    return {"status": "available", "installed": installed, "latest": latest, "notes": str(info.get("notes") or "")[:600],
            "bundle": assets[bundle], "signature": assets[f"{bundle}.sig"], "message": f"{latest} is available"}


def _plain(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code == 404:
        return "no updates have been published yet"
    if isinstance(code, int):
        return f"the update server returned HTTP {code}"
    text = str(getattr(exc, "reason", "") or exc).lower()
    if "name resolution" in text or "getaddrinfo" in text:
        return "no internet connection"
    if "timed out" in text:
        return "the update server did not answer in time"
    return "the update server could not be reached"


def signify_verify(bundle: Path, signature: Path, public_key: Path = PUBLIC_KEY) -> None:
    if not Path(SIGNIFY).is_file() or not public_key.is_file():
        raise UpdateError("Update refused: the signature checker or APVIS update key is missing")
    done = subprocess.run([SIGNIFY, "-V", "-q", "-p", str(public_key), "-x", str(signature), "-m", str(bundle)],
                          capture_output=True, text=True, timeout=30, check=False)
    if done.returncode != 0:
        raise UpdateError("Update refused: the signature does not match (the download may be damaged or not from APVIS)")


def _safe_extract(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:xz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not target.is_relative_to(dest.resolve()) or member.issym() or member.islnk() or member.isdev():
                raise UpdateError(f"Update refused: unsafe entry {member.name!r} in the bundle")
        tar.extractall(dest, filter="data")


def _check_manifest(folder: Path, installed: str, base: str) -> dict[str, Any]:
    try:
        manifest = _manifest(folder)
        files: dict[str, str] = manifest["files"]
        version = str(manifest["version"])
    except (OSError, ValueError, KeyError, TypeError):
        raise UpdateError("Update refused: the bundle has no readable manifest") from None
    if version_key(version) <= version_key(installed):
        raise UpdateError(f"Update refused: {version} is not newer than {installed}")
    if version_key(str(manifest.get("min_base", "0"))) > version_key(base):
        raise UpdateError(f"Update refused: it needs APVIS OS {manifest['min_base']} or newer; this image is {base}")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {"manifest.json"}
    if present != set(files):
        raise UpdateError("Update refused: the bundle's files do not match its manifest")
    for rel, digest in files.items():
        if hashlib.sha256((folder / rel).read_bytes()).hexdigest() != digest:
            raise UpdateError(f"Update refused: {rel} is damaged (checksum mismatch)")
    if not (folder / "share/qml/Home.qml").is_file() or not (folder / "python/apvis_os/__init__.py").is_file():
        raise UpdateError("Update refused: the bundle is incomplete")
    return manifest


def _switch(home: Path | None, folder: Path | None) -> None:
    """Name folder as the active update (None = back to the image), atomically."""
    pointer = root(home) / "current"
    if folder is None:
        pointer.unlink(missing_ok=True)
        return
    tmp = pointer.with_name(".current.tmp")
    tmp.write_text(folder.name, encoding="utf-8")
    os.replace(tmp, pointer)


def install(offer: dict[str, Any], fetch: Fetch = _fetch, verify: Verify = signify_verify,
            home: Path | None = None, release: Path = BASE_RELEASE) -> dict[str, Any]:
    """Download, verify, stage and switch. Nothing changes unless every check passes."""
    if offer.get("status") in {"current", "error"} or not offer.get("bundle") or not offer.get("signature"):
        raise UpdateError(offer.get("message") or "There is no newer update to install.")
    installed, base = installed_version(home, release), base_version(release)
    base_dir = root(home)
    base_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base_dir, prefix=".download-") as tmp:
        work = Path(tmp)
        bundle, signature = work / "bundle.tar.xz", work / "bundle.tar.xz.sig"
        try:
            bundle.write_bytes(fetch(offer["bundle"]))
            signature.write_bytes(fetch(offer["signature"]))
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"Download failed: {_plain(exc)}") from None
        verify(bundle, signature)
        staged = work / "staged"
        staged.mkdir()
        _safe_extract(bundle, staged)
        manifest = _check_manifest(staged, installed, base)
        from . import sysupdate
        try:
            if sysupdate.needed(manifest):                  # system packages first; nothing switches if they fail
                sysupdate.apply(bundle, signature)
        except (ValueError, RuntimeError, OSError) as exc:
            raise UpdateError(f"Update refused: {exc}") from None
        final = base_dir / manifest["version"]
        if final.exists():
            shutil.rmtree(final)
        shutil.move(str(staged), final)
    previous = current(home)
    _switch(home, final)
    _record(home, "installed", manifest["version"], f"from {previous['version'] if previous else base}")
    _prune(home)
    return {"ok": True, "version": manifest["version"], "message": f"Installed {manifest['version']}. APVIS Home restarts to use it."}


def _prune(home: Path | None) -> None:
    active = current(home)
    folders = sorted((p for p in root(home).iterdir() if p.is_dir() and not p.name.startswith(".")),
                     key=lambda p: version_key(p.name), reverse=True)
    keep = {Path(active["path"]).name} if active else set()
    for folder in folders:
        if folder.name not in keep and len(keep) < KEEP + (1 if active else 0):
            keep.add(folder.name)
    for folder in folders:
        if folder.name not in keep:
            shutil.rmtree(folder, ignore_errors=True)


def rollback(reason: str = "rolled back by the owner", home: Path | None = None,
             release: Path = BASE_RELEASE) -> dict[str, Any]:
    """Go back to the previous installed update, or to the image's own APVIS layer."""
    active = current(home)
    if active is None:
        return {"ok": False, "message": "Already running the APVIS layer that came with this image"}
    older = sorted((p for p in root(home).iterdir() if p.is_dir() and not p.name.startswith(".")
                    and version_key(p.name) < version_key(active["version"])),
                   key=lambda p: version_key(p.name), reverse=True)
    target = older[0] if older else None
    _switch(home, target)
    now = target.name if target else base_version(release)
    _record(home, "rolled back", active["version"], f"{reason}; now {now}")
    return {"ok": True, "version": now, "message": f"Rolled back from {active['version']} to {now}: {reason}"}


def status(home: Path | None = None, release: Path = BASE_RELEASE) -> dict[str, Any]:
    active = current(home)
    return {"installed": installed_version(home, release), "base": base_version(release),
            "fromUpdate": active is not None, "source": SOURCE_NAME, "history": history(home)[-8:][::-1]}


def main(argv: list[str] | None = None) -> int:
    """Launcher hook: `python3 -m apvis_os.updates rollback REASON` (runs from the image's package)."""
    import sys
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["rollback"]:
        result = rollback(" ".join(args[1:]) or "APVIS Home failed to start after the update")
        print(result["message"])
        return 0 if result["ok"] else 1
    if args[:1] == ["status"]:
        print(json.dumps(status(), indent=1))
        return 0
    print("usage: python3 -m apvis_os.updates rollback REASON | status")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
