"""Durable, explicit assumptions for long-running APVIS tasks.

An assumption is deliberately separate from a task's prose context.  It has a
decision, confidence, provenance, and a reversible flag so stale or uncertain
reasoning cannot silently become an instruction.  The ledger is append/update
only through atomic replacement and never executes an action.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .common import json_primitive, redact_sensitive, utc_now

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_CONFIDENCE = {"low", "medium", "high"}
_STATUS = {"open", "confirmed", "rejected", "superseded"}


@dataclass
class AssumptionRecord:
    assumption_id: str
    task_id: str
    statement: str
    decision: str
    confidence: str = "medium"
    reversible: bool = True
    source: str = "runtime"
    status: str = "open"
    created_at: str = ""
    updated_at: str = ""
    resolved_at: str | None = None

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.assumption_id) or not _IDENTIFIER.fullmatch(self.task_id):
            raise ValueError("assumption_id and task_id must be safe identifiers")
        for value, name in ((self.statement, "statement"), (self.decision, "decision"), (self.source, "source")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if self.confidence not in _CONFIDENCE or self.status not in _STATUS:
            raise ValueError("invalid assumption confidence or status")
        if not isinstance(self.reversible, bool):
            raise ValueError("reversible must be boolean")
        if not self.created_at:
            self.created_at = utc_now()
        if not self.updated_at:
            self.updated_at = self.created_at
        json_primitive(asdict(self), "assumption record")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AssumptionRecord":
        expected = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        if set(raw) != expected:
            raise ValueError("assumption record schema mismatch")
        return cls(**raw)


class AssumptionLedger:
    """Atomic per-task assumption records with explicit resolution."""

    def __init__(self, root: str | Path | None = None) -> None:
        state_root = Path(root or os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.root = state_root / "assumptions"

    def _path(self, task_id: str) -> Path:
        if not _IDENTIFIER.fullmatch(task_id):
            raise ValueError("task_id must be a safe identifier")
        return self.root / f"{task_id}.json"

    def _read(self, task_id: str) -> list[AssumptionRecord]:
        path = self._path(task_id)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("records"), list):
            raise ValueError("assumption ledger schema mismatch")
        return [AssumptionRecord.from_dict(item) for item in raw["records"]]

    def _write(self, task_id: str, records: list[AssumptionRecord]) -> Path:
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)
        path = self._path(task_id)
        payload = {"schema_version": 1, "task_id": task_id, "records": [record.to_dict() for record in records]}
        encoded = json.dumps(redact_sensitive(json_primitive(payload, "assumption ledger")), sort_keys=True, indent=2) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{task_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return path

    def record(self, record: AssumptionRecord) -> Path:
        records = self._read(record.task_id)
        if any(item.assumption_id == record.assumption_id for item in records):
            raise ValueError(f"duplicate assumption_id: {record.assumption_id}")
        records.append(record)
        return self._write(record.task_id, records)

    def list(self, task_id: str, *, status: str | None = None) -> list[AssumptionRecord]:
        records = self._read(task_id)
        if status is not None and status not in _STATUS:
            raise ValueError("invalid assumption status")
        return [record for record in records if status is None or record.status == status]

    def resolve(self, task_id: str, assumption_id: str, *, status: str, decision: str | None = None) -> AssumptionRecord:
        if status not in {"confirmed", "rejected", "superseded"}:
            raise ValueError("resolution status must be confirmed, rejected, or superseded")
        records = self._read(task_id)
        for record in records:
            if record.assumption_id == assumption_id:
                record.status = status
                if decision is not None:
                    if not decision.strip():
                        raise ValueError("decision cannot be empty")
                    record.decision = decision
                record.updated_at = utc_now()
                record.resolved_at = record.updated_at
                self._write(task_id, records)
                return record
        raise KeyError(assumption_id)

    def context(self, task_id: str) -> list[dict[str, Any]]:
        """Return only currently open assumptions for just-in-time context."""
        return [record.to_dict() for record in self.list(task_id, status="open")]
