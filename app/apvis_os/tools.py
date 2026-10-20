"""Inspectable tool contracts and relevance-based discovery."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .action_engine import PermissionClass
from .common import json_primitive, require_string


_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")


@dataclass(frozen=True)
class ToolContract:
    name: str
    purpose: str
    parameters: dict[str, Any]
    permission: PermissionClass
    expected_output: str
    possible_errors: tuple[str, ...] = ()
    timeout_seconds: int = 30
    keywords: tuple[str, ...] = ()
    replay_safe: bool = False

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ValueError("tool name must be a namespaced identifier")
        require_string(self.purpose, "purpose")
        require_string(self.expected_output, "expected_output")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be an object schema")
        if not isinstance(self.permission, PermissionClass):
            object.__setattr__(self, "permission", PermissionClass(self.permission))
        if self.timeout_seconds < 1 or self.timeout_seconds > 900:
            raise ValueError("timeout_seconds must be between 1 and 900")
        if not isinstance(self.replay_safe, bool):
            raise ValueError("replay_safe must be a boolean")
        if not all(isinstance(item, str) and item.strip() for item in self.possible_errors + self.keywords):
            raise ValueError("tool errors and keywords must be non-empty strings")
        json_primitive(self.parameters, "tool parameters")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["permission"] = self.permission.value
        value["possible_errors"] = list(self.possible_errors)
        value["keywords"] = list(self.keywords)
        return value


class ToolRegistry:
    """Registry is trusted code; discovery only returns contracts and never runs tools."""

    def __init__(self, contracts: Iterable[ToolContract] = ()) -> None:
        self._contracts: dict[str, ToolContract] = {}
        for contract in contracts:
            self.register(contract)

    def register(self, contract: ToolContract) -> None:
        if contract.name in self._contracts:
            raise ValueError(f"duplicate tool contract: {contract.name}")
        self._contracts[contract.name] = contract

    def get(self, name: str) -> ToolContract | None:
        return self._contracts.get(name)

    def discover(self, request: str, *, names: set[str] | None = None, limit: int = 8) -> list[ToolContract]:
        if limit < 1 or limit > 32:
            raise ValueError("limit must be between 1 and 32")
        requested = {token for token in re.findall(r"[a-z0-9_.-]+", request.lower())}
        scored: list[tuple[int, ToolContract]] = []
        for contract in self._contracts.values():
            if names is not None and contract.name not in names:
                continue
            corpus = {token for token in re.findall(r"[a-z0-9_.-]+", (contract.name + " " + contract.purpose + " " + " ".join(contract.keywords)).lower())}
            score = len(requested & corpus)
            if score:
                scored.append((score, contract))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [contract for _, contract in scored[:limit]]

    def all(self) -> list[ToolContract]:
        return [self._contracts[name] for name in sorted(self._contracts)]
