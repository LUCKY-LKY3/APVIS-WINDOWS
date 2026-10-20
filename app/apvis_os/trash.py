"""freedesktop.org Trash: anything APVIS removes can be restored from Files."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def move_to_trash(src: Path, home: Path | None = None) -> Path:
    """Move src into ~/.local/share/Trash with its .trashinfo; returns the trashed path."""
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"{src} does not exist")
    trash = (home or Path.home()) / ".local/share/Trash"
    (trash / "files").mkdir(parents=True, exist_ok=True)
    (trash / "info").mkdir(parents=True, exist_ok=True)
    name, n = src.name, 1
    while (trash / "files" / name).exists() or (trash / "info" / f"{name}.trashinfo").exists():
        n += 1
        name = f"{src.stem}.{n}{src.suffix}"
    info = trash / "info" / f"{name}.trashinfo"
    info.write_text(f"[Trash Info]\nPath={quote(str(src))}\nDeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n",
                    encoding="utf-8")
    target = trash / "files" / name
    try:
        shutil.move(str(src), str(target))
    except OSError:
        info.unlink(missing_ok=True)
        raise
    return target
