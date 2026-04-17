"""Portable RevenueCat subscriber snapshot and event storage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from errors import ConfigurationError


class SubscriberSnapshotStore:
    """Persist RevenueCat overview snapshots and webhook events for agent consumption."""

    def __init__(
        self,
        *,
        event_log_path: Path,
        snapshot_path: Path,
        overview_history_path: Path,
    ) -> None:
        self._event_log_path = event_log_path
        self._snapshot_path = snapshot_path
        self._overview_history_path = overview_history_path
        self._processed_event_ids = self._load_processed_event_ids()

    @property
    def event_log_path(self) -> Path:
        return self._event_log_path

    @property
    def snapshot_path(self) -> Path:
        return self._snapshot_path

    @property
    def overview_history_path(self) -> Path:
        return self._overview_history_path

    def get_snapshot(self) -> dict[str, Any]:
        if not self._snapshot_path.exists():
            return self._empty_snapshot()

        snapshot = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        snapshot.setdefault("event_log_path", str(self._event_log_path))
        snapshot.setdefault("overview_history_path", str(self._overview_history_path))
        return snapshot

    def record_overview_snapshot(
        self,
        overview: dict[str, Any],
        *,
        source: str = "revenuecat_overview_poll",
    ) -> dict[str, Any]:
        if not isinstance(overview, dict) or "metrics" not in overview:
            raise ConfigurationError(
                "RevenueCat overview payload is malformed",
                details={"overview": overview},
            )

        snapshot = self.get_snapshot()
        captured_at = datetime.now(UTC).isoformat()
        entry = {
            "captured_at": captured_at,
            "source": source,
            "project_id": overview.get("project_id"),
            "metrics": overview.get("metrics"),
        }
        snapshot["updated_at"] = captured_at
        snapshot["overview"] = entry
        snapshot["overview_history_path"] = str(self._overview_history_path)
        snapshot["event_log_path"] = str(self._event_log_path)
        self._append_overview_entry(entry)
        self._write_snapshot(snapshot)
        return snapshot

    def record_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event")
        if not isinstance(event, dict):
            raise ConfigurationError(
                "RevenueCat webhook payload is missing an event object",
                details={"payload": payload},
            )

        event_id = _normalize_str(event.get("id"))
        event_type = _normalize_str(event.get("type"))
        if not event_id or not event_type:
            raise ConfigurationError(
                "RevenueCat webhook payload is missing required event fields",
                details={"event": event},
            )

        received_at = datetime.now(UTC).isoformat()
        subscriber = payload.get("subscriber")
        subscriber_attributes = {}
        if isinstance(subscriber, dict):
            subscriber_attributes = subscriber.get("subscriber_attributes") or {}

        normalized = {
            "received_at": received_at,
            "event_id": event_id,
            "event_type": event_type,
            "app_user_id": _normalize_str(event.get("app_user_id")),
            "original_app_user_id": _normalize_str(event.get("original_app_user_id")),
            "aliases": _normalize_list(event.get("aliases")),
            "transferred_to": _normalize_list(event.get("transferred_to")),
            "transferred_from": _normalize_list(event.get("transferred_from")),
            "product_id": _normalize_str(event.get("product_id")),
            "store": _normalize_str(event.get("store")),
            "entitlement_ids": _normalize_list(event.get("entitlement_ids")),
            "environment": _normalize_str(payload.get("environment")),
            "subscriber_attributes_keys": sorted(
                key for key in subscriber_attributes.keys() if isinstance(key, str)
            ),
            "raw": payload,
        }

        if event_id in self._processed_event_ids:
            return {
                **normalized,
                "duplicate": True,
            }

        self._append_event(normalized)
        self._processed_event_ids.add(event_id)

        snapshot = self.get_snapshot()
        snapshot["updated_at"] = received_at
        related_user_ids = _candidate_user_ids(normalized)
        snapshot["recent_event_summary"] = {
            "event_id": event_id,
            "event_type": event_type,
            "received_at": received_at,
            "app_user_id": normalized["app_user_id"],
            "product_id": normalized["product_id"],
            "related_user_ids": related_user_ids,
        }

        users = snapshot.setdefault("users", {})
        for user_id in related_user_ids:
            users[user_id] = {
                "last_event_id": event_id,
                "last_event_type": event_type,
                "received_at": received_at,
                "product_id": normalized["product_id"],
                "store": normalized["store"],
                "entitlement_ids": normalized["entitlement_ids"],
                "aliases": normalized["aliases"],
                "transferred_to": normalized["transferred_to"],
                "transferred_from": normalized["transferred_from"],
                "related_user_ids": [candidate for candidate in related_user_ids if candidate != user_id],
            }

        self._write_snapshot(snapshot)
        return {
            **normalized,
            "duplicate": False,
            "related_user_ids": related_user_ids,
        }

    def list_recent_events(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        if not self._event_log_path.exists():
            return []

        events: list[dict[str, Any]] = []
        with self._event_log_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                events.append(json.loads(line))
        return events[-limit:]

    def list_recent_overview_snapshots(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        if not self._overview_history_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with self._overview_history_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                entries.append(json.loads(line))
        return entries[-limit:]

    def _append_event(self, payload: dict[str, Any]) -> None:
        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.write("\n")

    def _append_overview_entry(self, payload: dict[str, Any]) -> None:
        self._overview_history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._overview_history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.write("\n")

    def _load_processed_event_ids(self) -> set[str]:
        if not self._event_log_path.exists():
            return set()

        processed: set[str] = set()
        with self._event_log_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_id = _normalize_str(payload.get("event_id"))
                if event_id:
                    processed.add(event_id)
        return processed

    def _empty_snapshot(self) -> dict[str, Any]:
        return {
            "updated_at": None,
            "overview": None,
            "recent_event_summary": None,
            "users": {},
            "event_log_path": str(self._event_log_path),
            "overview_history_path": str(self._overview_history_path),
        }

    def _write_snapshot(self, payload: dict[str, Any]) -> None:
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _normalize_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        string_value = _normalize_str(item)
        if string_value:
            normalized.append(string_value)
    return normalized


def _candidate_user_ids(event: dict[str, Any]) -> list[str]:
    candidate_ids: list[str] = []
    for field_name in ("app_user_id", "original_app_user_id"):
        value = _normalize_str(event.get(field_name))
        if value:
            candidate_ids.append(value)
    for field_name in ("aliases", "transferred_to", "transferred_from"):
        candidate_ids.extend(_normalize_list(event.get(field_name)))
    return sorted(dict.fromkeys(candidate_ids))
