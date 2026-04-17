"""Tests for the Google Play Console scaffolding."""

from __future__ import annotations

from tools.play import PLAY_TOOLS


def test_play_tools_all_return_not_implemented() -> None:
    assert len(PLAY_TOOLS) >= 5
    for tool in PLAY_TOOLS:
        assert tool.name.startswith("gpc_")
        payload = tool.handler(None, {})
        assert payload["ok"] is False
        assert payload["error"]["code"] == "not_implemented"


def test_play_tool_schemas_have_descriptions() -> None:
    for tool in PLAY_TOOLS:
        for prop_name, prop in tool.input_schema.get("properties", {}).items():
            assert "description" in prop, f"{tool.name}.{prop_name} missing description"


def test_play_tools_registered_in_all_tools() -> None:
    from tools import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    assert "gpc_get_app_listing" in names
    assert "gpc_update_listing" in names
    assert "gpc_get_listing_health" in names
