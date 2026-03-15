"""Analysis tools that combine listing state with monetization signals."""

from __future__ import annotations

from typing import Any

from tooling import ToolDefinition
from tools.shared import (
    build_keyword_string,
    get_listing_snapshot,
    keyword_length,
    normalize_keywords,
    require_locale,
)


BENCHMARK_NOTES = [
    {
        "lever": "paywall_model",
        "benchmark": "Hard paywall with a 14-21 day trial outperforms freemium in the EV analysis.",
    },
    {
        "lever": "pricing",
        "benchmark": "The EV analysis recommends moving toward $12.99/month and $79.99/year pricing.",
    },
    {
        "lever": "copy_positioning",
        "benchmark": "Listing copy should emphasize durable styling value rather than AI novelty.",
    },
    {
        "lever": "experimentation",
        "benchmark": "Everything should be instrumented for A/B testing because experiment-heavy apps outperform materially.",
    },
]


def _copy_gaps(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    subtitle = (snapshot["app_info_localization"].get("subtitle") or "").lower()
    keywords = (snapshot["version_localization"].get("keywords") or "").lower()
    description = snapshot["version_localization"].get("description") or ""
    promo = snapshot["version_localization"].get("promotionalText")

    if not promo:
        gaps.append(
            {
                "severity": "medium",
                "area": "promotional_text",
                "reason": "Promotional text is empty, so there is no low-risk surface for seasonal or experimental messaging.",
            }
        )

    if not any(term in subtitle for term in ("ai", "stylist", "outfit")):
        gaps.append(
            {
                "severity": "high",
                "area": "subtitle",
                "reason": "Subtitle does not surface AI or stylist intent, which weakens conversion-oriented search positioning.",
            }
        )

    if "ai" not in keywords and "stylist" not in keywords:
        gaps.append(
            {
                "severity": "high",
                "area": "keywords",
                "reason": "Keywords omit AI/stylist intent even though those are target ASO themes for this app.",
            }
        )

    first_fold = "\n".join(description.splitlines()[:3]).lower()
    if "wardrobe" not in first_fold and "outfit" not in first_fold:
        gaps.append(
            {
                "severity": "medium",
                "area": "description",
                "reason": "The first visible lines do not foreground wardrobe or outfit planning value strongly enough.",
            }
        )

    if snapshot["current_version"].get("appVersionState") in {"WAITING_FOR_REVIEW", "IN_REVIEW"}:
        gaps.append(
            {
                "severity": "medium",
                "area": "version_state",
                "reason": "The current version is already in review, so version-scoped metadata edits may conflict until a new editable version exists.",
            }
        )

    return gaps


def get_listing_health(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    snapshot = get_listing_snapshot(runtime, locale=locale, include_screenshots=True)
    revenuecat = runtime.revenuecat.get_overview()
    metrics = (revenuecat or {}).get("metrics", {})

    return {
        "ok": True,
        "locale": locale,
        "listing": snapshot,
        "revenuecat": revenuecat,
        "observations": {
            "copy_gaps": _copy_gaps(snapshot),
            "benchmark_notes": BENCHMARK_NOTES,
            "summary": {
                "active_subscriptions": metrics.get("active_subscriptions"),
                "active_trials": metrics.get("active_trials"),
                "mrr": metrics.get("mrr"),
            },
        },
    }


def suggest_keyword_updates(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    snapshot = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    current = snapshot["version_localization"].get("keywords") or ""
    normalized_current = normalize_keywords(current)
    revenuecat = runtime.revenuecat.get_overview()
    metrics = (revenuecat or {}).get("metrics", {})

    preferred = [
        "ai stylist",
        "ai outfit",
        "outfit planner",
        "wardrobe app",
        "closet app",
        "style planner",
        "wardrobe planner",
    ]
    proposed = build_keyword_string(preferred, limit=100)

    return {
        "ok": True,
        "locale": locale,
        "current_keywords": normalized_current,
        "current_keyword_char_count": keyword_length(current),
        "proposed_keywords": proposed,
        "proposed_keyword_char_count": len(proposed),
        "rationale": [
            "Shift toward AI and stylist intent that is missing from the current keyword set.",
            "Keep high-intent wardrobe and outfit-planning phrases while staying under Apple’s 100 character limit.",
            (
                "RevenueCat overview is currently reporting "
                f"{metrics.get('active_subscriptions')} active subscriptions and "
                f"{metrics.get('active_trials')} active trials, so discovery intent still needs to be tightened."
            )
            if revenuecat
            else "RevenueCat was not configured for this server session, so keyword advice is copy-driven only.",
        ],
    }


ANALYSIS_TOOLS = [
    ToolDefinition(
        name="get_listing_health",
        description=(
            "Pull the current listing plus RevenueCat overview metrics and compare them "
            "against conversion-oriented listing heuristics."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=get_listing_health,
    ),
    ToolDefinition(
        name="suggest_keyword_updates",
        description="Suggest a new keyword set based on the current listing and RevenueCat overview signals.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=suggest_keyword_updates,
    ),
]
