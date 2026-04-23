"""Tests for MCP payload contracts and screenshot upload validation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import index
from errors import AscApiError
from tools.shared import extract_screenshot_upload_contract
from tools import write as write_tools


def test_unknown_tool_returns_failed_completion_contract() -> None:
    response = asyncio.run(index.call_tool("not_a_real_tool", {}))
    payload = json.loads(response[0].text)

    assert payload["ok"] is False
    assert payload["error"]["code"] == "unknown_tool"
    assert payload["completion_state"] == "failed"
    assert payload["should_continue"] is True


class FakeAsc:
    def create_screenshot_reservation(
        self,
        screenshot_set_id: str,
        *,
        file_name: str,
        file_size: int,
    ) -> dict:
        del screenshot_set_id, file_name, file_size
        return {"data": {"attributes": {"uploadOperations": [{"url": "https://upload"}]}}}

    def execute_upload_operations(self, operations: list[dict], file_path: str) -> list[dict]:
        del operations, file_path
        raise AssertionError("upload should not run when the reservation is malformed")

    def finalize_screenshot_upload(self, screenshot_id: str, file_path: str) -> dict:
        del screenshot_id, file_path
        raise AssertionError("finalize should not run when the reservation is malformed")


class FakeRuntime:
    def __init__(self) -> None:
        self.asc = FakeAsc()


def test_upload_screenshot_rejects_reservation_without_screenshot_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "shot.png"
    file_path.write_bytes(b"fake image payload")

    snapshot = {
        "version_localization": {"id": "version-loc"},
        "screenshot_sets": [{"id": "set-1", "display_type": "APP_IPHONE_67"}],
    }

    monkeypatch.setattr(write_tools, "get_listing_snapshot", lambda *args, **kwargs: snapshot)

    with pytest.raises(AscApiError) as exc_info:
        write_tools.upload_screenshot(
            FakeRuntime(),
            {
                "locale": "en-US",
                "display_type": "APP_IPHONE_67",
                "file_path": str(file_path),
            },
        )

    assert exc_info.value.status_code == 502
    assert "screenshot id" in exc_info.value.message


def test_upload_contract_rejects_missing_upload_operations() -> None:
    with pytest.raises(AscApiError) as exc_info:
        extract_screenshot_upload_contract({"data": {"id": "shot-1", "attributes": {}}})

    assert exc_info.value.status_code == 502
    assert "upload operations" in exc_info.value.message


# ---------------------------------------------------------------------------
# Regression tests for Apple JSON:API attribute names on write handlers.
#
# Apple's App Store Connect API rejects requests that use unknown attribute
# names with ENTITY_ERROR.ATTRIBUTE.UNKNOWN. Every update_* handler must send
# the exact camelCase attribute name Apple expects; prefixing it (e.g.
# "asc_description") is a silent-bug pattern that only surfaces against the
# live API. The tests below pin the attribute name each handler sends through
# to the client so the next regression is caught at unit-test time.
# ---------------------------------------------------------------------------


class CapturingAsc:
    """Fake ASC client that records the attributes dict passed to update_*.

    Exposes two capture slots so a single handler exercise cycle can touch
    either update_version_localization or update_app_info_localization
    without ambiguity.
    """

    def __init__(self) -> None:
        self.version_localization_calls: list[tuple[str, dict]] = []
        self.app_info_localization_calls: list[tuple[str, dict]] = []

    def update_version_localization(self, localization_id: str, attributes: dict) -> dict:
        self.version_localization_calls.append((localization_id, dict(attributes)))
        return {"data": {"id": localization_id, "attributes": dict(attributes)}}

    def update_app_info_localization(self, localization_id: str, attributes: dict) -> dict:
        self.app_info_localization_calls.append((localization_id, dict(attributes)))
        return {"data": {"id": localization_id, "attributes": dict(attributes)}}


class CapturingRuntime:
    def __init__(self) -> None:
        self.asc = CapturingAsc()


def _install_snapshot_and_log_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass live snapshot reads and mutation logging for handler unit tests."""
    snapshot = {
        "version_localization": {"id": "version-loc-id"},
        "app_info_localization": {"id": "app-info-loc-id"},
    }
    monkeypatch.setattr(
        write_tools,
        "get_listing_snapshot",
        lambda *args, **kwargs: snapshot,
    )
    monkeypatch.setattr(
        write_tools,
        "log_mutation",
        lambda *args, **kwargs: None,
    )


