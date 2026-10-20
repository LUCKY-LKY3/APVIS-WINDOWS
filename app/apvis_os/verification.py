"""Explicit verification contracts for consequential action results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .action_engine import ActionResult


@dataclass(frozen=True)
class VerificationResult:
    check: str
    status: str
    evidence: list[dict[str, Any]]
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.check, "status": self.status, "evidence": self.evidence, "detail": self.detail}


Verifier = Callable[[ActionResult], VerificationResult]


class VerificationRegistry:
    """Named verifiers are trusted code; unknown checks fail closed."""

    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {
            "result_has_evidence": self._result_has_evidence,
        }

    @staticmethod
    def _result_has_evidence(result: ActionResult) -> VerificationResult:
        if result.status in {"observed", "verified"} and result.evidence:
            return VerificationResult("result_has_evidence", "passed", result.evidence)
        return VerificationResult("result_has_evidence", "failed", result.evidence, "action returned no independent evidence")

    def register(self, name: str, verifier: Verifier) -> None:
        if not name or name in self._verifiers:
            raise ValueError("verification check name must be unique and non-empty")
        self._verifiers[name] = verifier

    def verify(self, checks: Iterable[str], result: ActionResult) -> list[VerificationResult]:
        outcomes: list[VerificationResult] = []
        for check in checks:
            verifier = self._verifiers.get(check)
            if verifier is None:
                outcomes.append(VerificationResult(check, "unavailable", [], "verification check is not registered"))
                continue
            try:
                outcomes.append(verifier(result))
            except Exception as exc:  # verifier failures become evidence, never hidden success
                outcomes.append(VerificationResult(check, "error", [], str(exc)))
        return outcomes
