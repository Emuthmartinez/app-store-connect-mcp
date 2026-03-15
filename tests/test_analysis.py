"""Tests for analysis tools."""

from __future__ import annotations

from pathlib import Path

from change_log import ChangeLogger
from config import Settings
from tools.analysis import get_listing_health, suggest_keyword_updates


class FakeAsc:
    def get_configured_app(self):
        return {
            "id": "6502372228",
            "attributes": {
                "name": "Example App",
                "bundleId": "com.example.app",
                "sku": "com.example.app",
                "primaryLocale": "en-US",
            },
        }

    def get_primary_app_info(self):
        return {"id": "app-info", "attributes": {"appStoreState": "READY_FOR_SALE", "state": "READY"}}

    def get_app_info_localizations(self, app_info_id: str):
        del app_info_id
        return [
            {
                "id": "info-loc",
                "attributes": {
                    "locale": "en-US",
                    "subtitle": "Weekly Outfit Planner",
                },
            }
        ]

    def get_current_version(self):
        return {
            "id": "version-id",
            "attributes": {
                "versionString": "1.0.48",
                "appVersionState": "WAITING_FOR_REVIEW",
            },
        }

    def get_version_localizations(self, version_id: str):
        del version_id
        return [
            {
                "id": "version-loc",
                "attributes": {
                    "locale": "en-US",
                    "description": "Plan your outfits for the week.\nFeel good fast.\nNo promo.",
                    "keywords": "outfit planner,closet app",
                    "promotionalText": None,
                    "whatsNew": "Bug fixes",
                },
            }
        ]

    def get_screenshot_sets(self, version_localization_id: str):
        del version_localization_id
        return []

    def get_screenshots(self, screenshot_set_id: str):
        del screenshot_set_id
        return []

    def find_locale(self, resources, locale: str):
        for resource in resources:
            if resource["attributes"]["locale"] == locale:
                return resource
        raise AssertionError("locale not found")


class FakeRevenueCat:
    def get_overview(self):
        return {
            "project_id": "proj5711c0c0",
            "metrics": {
                "active_subscriptions": 11,
                "active_trials": 13,
                "mrr": 50,
            },
        }


class Runtime:
    def __init__(self) -> None:
        self.asc = FakeAsc()
        self.revenuecat = FakeRevenueCat()
        self.settings = Settings(
            app_store_key_id="KEY1234567",
            app_store_issuer_id="issuer-id",
            app_store_private_key="-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----",
            app_store_bundle_id="example.bundle",
            app_store_sku="example.bundle",
            app_store_apple_id="123456789",
            app_store_name="Example",
            revenuecat_api_key="sk_test",
            revenuecat_project_id="proj",
            change_log_path=Path("/tmp/changes.jsonl"),
        )
        self.change_logger = ChangeLogger(self.settings.change_log_path)


def test_keyword_suggestion_stays_within_apple_limit(monkeypatch) -> None:
    monkeypatch.setenv("ASC_PREFERRED_KEYWORDS", '["ai stylist", "outfit planner", "wardrobe app"]')
    payload = suggest_keyword_updates(Runtime(), {"locale": "en-US"})

    assert payload["proposed_keyword_char_count"] <= 100
    assert "ai stylist" in payload["proposed_keywords"]


def test_keyword_suggestion_without_config() -> None:
    payload = suggest_keyword_updates(Runtime(), {"locale": "en-US"})

    assert payload["proposed_keywords"] is None
    assert "ASC_PREFERRED_KEYWORDS" in payload["note"]


def test_listing_health_flags_missing_promotional_text() -> None:
    payload = get_listing_health(Runtime(), {"locale": "en-US"})
    reasons = [gap["area"] for gap in payload["observations"]["copy_gaps"]]

    assert "promotional_text" in reasons
    assert payload["observations"]["summary"]["active_subscriptions"] == 11
