"""Capability routing separated from data sensitivity and destination policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .common import utc_now


class CapabilityRequirement(str, Enum):
    GENERAL = "general"
    FAST = "fast"
    LOCAL = "local"
    CODE = "code"
    VISION = "vision"
    DEEP = "deep"


class DataSensitivity(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


class DestinationPolicy(str, Enum):
    LOCAL_ONLY = "local-only"
    EXTERNAL_PUBLIC_ONLY = "external-public-only"
    EXTERNAL_PRIVATE_ALLOWED = "external-private-allowed"
    EXTERNAL_SENSITIVE_ALLOWED = "external-sensitive-allowed"


class ProviderLocality(str, Enum):
    LOCAL = "local"
    EXTERNAL = "external"


@dataclass(frozen=True)
class CapabilityAlias:
    alias: str
    requirement: CapabilityRequirement
    purpose: str

    def to_dict(self) -> dict[str, str]:
        return {"alias": self.alias, "requirement": self.requirement.value, "purpose": self.purpose}


@dataclass(frozen=True)
class ProviderCandidate:
    """Configured candidate metadata only; this package never calls a provider."""

    provider_id: str
    locality: ProviderLocality
    capabilities: frozenset[CapabilityRequirement]
    available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "locality": self.locality.value, "capabilities": sorted(item.value for item in self.capabilities), "available": self.available}


CAPABILITIES: dict[str, CapabilityAlias] = {
    "apvis-auto": CapabilityAlias("apvis-auto", CapabilityRequirement.GENERAL, "local-first automatic selection"),
    "apvis-fast": CapabilityAlias("apvis-fast", CapabilityRequirement.FAST, "low-latency assistance"),
    "apvis-local": CapabilityAlias("apvis-local", CapabilityRequirement.LOCAL, "local inference only"),
    "apvis-code": CapabilityAlias("apvis-code", CapabilityRequirement.CODE, "code-oriented assistance"),
    "apvis-vision": CapabilityAlias("apvis-vision", CapabilityRequirement.VISION, "image-aware assistance"),
    "apvis-deep": CapabilityAlias("apvis-deep", CapabilityRequirement.DEEP, "deliberate research assistance"),
}

# The image intentionally configures no candidate and performs no discovery.
CONFIGURED_PROVIDERS: tuple[ProviderCandidate, ...] = ()

_EXTERNAL_SENSITIVITY_ALLOWANCE: dict[DestinationPolicy, DataSensitivity | None] = {
    DestinationPolicy.LOCAL_ONLY: None,
    DestinationPolicy.EXTERNAL_PUBLIC_ONLY: DataSensitivity.PUBLIC,
    DestinationPolicy.EXTERNAL_PRIVATE_ALLOWED: DataSensitivity.PRIVATE,
    DestinationPolicy.EXTERNAL_SENSITIVE_ALLOWED: DataSensitivity.SENSITIVE,
}
_SENSITIVITY_RANK = {DataSensitivity.PUBLIC: 0, DataSensitivity.PRIVATE: 1, DataSensitivity.SENSITIVE: 2}


def _external_allowed(destination_policy: DestinationPolicy, data_sensitivity: DataSensitivity) -> bool:
    allowance = _EXTERNAL_SENSITIVITY_ALLOWANCE[destination_policy]
    return allowance is not None and _SENSITIVITY_RANK[data_sensitivity] <= _SENSITIVITY_RANK[allowance]


def eligible_candidates(requirement: CapabilityRequirement, destination_policy: DestinationPolicy, data_sensitivity: DataSensitivity, providers: Iterable[ProviderCandidate] = CONFIGURED_PROVIDERS) -> list[ProviderCandidate]:
    """Local candidates are always eligible; external candidates need explicit policy."""
    return [
        candidate for candidate in providers
        if requirement in candidate.capabilities
        and (candidate.locality == ProviderLocality.LOCAL or _external_allowed(destination_policy, data_sensitivity))
    ]


def explain_route(alias: str, destination_policy: DestinationPolicy = DestinationPolicy.LOCAL_ONLY, data_sensitivity: DataSensitivity = DataSensitivity.PRIVATE, providers: Iterable[ProviderCandidate] = CONFIGURED_PROVIDERS) -> dict[str, Any]:
    """Explain candidate eligibility without claiming provider/model availability."""
    capability = CAPABILITIES.get(alias)
    if capability is None:
        return {"requested_alias": alias, "status": "unknown", "reason": "alias is not registered", "observed_at": utc_now()}
    eligible = eligible_candidates(capability.requirement, destination_policy, data_sensitivity, providers)
    available = [candidate for candidate in eligible if candidate.available]
    result: dict[str, Any] = {
        "requested_alias": alias,
        "capability": capability.to_dict(),
        "data_sensitivity": data_sensitivity.value,
        "destination_policy": destination_policy.value,
        "external_destination_allowed": _external_allowed(destination_policy, data_sensitivity),
        "eligible_candidates": [candidate.to_dict() for candidate in eligible],
        "observed_at": utc_now(),
    }
    if not available:
        result.update({"status": "unavailable", "reason": "no eligible configured provider is available", "safe_default": "apvis-local"})
        return result
    result.update({"status": "available", "selected_candidate": available[0].to_dict()})
    return result
