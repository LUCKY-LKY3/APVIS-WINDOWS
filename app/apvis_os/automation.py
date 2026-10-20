"""Deterministic, inspectable automation execution boundary.

This module intentionally provides a manual/event evaluation path only. It does
not create a background scheduler, install manifests, or execute arbitrary
commands. Every action is translated to an ActionSpec and remains subject to
the Action Engine registry, permission match, preconditions, and verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .action_engine import ActionEngine, ActionResult, ActionSpec, PermissionClass
from .common import utc_now
from .events import EventLog
from .manifests import validate_automation_manifest


@dataclass(frozen=True)
class AutomationResult:
    automation_id: str
    status: str
    observed_at: str
    actions: list[dict[str, Any]]
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "automation_id": self.automation_id,
            "status": self.status,
            "observed_at": self.observed_at,
            "actions": self.actions,
            "reason": self.reason,
        }


class AutomationEngine:
    """Evaluate one manifest at a time; no implicit scheduling or installation."""

    def __init__(self, action_engine: ActionEngine | None = None, event_log: EventLog | None = None) -> None:
        self.action_engine = action_engine or ActionEngine()
        self.event_log = event_log or EventLog()

    @staticmethod
    def _conditions_pass(conditions: list[Any], observations: Mapping[str, Any]) -> bool:
        for condition in conditions:
            if not isinstance(condition, dict) or set(condition) != {"key", "equals"}:
                return False
            if observations.get(condition["key"]) != condition["equals"]:
                return False
        return True

    def run(self, manifest_path: str, *, trigger_type: str = "manual", observations: Mapping[str, Any] | None = None) -> AutomationResult:
        manifest = validate_automation_manifest(manifest_path)
        automation_id = manifest["id"]
        observed_at = utc_now()
        if not manifest["enabled"]:
            return AutomationResult(automation_id, "disabled", observed_at, [], "manifest is disabled")
        if manifest["trigger"]["type"] != trigger_type:
            return AutomationResult(automation_id, "not_due", observed_at, [], "trigger type does not match")
        if not self._conditions_pass(manifest["conditions"], observations or {}):
            return AutomationResult(automation_id, "blocked", observed_at, [], "conditions were not satisfied")

        actions: list[dict[str, Any]] = []
        for index, raw_action in enumerate(manifest["actions"]):
            action_type = raw_action["type"]
            declared = raw_action.get("permission", "READ")
            try:
                permission = PermissionClass(declared)
            except ValueError:
                return AutomationResult(automation_id, "blocked", observed_at, actions, f"unknown permission for action {index}")
            if permission.value not in manifest["permissions"]:
                return AutomationResult(automation_id, "blocked", observed_at, actions, f"manifest does not grant {permission.value}")
            action_id = raw_action.get("id", f"{automation_id}-{index}")
            inputs = raw_action.get("inputs", {})
            if not isinstance(inputs, dict):
                return AutomationResult(automation_id, "blocked", observed_at, actions, f"inputs for action {index} must be an object")
            result: ActionResult = self.action_engine.execute(ActionSpec(action_id, action_type, permission, inputs, verification=tuple(manifest["verification"])))
            actions.append(result.to_dict())
            if result.status not in {"observed", "verified"}:
                self.event_log.emit("AUTOMATION_FAILED", data={"automation_id": automation_id, "action_id": action_id, "status": result.status})
                return AutomationResult(automation_id, "failed", observed_at, actions, result.error or result.status)
        self.event_log.emit("AUTOMATION_COMPLETED", data={"automation_id": automation_id, "action_count": len(actions)})
        return AutomationResult(automation_id, "completed", observed_at, actions)
