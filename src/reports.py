"""Scheduled listing health report generator.

Produces a weekly report combining:
- Current listing health snapshot (from tools.analysis.get_listing_health)
- Recent change impact deltas (from tools.change_impact)
- RevenueCat metrics trend (from change_log.jsonl + overview history)

The report is rendered to Markdown and/or plain text so it can be emailed,
posted to Slack, or persisted to disk. This module provides the generation
primitives — scheduling (cron, Celery, whatever) is an integration concern
handled by the hosted cloud service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from tools.analysis import get_listing_health
from tools.change_impact import get_change_impact_analysis


@dataclass(slots=True)
class HealthReport:
    app_name: str
    bundle_id: str
    locale: str
    score: int
    gaps: list[dict[str, Any]]
    revenuecat: dict[str, Any] | None
    recent_changes: list[dict[str, Any]]
    generated_at: str

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append("# Weekly App Store Health Report")
        lines.append("")
        lines.append(f"**App:** {self.app_name} ({self.bundle_id})")
        lines.append(f"**Locale:** {self.locale}")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append(f"**Health Score:** {self.score}/100")
        lines.append("")

        if self.revenuecat:
            metrics = self.revenuecat.get("metrics") or {}
            lines.append("## Revenue Snapshot")
            lines.append("")
            lines.append(f"- Active subscriptions: {metrics.get('active_subscriptions')}")
            lines.append(f"- Active trials: {metrics.get('active_trials')}")
            lines.append(f"- MRR: ${metrics.get('mrr')}")
            lines.append("")

        lines.append("## Listing Gaps")
        lines.append("")
        if not self.gaps:
            lines.append("_No gaps detected this week. Nice._")
        else:
            for gap in self.gaps:
                severity = gap.get("severity", "unknown")
                area = gap.get("area", "unknown")
                reason = gap.get("reason", "")
                lines.append(f"- **[{severity}] {area}** — {reason}")
        lines.append("")

        lines.append("## Recent Changes & Revenue Correlation")
        lines.append("")
        if not self.recent_changes:
            lines.append("_No recent listing mutations to analyze._")
        else:
            for change in self.recent_changes[:5]:
                delta = change.get("delta_pct") or {}
                mrr_delta = delta.get("mrr")
                subs_delta = delta.get("active_subscriptions")
                lines.append(
                    f"- `{change.get('operation')}` at {change.get('timestamp')} — "
                    f"MRR Δ {mrr_delta if mrr_delta is not None else 'n/a'}%, "
                    f"subs Δ {subs_delta if subs_delta is not None else 'n/a'}%"
                )
        lines.append("")
        lines.append("---")
        lines.append("_Correlations are signals, not proof. Investigate before acting._")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "bundle_id": self.bundle_id,
            "locale": self.locale,
            "score": self.score,
            "gaps": self.gaps,
            "revenuecat": self.revenuecat,
            "recent_changes": self.recent_changes,
            "generated_at": self.generated_at,
        }


def _compute_health_score(gaps: list[dict[str, Any]]) -> int:
    """Simple 0-100 score: start at 100, subtract per gap weighted by severity."""
    weights = {"critical": 30, "high": 20, "medium": 10, "low": 5}
    penalty = sum(weights.get(g.get("severity", "medium"), 10) for g in gaps)
    return max(0, min(100, 100 - penalty))


def generate_health_report(runtime: Any, *, locale: str = "en-US") -> HealthReport:
    """Generate a full report from live runtime state."""
    health = get_listing_health(runtime, {"locale": locale})
    listing = health.get("listing", {}) or {}
    app = listing.get("app", {}) or {}
    gaps = (health.get("observations") or {}).get("copy_gaps") or []

    impact = get_change_impact_analysis(runtime, {"limit": 10, "before_days": 7, "after_days": 7})
    analyses = impact.get("analyses") or []

    return HealthReport(
        app_name=app.get("name") or "Unknown App",
        bundle_id=app.get("bundle_id") or "unknown",
        locale=locale,
        score=_compute_health_score(gaps),
        gaps=gaps,
        revenuecat=health.get("revenuecat"),
        recent_changes=analyses,
        generated_at=datetime.now(UTC).isoformat(),
    )


def should_send_report(
    *,
    last_sent_at: datetime | None,
    now: datetime | None = None,
    cadence_days: int = 7,
) -> bool:
    """Decide whether a report is due. Used by the scheduler."""
    now = now or datetime.now(UTC)
    if last_sent_at is None:
        return True
    return now - last_sent_at >= timedelta(days=cadence_days)
