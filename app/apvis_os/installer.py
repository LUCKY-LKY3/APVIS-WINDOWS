"""Install APVIS OS from the live system onto a whole disk (V2-14).

Runs as root through /usr/local/lib/apvis-os/apvis-install (pkexec, live
session only). The owner picks the disk and must type its name; the live
medium and removable disks are never offered. Before the disk is erased, an
existing Ollama install on it (binary, libraries and models) is copied to RAM
and restored afterwards so Ask keeps working. Every step is checked and the
result is verified before success is reported. Progress is printed as JSON
lines for the Home installer page.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

LIVE_MEDIUM = Path("/run/live/medium")
SQUASHFS = LIVE_MEDIUM / "live/filesystem.squashfs"
TARGET = Path("/mnt/apvis-target")
BACKUP = Path("/mnt/apvis-ollama-backup")
MIN_DISK_BYTES = 16 * 1024 ** 3
LIVE_PACKAGES = ("live-boot", "live-boot-initramfs-tools", "live-config", "live-config-systemd", "live-tools")
OLLAMA_MODEL_DIRS = ("usr/share/ollama/.ollama/models", "var/lib/ollama/.ollama/models", "root/.ollama/models")
INSTALL_POLKIT_RULE = "etc/polkit-1/rules.d/60-apvis-install.rules"
RAM_HEADROOM = int(1.5 * 1024 ** 3)
# V4 login screen: the live USB autologins (etc/greetd/config.toml in the image); an installed system shows
# the APVIS login screen at every boot. Debian's greetd runs its greeter as "_greetd"; other names are
# accepted in case the packaging changes.
GREETER_USERS = ("_greetd", "greeter", "greetd")
GREETER_SESSION = "/usr/local/lib/apvis-os/apvis-greeter-session"

Run = Callable[..., subprocess.CompletedProcess]


class InstallError(RuntimeError):
    """A step failed; the message says which, in plain words."""


def emit(step: str, pct: int, message: str, **extra: Any) -> None:
    print(json.dumps({"step": step, "pct": pct, "message": message, **extra}), flush=True)


def run(argv: list[str], *, input_text: str | None = None, check: bool = True, timeout: float = 1800) -> subprocess.CompletedProcess:
    done = subprocess.run(argv, input=input_text, capture_output=True, text=True, timeout=timeout, check=False)
    if check and done.returncode != 0:
        tail = (done.stderr or done.stdout).strip().splitlines()
        raise InstallError(f"{Path(argv[0]).name} failed: {tail[-1] if tail else 'exit ' + str(done.returncode)}")
    return done


# ---------------------------------------------------------------- disks

def live_disk(run_: Run = run) -> str | None:
    """The disk the live system booted from (never offered as a target)."""
    try:
        source = run_(["findmnt", "-no", "SOURCE", str(LIVE_MEDIUM)], check=False).stdout.strip()
        if not source:
            return None
        parent = run_(["lsblk", "-no", "PKNAME", source], check=False).stdout.strip()
        return "/dev/" + (parent or Path(source).name)
    except (OSError, subprocess.SubprocessError):
        return None


def candidate_disks(lsblk: dict[str, Any], live: str | None) -> list[dict[str, Any]]:
    """Internal, writable, big-enough disks, excluding the live medium and USB/removable ones."""
    found = []
    for dev in lsblk.get("blockdevices", []):
        path = dev.get("path") or "/dev/" + dev.get("name", "")
        if dev.get("type") != "disk" or path == live or dev.get("ro") in (True, "1"):
            continue
        if dev.get("rm") in (True, "1") or (dev.get("tran") or "") == "usb":
            continue
        if re.match(r"^/dev/(loop|zram|sr|ram)", path):
            continue
        size = int(dev.get("size") or 0)
        if size < MIN_DISK_BYTES:
            continue
        parts = [{"path": c.get("path"), "fstype": c.get("fstype") or "", "label": c.get("label") or "",
                  "size": int(c.get("size") or 0)} for c in dev.get("children", []) or []]
        found.append({"path": path, "name": Path(path).name, "model": (dev.get("model") or "").strip() or "Disk",
                      "size": size, "partitions": parts})
    return found


def list_disks(run_: Run = run) -> list[dict[str, Any]]:
    out = run_(["lsblk", "-J", "-b", "-o", "NAME,PATH,SIZE,MODEL,TYPE,RM,RO,TRAN,FSTYPE,LABEL"]).stdout
    return candidate_disks(json.loads(out), live_disk(run_))


def partition_path(disk: str, number: int) -> str:
    """/dev/sda + 3 -> /dev/sda3; /dev/nvme0n1 + 3 -> /dev/nvme0n1p3."""
    return f"{disk}p{number}" if re.search(r"\d$", disk) else f"{disk}{number}"


# ---------------------------------------------------------------- Ollama

def find_ollama(root: Path) -> dict[str, Any] | None:
    """An Ollama install inside a mounted root filesystem, with sizes."""
    models = next((root / d for d in OLLAMA_MODEL_DIRS if (root / d / "manifests").is_dir()), None)
    if models is None:
        homes = root / "home"
        if homes.is_dir():
            models = next((h / ".ollama/models" for h in sorted(homes.iterdir())
                           if (h / ".ollama/models/manifests").is_dir()), None)
    if models is None:
        return None
    size = sum(f.stat().st_size for f in models.rglob("*") if f.is_file())
    names = sorted({"/".join(p.relative_to(models / "manifests").parts[-2:]).replace("/", ":")
                    for p in (models / "manifests").rglob("*") if p.is_file()})
    binary = root / "usr/local/bin/ollama"
    libs = root / "usr/local/lib/ollama"
    lib_size = sum(f.stat().st_size for f in libs.rglob("*") if f.is_file()) if libs.is_dir() else 0
    return {"models_dir": str(models), "models_bytes": size, "models": names,
            "binary": str(binary) if binary.is_file() else "", "libs": str(libs) if libs.is_dir() else "",
            "total_bytes": size + lib_size + (binary.stat().st_size if binary.is_file() else 0)}


def ram_available(meminfo: str | None = None) -> int:
    text = meminfo if meminfo is not None else Path("/proc/meminfo").read_text()
    m = re.search(r"^MemAvailable:\s+(\d+) kB", text, re.M)
    return int(m.group(1)) * 1024 if m else 0


def backup_fits(total_bytes: int, meminfo: str | None = None) -> bool:
    return total_bytes + RAM_HEADROOM <= ram_available(meminfo)


def linux_partitions(lsblk: dict[str, Any]) -> list[dict[str, Any]]:
    """Partitions with a Linux filesystem, whether lsblk printed a tree or a flat list."""
    found, stack = [], list(lsblk.get("blockdevices", []))
    while stack:
        dev = stack.pop(0)
        stack.extend(dev.get("children", []) or [])
        if dev.get("fstype") in {"ext4", "ext3", "xfs", "btrfs"} and dev.get("path"):
            found.append(dev)
    return found


def scan_ollama(disk: str, run_: Run = run) -> dict[str, Any]:
    """Look for Ollama on each Linux partition of the disk (mounted read-only)."""
    probe = Path("/mnt/apvis-probe")
    probe.mkdir(parents=True, exist_ok=True)
    lsblk = json.loads(run_(["lsblk", "-J", "-b", "-o", "NAME,PATH,FSTYPE", disk]).stdout)
    for part in linux_partitions(lsblk):
        if run_(["mount", "-o", "ro", part["path"], str(probe)], check=False).returncode != 0:
            continue
        try:
            found = find_ollama(probe)
            if found:
                return {**found, "partition": part["path"], "fits": backup_fits(found["total_bytes"])}
        finally:
            run_(["umount", str(probe)], check=False)
    return {}


def backup_ollama(info: dict[str, Any], run_: Run = run) -> Path:
    """Copy the Ollama binary, libraries and models into a RAM disk."""
    BACKUP.mkdir(parents=True, exist_ok=True)
    size_mb = (info["total_bytes"] + 256 * 1024 ** 2) // (1024 ** 2) + 1
    run_(["mount", "-t", "tmpfs", "-o", f"size={size_mb}m,mode=0700", "tmpfs", str(BACKUP)])
    probe = Path("/mnt/apvis-probe")
    run_(["mount", "-o", "ro", info["partition"], str(probe)])
    try:
        rel = lambda p: Path(p).relative_to(probe) if p else None
        run_(["cp", "-a", str(probe / rel(info["models_dir"])), str(BACKUP / "models")])
        if info.get("binary"):
            run_(["cp", "-a", str(probe / rel(info["binary"])), str(BACKUP / "ollama")])
        if info.get("libs"):
            run_(["cp", "-a", str(probe / rel(info["libs"])), str(BACKUP / "lib")])
    finally:
        run_(["umount", str(probe)], check=False)
    return BACKUP


OLLAMA_SERVICE = """[Unit]
Description=Ollama (local AI for APVIS Ask; restored by the APVIS installer)
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=127.0.0.1:11434"

