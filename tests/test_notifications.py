"""Tests for the notifications dispatcher."""

from __future__ import annotations

from typing import Any

from notifications import (
    NotificationDispatcher,
    build_listing_health_alert,
    build_mrr_delta_alert,
)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeSession:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []

    def post(self, url, *, data, headers, timeout):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return _FakeResponse(self.status_code)


def test_notification_disabled_when_no_url() -> None:
    dispatcher = NotificationDispatcher(webhook_url=None)
    assert dispatcher.enabled is False
    result = dispatcher.send(title="t", body="b")
    assert result["ok"] is False
    assert result["skipped"] is True


def test_notification_sends_to_slack() -> None:
    session = _FakeSession()
    dispatcher = NotificationDispatcher(
        webhook_url="https://hooks.slack.com/test",
        provider="slack",
        min_severity="info",
        session=session,
    )
    result = dispatcher.send(title="Health drop", body="score 42", severity="warning")
    assert result["ok"] is True
    assert len(session.calls) == 1
    assert b"Health drop" in session.calls[0]["data"]


def test_notification_respects_min_severity() -> None:
    session = _FakeSession()
    dispatcher = NotificationDispatcher(
        webhook_url="https://hooks.slack.com/test",
        min_severity="critical",
        session=session,
    )
    result = dispatcher.send(title="t", body="b", severity="warning")
    assert result["skipped"] is True
    assert len(session.calls) == 0


def test_build_listing_health_alert_critical_below_threshold() -> None:
    title, body, severity = build_listing_health_alert(
        app_name="Demo",
        score=30,
        threshold=60,
        top_gaps=["keywords missing"],
    )
    assert "Demo" in title
    assert "keywords missing" in body
    assert severity == "critical"


def test_build_mrr_delta_alert_critical_on_large_drop() -> None:
    title, body, severity = build_mrr_delta_alert(
        app_name="Demo",
        before_mrr=1000.0,
        after_mrr=700.0,
        window_days=7,
    )
    assert "down" in title
    assert severity == "critical"
    assert "7" in body
