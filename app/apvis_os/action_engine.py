"""Registry-bound actions: action specs cannot grant themselves authority."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .common import json_primitive, redact_sensitive, utc_now
from .system_graph import SystemGraph


class PermissionClass(str, Enum):
    READ = "READ"
    LOCAL_SAFE_WRITE = "LOCAL_SAFE_WRITE"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")


@dataclass(frozen=True)
class Precondition:
    key: str
    expected: Any
    description: str


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    action_type: str
    permission: PermissionClass
    inputs: dict[str, Any] = field(default_factory=dict)
    preconditions: tuple[Precondition, ...] = ()
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    verification: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.action_id or not self.action_type:
            raise ValueError("action_id and action_type are required")
        json_primitive(self.inputs, "action inputs")

    def to_dict(self) -> dict[str, Any]:
        return {"action_id": self.action_id, "action_type": self.action_type, "permission": self.permission.value, "inputs": self.inputs, "preconditions": [asdict(item) for item in self.preconditions], "retry": {"max_attempts": self.retry.max_attempts, "retryable_errors": list(self.retry.retryable_errors)}, "verification": list(self.verification)}


@dataclass(frozen=True)
class ActionResult:
    action_id: str
    status: str
    observed_at: str
    attempts: int
    result: dict[str, Any]
    evidence: list[dict[str, Any]]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    """Append JSON records through O_APPEND; this API intentionally cannot truncate."""

    def __init__(self, path: str | Path | None = None) -> None:
        root = Path(os.environ.get("APVIS_OS_STATE_DIR", "/var/lib/apvis-os"))
        self.path = Path(path or root / "audit.jsonl")

    def append(self, event: dict[str, Any]) -> None:
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        record = json.dumps(json_primitive(event, "audit event"), sort_keys=True) + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, record.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)


Executor = Callable[[ActionSpec], tuple[dict[str, Any], list[dict[str, Any]]]]


@dataclass(frozen=True)
class ActionRegistration:
    required_permission: PermissionClass
    executor: Executor


class ActionEngine:
    """Executes only trusted registry entries; caller input is never authorization."""

    def __init__(self, audit_log: AuditLog | None = None, verification_registry: Any | None = None) -> None:
        self.audit_log = audit_log or AuditLog()
        if verification_registry is None:
            # Lazy import avoids a module cycle: verification results refer to
            # ActionResult, while the action engine owns execution.
            from .verification import VerificationRegistry

            verification_registry = VerificationRegistry()
        self.verification_registry = verification_registry
        self._registry: dict[str, ActionRegistration] = {"inspect_system": ActionRegistration(PermissionClass.READ, self._inspect_system)}

    def register(self, action_type: str, required_permission: PermissionClass, executor: Executor) -> None:
        """Trusted code adds action types; action specs can never register themselves."""
        if not action_type or action_type in self._registry:
            raise ValueError("action type must be unique and non-empty")
        self._registry[action_type] = ActionRegistration(required_permission, executor)

    @staticmethod
    def _inspect_system(spec: ActionSpec) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        graph = SystemGraph()
        requested = spec.inputs.get("subjects", ["identity", "uptime", "cpu", "memory", "storage", "network", "graphics", "processes"])
        if not isinstance(requested, list) or not all(isinstance(item, str) for item in requested):
            raise ValueError("subjects must be a list of names")
        methods = {"identity": graph.identity, "uptime": graph.uptime, "cpu": graph.cpu, "memory": graph.memory, "storage": graph.storage, "network": graph.network, "graphics": graph.graphics, "processes": graph.processes}
        unknown = sorted(set(requested) - methods.keys())
        if unknown:
            raise ValueError(f"unknown inspect subjects: {', '.join(unknown)}")
        evidence = [methods[name]().to_dict() for name in requested]
        return {"observations": evidence}, evidence

    def _record(self, spec: ActionSpec, result: ActionResult) -> ActionResult:
        self.audit_log.append(redact_sensitive({"event": "action", "spec": spec.to_dict(), "result": result.to_dict()}))
        return result

    def execute(self, spec: ActionSpec, observed_context: dict[str, Any] | None = None) -> ActionResult:
        """Use context only as reported precondition evidence, never as a grant."""
        registration = self._registry.get(spec.action_type)
        if registration is None:
            return self._record(spec, ActionResult(spec.action_id, "rejected", utc_now(), 0, {}, [], "unregistered action type"))
        if spec.permission != registration.required_permission:
            return self._record(spec, ActionResult(spec.action_id, "rejected", utc_now(), 0, {}, [], "declared permission does not match trusted action registry"))
        context = observed_context or {}
        for condition in spec.preconditions:
            if context.get(condition.key) != condition.expected:
                return self._record(spec, ActionResult(spec.action_id, "blocked", utc_now(), 0, {}, [], f"precondition failed: {condition.description}"))
        error: Exception | None = None
        for attempt in range(1, spec.retry.max_attempts + 1):
            try:
                payload, evidence = registration.executor(spec)
                status = "observed"
                error_message: str | None = None
                if spec.verification:
                    outcomes = self.verification_registry.verify(spec.verification, ActionResult(spec.action_id, status, utc_now(), attempt, payload, evidence))
                    evidence = [*evidence, *[{"verification": outcome.to_dict()} for outcome in outcomes]]
                    if outcomes and all(outcome.status == "passed" for outcome in outcomes):
                        status = "verified"
                    else:
                        status = "verification_failed"
                        error_message = "one or more verification checks did not pass"
                return self._record(spec, ActionResult(spec.action_id, status, utc_now(), attempt, payload, evidence, error_message))
            except Exception as exc:
                error = exc
                if type(exc).__name__ not in spec.retry.retryable_errors:
                    break
        return self._record(spec, ActionResult(spec.action_id, "failed", utc_now(), attempt, {}, [], str(error)))
