"""Outbound webhook notifications for Slack/Discord (Team tier feature).

Sends event-driven alerts when:
- Listing health score drops below threshold
- RevenueCat metrics change significantly
- ASC review state transitions (via explicit calls from version tools)

Designed to be provider-agnostic: any HTTPS endpoint that accepts a POST with
a JSON body containing a "text" field works. That covers Slack incoming
webhooks, Discord webhooks (via ?wait=true&content= adapter), and generic
webhook receivers.

Reads configuration from env vars:
  ASC_NOTIFICATION_WEBHOOK_URL      The full webhook URL.
  ASC_NOTIFICATION_PROVIDER         One of: "slack" (default), "discord", "generic".
  ASC_NOTIFICATION_MIN_SEVERITY     One of: "info", "warning", "critical". Default "warning".

If ASC_NOTIFICATION_WEBHOOK_URL is unset, notifications no-op silently —
which matches the Free tier experience.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


def _format_slack(title: str, body: str, severity: str) -> dict[str, Any]:
    emoji = {"info": ":information_source:", "warning": ":warning:", "critical": ":rotating_light:"}.get(
        severity, ":information_source:"
    )
    return {
        "text": f"{emoji} *{title}*\n{body}",
    }


def _format_discord(title: str, body: str, severity: str) -> dict[str, Any]:
    emoji = {"info": "i", "warning": "!", "critical": "!!"}.get(severity, "i")
    return {"content": f"**[{emoji}] {title}**\n{body}"}


def _format_generic(title: str, body: str, severity: str) -> dict[str, Any]:
    return {"severity": severity, "title": title, "text": body}


class NotificationDispatcher:
    """Fire-and-forget outbound notification sender."""

    def __init__(
        self,
        *,
        webhook_url: str | None = None,
        provider: str = "slack",
        min_severity: str = "warning",
        session: requests.Session | None = None,
    ) -> None:
        self._webhook_url = webhook_url or os.environ.get("ASC_NOTIFICATION_WEBHOOK_URL", "").strip() or None
        self._provider = (provider or os.environ.get("ASC_NOTIFICATION_PROVIDER", "slack")).lower()
        self._min_severity = (
            min_severity or os.environ.get("ASC_NOTIFICATION_MIN_SEVERITY", "warning")
        ).lower()
        self._session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    def send(
        self,
        *,
        title: str,
        body: str,
        severity: str = "warning",
    ) -> dict[str, Any]:
        """Send a notification. Returns a result dict; never raises for network errors."""
        if not self.enabled:
            return {"ok": False, "skipped": True, "reason": "No webhook URL configured."}

        if _SEVERITY_ORDER.get(severity, 1) < _SEVERITY_ORDER.get(self._min_severity, 1):
            return {"ok": True, "skipped": True, "reason": f"Below min severity {self._min_severity!r}."}

        if self._provider == "discord":
            payload = _format_discord(title, body, severity)
        elif self._provider == "generic":
            payload = _format_generic(title, body, severity)
        else:
            payload = _format_slack(title, body, severity)

        try:
            response = self._session.post(
                self._webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            return {
                "ok": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "provider": self._provider,
            }
        except requests.RequestException as exc:
            logger.warning("Notification dispatch failed: %s", exc)
            return {"ok": False, "error": str(exc), "provider": self._provider}


def build_listing_health_alert(
    *,
    app_name: str,
    score: int,
    threshold: int,
    top_gaps: list[str],
) -> tuple[str, str, str]:
    severity = "critical" if score < max(threshold - 20, 0) else "warning"
    title = f"Listing health alert: {app_name} scored {score}/100"
    lines = [
        f"Health score {score} dropped below threshold {threshold}.",
        "",
        "Top gaps:",
        *[f"- {gap}" for gap in top_gaps[:5]],
    ]
    return title, "\n".join(lines), severity


def build_mrr_delta_alert(
    *,
    app_name: str,
    before_mrr: float,
    after_mrr: float,
    window_days: int,
) -> tuple[str, str, str]:
    pct = (
        (100.0 if after_mrr else 0.0)
        if before_mrr == 0
        else (after_mrr - before_mrr) / abs(before_mrr) * 100.0
    )
    direction = "up" if pct >= 0 else "down"
    severity = "critical" if abs(pct) >= 25 else "warning"
    title = f"MRR shift: {app_name} is {direction} {abs(pct):.1f}%"
    body = (
        f"Over the last {window_days} days, MRR moved from ${before_mrr:.2f} "
        f"to ${after_mrr:.2f} ({pct:+.1f}%)."
    )
    return title, body, severity
