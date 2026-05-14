#!/usr/bin/env python3
# ruff: noqa: E402
"""stdio MCP entrypoint for App Store Connect listing management."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Route all logging to stderr so stdout stays clean for the MCP stdio protocol.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)

__version__ = "0.2.0"

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from auth import AppStoreJwtProvider
from change_log import ChangeLogger
from client import AppStoreConnectClient
from config import Settings
from errors import AppStoreConnectMcpError, serialize_error
from revenuecat import RevenueCatMetricsClient
from subscriber_state import SubscriberSnapshotStore
from tooling import extract_app_selector, strip_app_selector
from tools import ALL_TOOLS

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent
except ImportError:
    print(
        "Error: MCP SDK not installed. Install dependencies from app-store-connect-mcp/pyproject.toml.",
        file=sys.stderr,
    )
    sys.exit(1)

logger = logging.getLogger("app_store_connect_mcp")


@dataclass(slots=True)
class Runtime:
    """Shared runtime dependencies for tool handlers."""

    settings: Settings
    asc: AppStoreConnectClient
    revenuecat: RevenueCatMetricsClient
    change_logger: ChangeLogger
    subscriber_store: SubscriberSnapshotStore


SERVER_NAME = "app_store_connect_mcp"
server = Server(SERVER_NAME)
tool_map = {tool.name: tool for tool in ALL_TOOLS}
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        try:
            settings = Settings.load()
        except AppStoreConnectMcpError as exc:
            hint_lines = [
                f"Configuration error: {exc.message}",
                "",
                "Required environment variables:",
                "  APP_STORE_KEY_ID",
                "  APP_STORE_ISSUER_ID",
                "  APP_STORE_PRIVATE_KEY  (inline PEM or path to .p8 file)",
                "  APP_STORE_BUNDLE_ID",
                "",
                "Set them in .env, a profile file (profiles/*.env), or the process environment.",
                "See .env.example for a template.",
            ]
            if hasattr(exc, "details") and exc.details:
                hint_lines.append(f"  Details: {exc.details}")
            logger.error("\n".join(hint_lines))
            raise
        token_provider = AppStoreJwtProvider(settings)
        _runtime = Runtime(
            settings=settings,
            asc=AppStoreConnectClient(settings, token_provider),
            revenuecat=RevenueCatMetricsClient(settings),
            change_logger=ChangeLogger(settings.change_log_path),
            subscriber_store=SubscriberSnapshotStore(
                event_log_path=settings.revenuecat_event_log_path,
                snapshot_path=settings.revenuecat_snapshot_path,
                overview_history_path=settings.revenuecat_overview_history_path,
            ),
        )
    return _runtime


def _to_text(payload: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


def _finalize_payload(payload: dict, *, completion_state: str) -> dict:
    payload.setdefault("completion_state", completion_state)
    payload.setdefault("should_continue", True)
    return payload


def _run_tool(definition, runtime: Runtime, arguments: dict) -> dict:
    selector = extract_app_selector(arguments) if definition.supports_app_selection else None
    tool_arguments = strip_app_selector(arguments) if definition.supports_app_selection else arguments

    with runtime.asc.use_app_selector(selector):
        return definition.handler(runtime, tool_arguments)


@server.list_tools()
async def list_tools():
    return [tool.to_mcp_tool() for tool in ALL_TOOLS]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None):
    definition = tool_map.get(name)
    if definition is None:
        return _to_text(
            _finalize_payload(
                {
                    "ok": False,
                    "error": {
                        "code": "unknown_tool",
                        "message": f"Unknown tool: {name}",
                        "retryable": False,
                    },
                },
                completion_state="failed",
            )
        )

    try:
        payload = await asyncio.to_thread(
            _run_tool,
            definition,
            get_runtime(),
            arguments or {},
        )
        return _to_text(_finalize_payload(payload, completion_state="completed"))
    except Exception as exc:  # pragma: no cover - guarded by unit tests around payloads
        return _to_text(_finalize_payload(serialize_error(exc), completion_state="failed"))


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def cli_main() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
