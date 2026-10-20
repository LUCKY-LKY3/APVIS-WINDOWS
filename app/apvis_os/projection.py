"""Read-only, privacy-aware shell projection of persisted APVIS state.

Persisted task status is not proof that an executor is still running. This
projection deliberately labels active records as needing continuity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .common import utc_now
from .focus import FocusStore
from .task_state import TaskStore


class DisplayContext(str, Enum):
    PRIVATE = "private"
    SHARED = "shared"
    LOCKED = "locked"


class NucleusMode(str, Enum):
    IDLE = "idle"
    ATTENTION = "attention"
    CONTINUITY_UNKNOWN = "continuity_unknown"
    # Reserved: typed now so renderers can be built against them, but no
    # projection may emit them until a real event source exists. A model
    # response can never select one of these.
    LISTENING = "listening"
    RETRIEVAL = "retrieval"
    WORKING = "working"
    SUCCESS = "success"
    ERROR = "error"
    LOCAL_ONLY = "local_only"
    RECOVERY = "recovery"


# Modes the platform can actually observe today.
OBSERVABLE_MODES = frozenset({NucleusMode.IDLE, NucleusMode.ATTENTION, NucleusMode.CONTINUITY_UNKNOWN})


_ACTIVE = {
    "pending", "queued", "planning", "running", "waiting",
    "approval_required", "verifying", "recovering",
}
_ATTENTION = {"approval_required", "failed", "interrupted"}


@dataclass(frozen=True)
class ShellProjection:
    schema_version: int
    generated_at: str
    display_context: DisplayContext
    nucleus_mode: NucleusMode
    status_text: str
    focus: dict[str, Any] | None
    focus_revision: int
    task_counts: dict[str, int]
    unreadable_task_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "display_context": self.display_context.value,
            "nucleus_mode": self.nucleus_mode.value,
            "status_text": self.status_text,
            "focus": self.focus,
            "focus_revision": self.focus_revision,
            "task_counts": self.task_counts,
            "unreadable_task_count": self.unreadable_task_count,
        }


class ShellProjector:
    """Derive a UI snapshot without changing task or Focus state."""

    def __init__(self, focus_store: FocusStore | None = None, task_store: TaskStore | None = None) -> None:
        self.focus_store = focus_store or FocusStore()
        self.task_store = task_store or TaskStore()

    def snapshot(self, display_context: DisplayContext = DisplayContext.PRIVATE) -> ShellProjection:
        if not isinstance(display_context, DisplayContext):
            display_context = DisplayContext(display_context)
        focus_state = self.focus_store.get()
        focus = None
        if focus_state.current is not None and display_context == DisplayContext.PRIVATE:
            record = focus_state.current
            focus = {
                "focus_id": record.focus_id,
                "kind": record.kind.value,
                "label": record.label,
                "sensitivity": record.sensitivity.value,
                "updated_at": record.updated_at,
            }

        counts: dict[str, int] = {}
        unreadable = 0
        for task_id in self.task_store.list_ids():
            try:
                status = self.task_store.load(task_id).final_status
            except (OSError, ValueError, TypeError, KeyError):
                unreadable += 1
                continue
            counts[status] = counts.get(status, 0) + 1

        attention = unreadable + sum(counts.get(status, 0) for status in _ATTENTION)
        continuity = sum(counts.get(status, 0) for status in _ACTIVE)
        if attention:
            mode = NucleusMode.ATTENTION
            waiting, failed = counts.get("approval_required", 0), counts.get("failed", 0)
            parts = [f"{waiting} waiting for your approval" if waiting else "",
                     f"{failed} did not complete" if failed else "",
                     f"{attention - waiting - failed} need a check" if attention - waiting - failed else ""]
            status_text = "; ".join(p for p in parts if p).capitalize()
        elif continuity:
            mode = NucleusMode.CONTINUITY_UNKNOWN
            status_text = f"{continuity} task record(s) need continuity checks"
        else:
            mode = NucleusMode.IDLE
            status_text = "No task needs attention"

        return ShellProjection(
            1, utc_now(), display_context, mode, status_text,
            focus, focus_state.revision, counts, unreadable,
        )
