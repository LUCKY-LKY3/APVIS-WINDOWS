"""Small, dependency-free validation helpers shared by platform boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping

_SENSITIVE_KEY_PARTS = ("password", "passphrase", "token", "secret", "api_key", "private_key", "credential", "cookie", "authorization")
_PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----.*?-----END [^-\r\n]*PRIVATE KEY-----", re.DOTALL)
_AUTHORIZATION_VALUE = re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+")
_BEARER_VALUE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passphrase|token|secret|api[-_]?key|private[-_]?key|credential|cookie|authorization)"
    r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)


def utc_now() -> str:
    """Return an RFC 3339 UTC timestamp with explicit timezone."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{label} must be a non-empty string")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def json_primitive(value: Any, label: str = "value") -> Any:
    """Reject values that cannot be safely represented as JSON records."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_primitive(item, label) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: json_primitive(item, label) for key, item in value.items()}
    raise ValueError(f"{label} must contain JSON-serializable data")


def redact_sensitive(value: Any) -> Any:
    """Redact common credential-shaped mapping fields before persistence."""
    if isinstance(value, str):
        value = _PRIVATE_KEY_BLOCK.sub("[REDACTED PRIVATE KEY]", value)
        value = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", value)
        value = _BEARER_VALUE.sub(r"\1[REDACTED]", value)
        return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower().replace("-", "_")
            redacted[key] = "[REDACTED]" if any(part in lowered for part in _SENSITIVE_KEY_PARTS) else redact_sensitive(item)
        return redacted
    return value
