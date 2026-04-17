"""Tests for the change impact analysis tool."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from config import Settings
from tools.change_impact import get_change_impact_analysis


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_store_key_id="KEY",
        app_store_issuer_id="ISSUER",
        app_store_private_key="PEM",
        app_store_bundle_id="com.example.app",
        app_store_sku=None,
        app_store_apple_id=None,
        app_store_name=None,
        revenuecat_api_key=None,
        revenuecat_project_id=None,
        change_log_path=tmp_path / "changes.jsonl",
        revenuecat_event_log_path=tmp_path / "events.jsonl",
        revenuecat_snapshot_path=tmp_path / "snapshot.json",
        revenuecat_overview_history_path=tmp_path / "overview.jsonl",
    )


class _Runtime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


def _write_overview(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r) + "\n")


def test_change_impact_computes_deltas(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    change_time = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    # Freeze the logger's clock by writing the record manually.
    settings.change_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.change_log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": change_time.isoformat(),
                    "operation": "update_keywords",
                    "locale": "en-US",
                    "target": {"id": "loc-1"},
                    "before": {"keywords": "old,terms"},
                    "after": {"keywords": "new,terms"},
                    "revenuecat_metrics": {"metrics": {"mrr": 100}},
                },
                sort_keys=True,
            )
            + "\n"
        )

    # 7 days of "before" and "after" metrics.
    overview_records = []
    for d in range(-6, 0):
        ts = (change_time + timedelta(days=d)).isoformat()
        overview_records.append(
            {"timestamp": ts, "metrics": {"active_subscriptions": 100, "active_trials": 20, "mrr": 500}}
        )
    for d in range(1, 8):
        ts = (change_time + timedelta(days=d)).isoformat()
        overview_records.append(
            {"timestamp": ts, "metrics": {"active_subscriptions": 120, "active_trials": 25, "mrr": 600}}
        )
    _write_overview(settings.revenuecat_overview_history_path, overview_records)

    result = get_change_impact_analysis(_Runtime(settings), {"before_days": 7, "after_days": 7})

    assert result["ok"] is True
    assert result["analyzed"] == 1
    analysis = result["analyses"][0]
    assert analysis["operation"] == "update_keywords"
    assert analysis["delta_pct"]["mrr"] == 20.0  # 500 -> 600
    assert analysis["delta_pct"]["active_subscriptions"] == 20.0  # 100 -> 120
    assert "caveat" in result


def test_change_impact_empty_log(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    result = get_change_impact_analysis(_Runtime(settings), {})
    assert result["ok"] is True
    assert result["analyzed"] == 0
    assert result["analyses"] == []


def test_change_impact_rejects_invalid_window(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    result = get_change_impact_analysis(_Runtime(settings), {"before_days": 0})
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_window"


def test_change_impact_operation_filter(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    settings.change_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.change_log_path.open("a", encoding="utf-8") as handle:
        for op in ("update_keywords", "update_description"):
            handle.write(
                json.dumps(
                    {
                        "timestamp": datetime(2026, 3, 1, tzinfo=UTC).isoformat(),
                        "operation": op,
                        "locale": "en-US",
                        "target": {},
                        "before": {},
                        "after": {},
                        "revenuecat_metrics": None,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    result = get_change_impact_analysis(
        _Runtime(settings),
        {"operation": "update_keywords"},
    )
    assert result["analyzed"] == 1
    assert result["analyses"][0]["operation"] == "update_keywords"
