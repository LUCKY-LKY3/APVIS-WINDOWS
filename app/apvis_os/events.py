"""Small structured event sink for observable APVIS platform activity.

Events are intentionally descriptive rather than model reasoning.  The sink
only appends validated JSON records and never stores credentials or prompts by
default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import json_primitive, redact_sensitive, utc_now


class EventLog:
    """Append-only JSONL event log with a durable write boundary."""

    def __init__(self, path: str | Path | None = None) -> None:
        state_dir = Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.path = Path(path or state_dir / "events.jsonl")

    def emit(self, event: str, *, task_id: str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not event or any(character.isspace() for character in event):
            raise ValueError("event must be a non-empty token")
        record: dict[str, Any] = {"schema_version": 1, "event": event, "observed_at": utc_now()}
        if task_id is not None:
            record["task_id"] = task_id
        if data is not None:
            record["data"] = redact_sensitive(json_primitive(data, "event data"))
        encoded = json.dumps(record, sort_keys=True) + "\n"
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, encoded.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return record
