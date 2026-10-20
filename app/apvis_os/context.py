"""Just-in-time context construction with deterministic budgeting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .common import json_primitive, require_string
from .memory import MemoryRecord, MemoryStore
from .tools import ToolContract


@dataclass(frozen=True)
class ContextBudget:
    max_chars: int = 16_000
    max_memory_items: int = 8
    max_observations: int = 16
    max_tools: int = 8

    def __post_init__(self) -> None:
        if self.max_chars < 2_000 or self.max_chars > 128_000:
            raise ValueError("max_chars must be between 2000 and 128000")
        if min(self.max_memory_items, self.max_observations, self.max_tools) < 0:
            raise ValueError("context item limits cannot be negative")


@dataclass(frozen=True)
class ContextPackage:
    schema_version: int
    sections: dict[str, Any]
    omitted: list[str]
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sections": self.sections,
            "omitted": self.omitted,
            "estimated_tokens": self.estimated_tokens,
        }


class ContextEngine:
    """Prioritise current task constraints over optional recalled material."""

    def __init__(self, memory_store: MemoryStore | None = None, budget: ContextBudget | None = None) -> None:
        self.memory_store = memory_store
        self.budget = budget or ContextBudget()

    @staticmethod
    def _size(value: Any) -> int:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    def build(
        self,
        *,
        core: dict[str, Any],
        current_request: str,
        task: dict[str, Any] | None = None,
        memory_query: str | None = None,
        memories: Iterable[MemoryRecord] | None = None,
        recent_observations: Iterable[dict[str, Any]] = (),
        tools: Iterable[ToolContract] = (),
    ) -> ContextPackage:
        require_string(current_request, "current_request")
        json_primitive(core, "core context")
        if task is not None:
            json_primitive(task, "task context")
        sections: dict[str, Any] = {"core": core, "request": current_request}
        omitted: list[str] = []
        # Constraints and the current step are deliberately retained before optional context.
        if task is not None:
            sections["task"] = {
                key: task.get(key)
                for key in ("task_id", "normalized_objective", "current_step", "constraints", "assumptions", "pending_steps", "replay_safety")
                if key in task
            }
        selected_memories = list(memories or ())
        if self.memory_store is not None and memory_query:
            selected_memories = self.memory_store.retrieve(memory_query, limit=self.budget.max_memory_items)
        sections["memories"] = [record.to_dict() for record in selected_memories[: self.budget.max_memory_items]]
        sections["observations"] = list(recent_observations)[: self.budget.max_observations]
        sections["tools"] = [contract.to_dict() for contract in list(tools)[: self.budget.max_tools]]

        # Trim lowest-value sections first, preserving objective/constraints.
        priority = ["tools", "observations", "memories", "task", "request", "core"]
        while self._size(sections) > self.budget.max_chars:
            removed = False
            for name in priority:
                if name not in sections:
                    continue
                value = sections[name]
                if isinstance(value, list) and value:
                    value.pop()
                    omitted.append(name)
                    removed = True
                    break
                if name in {"tools", "observations", "memories"}:
                    omitted.append(name)
                    sections.pop(name)
                    removed = True
                    break
            if not removed:
                # The mandatory request/core cannot be discarded; bound their text safely.
                if self._size(sections["request"]) > self.budget.max_chars // 2:
                    sections["request"] = current_request[: self.budget.max_chars // 2]
                    omitted.append("request-truncated")
                break
        return ContextPackage(1, sections, sorted(set(omitted)), self._size(sections) // 4)
