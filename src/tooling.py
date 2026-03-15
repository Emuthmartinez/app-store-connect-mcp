"""Shared tool registration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from mcp.types import Tool


ToolHandler = Callable[[Any, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Description plus handler for an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_mcp_tool(self) -> Tool:
        kwargs: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            kwargs["annotations"] = self.annotations
        return Tool(**kwargs)
