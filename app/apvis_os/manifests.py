"""Fail-closed validation for inspectable automation and extension manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .action_engine import PermissionClass
from .common import require_bool, require_mapping, require_string


def _read(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return require_mapping(json.load(handle), "manifest")


def _only(raw: dict[str, Any], permitted: set[str], label: str) -> None:
    unknown = sorted(set(raw) - permitted)
    if unknown:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(unknown)}")


def _permission_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item in PermissionClass._value2member_map_ for item in value):
        raise ValueError(f"{label} must contain known permission classes")
    return value


def validate_automation_manifest(path: str | Path) -> dict[str, Any]:
    raw = _read(path)
    _only(raw, {"schema_version", "id", "enabled", "trigger", "conditions", "actions", "permissions", "verification", "history"}, "automation manifest")
    if raw.get("schema_version") != 1:
        raise ValueError("automation manifest schema_version must be 1")
    require_string(raw.get("id"), "id")
    require_bool(raw.get("enabled"), "enabled")
    trigger = require_mapping(raw.get("trigger"), "trigger")
    require_string(trigger.get("type"), "trigger.type")
    if not isinstance(raw.get("conditions"), list) or not isinstance(raw.get("actions"), list) or not raw["actions"]:
        raise ValueError("conditions and non-empty actions are required lists")
    for index, action in enumerate(raw["actions"]):
        item = require_mapping(action, f"actions[{index}]")
        require_string(item.get("type"), f"actions[{index}].type")
    _permission_list(raw.get("permissions"), "permissions")
    if not isinstance(raw.get("verification"), list) or not isinstance(raw.get("history"), list):
        raise ValueError("verification and history must be lists")
    return raw


def validate_extension_manifest(path: str | Path) -> dict[str, Any]:
    raw = _read(path)
    _only(raw, {"schema_version", "id", "version", "provenance", "compatibility", "capabilities", "permissions"}, "extension manifest")
    if raw.get("schema_version") != 1:
        raise ValueError("extension manifest schema_version must be 1")
    for field in ("id", "version"):
        require_string(raw.get(field), field)
    provenance = require_mapping(raw.get("provenance"), "provenance")
    for field in ("publisher", "source", "integrity"):
        require_string(provenance.get(field), f"provenance.{field}")
    compatibility = require_mapping(raw.get("compatibility"), "compatibility")
    require_string(compatibility.get("apvis_os"), "compatibility.apvis_os")
    if not isinstance(raw.get("capabilities"), list) or not raw["capabilities"] or not all(isinstance(item, str) and item for item in raw["capabilities"]):
        raise ValueError("capabilities must be a non-empty list of strings")
    _permission_list(raw.get("permissions"), "permissions")
    return raw
