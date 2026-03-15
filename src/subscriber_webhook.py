#!/usr/bin/env python3
"""Portable RevenueCat webhook listener for local subscriber state refresh."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from config import Settings
from errors import ConfigurationError
from subscriber_state import SubscriberSnapshotStore


def verify_revenuecat_webhook_authorization(
    provided_header: str | None,
    expected_header: str | None,
) -> bool:
    """Return True when webhook authorization is disabled or the header matches."""

    if not expected_header:
        return True
    return provided_header == expected_header


def build_webhook_handler(
    *,
    settings: Settings,
    store: SubscriberSnapshotStore,
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to the configured settings and store."""

    class RevenueCatWebhookHandler(BaseHTTPRequestHandler):
        server_version = "RevenueCatWebhook/0.1"

        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                self._write_json(404, {"ok": False, "error": "not_found"})
                return

            snapshot = store.get_snapshot()
            self._write_json(
                200,
                {
                    "ok": True,
                    "webhook_path": settings.revenuecat_webhook_path,
                    "snapshot_path": str(store.snapshot_path),
                    "event_log_path": str(store.event_log_path),
                    "overview_history_path": str(store.overview_history_path),
                    "last_updated_at": snapshot.get("updated_at"),
                },
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != settings.revenuecat_webhook_path:
                self._write_json(404, {"ok": False, "error": "not_found"})
                return

            provided_header = self.headers.get("Authorization")
            if not verify_revenuecat_webhook_authorization(
                provided_header=provided_header,
                expected_header=settings.revenuecat_webhook_auth_header,
            ):
                self._write_json(401, {"ok": False, "error": "invalid_authorization"})
                return

            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(400, {"ok": False, "error": "invalid_json"})
                return

            try:
                event = store.record_webhook_event(payload)
            except ConfigurationError as exc:
                self._write_json(400, exc.as_dict())
                return

            self._write_json(
                200,
                {
                    "ok": True,
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "app_user_id": event["app_user_id"],
                    "duplicate": bool(event.get("duplicate")),
                },
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            del format, args

        def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return RevenueCatWebhookHandler


def main() -> int:
    settings = Settings.load()
    store = SubscriberSnapshotStore(
        event_log_path=settings.revenuecat_event_log_path,
        snapshot_path=settings.revenuecat_snapshot_path,
        overview_history_path=settings.revenuecat_overview_history_path,
    )
    handler = build_webhook_handler(settings=settings, store=store)
    server = ThreadingHTTPServer(
        (settings.revenuecat_webhook_host, settings.revenuecat_webhook_port),
        handler,
    )
    print(
        "RevenueCat webhook listener ready "
        f"on http://{settings.revenuecat_webhook_host}:{settings.revenuecat_webhook_port}"
        f"{settings.revenuecat_webhook_path}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