# Attribute names Apple's JSON:API expects for each handler. Prefixing any of
# these (e.g. "asc_description") triggers ENTITY_ERROR.ATTRIBUTE.UNKNOWN.
# See: https://developer.apple.com/documentation/appstoreconnectapi
APPLE_ATTRIBUTE_NAMES = {
    "description": "description",
    "keywords": "keywords",
    "subtitle": "subtitle",
    "promotional_text": "promotionalText",
    "whats_new": "whatsNew",
}


def test_update_description_sends_apple_attribute_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_description(
        runtime,
        {"locale": "en-US", "description": "hello world"},
    )

    assert len(runtime.asc.version_localization_calls) == 1
    _, attributes = runtime.asc.version_localization_calls[0]
    assert APPLE_ATTRIBUTE_NAMES["description"] in attributes
    assert attributes[APPLE_ATTRIBUTE_NAMES["description"]] == "hello world"
    # Guard against the historical 'asc_' prefix regression.
    assert "asc_description" not in attributes


def test_update_keywords_sends_apple_attribute_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_keywords(
        runtime,
        {"locale": "en-US", "keywords": "wardrobe,fashion,weather"},
    )

    assert len(runtime.asc.version_localization_calls) == 1
    _, attributes = runtime.asc.version_localization_calls[0]
    assert APPLE_ATTRIBUTE_NAMES["keywords"] in attributes
    assert attributes[APPLE_ATTRIBUTE_NAMES["keywords"]] == "wardrobe,fashion,weather"
    assert "asc_keywords" not in attributes


def test_update_subtitle_sends_apple_attribute_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_subtitle(
        runtime,
        {"locale": "en-US", "subtitle": "AI stylist for your closet"},
    )

    assert len(runtime.asc.app_info_localization_calls) == 1
    _, attributes = runtime.asc.app_info_localization_calls[0]
    assert APPLE_ATTRIBUTE_NAMES["subtitle"] in attributes
    assert attributes[APPLE_ATTRIBUTE_NAMES["subtitle"]] == "AI stylist for your closet"
    assert "asc_subtitle" not in attributes


def test_update_promotional_text_sends_apple_attribute_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_promotional_text(
        runtime,
        {"locale": "en-US", "promotional_text": "Plan your week of outfits."},
    )

    assert len(runtime.asc.version_localization_calls) == 1
    _, attributes = runtime.asc.version_localization_calls[0]
    assert APPLE_ATTRIBUTE_NAMES["promotional_text"] in attributes
    assert (
        attributes[APPLE_ATTRIBUTE_NAMES["promotional_text"]]
        == "Plan your week of outfits."
    )


def test_update_promotional_text_clears_field_with_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_promotional_text(
        runtime,
        {"locale": "en-US", "promotional_text": None},
    )

    _, attributes = runtime.asc.version_localization_calls[0]
    assert attributes[APPLE_ATTRIBUTE_NAMES["promotional_text"]] is None


def test_update_whats_new_sends_apple_attribute_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_whats_new(
        runtime,
        {"locale": "en-US", "whats_new": "Release notes"},
    )

    assert len(runtime.asc.version_localization_calls) == 1
    _, attributes = runtime.asc.version_localization_calls[0]
    assert APPLE_ATTRIBUTE_NAMES["whats_new"] in attributes
    assert attributes[APPLE_ATTRIBUTE_NAMES["whats_new"]] == "Release notes"


def test_no_write_handler_sends_asc_prefixed_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch-all: no update_* handler may send an 'asc_' prefixed attribute.

    If a future contributor copies an existing handler and forgets to convert
    the field name to Apple's camelCase, this test fires before the broken
    payload ever reaches production.
    """
    _install_snapshot_and_log_stubs(monkeypatch)
    runtime = CapturingRuntime()

    write_tools.update_description(runtime, {"locale": "en-US", "description": "x"})
    write_tools.update_keywords(runtime, {"locale": "en-US", "keywords": "x"})
    write_tools.update_subtitle(runtime, {"locale": "en-US", "subtitle": "x"})
    write_tools.update_promotional_text(
        runtime, {"locale": "en-US", "promotional_text": "x"}
    )
    write_tools.update_whats_new(runtime, {"locale": "en-US", "whats_new": "x"})

    all_calls = (
        runtime.asc.version_localization_calls
        + runtime.asc.app_info_localization_calls
    )
    for _, attributes in all_calls:
        asc_prefixed = [key for key in attributes if key.startswith("asc_")]
        assert not asc_prefixed, (
            f"Handler sent asc_-prefixed attribute(s) {asc_prefixed}; "
            "Apple's API rejects these with ENTITY_ERROR.ATTRIBUTE.UNKNOWN."
        )
