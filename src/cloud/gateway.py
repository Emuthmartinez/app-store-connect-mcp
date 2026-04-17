"""HTTP + SSE gateway that exposes the MCP server as a hosted service.

Speaks two endpoints:

  POST /v1/tools/list
       Returns the tool catalog (no auth required — useful for discovery).

  POST /v1/tools/call
       Body: {"tool": "...", "arguments": {...}}
       Headers: Authorization: Bearer ascmcp_xxx
       Returns: the tool result JSON payload.

  GET  /health
       Liveness check.

  GET  /v1/sse (with ?api_key=ascmcp_xxx)
       Long-lived SSE stream for MCP clients that want push semantics.
       Emits keepalives every 25s to survive reverse proxies.

This module intentionally uses only stdlib http.server so the gateway
has zero extra dependencies beyond what the core MCP server already
requires. For real production scale, swap to FastAPI + Uvicorn.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from cloud.auth import ApiKeyRegistry, obfuscate_api_key
from cloud.tenants import TenantRegistry
from errors import serialize_error
from tools import ALL_TOOLS

logger = logging.getLogger(__name__)
_tool_map = {tool.name: tool for tool in ALL_TOOLS}


class _GatewayState:
    def __init__(self, tenant_registry: TenantRegistry, api_key_registry: ApiKeyRegistry) -> None:
        self.tenants = tenant_registry
        self.api_keys = api_key_registry
        self.request_count = 0
        self._lock = threading.Lock()

    def increment_request(self) -> None:
        with self._lock:
            self.request_count += 1


def _make_handler(state: _GatewayState) -> type[BaseHTTPRequestHandler]:
    class GatewayHandler(BaseHTTPRequestHandler):
        # Silence BaseHTTPRequestHandler's default stderr spam; we log explicitly.
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _authenticate(self) -> tuple[str | None, dict[str, Any] | None]:
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return None, {
                    "ok": False,
                    "error": {
                        "code": "unauthenticated",
                        "message": "Missing Bearer token in Authorization header.",
                        "retryable": False,
                    },
                }
            raw_key = header[len("Bearer ") :].strip()
            record = state.api_keys.authenticate(raw_key)
            if record is None:
                logger.info("Auth failure for key %s", obfuscate_api_key(raw_key))
                return None, {
                    "ok": False,
                    "error": {
                        "code": "unauthenticated",
                        "message": "API key is not recognized.",
                        "retryable": False,
                    },
                }
            return record.tenant_id, None

        def do_GET(self) -> None:
            state.increment_request()
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._write_json(200, {"ok": True, "service": "app-store-connect-mcp-gateway"})
                return
            if parsed.path == "/v1/tools/list":
                self._write_json(
                    200,
                    {
                        "ok": True,
                        "tools": [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "annotations": tool.annotations,
                            }
                            for tool in ALL_TOOLS
                        ],
                    },
                )
                return
            if parsed.path == "/v1/sse":
                self._handle_sse(parsed)
                return
            self._write_json(404, {"ok": False, "error": {"code": "not_found", "message": parsed.path}})

        def do_POST(self) -> None:
            state.increment_request()
            parsed = urlparse(self.path)
            if parsed.path == "/v1/tools/call":
                self._handle_tool_call()
                return
            if parsed.path == "/v1/tools/list":
                self.do_GET()
                return
            self._write_json(404, {"ok": False, "error": {"code": "not_found", "message": parsed.path}})

        def _handle_tool_call(self) -> None:
            tenant_id, auth_error = self._authenticate()
            if auth_error is not None:
                self._write_json(401, auth_error)
                return

            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(
                    400,
                    {
                        "ok": False,
                        "error": {
                            "code": "invalid_json",
                            "message": "Request body is not valid JSON.",
                            "retryable": False,
                        },
                    },
                )
                return

            tool_name = body.get("tool")
            arguments = body.get("arguments") or {}
            definition = _tool_map.get(tool_name)
            if definition is None:
                self._write_json(
                    404,
                    {
                        "ok": False,
                        "error": {
                            "code": "unknown_tool",
                            "message": f"Unknown tool: {tool_name!r}",
                            "retryable": False,
                        },
                    },
                )
                return

            try:
                runtime = state.tenants.get_runtime(tenant_id)
                payload = definition.handler(runtime, arguments)
                payload.setdefault("completion_state", "completed")
                payload.setdefault("should_continue", True)
                self._write_json(200, payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Tool call failed for tenant=%s tool=%s", tenant_id, tool_name)
                self._write_json(500, serialize_error(exc))

        def _handle_sse(self, parsed: Any) -> None:
            query = parse_qs(parsed.query or "")
            raw_key = (query.get("api_key") or [""])[0]
            record = state.api_keys.authenticate(raw_key)
            if record is None:
                self._write_json(
                    401,
                    {
                        "ok": False,
                        "error": {"code": "unauthenticated", "message": "Missing or invalid api_key."},
                    },
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            try:
                self.wfile.write(
                    f"event: ready\ndata: {json.dumps({'tenant_id': record.tenant_id})}\n\n".encode()
                )
                self.wfile.flush()
                while True:
                    time.sleep(25)
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    return GatewayHandler


def build_gateway(
    *,
    tenant_registry: TenantRegistry,
    api_key_registry: ApiKeyRegistry,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """Construct (but do not start) a threaded HTTP gateway."""
    state = _GatewayState(tenant_registry, api_key_registry)
    handler_cls = _make_handler(state)
    return ThreadingHTTPServer((host, port), handler_cls)


def serve_forever(server: ThreadingHTTPServer) -> None:
    host, port = server.server_address
    logger.warning("Gateway listening on http://%s:%s", host, port)
    server.serve_forever()