[Install]
WantedBy=multi-user.target
"""


def restore_ollama(target: Path, run_: Run = run) -> int:
    """Put the backed-up Ollama into the new system; returns the number of models restored."""
    models = target / "usr/share/ollama/.ollama/models"
    models.parent.mkdir(parents=True, exist_ok=True)
    run_(["cp", "-a", str(BACKUP / "models"), str(models)])
    if (BACKUP / "ollama").is_file():
        (target / "usr/local/bin").mkdir(parents=True, exist_ok=True)
        run_(["cp", "-a", str(BACKUP / "ollama"), str(target / "usr/local/bin/ollama")])
    if (BACKUP / "lib").is_dir():
        run_(["cp", "-a", str(BACKUP / "lib"), str(target / "usr/local/lib/ollama")])
    chroot(target, ["sh", "-c", "getent passwd ollama >/dev/null || useradd -r -s /bin/false -U -m -d /usr/share/ollama ollama"], run_)
    chroot(target, ["chown", "-R", "ollama:ollama", "/usr/share/ollama"], run_)
    (target / "etc/systemd/system/ollama.service").write_text(OLLAMA_SERVICE)
    if (target / "usr/local/bin/ollama").is_file():
        chroot(target, ["systemctl", "enable", "ollama.service"], run_)
    return sum(1 for p in (models / "manifests").rglob("*") if p.is_file())


# ---------------------------------------------------------------- system

def chroot(target: Path, argv: list[str], run_: Run = run, input_text: str | None = None) -> subprocess.CompletedProcess:
    return run_(["chroot", str(target)] + argv, input_text=input_text)


def fstab(root_uuid: str, efi_uuid: str) -> str:
    return ("# APVIS OS (written by the installer)\n"
            f"UUID={root_uuid}  /          ext4  errors=remount-ro  0  1\n"
            f"UUID={efi_uuid}  /boot/efi  vfat  umask=0077         0  1\n")


GRUB_DEFAULT = """# APVIS OS boot menu (written by the installer)
GRUB_DEFAULT=0
GRUB_TIMEOUT=2
GRUB_TIMEOUT_STYLE=menu
GRUB_DISTRIBUTOR="APVIS OS"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX=""
GRUB_GFXMODE=1920x1080,1600x900,1280x720,auto
GRUB_GFXPAYLOAD_LINUX=keep
GRUB_THEME=/boot/grub/themes/apvis/theme.txt
GRUB_DISABLE_OS_PROBER=true
"""


def uuid_of(device: str, run_: Run = run) -> str:
    return run_(["blkid", "-s", "UUID", "-o", "value", device]).stdout.strip()


def greeter_user(passwd_text: str) -> str | None:
    """greetd's greeter account, read from the new system's /etc/passwd."""
    names = {line.split(":", 1)[0] for line in passwd_text.splitlines() if line.strip() and not line.startswith("#")}
    return next((name for name in GREETER_USERS if name in names), None)


def greetd_config(user: str) -> str:
    """No initial_session (no autologin): greetd starts the login screen on vt1 at every boot. The command
    runs the APVIS greeter in cage and falls back to the text login (agreety) if it can't start."""
    lines = ["# APVIS OS login screen (written by the installer). The live USB keeps autologin; an installed",
             "# system asks at every boot. If the login screen fails to start, the text login takes over, and",
             "# Ctrl+Alt+F2 always offers a text console.",
             "[terminal]",
             "vt = 1",
             "",
             "[default_session]",
             f'command = "{GREETER_SESSION}"',
             f'user = "{user}"']
    return chr(10).join(lines) + chr(10)


