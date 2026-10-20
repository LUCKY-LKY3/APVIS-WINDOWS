"""Provider-neutral APVIS task orchestration boundary.

The runtime owns lifecycle and evidence discipline.  Planning and execution are
injected capabilities, so this module does not make model calls or execute
arbitrary shell commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .action_engine import PermissionClass
from .context import ContextEngine, ContextPackage
from .events import EventLog
from .assumptions import AssumptionLedger, AssumptionRecord
from .common import utc_now
from .task_state import TaskState, TaskStore
from .tools import ToolContract


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    description: str
    tool_name: str | None = None
    retry_limit: int = 1

    def __post_init__(self) -> None:
        if not self.step_id or not self.description:
            raise ValueError("plan step requires an id and description")
        if not 1 <= self.retry_limit <= 3:
            raise ValueError("retry_limit must be between 1 and 3")


@dataclass(frozen=True)
class StepOutcome:
    status: str
    result: dict[str, Any] = None  # type: ignore[assignment]
    evidence: list[dict[str, Any]] = None  # type: ignore[assignment]
    error: str | None = None
    retryable: bool = False
    verified: bool = False

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed", "interrupted", "waiting", "approval_required"}:
            raise ValueError("unsupported step outcome status")
        object.__setattr__(self, "result", self.result or {})
        object.__setattr__(self, "evidence", self.evidence or [])


Planner = Callable[[ContextPackage], list[PlanStep]]
Executor = Callable[[PlanStep, ContextPackage], StepOutcome]


class AgentRuntime:
    """Run bounded plans while persisting enough state for interruption recovery."""

    def __init__(self, task_store: TaskStore, context_engine: ContextEngine, event_log: EventLog | None = None, assumption_ledger: AssumptionLedger | None = None) -> None:
        self.task_store = task_store
        self.context_engine = context_engine
        self.event_log = event_log or EventLog()
        self.assumption_ledger = assumption_ledger or AssumptionLedger()

    def create_task(self, task_id: str, objective: str, *, constraints: Iterable[str] = ()) -> TaskState:
        state = TaskState(
            schema_version=1,
            revision=0,
            task_id=task_id,
            original_objective=objective,
            normalized_objective=" ".join(objective.lower().split()),
            constraints=list(constraints),
            replay_safety="unknown",
            final_status="pending",
        )
        self.task_store.save(state)
        self.event_log.emit("TASK_STARTED", task_id=task_id, data={"objective": state.normalized_objective})
        return state

    def _context(self, state: TaskState, request: str, tools: Iterable[ToolContract]) -> ContextPackage:
        task_payload = state.to_dict()
        task_payload["assumption_ledger"] = self.assumption_ledger.context(state.task_id)
        package = self.context_engine.build(
            core={"identity": "APVIS OS", "policy": "provider-neutral, local-first, evidence-backed"},
            current_request=request,
            task=task_payload,
            memory_query=request,
            recent_observations=state.observations[-16:],
            tools=tools,
        )
        self.event_log.emit("CONTEXT_BUILT", task_id=state.task_id, data={"estimated_tokens": package.estimated_tokens, "omitted": package.omitted})
        return package

    def record_assumption(self, record: AssumptionRecord) -> None:
        try:
            self.task_store.load(record.task_id)
        except FileNotFoundError as exc:
            raise KeyError(record.task_id) from exc
        self.assumption_ledger.record(record)
        self.event_log.emit("ASSUMPTION_RECORDED", task_id=record.task_id, data={"assumption_id": record.assumption_id, "confidence": record.confidence})
        return None

    def resolve_assumption(self, task_id: str, assumption_id: str, *, status: str, decision: str | None = None) -> AssumptionRecord:
        record = self.assumption_ledger.resolve(task_id, assumption_id, status=status, decision=decision)
        self.event_log.emit("ASSUMPTION_RESOLVED", task_id=task_id, data={"assumption_id": assumption_id, "status": status})
        return record

    def cancel(self, task_id: str, *, reason: str = "cancelled by user") -> TaskState:
        """Cancel without replaying or claiming that an in-flight action stopped."""
        state = self.task_store.load(task_id)
        if state.final_status in {"succeeded", "completed", "failed", "cancelled", "interrupted"}:
            return state
        state.final_status = "cancelled"
        state.interruption = {"reason": reason, "detected_at": utc_now()}
        state.uncertain_outcome = {"reason": "cancellation does not prove an in-flight action was undone"}
        state.replay_safety = "unknown"
        self.task_store.save(state)
        self.event_log.emit("TASK_CANCELLED", task_id=task_id, data={"reason": reason})
        return state

    def run(self, task_id: str, *, request: str, planner: Planner, executor: Executor, tools: Iterable[ToolContract] = ()) -> TaskState:
        state = self.task_store.load(task_id)
        if state.final_status in {"completed", "succeeded", "failed", "cancelled", "interrupted"}:
            # A terminal record is evidence about a prior run, not permission
            # to replay its tools. Callers must create a new task or perform an
            # explicit, separately reviewed recovery operation.
            self.event_log.emit("TASK_NOT_RESUMED", task_id=task_id, data={"status": state.final_status})
            return state
        state.final_status = "planning"
        self.task_store.save(state)
        trusted_tools = tuple(tools)
        tool_by_name = {tool.name: tool for tool in trusted_tools}
        plan = planner(self._context(state, request, trusted_tools))
        if not plan:
            state.final_status = "failed"
            state.errors.append({"type": "empty_plan", "detail": "planner returned no steps"})
            self.task_store.save(state)
            self.event_log.emit("TASK_FAILED", task_id=task_id, data={"reason": "empty_plan"})
            return state
        step_ids = [step.step_id for step in plan]
        if len(step_ids) != len(set(step_ids)):
            state.final_status = "failed"
            state.errors.append({"type": "duplicate_step_id", "detail": "planner returned duplicate step identifiers"})
            self.task_store.save(state)
            self.event_log.emit("TASK_FAILED", task_id=task_id, data={"reason": "duplicate_step_id"})
            return state
        unknown_tools = sorted({step.tool_name for step in plan if step.tool_name is not None and step.tool_name not in tool_by_name})
        if unknown_tools:
            state.final_status = "failed"
            state.errors.append({"type": "unregistered_tool", "tools": unknown_tools})
            self.task_store.save(state)
            self.event_log.emit("TASK_FAILED", task_id=task_id, data={"reason": "unregistered_tool", "tools": unknown_tools})
            return state
        state.plan = [step.description for step in plan]
        state.pending_steps = [step.step_id for step in plan]
        state.final_status = "running"
        self.task_store.save(state)
        self.event_log.emit("PLAN_UPDATED", task_id=task_id, data={"steps": state.plan})

        for step in plan:
            contract = tool_by_name.get(step.tool_name) if step.tool_name is not None else None
            automatic_retry_allowed = (
                step.tool_name is None
                or contract.permission == PermissionClass.READ
                or (contract.permission == PermissionClass.LOCAL_SAFE_WRITE and contract.replay_safe)
            )
            state.current_step = step.step_id
            state.pending_steps = [item for item in state.pending_steps if item != step.step_id]
            self.task_store.save(state)
            attempts = 0
            while attempts < step.retry_limit:
                attempts += 1
                state.retry_counts[step.step_id] = attempts - 1
                self.event_log.emit("TOOL_SELECTED", task_id=task_id, data={"step_id": step.step_id, "tool": step.tool_name})
                try:
                    outcome = executor(step, self._context(state, request, trusted_tools))
                except Exception as exc:  # injected executor failures are recoverable only within the bound
                    outcome = StepOutcome("failed", error=str(exc), retryable=True)
                state.tool_action_results.append({"step_id": step.step_id, "status": outcome.status, "result": outcome.result, "evidence": outcome.evidence, "attempt": attempts})
                if outcome.status == "interrupted":
                    state.interruption = {"step_id": step.step_id, "attempt": attempts}
                    state.uncertain_outcome = {"step_id": step.step_id, "reason": "executor interrupted before verification"}
                    state.replay_safety = "unknown"
                    state.final_status = "interrupted"
                    self.task_store.save(state)
                    self.event_log.emit("TASK_FAILED", task_id=task_id, data={"reason": "interrupted"})
                    return state
                if outcome.status == "approval_required":
                    state.final_status = "approval_required"
                    self.task_store.save(state)
                    return state
                if outcome.status == "waiting":
                    state.final_status = "waiting"
                    self.task_store.save(state)
                    return state
                if outcome.status == "completed" and outcome.verified:
                    state.completed_steps.append(step.step_id)
                    state.verification.append({"step_id": step.step_id, "status": "passed", "evidence": outcome.evidence})
                    break
                state.errors.append({"step_id": step.step_id, "error": outcome.error or "verification failed", "attempt": attempts})
                if attempts < step.retry_limit and outcome.retryable:
                    if not automatic_retry_allowed:
                        state.uncertain_outcome = {"step_id": step.step_id, "reason": "automatic retry denied because the tool contract is not safely replayable"}
                        state.replay_safety = "unknown"
                        state.final_status = "failed"
                        self.task_store.save(state)
                        self.event_log.emit("RECOVERY_BLOCKED", task_id=task_id, data={"step_id": step.step_id, "reason": "unsafe_replay"})
                        return state
                    state.final_status = "recovering"
                    self.task_store.save(state)
                    self.event_log.emit("RECOVERY", task_id=task_id, data={"step_id": step.step_id, "attempt": attempts})
                    continue
                state.final_status = "failed"
                self.task_store.save(state)
                self.event_log.emit("TASK_FAILED", task_id=task_id, data={"step_id": step.step_id, "reason": "verification_failed"})
                return state

        state.current_step = None
        state.final_status = "completed"
        state.replay_safety = "safe"
        self.task_store.save(state)
        self.event_log.emit("TASK_COMPLETED", task_id=task_id, data={"steps": state.completed_steps})
        return state
