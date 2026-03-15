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