def configure_login(target: Path, run_: Run = run) -> str:
    """Show the login screen at every boot of the installed system (APVIS and Guest accounts)."""
    passwd = target / "etc/passwd"
    user = greeter_user(passwd.read_text(encoding="utf-8", errors="replace") if passwd.is_file() else "")
    if user is None:
        chroot(target, ["useradd", "--system", "--user-group", "--home-dir", "/var/lib/greetd", "--no-create-home",
                        "--shell", "/usr/sbin/nologin", "_greetd"], run_)
        chroot(target, ["usermod", "-aG", "video", "_greetd"], run_)
        user = "_greetd"
    config = target / "etc/greetd/config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(greetd_config(user), encoding="utf-8")
    return user


def request_ai_setup(target: Path, run_: Run = run) -> None:
    """First start: install Ollama and the recommended models (apvis_os.aisetup)."""
    state = target / "var/lib/apvis-os"
    state.mkdir(parents=True, exist_ok=True)
    (state / "ai-setup.request").write_text("requested by the installer" + chr(10))
    chroot(target, ["systemctl", "enable", "apvis-ai-setup.service"], run_)


def install(disk: str, password: str, *, restore_models: bool, setup_ai: bool = False, run_: Run = run) -> dict[str, Any]:
    if disk not in {d["path"] for d in list_disks(run_)}:
        raise InstallError(f"{disk} is not an allowed install target")
    if len(password) < 6:
        raise InstallError("the password must be at least 6 characters")
    if not SQUASHFS.is_file():
        raise InstallError("this is not running from the APVIS OS live media")
    models_restored = 0
    backed_up = False
    if restore_models:
        emit("backup", 3, "Looking for your Ollama models…")
        info = scan_ollama(disk, run_)
        if info and info.get("fits"):
            emit("backup", 5, f"Copying {len(info['models'])} Ollama models to memory ({info['total_bytes'] // 1024 ** 2} MB)…")
            backup_ollama(info, run_)
            backed_up = True
        elif info:
            raise InstallError("your Ollama models don't fit in memory for the backup; free RAM or install without them")
    emit("partition", 10, f"Erasing {disk} and creating partitions…")
    run_(["wipefs", "-a", disk])
    run_(["sgdisk", "--zap-all", disk])
    run_(["sgdisk", "-n1:0:+1M", "-t1:ef02", "-c1:BIOS", "-n2:0:+512M", "-t2:ef00", "-c2:EFI",
          "-n3:0:0", "-t3:8300", "-c3:APVIS", disk])
    run_(["partprobe", disk], check=False)
    run_(["udevadm", "settle"], check=False)
    efi, root = partition_path(disk, 2), partition_path(disk, 3)
    emit("format", 14, "Formatting…")
    run_(["mkfs.vfat", "-F", "32", "-n", "EFI", efi])
    run_(["mkfs.ext4", "-F", "-q", "-L", "APVIS", root])
    TARGET.mkdir(parents=True, exist_ok=True)
    run_(["mount", root, str(TARGET)])
    mounted = [str(TARGET)]
    try:
        (TARGET / "boot/efi").mkdir(parents=True, exist_ok=True)
        run_(["mount", efi, str(TARGET / "boot/efi")])
        mounted.append(str(TARGET / "boot/efi"))
        emit("copy", 18, "Copying APVIS OS to the disk…")
        copy_system(TARGET)
        for fs in ("dev", "proc", "sys", "run"):
            run_(["mount", "--bind", f"/{fs}", str(TARGET / fs)])
            mounted.append(str(TARGET / fs))
        if Path("/sys/firmware/efi/efivars").is_dir():
            run_(["mount", "--bind", "/sys/firmware/efi/efivars", str(TARGET / "sys/firmware/efi/efivars")], check=False)
            mounted.append(str(TARGET / "sys/firmware/efi/efivars"))
        emit("configure", 72, "Setting up the new system…")
        (TARGET / "etc/fstab").write_text(fstab(uuid_of(root, run_), uuid_of(efi, run_)))
        (TARGET / "etc/hostname").write_text("apvis\n")
        (TARGET / "etc/hosts").write_text("127.0.0.1 localhost\n127.0.1.1 apvis\n::1 localhost ip6-localhost ip6-loopback\n")
        kernel_from_medium(TARGET)
        chroot(TARGET, ["apt-get", "purge", "-y", "-q"] + [p for p in LIVE_PACKAGES if package_installed(TARGET, p)], run_)
        (TARGET / INSTALL_POLKIT_RULE).unlink(missing_ok=True)          # the installer only runs from live media
        chroot(TARGET, ["chpasswd"], run_, input_text=f"apvis:{password}\n")
        chroot(TARGET, ["usermod", "-aG", "sudo", "apvis"], run_)
        configure_login(TARGET, run_)                                  # V4: the login screen at every boot
        emit("configure", 78, "Building the start-up image…")
        chroot(TARGET, ["sh", "-c", "update-initramfs -u -k all || update-initramfs -c -k all"], run_)
        emit("bootloader", 86, "Installing the boot menu…")
        theme = TARGET / "boot/grub/themes/apvis"
        theme.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(LIVE_MEDIUM / "boot/grub/apvis-theme", theme, dirs_exist_ok=True)
        (TARGET / "etc/default").mkdir(parents=True, exist_ok=True)
        (TARGET / "etc/default/grub").write_text(GRUB_DEFAULT)
        chroot(TARGET, ["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--bootloader-id=APVIS", "--recheck"], run_)
        chroot(TARGET, ["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--removable", "--no-nvram"], run_)
        chroot(TARGET, ["grub-install", "--target=i386-pc", disk], run_)
        chroot(TARGET, ["grub-mkconfig", "-o", "/boot/grub/grub.cfg"], run_)
        if backed_up:
            emit("ollama", 92, "Restoring your Ollama models…")
            models_restored = restore_ollama(TARGET, run_)
        ai_requested = setup_ai and not models_restored
        if ai_requested:
            emit("ollama", 94, "Local AI will be set up on the first start…")
            request_ai_setup(TARGET, run_)
        emit("verify", 96, "Checking the installed system…")
        problems = verify(TARGET, uuid_of(root, run_))
        if problems:
            raise InstallError("the installed system failed its checks: " + "; ".join(problems))
    finally:
        for path in reversed(mounted):
            run_(["umount", "-l", path], check=False)
        run_(["sync"], check=False)
    msg = ("APVIS OS is installed." + (f" {models_restored} Ollama models restored." if backed_up else "")
           + (" Local AI downloads on the first start (needs internet)." if setup_ai and not models_restored else "")
           + " Press Restart, then take the USB stick out when the screen goes dark (not before: the installer runs from it).")
    return {"ok": True, "message": msg, "models": models_restored}


