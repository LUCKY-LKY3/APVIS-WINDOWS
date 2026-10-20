"""Atomic task records with enough continuity metadata to avoid unsafe replay claims."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .common import json_primitive, redact_sensitive, utc_now

_TASK_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_STATUS = {
    "pending", "queued", "planning", "running", "waiting", "approval_required",
    "verifying", "recovering", "succeeded", "completed", "failed", "cancelled",
    "interrupted",
}
_REPLAY_SAFETY = {"safe", "unsafe", "unknown"}
_REQUIRED_FIELDS = {
    "schema_version", "revision", "task_id", "original_objective", "normalized_objective", "plan", "current_step", "completed_steps", "pending_steps", "constraints", "assumptions", "observations", "tool_action_results", "errors", "retry_counts", "created_at", "updated_at", "verification", "uncertain_outcome", "interruption", "replay_safety", "final_status",
}


@dataclass
class TaskState:
    schema_version: int
    revision: int
    task_id: str
    original_objective: str
    normalized_objective: str
    plan: list[str] = field(default_factory=list)
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    tool_action_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    retry_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    verification: list[dict[str, Any]] = field(default_factory=list)
    uncertain_outcome: dict[str, Any] | None = None
    interruption: dict[str, Any] | None = None
    replay_safety: str = "unknown"
    final_status: str = "pending"

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("unsupported task schema_version or revision")
        if not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must be a safe identifier")
        if not self.original_objective.strip() or not self.normalized_objective.strip():
            raise ValueError("task objectives are required")
        if self.final_status not in _STATUS or self.replay_safety not in _REPLAY_SAFETY:
            raise ValueError("task status or replay_safety is invalid")
        if self.final_status == "interrupted" and self.interruption is None:
            raise ValueError("interrupted tasks require interruption metadata")
        for label, value in (("plan", self.plan), ("completed_steps", self.completed_steps), ("pending_steps", self.pending_steps), ("constraints", self.constraints), ("assumptions", self.assumptions)):
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{label} must be a list of strings")
        if self.current_step is not None and not isinstance(self.current_step, str):
            raise ValueError("current_step must be a string or null")
        if not isinstance(self.retry_counts, dict) or not all(isinstance(key, str) and isinstance(value, int) and value >= 0 for key, value in self.retry_counts.items()):
            raise ValueError("retry_counts must map names to non-negative integers")
        if self.uncertain_outcome is not None and not isinstance(self.uncertain_outcome, dict):
            raise ValueError("uncertain_outcome must be an object or null")
        if self.interruption is not None and not isinstance(self.interruption, dict):
            raise ValueError("interruption must be an object or null")
        json_primitive(asdict(self), "task state")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskState":
        if set(raw) != _REQUIRED_FIELDS:
            missing = sorted(_REQUIRED_FIELDS - set(raw))
            unknown = sorted(set(raw) - _REQUIRED_FIELDS)
            raise ValueError(f"task state schema mismatch; missing={missing}, unknown={unknown}")
        return cls(**raw)


class TaskStore:
    """Atomic storage only; it does not claim leases or concurrent execution control."""

    def __init__(self, state_dir: str | Path | None = None) -> None:
        # APVIS_OS_STATE_DIR is the platform state root for every store.
        root = Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.state_dir = Path(state_dir or root / "tasks")

    def _path(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("task_id must be a safe identifier")
        return self.state_dir / f"{task_id}.json"

    def save(self, state: TaskState) -> Path:
        self.state_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
        state.revision += 1
        state.updated_at = utc_now()
        destination = self._path(state.task_id)
        encoded = json.dumps(redact_sensitive(state.to_dict()), sort_keys=True, indent=2) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{state.task_id}.", suffix=".tmp", dir=self.state_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
            if os.name != "nt":
                directory_fd = os.open(self.state_dir, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return destination

    def load(self, task_id: str) -> TaskState:
        with self._path(task_id).open(encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("task state must be an object")
        return TaskState.from_dict(raw)

    def list_ids(self) -> list[str]:
        if not self.state_dir.is_dir():
            return []
        return sorted(path.stem for path in self.state_dir.glob("*.json") if _TASK_ID.fullmatch(path.stem))

    def list_incomplete(self) -> list[str]:
        """Return persisted tasks that may need restart/recovery handling."""
        incomplete: list[str] = []
        for task_id in self.list_ids():
            try:
                if self.load(task_id).final_status in {"pending", "queued", "planning", "running", "waiting", "approval_required", "verifying", "recovering"}:
                    incomplete.append(task_id)
            except (OSError, ValueError, json.JSONDecodeError):
                # A malformed record is still a visible recovery concern, but
                # callers must inspect it rather than silently rewriting it.
                incomplete.append(task_id)
        return incomplete

    def recover_interrupted(self, *, stale_after_seconds: int = 300, reason: str = "runtime restart") -> list[str]:
        """Mark stale active tasks uncertain without replaying their actions."""
        if stale_after_seconds < 0:
            raise ValueError("stale_after_seconds cannot be negative")
        now = datetime.now(UTC)
        recovered: list[str] = []
        active = {"pending", "queued", "planning", "running", "waiting", "approval_required", "verifying", "recovering"}
        for task_id in self.list_ids():
            state = self.load(task_id)
            if state.final_status not in active:
                continue
            try:
                updated = datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
            except ValueError:
                updated = datetime.min.replace(tzinfo=UTC)
            age = (now - updated).total_seconds()
            if age < stale_after_seconds:
                continue
            state.final_status = "interrupted"
            state.interruption = {"reason": reason, "detected_at": now.isoformat().replace("+00:00", "Z"), "age_seconds": int(max(age, 0))}
            state.uncertain_outcome = {"reason": "task was active when the runtime stopped"}
            state.replay_safety = "unknown"
            self.save(state)
            recovered.append(task_id)
        return recovered
