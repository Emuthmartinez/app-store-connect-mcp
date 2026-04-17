"""Tests for the scheduled reports module."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from reports import HealthReport, _compute_health_score, should_send_report


def test_health_score_no_gaps() -> None:
    assert _compute_health_score([]) == 100


def test_health_score_penalizes_by_severity() -> None:
    gaps = [
        {"severity": "high"},
        {"severity": "medium"},
        {"severity": "low"},
    ]
    # 100 - 20 - 10 - 5 = 65
    assert _compute_health_score(gaps) == 65


def test_health_score_floors_at_zero() -> None:
    gaps = [{"severity": "critical"} for _ in range(10)]
    assert _compute_health_score(gaps) == 0


def test_should_send_report_first_time() -> None:
    assert should_send_report(last_sent_at=None) is True


def test_should_send_report_within_cadence() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(days=2)
    assert should_send_report(last_sent_at=recent, now=now, cadence_days=7) is False


def test_should_send_report_past_cadence() -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=10)
    assert should_send_report(last_sent_at=old, now=now, cadence_days=7) is True


def test_health_report_markdown_render() -> None:
    report = HealthReport(
        app_name="Demo",
        bundle_id="com.demo",
        locale="en-US",
        score=75,
        gaps=[{"severity": "high", "area": "keywords", "reason": "missing"}],
        revenuecat={"metrics": {"active_subscriptions": 10, "active_trials": 5, "mrr": 200}},
        recent_changes=[
            {
                "operation": "update_keywords",
                "timestamp": "2026-03-01T12:00:00+00:00",
                "delta_pct": {"mrr": 12.5, "active_subscriptions": 8.3},
            }
        ],
        generated_at="2026-03-15T12:00:00+00:00",
    )
    md = report.to_markdown()
    assert "Demo" in md
    assert "75/100" in md
    assert "keywords" in md
    assert "update_keywords" in md
    assert "12.5" in md


def test_health_report_to_dict_roundtrip() -> None:
    report = HealthReport(
        app_name="A",
        bundle_id="b",
        locale="en-US",
        score=50,
        gaps=[],
        revenuecat=None,
        recent_changes=[],
        generated_at="2026-01-01T00:00:00+00:00",
    )
    payload = report.to_dict()
    assert payload["app_name"] == "A"
    assert payload["score"] == 50
