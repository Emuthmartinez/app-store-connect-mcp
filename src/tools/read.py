"""Read tools for App Store Connect listing management."""

from __future__ import annotations

from typing import Any

from tooling import ToolDefinition
from tools.shared import get_listing_snapshot, require_locale, summarize_screenshot_sets


def get_app_info(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    snapshot = get_listing_snapshot(runtime, locale="en-US", include_screenshots=False)
    return {
        "ok": True,
        "app": snapshot["app"],
        "app_info": snapshot["app_info"],
        "current_version": snapshot["current_version"],
    }


def get_app_listing(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    snapshot = get_listing_snapshot(runtime, locale=locale, include_screenshots=True)
    return {
        "ok": True,
        "locale": locale,
        "listing": snapshot,
    }


def get_app_versions(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    versions = runtime.asc.get_app_versions()
    return {
        "ok": True,
        "versions": [
            {
                "id": version.get("id"),
                **version.get("attributes", {}),
            }
            for version in versions
        ],
    }


def get_app_screenshots(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    snapshot = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    screenshot_sets = summarize_screenshot_sets(
        runtime,
        version_localization_id=snapshot["version_localization"]["id"],
    )
    return {
        "ok": True,
        "locale": locale,
        "version": snapshot["current_version"],
        "screenshot_sets": screenshot_sets,
    }


def get_app_pricing(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    pricing = runtime.asc.get_app_price_schedule()
    return {
        "ok": True,
        "pricing": pricing,
        "note": (
            "This endpoint reflects the app download price schedule. Subscription "
            "product pricing is managed separately from the App Store version listing."
        ),
    }


READ_TOOLS = [
    ToolDefinition(
        name="asc_get_app_info",
        description="Fetch app metadata, bundle id, current version, and release state.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_app_info,
    ),
    ToolDefinition(
        name="asc_get_app_listing",
        description=(
            "Fetch localized App Store listing metadata, including description, keywords, "
            "subtitle, promotional text, what’s new, and screenshot summaries."
        ),
        input_schema={
            "type": "object",
            "properties": {
            "locale": {"type": "string", "description": "BCP 47 locale code, e.g. en-US, ja, de-DE."},
            },
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_app_listing,
    ),
    ToolDefinition(
        name="asc_get_app_versions",
        description="List all App Store versions for the configured app with their states.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_app_versions,
    ),
    ToolDefinition(
        name="asc_get_app_screenshots",
        description="List screenshot sets and assets for a locale on the current App Store version.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string", "description": "BCP 47 locale code, e.g. en-US, ja, de-DE."},
            },
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_app_screenshots,
    ),
    ToolDefinition(
        name="asc_get_app_pricing",
        description="Fetch the current app price schedule and availability relationships.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_app_pricing,
    ),
]
