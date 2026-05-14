"""Shared tool registration helpers."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.types import Tool

from errors import ConfigurationError

ToolHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]
APP_SELECTOR_FIELDS = ("app_id", "bundle_id", "app_name")
APP_SELECTOR_SCHEMA: dict[str, dict[str, str]] = {
    "app_id": {
        "type": "string",
        "description": (
            "Optional App Store Connect app id to target for this call. Overrides the configured default app."
        ),
    },
    "bundle_id": {
        "type": "string",
        "description": (
            "Optional bundle id to target for this call, e.g. com.example.app. Overrides the configured default app."
        ),
    },
    "app_name": {
        "type": "string",
        "description": (
            "Optional exact App Store app name to target for this call. Prefer app_id or bundle_id when available."
        ),
    },
}


def extract_app_selector(arguments: dict[str, Any]) -> dict[str, str] | None:
    """Extract an optional per-call app selector from MCP arguments."""

    selected: dict[str, str] = {}
    for field_name in APP_SELECTOR_FIELDS:
        raw_value = arguments.get(field_name)
        value = "" if raw_value is None else str(raw_value).strip()
        if value:
            selected[field_name] = value

    if not selected:
        return None
    if len(selected) > 1:
        raise ConfigurationError(
            "Provide only one app selector per call",
            details={"provided": sorted(selected)},
        )
    return selected


def strip_app_selector(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return arguments without the common app-selector fields."""

    return {key: value for key, value in arguments.items() if key not in APP_SELECTOR_FIELDS}


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Description plus handler for an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    annotations: dict[str, Any] = field(default_factory=dict)
    supports_app_selection: bool = True

    def to_mcp_tool(self) -> Tool:
        input_schema = copy.deepcopy(self.input_schema)
        if self.supports_app_selection and input_schema.get("type") == "object":
            properties = input_schema.setdefault("properties", {})
            for key, value in APP_SELECTOR_SCHEMA.items():
                properties.setdefault(key, value)

        kwargs: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": input_schema,
        }
        if self.annotations:
            kwargs["annotations"] = self.annotations
        return Tool(**kwargs)
