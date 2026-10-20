"""Local-first APVIS OS platform foundation.

The package deliberately exposes data models and bounded local services only.  It
does not load provider secrets, execute arbitrary commands, or grant privileges.
"""

from .action_engine import ActionEngine, ActionSpec, PermissionClass
from .automation import AutomationEngine, AutomationResult
from .assumptions import AssumptionLedger, AssumptionRecord
from .agent_runtime import AgentRuntime, PlanStep, StepOutcome
from .context import ContextBudget, ContextEngine, ContextPackage
from .events import EventLog
from .memory import MemoryKind, MemoryRecord, MemoryStore
from .providers import ProviderAdapter, ProviderRegistry, ProviderRequest, ProviderResponse
from .system_graph import Observation, SystemGraph
from .task_state import TaskState, TaskStore
from .tools import ToolContract, ToolRegistry
from .verification import VerificationRegistry, VerificationResult

__all__ = [
    "ActionEngine",
    "ActionSpec",
    "AgentRuntime",
    "AssumptionLedger",
    "AssumptionRecord",
    "AutomationEngine",
    "AutomationResult",
    "ContextBudget",
    "ContextEngine",
    "ContextPackage",
    "EventLog",
    "MemoryKind",
    "MemoryRecord",
    "MemoryStore",
    "Observation",
    "PlanStep",
    "PermissionClass",
    "ProviderAdapter",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "StepOutcome",
    "SystemGraph",
    "TaskState",
    "TaskStore",
    "ToolContract",
    "ToolRegistry",
    "VerificationRegistry",
    "VerificationResult",
]
