"""Durable, APVIS-owned Focus shared by contextual surfaces.

Focus describes what the user is concerned with. It is never an instruction,
permission grant, model response, or proof that a task succeeded.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Iterator

from .common import require_string, utc_now
from .intelligence import DataSensitivity

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FIELDS = {
    "focus_id", "kind", "target", "label", "workspace_id", "task_id",
    "source", "sensitivity", "created_at", "updated_at",
}
_SNAPSHOT_FIELDS = {"schema_version", "revision", "changed_at", "current"}


class FocusKind(str, Enum):
    QUESTION = "question"
    TASK = "task"
    FILE = "file"
    PROJECT = "project"
    APPLICATION = "application"
    PLACE = "place"
    FLIGHT = "flight"
    OBJECT = "object"
    DEVICE = "device"
    SITUATION = "situation"
    RESEARCH = "research"


@dataclass(frozen=True)
class FocusRecord:
    focus_id: str
    kind: FocusKind
    target: str
    label: str
    workspace_id: str | None = None
    task_id: str | None = None
    source: str = "user"
    sensitivity: DataSensitivity = DataSensitivity.PRIVATE
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.focus_id):
            raise ValueError("focus_id must be a safe identifier")
        if not isinstance(self.kind, FocusKind):
            object.__setattr__(self, "kind", FocusKind(self.kind))
        if not isinstance(self.sensitivity, DataSensitivity):
            object.__setattr__(self, "sensitivity", DataSensitivity(self.sensitivity))
        for name in ("target", "label", "source"):
            value = require_string(getattr(self, name), name)
            if len(value) > (2048 if name == "target" else 256):
                raise ValueError(f"{name} is too long")
        for name in ("workspace_id", "task_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not _ID.fullmatch(value)):
                raise ValueError(f"{name} must be a safe identifier or null")
        for name in ("created_at", "updated_at"):
            require_string(getattr(self, name), name)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["sensitivity"] = self.sensitivity.value
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FocusRecord:
        if not isinstance(raw, dict) or set(raw) != _FIELDS:
            raise ValueError("focus record schema mismatch")
        return cls(**raw)


@dataclass(frozen=True)
class FocusSnapshot:
    schema_version: int
    revision: int
    changed_at: str | None
    current: FocusRecord | None

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("unsupported Focus snapshot schema or revision")
        if self.changed_at is not None:
            require_string(self.changed_at, "changed_at")
        if self.current is not None and not isinstance(self.current, FocusRecord):
            raise ValueError("current Focus must be a FocusRecord or null")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "changed_at": self.changed_at,
            "current": self.current.to_dict() if self.current else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FocusSnapshot:
        if not isinstance(raw, dict) or set(raw) != _SNAPSHOT_FIELDS:
            raise ValueError("Focus snapshot schema mismatch")
        current = raw["current"]
        if current is not None:
            current = FocusRecord.from_dict(current)
        return cls(raw["schema_version"], raw["revision"], raw["changed_at"], current)


class FocusStore:
    """One active Focus with optimistic revisions and an interprocess write lock."""

    def __init__(self, path: str | Path | None = None) -> None:
        state_dir = Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.path = Path(path or state_dir / "focus" / "current.json")
        self.lock_path = self.path.with_name(self.path.name + ".lock")

    def get(self) -> FocusSnapshot:
        try:
            with self.path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            return FocusSnapshot(1, 0, None, None)
        return FocusSnapshot.from_dict(raw)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write(self, snapshot: FocusSnapshot) -> None:
        encoded = json.dumps(snapshot.to_dict(), indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".focus.", suffix=".tmp", dir=self.path.parent)
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _check_revision(current: FocusSnapshot, expected_revision: int) -> None:
        if not isinstance(expected_revision, int) or expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer")
        if current.revision != expected_revision:
            raise ValueError(
                f"Focus revision changed: expected {expected_revision}, current {current.revision}"
            )

    def set(self, record: FocusRecord, *, expected_revision: int) -> FocusSnapshot:
        if not isinstance(record, FocusRecord):
            raise ValueError("record must be a FocusRecord")
        with self._locked():
            current = self.get()
            self._check_revision(current, expected_revision)
            now = utc_now()
            if current.current and current.current.focus_id == record.focus_id:
                record = replace(record, created_at=current.current.created_at, updated_at=now)
            else:
                record = replace(record, created_at=now, updated_at=now)
            updated = FocusSnapshot(1, current.revision + 1, now, record)
            self._write(updated)
            return updated

    def clear(self, *, expected_revision: int) -> FocusSnapshot:
        with self._locked():
            current = self.get()
            self._check_revision(current, expected_revision)
            if current.current is None:
                return current
            now = utc_now()
            updated = FocusSnapshot(1, current.revision + 1, now, None)
            self._write(updated)
            return updated