def copy_system(target: Path) -> None:
    """unsquashfs with real progress (it prints a percentage)."""
    proc = subprocess.Popen(["unsquashfs", "-f", "-percentage", "-d", str(target), str(SQUASHFS)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    last = -1
    assert proc.stdout is not None
    for line in proc.stdout:
        m = re.match(r"^\s*(\d{1,3})\s*$", line)
        if m and int(m.group(1)) != last:
            last = int(m.group(1))
            emit("copy", 18 + last * 52 // 100, f"Copying APVIS OS to the disk… {last}%")
    if proc.wait() != 0:
        raise InstallError("copying the system failed (unsquashfs)")


def kernel_from_medium(target: Path) -> None:
    """The live image keeps its kernel beside the squashfs; the new system needs it in /boot."""
    boot = target / "boot"
    if any(boot.glob("vmlinuz-*")):
        return
    for kernel in (LIVE_MEDIUM / "live").glob("vmlinuz-*"):
        shutil.copy2(kernel, boot / kernel.name)


def package_installed(target: Path, name: str) -> bool:
    return (target / "var/lib/dpkg/info" / f"{name}.list").exists()


def verify(target: Path, root_uuid: str) -> list[str]:
    problems = []
    grub = target / "boot/grub/grub.cfg"
    if not grub.is_file() or root_uuid not in grub.read_text(errors="replace"):
        problems.append("boot menu does not point at the new system")
    if not (target / "boot/efi/EFI/BOOT/BOOTX64.EFI").is_file():
        problems.append("UEFI boot file missing")
    if not any((target / "boot").glob("initrd.img-*")) or not any((target / "boot").glob("vmlinuz-*")):
        problems.append("kernel or start-up image missing")
    if root_uuid not in (target / "etc/fstab").read_text():
        problems.append("fstab does not name the new root")
    if package_installed(target, "live-boot"):
        problems.append("live-system packages still installed")
    greetd = target / "etc/greetd/config.toml"
    login = greetd.read_text(encoding="utf-8", errors="replace") if greetd.is_file() else ""
    if GREETER_SESSION not in login or "initial_session" in login:
        problems.append("the login screen is not set up")
    return problems


def main(argv: Iterable[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["disks"]:
            print(json.dumps(list_disks()))
        elif args[:1] == ["scan"] and len(args) == 2:
            print(json.dumps(scan_ollama(args[1])))
        elif args[:1] == ["install"] and len(args) >= 2:
            password = sys.stdin.readline().rstrip("\n")
            result = install(args[1], password, restore_models="--restore-ollama" in args, setup_ai="--setup-ai" in args)
            print(json.dumps({"done": True, **result}), flush=True)
        else:
            print("usage: apvis-install disks | scan DISK | install DISK [--restore-ollama] [--setup-ai] (password on stdin)")
            return 2
    except (InstallError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(json.dumps({"done": True, "ok": False, "message": f"Install stopped: {exc}"}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
