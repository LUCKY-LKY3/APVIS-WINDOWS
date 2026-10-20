"""Provider-neutral request/response boundary for the Intelligence Fabric."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Protocol

from .common import json_primitive, require_string, utc_now
from .intelligence import (
    CAPABILITIES,
    DataSensitivity,
    DestinationPolicy,
    ProviderCandidate,
    eligible_candidates,
)


@dataclass(frozen=True)
class ProviderRequest:
    request_id: str
    alias: str
    prompt: str
    data_sensitivity: DataSensitivity = DataSensitivity.PRIVATE
    destination_policy: DestinationPolicy = DestinationPolicy.LOCAL_ONLY
    context: dict[str, Any] | None = None
    max_output_tokens: int = 2048

    def __post_init__(self) -> None:
        require_string(self.request_id, "request_id")
        require_string(self.alias, "alias")
        require_string(self.prompt, "prompt")
        if not isinstance(self.data_sensitivity, DataSensitivity):
            object.__setattr__(self, "data_sensitivity", DataSensitivity(self.data_sensitivity))
        if not isinstance(self.destination_policy, DestinationPolicy):
            object.__setattr__(self, "destination_policy", DestinationPolicy(self.destination_policy))
        if self.context is not None:
            json_primitive(self.context, "provider context")
        if not 1 <= self.max_output_tokens <= 131_072:
            raise ValueError("max_output_tokens must be between 1 and 131072")


@dataclass(frozen=True)
class ProviderResponse:
    provider_id: str
    request_id: str
    status: str
    text: str = ""
    evidence: list[dict[str, Any]] | None = None
    error: str | None = None
    observed_at: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"completed", "unavailable", "failed"}:
            raise ValueError("unsupported provider response status")
        object.__setattr__(self, "evidence", self.evidence or [])
        if not self.observed_at:
            object.__setattr__(self, "observed_at", utc_now())
        json_primitive({"provider_id": self.provider_id, "request_id": self.request_id, "status": self.status, "text": self.text, "evidence": self.evidence, "error": self.error, "observed_at": self.observed_at}, "provider response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "request_id": self.request_id,
            "status": self.status,
            "text": self.text,
            "evidence": self.evidence,
            "error": self.error,
            "observed_at": self.observed_at,
        }


class ProviderAdapter(Protocol):
    """An adapter may call a model, but cannot change APVIS policy."""

    @property
    def candidate(self) -> ProviderCandidate: ...

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...


@dataclass
class _Circuit:
    failures: int = 0
    opened_at: float | None = None


class ProviderRegistry:
    """Select only registered adapters eligible under hard privacy policy."""

    def __init__(self, adapters: tuple[ProviderAdapter, ...] = (), *, failure_threshold: int = 2, cooldown_seconds: float = 30.0, clock: Any = time.monotonic) -> None:
        if not 1 <= failure_threshold <= 5:
            raise ValueError("failure_threshold must be between 1 and 5")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        self._adapters: dict[str, ProviderAdapter] = {}
        self._circuits: dict[str, _Circuit] = {}
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ProviderAdapter) -> None:
        provider_id = adapter.candidate.provider_id
        if provider_id in self._adapters:
            raise ValueError(f"duplicate provider adapter: {provider_id}")
        self._adapters[provider_id] = adapter
        self._circuits.setdefault(provider_id, _Circuit())

    def health(self) -> dict[str, dict[str, Any]]:
        """Return routing health without exposing request content."""
        now = self._clock()
        result: dict[str, dict[str, Any]] = {}
        for provider_id in sorted(self._adapters):
            circuit = self._circuits[provider_id]
            open_until = None if circuit.opened_at is None else circuit.opened_at + self.cooldown_seconds
            result[provider_id] = {"failures": circuit.failures, "state": "open" if open_until is not None and now < open_until else "closed", "cooldown_remaining": max(0.0, open_until - now) if open_until is not None else 0.0}
        return result

    def _available_for_attempt(self, provider_id: str) -> bool:
        circuit = self._circuits[provider_id]
        if circuit.opened_at is None:
            return True
        if self._clock() - circuit.opened_at >= self.cooldown_seconds:
            circuit.opened_at = None
            circuit.failures = 0
            return True
        return False

    def _failure(self, provider_id: str) -> None:
        circuit = self._circuits[provider_id]
        circuit.failures += 1
        if circuit.failures >= self.failure_threshold:
            circuit.opened_at = self._clock()

    def _success(self, provider_id: str) -> None:
        circuit = self._circuits[provider_id]
        circuit.failures = 0
        circuit.opened_at = None

    def eligible(self, request: ProviderRequest) -> list[ProviderAdapter]:
        capability = CAPABILITIES.get(request.alias)
        if capability is None:
            return []
        candidates = eligible_candidates(capability.requirement, request.destination_policy, request.data_sensitivity, (adapter.candidate for adapter in self._adapters.values()))
        allowed = {candidate.provider_id for candidate in candidates if candidate.available}
        return [self._adapters[provider_id] for provider_id in sorted(allowed) if self._available_for_attempt(provider_id)]

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        eligible = self.eligible(request)
        if not eligible:
            return ProviderResponse("none", request.request_id, "unavailable", error="no eligible configured provider adapter")
        failures: list[dict[str, str]] = []
        for adapter in eligible:
            provider_id = adapter.candidate.provider_id
            try:
                response = adapter.generate(request)
            except Exception as exc:  # provider failures remain data at this boundary
                self._failure(provider_id)
                failures.append({"provider_id": provider_id, "error_type": type(exc).__name__})
                continue
            if response.provider_id != provider_id or response.request_id != request.request_id:
                self._failure(provider_id)
                failures.append({"provider_id": provider_id, "error_type": "identity_mismatch"})
                continue
            if response.status == "completed":
                self._success(provider_id)
                return response
            self._failure(provider_id)
            failures.append({"provider_id": provider_id, "error_type": response.status})
        return ProviderResponse("none", request.request_id, "failed", error="all eligible provider adapters failed", evidence=[{"attempts": failures}])
