"""Tests for generic ASC tools and portable subscriber freshness state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from errors import ConfigurationError
from subscriber_state import SubscriberSnapshotStore
from subscriber_webhook import verify_revenuecat_webhook_authorization
from tools.generic import asc_api_get, asc_api_list, asc_api_patch, get_asc_api_capabilities
from tools.subscriber import list_subscriber_overview_history, refresh_subscriber_overview


class FakeChangeLogger:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class FakeAsc:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self.localization_state = {
            "id": "loc-1",
            "type": "appInfoLocalizations",
            "attributes": {"subtitle": "Before"},
        }

    def request(self, method: str, path: str, *, json_body: dict | None = None):
        self.calls.append((method, path, json_body))
        if method == "GET":
            if path.startswith("/v1/apps?"):
                return {
                    "data": [
                        {
                            "id": "app-1",
                            "attributes": {
                                "bundleId": "example.bundle",
                                "name": "Example App",
                            },
                        }
                    ]
                }
            if path == "/v1/appInfoLocalizations/loc-1":
                return {"data": self.localization_state}
            return {"data": {"id": "ok"}}

        if method == "PATCH" and path == "/v1/appInfoLocalizations/loc-1":
            attributes = json_body["data"]["attributes"]
            self.localization_state = {
                **self.localization_state,
                "attributes": {**self.localization_state["attributes"], **attributes},
            }
            return {"data": self.localization_state}

        return {"data": {"id": "ok"}}

    def get_collection(self, path: str):
        self.calls.append(("LIST", path, None))
        return [{"id": "one"}, {"id": "two"}]

    def get_configured_app(self):
        return {
            "id": "app-1",
            "attributes": {
                "bundleId": "example.bundle",
                "name": "Example App",
            },
        }

    def get_primary_app_info(self):
        return {"id": "app-info-1"}

    def get_app_info_localizations(self, app_info_id: str):
        assert app_info_id == "app-info-1"
        return [{"id": "info-loc-1", "attributes": {"locale": "en-US"}}]

    def get_current_version(self):
        return {
            "id": "version-1",
            "attributes": {
                "appVersionState": "WAITING_FOR_REVIEW",
                "versionString": "1.0.48",
            },
        }

    def get_version_localizations(self, version_id: str):
        assert version_id == "version-1"
        return [{"id": "version-loc-1", "attributes": {"locale": "en-US"}}]


class FakeRevenueCat:
    def get_overview(self):
        return {
            "project_id": "proj5711c0c0",
            "metrics": {
                "active_subscriptions": 12,
                "active_trials": 14,
                "mrr": 64,
            },
        }


class Runtime:
    def __init__(self, tmp_path: Path) -> None:
        self.settings = type(
            "Settings",
            (),
            {"app_store_base_url": "https://api.appstoreconnect.apple.com"},
        )()
        self.asc = FakeAsc()
        self.revenuecat = FakeRevenueCat()
        self.change_logger = FakeChangeLogger()
        self.subscriber_store = SubscriberSnapshotStore(
            event_log_path=tmp_path / "events.jsonl",
            snapshot_path=tmp_path / "snapshot.json",
            overview_history_path=tmp_path / "overview-history.jsonl",
        )


def test_asc_api_get_supports_full_url_and_query(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path)

    payload = asc_api_get(
        runtime,
        {
            "path": "https://api.appstoreconnect.apple.com/v1/apps",
            "query": {"limit": 1, "filter[bundleId]": "example.bundle"},
        },
    )

    assert payload["ok"] is True
    method, path, body = runtime.asc.calls[0]
    assert method == "GET"
    assert path.startswith("/v1/apps?")
    assert "limit=1" in path
    assert "filter%5BbundleId%5D=example.bundle" in path
    assert body is None


def test_asc_api_list_rejects_non_v1_path(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path)

    with pytest.raises(ConfigurationError):
        asc_api_list(runtime, {"path": "/not-v1/apps"})


def test_generic_patch_logs_before_after_and_metrics(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path)

    payload = asc_api_patch(
        runtime,
        {
            "path": "/v1/appInfoLocalizations/loc-1",
            "body": {
                "data": {
                    "type": "appInfoLocalizations",
                    "id": "loc-1",
                    "attributes": {"subtitle": "After"},
                }
            },
        },
    )

    assert payload["after"]["response"]["data"]["attributes"]["subtitle"] == "After"
    assert len(runtime.change_logger.records) == 1
    record = runtime.change_logger.records[0]
    assert record["operation"] == "asc_api_patch"
    assert record["before"]["response"]["data"]["attributes"]["subtitle"] == "Before"
    assert record["after"]["path_snapshot"]["response"]["data"]["attributes"]["subtitle"] == "After"
    assert record["revenuecat_metrics"]["metrics"]["mrr"] == 64


def test_get_asc_api_capabilities_returns_runtime_entities_and_catalog(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path)

    payload = get_asc_api_capabilities(runtime, {"search": "screenshots"})

    assert payload["ok"] is True
    assert payload["runtime_entities"]["configured_app"]["paths"]["app_infos"] == "/v1/apps/app-1/appInfos"
    assert payload["runtime_entities"]["version_localizations"][0]["relationships"]["screenshot_sets"] == (
        "/v1/appStoreVersionLocalizations/version-loc-1/appScreenshotSets"
    )
    assert payload["catalog"][0]["resource_type"] == "appScreenshotSets"
    assert payload["generic_tools"][2]["logs_mutations"] is True


def test_subscriber_snapshot_store_records_overview_and_webhook_event(tmp_path: Path) -> None:
    store = SubscriberSnapshotStore(
        event_log_path=tmp_path / "events.jsonl",
        snapshot_path=tmp_path / "snapshot.json",
        overview_history_path=tmp_path / "overview-history.jsonl",
    )

    store.record_overview_snapshot(
        {
            "project_id": "proj",
            "metrics": {"active_subscriptions": 12, "mrr": 64},
        }
    )
    event = store.record_webhook_event(
        {
            "api_version": "1.0",
            "event": {
                "id": "evt_12345abcde",
                "type": "INITIAL_PURCHASE",
                "app_user_id": "firebase_user_123",
                "product_id": "premium_monthly",
                "store": "app_store",
                "entitlement_ids": ["premium"],
            },
            "subscriber": {
                "subscriber_attributes": {
                    "affiliate_id": {"value": "creator_1", "updated_at_ms": 1}
                }
            },
        }
    )

    snapshot = json.loads(store.snapshot_path.read_text(encoding="utf-8"))
    events = store.list_recent_events(limit=5)
    overview_history = store.list_recent_overview_snapshots(limit=5)

    assert event["event_id"] == "evt_12345abcde"
    assert snapshot["overview"]["metrics"]["mrr"] == 64
    assert snapshot["users"]["firebase_user_123"]["last_event_type"] == "INITIAL_PURCHASE"
    assert events[-1]["event_type"] == "INITIAL_PURCHASE"
    assert overview_history[-1]["metrics"]["active_subscriptions"] == 12


def test_subscriber_snapshot_store_is_idempotent_for_duplicate_events(tmp_path: Path) -> None:
    store = SubscriberSnapshotStore(
        event_log_path=tmp_path / "events.jsonl",
        snapshot_path=tmp_path / "snapshot.json",
        overview_history_path=tmp_path / "overview-history.jsonl",
    )
    payload = {
        "event": {
            "id": "evt_duplicate",
            "type": "RENEWAL",
            "app_user_id": "user-1",
        }
    }

    first = store.record_webhook_event(payload)
    second = store.record_webhook_event(payload)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert len(store.list_recent_events(limit=10)) == 1


def test_transfer_and_alias_events_update_all_related_users(tmp_path: Path) -> None:
    store = SubscriberSnapshotStore(
        event_log_path=tmp_path / "events.jsonl",
        snapshot_path=tmp_path / "snapshot.json",
        overview_history_path=tmp_path / "overview-history.jsonl",
    )

    store.record_webhook_event(
        {
            "event": {
                "id": "evt_transfer",
                "type": "TRANSFER",
                "original_app_user_id": "orig-user",
                "aliases": ["alias-user"],
                "transferred_from": ["source-user"],
                "transferred_to": ["dest-user"],
                "product_id": "premium_yearly",
                "store": "app_store",
                "entitlement_ids": ["premium"],
            }
        }
    )

    snapshot = store.get_snapshot()

    for user_id in ["orig-user", "alias-user", "source-user", "dest-user"]:
        assert snapshot["users"][user_id]["last_event_id"] == "evt_transfer"
        assert snapshot["users"][user_id]["related_user_ids"]


def test_overview_history_is_append_only(tmp_path: Path) -> None:
    store = SubscriberSnapshotStore(
        event_log_path=tmp_path / "events.jsonl",
        snapshot_path=tmp_path / "snapshot.json",
        overview_history_path=tmp_path / "overview-history.jsonl",
    )

    store.record_overview_snapshot({"project_id": "proj", "metrics": {"mrr": 64}})
    store.record_overview_snapshot({"project_id": "proj", "metrics": {"mrr": 72}})

    entries = store.list_recent_overview_snapshots(limit=10)

    assert len(entries) == 2
    assert entries[-1]["metrics"]["mrr"] == 72


def test_refresh_subscriber_overview_persists_snapshot_and_history(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path)

    payload = refresh_subscriber_overview(runtime, {})

    assert payload["overview"]["metrics"]["active_subscriptions"] == 12
    snapshot = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["overview"]["metrics"]["mrr"] == 64

    history_payload = list_subscriber_overview_history(runtime, {"limit": 5})
    assert history_payload["entries"][-1]["metrics"]["active_trials"] == 14


def test_verify_revenuecat_webhook_authorization() -> None:
    assert verify_revenuecat_webhook_authorization(None, None) is True
    assert verify_revenuecat_webhook_authorization("Bearer ok", "Bearer ok") is True
    assert verify_revenuecat_webhook_authorization("Bearer wrong", "Bearer ok") is False
