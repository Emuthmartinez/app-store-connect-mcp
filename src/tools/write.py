"""Write tools for App Store Connect listing management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from errors import ConfigurationError
from tooling import ToolDefinition
from tools.shared import (
    extract_screenshot_upload_contract,
    get_listing_snapshot,
    keyword_length,
    log_mutation,
    require_file_path,
    require_locale,
    summarize_screenshot_sets,
)


def _update_version_localization_field(
    runtime: Any,
    *,
    locale: str,
    operation: str,
    field_name: str,
    new_value: str | None,
) -> dict[str, Any]:
    before = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    localization_id = before["version_localization"]["id"]
    runtime.asc.update_version_localization(localization_id, {field_name: new_value})
    after = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    log_mutation(
        runtime,
        operation=operation,
        locale=locale,
        target={"resource_type": "appStoreVersionLocalization", "id": localization_id},
        before=before,
        after=after,
    )
    return {"ok": True, "locale": locale, "before": before, "after": after}


def _update_app_info_localization_field(
    runtime: Any,
    *,
    locale: str,
    operation: str,
    field_name: str,
    new_value: str | None,
) -> dict[str, Any]:
    before = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    localization_id = before["app_info_localization"]["id"]
    runtime.asc.update_app_info_localization(localization_id, {field_name: new_value})
    after = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    log_mutation(
        runtime,
        operation=operation,
        locale=locale,
        target={"resource_type": "appInfoLocalization", "id": localization_id},
        before=before,
        after=after,
    )
    return {"ok": True, "locale": locale, "before": before, "after": after}


def update_description(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    description = str(arguments.get("description") or "").strip()
    if not description:
        raise ConfigurationError("Description must be a non-empty string")
    return _update_version_localization_field(
        runtime,
        locale=locale,
        operation="update_description",
        field_name="description",
        new_value=description,
    )


def update_keywords(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    keywords = str(arguments.get("keywords") or "").strip()
    if not keywords:
        raise ConfigurationError("Keywords must be a non-empty comma-separated string")
    length = keyword_length(keywords)
    if length > 100:
        raise ConfigurationError(
            "Keywords exceed Apple’s 100 character limit",
            details={"length": length, "keywords": keywords},
        )
    return _update_version_localization_field(
        runtime,
        locale=locale,
        operation="update_keywords",
        field_name="keywords",
        new_value=keywords,
    )


def update_promotional_text(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    promotional_text = arguments.get("promotional_text")
    value = None if promotional_text is None else str(promotional_text).strip() or None
    return _update_version_localization_field(
        runtime,
        locale=locale,
        operation="update_promotional_text",
        field_name="promotionalText",
        new_value=value,
    )


def update_whats_new(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    whats_new = str(arguments.get("whats_new") or "").strip()
    if not whats_new:
        raise ConfigurationError("What’s New text must be a non-empty string")
    return _update_version_localization_field(
        runtime,
        locale=locale,
        operation="update_whats_new",
        field_name="whatsNew",
        new_value=whats_new,
    )


def update_subtitle(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    subtitle = str(arguments.get("subtitle") or "").strip()
    if not subtitle:
        raise ConfigurationError("Subtitle must be a non-empty string")
    if len(subtitle) > 30:
        raise ConfigurationError(
            "Subtitle exceeds Apple’s 30 character limit",
            details={"length": len(subtitle), "subtitle": subtitle},
        )
    return _update_app_info_localization_field(
        runtime,
        locale=locale,
        operation="update_subtitle",
        field_name="subtitle",
        new_value=subtitle,
    )


def upload_screenshot(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    locale = require_locale(arguments)
    display_type = str(arguments.get("display_type") or "").strip()
    if not display_type:
        raise ConfigurationError("display_type is required, for example APP_IPHONE_67")
    file_path = require_file_path(arguments)

    before = get_listing_snapshot(runtime, locale=locale, include_screenshots=True)
    screenshot_sets = before.get("screenshot_sets", [])
    target_set = next(
        (
            item
            for item in screenshot_sets
            if item.get("display_type") == display_type
        ),
        None,
    )
    if target_set is None:
        created = runtime.asc.create_screenshot_set(
            before["version_localization"]["id"],
            display_type=display_type,
        )
        target_set_id = created["data"]["id"]
    else:
        target_set_id = str(target_set["id"])

    file_name = Path(file_path).name
    file_size = Path(file_path).stat().st_size
    reservation = runtime.asc.create_screenshot_reservation(
        target_set_id,
        file_name=file_name,
        file_size=file_size,
    )
    screenshot_id, operations = extract_screenshot_upload_contract(reservation)
    upload_results = runtime.asc.execute_upload_operations(operations, file_path)
    finalized = runtime.asc.finalize_screenshot_upload(
        screenshot_id=screenshot_id,
        file_path=file_path,
    )

    after = get_listing_snapshot(runtime, locale=locale, include_screenshots=False)
    after["screenshot_sets"] = summarize_screenshot_sets(
        runtime,
        version_localization_id=after["version_localization"]["id"],
    )
    log_mutation(
        runtime,
        operation="upload_screenshot",
        locale=locale,
        target={
            "resource_type": "appScreenshotSet",
            "id": target_set_id,
            "display_type": display_type,
            "file_name": file_name,
        },
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "locale": locale,
        "display_type": display_type,
        "reservation": reservation,
        "upload_results": upload_results,
        "finalized": finalized,
        "after": after,
    }


def submit_for_review(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    version = runtime.asc.get_current_version()
    state = version.get("attributes", {}).get("appVersionState")
    if state in {
        "WAITING_FOR_REVIEW",
        "IN_REVIEW",
        "PENDING_DEVELOPER_RELEASE",
        "PENDING_APPLE_RELEASE",
        "PROCESSING_FOR_DISTRIBUTION",
    }:
        return {
            "ok": True,
            "already_submitted": True,
            "version": {"id": version.get("id"), **version.get("attributes", {})},
        }

    submission = runtime.asc.submit_for_review(version["id"])
    refreshed_version = runtime.asc.get_current_version()
    log_mutation(
        runtime,
        operation="submit_for_review",
        locale=None,
        target={"resource_type": "appStoreVersion", "id": version["id"]},
        before={"version": version},
        after={"version": refreshed_version},
    )
    return {
        "ok": True,
        "submission": submission,
        "version": {"id": refreshed_version.get("id"), **refreshed_version.get("attributes", {})},
    }


WRITE_TOOLS = [
    ToolDefinition(
        name="update_description",
        description="Update the localized App Store description for the current version.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["locale", "description"],
            "additionalProperties": False,
        },
        handler=update_description,
    ),
    ToolDefinition(
        name="update_keywords",
        description="Update localized App Store keywords for the current version.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "keywords": {"type": "string"},
            },
            "required": ["locale", "keywords"],
            "additionalProperties": False,
        },
        handler=update_keywords,
    ),
    ToolDefinition(
        name="update_promotional_text",
        description="Update promotional text, which can change without shipping a new version.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "promotional_text": {
                    "type": ["string", "null"],
                    "description": "Use null to clear the field.",
                },
            },
            "required": ["locale"],
            "additionalProperties": False,
        },
        handler=update_promotional_text,
    ),
    ToolDefinition(
        name="update_whats_new",
        description="Update the localized What’s New text for the current version.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "whats_new": {"type": "string"},
            },
            "required": ["locale", "whats_new"],
            "additionalProperties": False,
        },
        handler=update_whats_new,
    ),
    ToolDefinition(
        name="update_subtitle",
        description="Update the localized subtitle in App Store Connect.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "subtitle": {"type": "string"},
            },
            "required": ["locale", "subtitle"],
            "additionalProperties": False,
        },
        handler=update_subtitle,
    ),
    ToolDefinition(
        name="upload_screenshot",
        description="Upload a screenshot into a locale/display-type screenshot set.",
        input_schema={
            "type": "object",
            "properties": {
                "locale": {"type": "string"},
                "display_type": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["locale", "display_type", "file_path"],
            "additionalProperties": False,
        },
        handler=upload_screenshot,
    ),
    ToolDefinition(
        name="submit_for_review",
        description="Submit the current editable version for App Review.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=submit_for_review,
    ),
]
