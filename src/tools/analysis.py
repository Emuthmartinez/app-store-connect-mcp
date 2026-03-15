"""Analysis tools that combine listing state with monetization signals."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from tooling import ToolDefinition

logger = logging.getLogger(__name__)
from tools.shared import (
    build_keyword_string,
    get_listing_snapshot,
    keyword_length,
    normalize_keywords,
    require_locale,
)

_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


@lru_cache(maxsize=16)
def _load_json_env(env_var: str, expected_type: type) -> Any:
    """Load and validate JSON from an environment variable. Cached for the process lifetime."""
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, expected_type):
            return value
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _copy_gaps(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    subtitle = (snapshot["app_info_localization"].get("subtitle") or "").lower()
    keywords = (snapshot["version_localization"].get("keywords") or "").lower()
    promo = snapshot["version_localization"].get("promotionalText")

    if not promo:
        gaps.append(
            {
                "severity": "medium",
                "area": "promotional_text",
                "reason": "Promotional text is empty, so there is no low-risk surface for seasonal or experimental messaging.",
            }
        )

    copy_terms = _load_json_env("ASC_COPY_TERMS", dict) or {}
    subtitle_terms = copy_terms.get("subtitle", [])
    if subtitle_terms and not any(term.lower() in subtitle for term in subtitle_terms):
        gaps.append(
            {
                "severity": "high",
                "area": "subtitle",
                "reason": f"Subtitle does not contain any of the configured target terms: {', '.join(subtitle_terms)}.",
            }
        )

    keyword_terms = copy_terms.get("keywords", [])
    if keyword_terms and not any(term.lower() in keywords for term in keyword_terms):
        gaps.append(
            {
                "severity": "high",
                "area": "keywords",
                "reason": f"Keywords omit configured target terms: {', '.join(keyword_terms)}.",
            }
        )

    description = snapshot["version_localization"].get("description") or ""
    description_terms = copy_terms.get("description_first_fold", [])
    if description_terms:
        first_fold = "\n".join(description.splitlines()[:3]).lower()
        if not any(term.lower() in first_fold for term in description_terms):
            gaps.append(
                {
                    "severity": "medium",
                    "area": "description",
                    "reason": f"The first visible lines do not foreground configured terms: {', '.join(description_terms)}.",
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
            "benchmark_notes": _load_json_env("ASC_BENCHMARK_NOTES", list) or [],
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

    preferred = _load_json_env("ASC_PREFERRED_KEYWORDS", list) or []
    if not preferred:
        return {
            "ok": True,
            "locale": locale,
            "current_keywords": normalized_current,
            "current_keyword_char_count": keyword_length(current),
            "proposed_keywords": None,
            "note": (
                "No preferred keywords configured. Set ASC_PREFERRED_KEYWORDS as a JSON array "
                "of keyword strings to enable keyword suggestions."
            ),
        }

    proposed = build_keyword_string(preferred, limit=100)

    rationale = [
        "Proposed keywords are drawn from the configured ASC_PREFERRED_KEYWORDS list.",
        "Keywords are packed to stay under Apple's 100 character limit.",
    ]
    if revenuecat:
        rationale.append(
            f"RevenueCat overview is currently reporting "
            f"{metrics.get('active_subscriptions')} active subscriptions and "
            f"{metrics.get('active_trials')} active trials."
        )
    else:
        rationale.append(
            "RevenueCat was not configured for this server session, so keyword advice is copy-driven only."
        )

    return {
        "ok": True,
        "locale": locale,
        "current_keywords": normalized_current,
        "current_keyword_char_count": keyword_length(current),
        "proposed_keywords": proposed,
        "proposed_keyword_char_count": len(proposed),
        "rationale": rationale,
    }


ANALYSIS_TOOLS = [
    ToolDefinition(
        name="asc_get_listing_health",
        description=(
            "Pull the current listing plus RevenueCat overview metrics and compare them "
            "against conversion-oriented listing heuristics. Configure heuristics via "
            "ASC_COPY_TERMS and ASC_BENCHMARK_NOTES environment variables."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "locale": {
                    "type": "string",
                    "description": "BCP 47 locale code, e.g. en-US, ja, de-DE.",
                },
            },
            "additionalProperties": False,
        },
        handler=get_listing_health,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    ToolDefinition(
        name="asc_suggest_keyword_updates",
        description=(
            "Suggest a new keyword set based on the current listing and RevenueCat overview signals. "
            "Configure preferred keywords via the ASC_PREFERRED_KEYWORDS environment variable."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "locale": {
                    "type": "string",
                    "description": "BCP 47 locale code, e.g. en-US, ja, de-DE.",
                },
            },
            "additionalProperties": False,
        },
        handler=suggest_keyword_updates,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
]
