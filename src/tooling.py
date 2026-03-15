"""Shared tool registration helpers."""

from __future__ import annotations

from dataclasses import dataclass
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

    def to_mcp_tool(self) -> Tool:
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
        )
