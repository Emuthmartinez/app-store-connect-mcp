"""Tests for the diagnostics tool."""

from __future__ import annotations

from pathlib import Path

from config import Settings
from tools.diagnostics import test_connection as run_connection_check


class _TokenProvider:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def get_token(self, force_refresh: bool = False) -> str:
        del force_refresh
        if self._should_fail:
            raise RuntimeError("bad key")
        return "tok"


class _Asc:
    def __init__(self, token_provider, app=None, should_fail_app: bool = False) -> None:
        self._token_provider = token_provider
        self._app = app or {
            "id": "123",
            "attributes": {"name": "Demo", "bundleId": "com.demo", "primaryLocale": "en-US"},
        }
        self._should_fail_app = should_fail_app

    def get_configured_app(self):
        if self._should_fail_app:
            raise RuntimeError("app lookup failed")
        return self._app


class _RevenueCat:
    def __init__(self, overview=None) -> None:
        self._overview = overview

    def get_overview(self):
        return self._overview


class _Runtime:
    def __init__(self, *, settings, asc, revenuecat) -> None:
        self.settings = settings
        self.asc = asc
        self.revenuecat = revenuecat


def _make_settings(tmp_path: Path, *, with_rc: bool = False) -> Settings:
    return Settings(
        app_store_key_id="KEY",
        app_store_issuer_id="ISSUER",
        app_store_private_key="PEM",
        app_store_bundle_id="com.example.app",
        app_store_sku=None,
        app_store_apple_id=None,
        app_store_name=None,
        revenuecat_api_key="sk" if with_rc else None,
        revenuecat_project_id="proj" if with_rc else None,
        change_log_path=tmp_path / "changes.jsonl",
        revenuecat_event_log_path=tmp_path / "events.jsonl",
        revenuecat_snapshot_path=tmp_path / "snapshot.json",
        revenuecat_overview_history_path=tmp_path / "overview.jsonl",
    )


def test_diagnostic_all_green(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    runtime = _Runtime(
        settings=settings,
        asc=_Asc(_TokenProvider()),
        revenuecat=_RevenueCat(),
    )
    result = run_connection_check(runtime, {})
    assert result["ok"] is True
    by_name = {c["name"]: c for c in result["checks"]}
    assert by_name["asc_credentials_configured"]["ok"] is True
    assert by_name["asc_jwt_mint"]["ok"] is True
    assert by_name["asc_app_lookup"]["ok"] is True
    assert by_name["revenuecat_overview"]["configured"] is False


def test_diagnostic_missing_credentials(tmp_path: Path) -> None:
    settings = Settings(
        app_store_key_id="",
        app_store_issuer_id="",
        app_store_private_key="",
        app_store_bundle_id="",
        app_store_sku=None,
        app_store_apple_id=None,
        app_store_name=None,
        revenuecat_api_key=None,
        revenuecat_project_id=None,
        change_log_path=tmp_path / "changes.jsonl",
    )
    runtime = _Runtime(
        settings=settings,
        asc=_Asc(_TokenProvider()),
        revenuecat=_RevenueCat(),
    )
    result = run_connection_check(runtime, {})
    assert result["ok"] is False


def test_diagnostic_revenuecat_failure_fails_overall(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path, with_rc=True)

    class _BrokenRc:
        def get_overview(self):
            raise RuntimeError("401")

    runtime = _Runtime(
        settings=settings,
        asc=_Asc(_TokenProvider()),
        revenuecat=_BrokenRc(),
    )
    result = run_connection_check(runtime, {})
    assert result["ok"] is False
    rc_check = next(c for c in result["checks"] if c["name"] == "revenuecat_overview")
    assert rc_check["ok"] is False
    assert rc_check["configured"] is True
