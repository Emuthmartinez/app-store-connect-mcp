"""Change impact analysis: correlate listing mutations with RevenueCat metrics.

This is the revenue-correlation moat. By reading the append-only change log
(populated by log_mutation on every write tool) and the RevenueCat overview
history (populated by the webhook listener and polling), we can show which
listing edits preceded subscription lifts or drops.

Correlation, not causation. We always surface the caveat in the payload.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tooling import ToolDefinition

_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

_WRITE_OPERATIONS = {
    "update_description",
    "update_keywords",
    "update_subtitle",
    "update_promotional_text",
    "update_whats_new",
    "upload_screenshot",
    "submit_for_review",
    "release_app_store_version",
    "assign_build_to_version",
    "create_product_page_optimization_experiment",
    "create_custom_product_page",
    "create_custom_product_page_version",
    "create_custom_product_page_localization",
    "upload_custom_product_page_screenshot",
    "api_post",
    "api_patch",
    "api_delete",
}


@dataclass(slots=True)
class _OverviewPoint:
    timestamp: datetime
    active_subscriptions: int | None
    active_trials: int | None
    mrr: float | None


def _parse_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return records


def _load_overview_history(path: Path) -> list[_OverviewPoint]:
    points: list[_OverviewPoint] = []
    for record in _read_jsonl(path):
        ts = _parse_timestamp(record.get("timestamp") or record.get("recorded_at"))
        if ts is None:
            continue
        metrics = record.get("metrics") or {}
        if not isinstance(metrics, dict):
            continue
        points.append(
            _OverviewPoint(
                timestamp=ts,
                active_subscriptions=_coerce_int(metrics.get("active_subscriptions")),
                active_trials=_coerce_int(metrics.get("active_trials")),
                mrr=_coerce_float(metrics.get("mrr")),
            )
        )
    points.sort(key=lambda p: p.timestamp)
    return points


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _window_average(
    points: list[_OverviewPoint],
    *,
    center: datetime,
    before_days: int,
    after_days: int,
    side: str,
) -> dict[str, float | None]:
    if side == "before":
        start = center - timedelta(days=before_days)
        end = center
    else:
        start = center
        end = center + timedelta(days=after_days)

    in_window = [p for p in points if start <= p.timestamp <= end]
    if not in_window:
        return {
            "sample_size": 0,
            "active_subscriptions_avg": None,
            "active_trials_avg": None,
            "mrr_avg": None,
        }

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    subs = [p.active_subscriptions for p in in_window if p.active_subscriptions is not None]
    trials = [p.active_trials for p in in_window if p.active_trials is not None]
    mrrs = [p.mrr for p in in_window if p.mrr is not None]

    return {
        "sample_size": len(in_window),
        "active_subscriptions_avg": _avg([float(v) for v in subs]),
        "active_trials_avg": _avg([float(v) for v in trials]),
        "mrr_avg": _avg(mrrs),
    }


def _pct_change(before: float | None, after: float | None) -> float | None:
    if before is None or after is None:
        return None
    if before == 0:
        return None
    return round(((after - before) / abs(before)) * 100.0, 2)


def _summarize_change(record: dict[str, Any]) -> dict[str, Any]:
    before = record.get("before") or {}
    after = record.get("after") or {}
    summary: dict[str, Any] = {}
    if isinstance(before, dict) and isinstance(after, dict):
        common_keys = set(before.keys()) | set(after.keys())
        interesting_keys = {"keywords", "subtitle", "description", "promotionalText", "whatsNew"}
        for key in common_keys & interesting_keys:
            if before.get(key) != after.get(key):
                summary[key] = {
                    "before": before.get(key),
                    "after": after.get(key),
                }
    return summary


def get_change_impact_analysis(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    before_days_raw = arguments.get("before_days")
    after_days_raw = arguments.get("after_days")
    before_days = int(before_days_raw) if before_days_raw is not None else 7
    after_days = int(after_days_raw) if after_days_raw is not None else 7
    operation_filter = arguments.get("operation")
    locale_filter = arguments.get("locale")
    limit = int(arguments.get("limit") or 20)

    if before_days <= 0 or after_days <= 0:
        return {
            "ok": False,
            "error": {
                "code": "invalid_window",
                "message": "before_days and after_days must be positive integers.",
                "retryable": False,
            },
        }

    settings = runtime.settings
    change_records = _read_jsonl(settings.change_log_path)
    mutations = [r for r in change_records if r.get("operation") in _WRITE_OPERATIONS]

    if operation_filter:
        mutations = [r for r in mutations if r.get("operation") == operation_filter]
    if locale_filter:
        mutations = [r for r in mutations if r.get("locale") == locale_filter]

    overview_path = settings.revenuecat_overview_history_path
    overview_points = _load_overview_history(overview_path)

    analyses: list[dict[str, Any]] = []
    for record in mutations[-limit:][::-1]:
        ts = _parse_timestamp(record.get("timestamp"))
        if ts is None:
            continue
        before_window = _window_average(
            overview_points,
            center=ts,
            before_days=before_days,
            after_days=after_days,
            side="before",
        )
        after_window = _window_average(
            overview_points,
            center=ts,
            before_days=before_days,
            after_days=after_days,
            side="after",
        )
        analyses.append(
            {
                "operation": record.get("operation"),
                "locale": record.get("locale"),
                "timestamp": record.get("timestamp"),
                "target": record.get("target"),
                "change_summary": _summarize_change(record),
                "metrics_before": before_window,
                "metrics_after": after_window,
                "delta_pct": {
                    "active_subscriptions": _pct_change(
                        before_window["active_subscriptions_avg"],
                        after_window["active_subscriptions_avg"],
                    ),
                    "active_trials": _pct_change(
                        before_window["active_trials_avg"],
                        after_window["active_trials_avg"],
                    ),
                    "mrr": _pct_change(
                        before_window["mrr_avg"],
                        after_window["mrr_avg"],
                    ),
                },
                "metrics_at_change": record.get("revenuecat_metrics"),
            }
        )

    return {
        "ok": True,
        "window": {"before_days": before_days, "after_days": after_days},
        "total_mutations_in_log": len(mutations),
        "analyzed": len(analyses),
        "overview_samples_available": len(overview_points),
        "analyses": analyses,
        "caveat": (
            "These deltas are correlational, not causal. App Store ranking shifts, "
            "marketing campaigns, seasonality, and many other factors can move "
            "RevenueCat metrics during the same window. Use this as a signal to "
            "investigate, not as proof."
        ),
    }


CHANGE_IMPACT_TOOLS = [
    ToolDefinition(
        name="asc_get_change_impact_analysis",
        description=(
            "Correlate listing mutations with RevenueCat overview metrics. For each "
            "recent write operation, compute the average active_subscriptions, "
            "active_trials, and mrr in the N days before and N days after the change, "
            "and return the percent delta. Useful for spotting which listing edits "
            "preceded subscription lifts or drops. Always review the caveat — these "
            "are correlations, not causal proofs."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "before_days": {
                    "type": "integer",
                    "description": "How many days of RevenueCat history to average before each change. Default 7.",
                    "minimum": 1,
                    "maximum": 90,
                },
                "after_days": {
                    "type": "integer",
                    "description": "How many days of RevenueCat history to average after each change. Default 7.",
                    "minimum": 1,
                    "maximum": 90,
                },
                "operation": {
                    "type": "string",
                    "description": "Optional filter to restrict to a single operation (e.g. update_keywords).",
                },
                "locale": {
                    "type": "string",
                    "description": "Optional BCP 47 locale filter (e.g. en-US).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recent mutations to analyze. Default 20.",
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "additionalProperties": False,
        },
        handler=get_change_impact_analysis,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
]
