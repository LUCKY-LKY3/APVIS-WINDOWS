"""Bounded, provenance-bearing APVIS memory storage.

The store keeps explicit records instead of silently persisting conversation
transcripts.  Callers decide what is useful enough to save, while retrieval is
deterministic, relevance-ranked, and safe to inspect offline.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .common import json_primitive, redact_sensitive, require_string, utc_now


class MemoryKind(str, Enum):
    WORKING = "working"
    SESSION = "session"
    USER = "user"
    TASK = "task"
    PROJECT = "project"
    SYSTEM = "system"
    OBSERVED = "observed"


_MEMORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass
class MemoryRecord:
    memory_id: str
    kind: MemoryKind
    content: str
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    stable_key: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not _MEMORY_ID.fullmatch(self.memory_id):
            raise ValueError("memory_id must be a safe identifier")
        if not isinstance(self.kind, MemoryKind):
            self.kind = MemoryKind(self.kind)
        require_string(self.content, "content")
        if not isinstance(self.tags, list) or not all(isinstance(item, str) and item.strip() for item in self.tags):
            raise ValueError("tags must be a list of non-empty strings")
        if not isinstance(self.provenance, dict):
            raise ValueError("provenance must be an object")
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ValueError("confidence must be numeric")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.stable_key is not None:
            require_string(self.stable_key, "stable_key")
        json_primitive(asdict(self), "memory record")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "MemoryRecord":
        return cls(**raw)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", value.lower())}


def _expired(record: MemoryRecord, now: datetime) -> bool:
    if not record.expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return expiry <= now


class MemoryStore:
    """Atomic JSON storage with explicit replacement and deletion semantics."""

    def __init__(self, path: str | Path | None = None) -> None:
        state_dir = Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.path = Path(path or state_dir / "memory.json")

    def _read(self) -> list[MemoryRecord]:
        if not self.path.is_file():
            return []
        with self.path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, list):
            raise ValueError("memory store must contain a list")
        return [MemoryRecord.from_dict(item) for item in raw if isinstance(item, dict)]

    def _write(self, records: Iterable[MemoryRecord]) -> None:
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".memory.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(redact_sensitive([record.to_dict() for record in records]), handle, indent=2, sort_keys=True)
                handle.write("\n")
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

    def upsert(self, record: MemoryRecord) -> MemoryRecord:
        records = self._read()
        identity = record.stable_key or hashlib.sha256(record.content.strip().lower().encode("utf-8")).hexdigest()
        for index, existing in enumerate(records):
            existing_identity = existing.stable_key or hashlib.sha256(existing.content.strip().lower().encode("utf-8")).hexdigest()
            if existing.memory_id == record.memory_id or existing_identity == identity:
                record.created_at = existing.created_at
                record.updated_at = utc_now()
                records[index] = record
                self._write(records)
                return record
        self._write([*records, record])
        return record

    def retrieve(self, query: str, *, kinds: set[MemoryKind] | None = None, limit: int = 8) -> list[MemoryRecord]:
        if limit < 1 or limit > 64:
            raise ValueError("limit must be between 1 and 64")
        query_tokens = _tokens(query)
        now = datetime.now(UTC)
        scored: list[tuple[float, MemoryRecord]] = []
        for record in self._read():
            if kinds and record.kind not in kinds:
                continue
            if _expired(record, now):
                continue
            haystack = _tokens(record.content) | _tokens(" ".join(record.tags))
            overlap = len(query_tokens & haystack) if query_tokens else 0
            if query_tokens and overlap == 0:
                continue
            recency = 0.0
            try:
                age_days = max((now - datetime.fromisoformat(record.updated_at.replace("Z", "+00:00"))).total_seconds() / 86_400, 0.0)
                recency = 1.0 / (1.0 + age_days)
            except ValueError:
                pass
            scored.append((overlap * 10.0 + recency + record.confidence, record))
        scored.sort(key=lambda item: (-item[0], item[1].updated_at, item[1].memory_id))
        return [record for _, record in scored[:limit]]

    def delete(self, memory_id: str) -> bool:
        records = self._read()
        remaining = [record for record in records if record.memory_id != memory_id]
        if len(remaining) == len(records):
            return False
        self._write(remaining)
        return True

    def consolidate(self) -> int:
        """Remove duplicate content while preserving the newest record."""
        records = self._read()
        newest: dict[str, MemoryRecord] = {}
        for record in records:
            identity = record.stable_key or hashlib.sha256(record.content.strip().lower().encode("utf-8")).hexdigest()
            prior = newest.get(identity)
            if prior is None or record.updated_at > prior.updated_at:
                newest[identity] = record
        deduped = list(newest.values())
        removed = len(records) - len(deduped)
        if removed:
            self._write(deduped)
        return removed
