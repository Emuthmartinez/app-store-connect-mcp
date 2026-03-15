"""Custom Product Page tools for experimentation workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from errors import ConfigurationError
from tooling import ToolDefinition
from tools.shared import (
    extract_screenshot_upload_contract,
    log_mutation,
    require_file_path,
    require_locale,
    summarize_cpp_screenshot_sets,
)


def _serialize_custom_product_page(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": page.get("id"),
        **page.get("attributes", {}),
    }


def _serialize_custom_product_page_version(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": version.get("id"),
        **version.get("attributes", {}),
    }


def _serialize_custom_product_page_localization(
    runtime: Any,
    localization: dict[str, Any],
    *,
    include_screenshots: bool,
) -> dict[str, Any]:
    summary = {
        "id": localization.get("id"),
        **localization.get("attributes", {}),
    }
    if include_screenshots and localization.get("id"):
        summary["screenshot_sets"] = summarize_cpp_screenshot_sets(runtime, localization["id"])
    return summary


def _get_custom_product_page_snapshot(
    runtime: Any,
    page_id: str,
    *,
    include_screenshots: bool,
) -> dict[str, Any]:
    page = runtime.asc.get_custom_product_page(page_id)["data"]
    versions = runtime.asc.get_custom_product_page_versions(page_id)
    serialized_versions: list[dict[str, Any]] = []
    for version in versions:
        localizations = runtime.asc.get_custom_product_page_localizations(version["id"])
        serialized_versions.append(
            {
                **_serialize_custom_product_page_version(version),
                "localizations": [
                    _serialize_custom_product_page_localization(
                        runtime,
                        localization,
                        include_screenshots=include_screenshots,
                    )
                    for localization in localizations
                ],
            }
        )
    return {
        "page": _serialize_custom_product_page(page),
        "versions": serialized_versions,
    }


def _get_custom_product_page_version_snapshot(
    runtime: Any,
    version_id: str,
    *,
    include_screenshots: bool,
) -> dict[str, Any]:
    version = runtime.asc.get_custom_product_page_version(version_id)
    localizations = runtime.asc.get_custom_product_page_localizations(version_id)
    return {
        "version": _serialize_custom_product_page_version(version),
        "localizations": [
            _serialize_custom_product_page_localization(
                runtime,
                localization,
                include_screenshots=include_screenshots,
            )
            for localization in localizations
        ],
    }


def _resolve_cpp_localization(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    localization_id = str(arguments.get("localization_id") or "").strip()
    if localization_id:
        return runtime.asc.get_custom_product_page_localization(localization_id)

    version_id = str(arguments.get("page_version_id") or arguments.get("version_id") or "").strip()
    if not version_id:
        raise ConfigurationError(
            "Provide localization_id or page_version_id plus locale",
        )
    locale = require_locale(arguments)
    localizations = runtime.asc.get_custom_product_page_localizations(version_id)
    for localization in localizations:
        if str(localization.get("attributes", {}).get("locale", "")).lower() == locale.lower():
            return localization

    raise ConfigurationError(
        "No custom product page localization matched the requested locale",
        details={"page_version_id": version_id, "locale": locale},
    )


def list_custom_product_pages(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    include_versions = bool(arguments.get("include_versions", True))
    limit = int(arguments.get("limit") or 20)
    payload = runtime.asc.get_custom_product_pages(include_versions=include_versions, limit=limit)
    pages = payload.get("data", [])
    summary = []
    for page in pages:
        item = _serialize_custom_product_page(page)
        if include_versions:
            versions = runtime.asc.get_custom_product_page_versions(page["id"])
            item["versions"] = [
                _serialize_custom_product_page_version(version)
                for version in versions
            ]
        summary.append(item)
    return {
        "ok": True,
        "custom_product_pages": summary,
    }


def get_custom_product_page(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    page_id = str(arguments.get("page_id") or "").strip()
    if not page_id:
        raise ConfigurationError("page_id is required")
    include_screenshots = bool(arguments.get("include_screenshots", True))
    return {
        "ok": True,
        "custom_product_page": _get_custom_product_page_snapshot(
            runtime,
            page_id,
            include_screenshots=include_screenshots,
        ),
    }


def create_custom_product_page(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ConfigurationError("name must be a non-empty string")
    locale = str(arguments.get("locale") or "en-US").strip()
    if not locale:
        raise ConfigurationError("locale must be a non-empty string")
    promotional_text = arguments.get("promotional_text")
    if promotional_text is not None:
        promotional_text = str(promotional_text)
    deep_link = arguments.get("deep_link")
    if deep_link is not None:
        deep_link = str(deep_link).strip() or None
    visible = bool(arguments.get("visible", False))

    before = {
        "custom_product_pages": list_custom_product_pages(
            runtime,
            {"include_versions": False, "limit": 50},
        )["custom_product_pages"]
    }
    created = runtime.asc.create_custom_product_page(
        name=name,
        locale=locale,
        promotional_text=promotional_text,
        deep_link=deep_link,
    )
    page_id = created["data"]["id"]
    if visible:
        runtime.asc.update_custom_product_page(page_id, {"visible": True})
    after = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    log_mutation(
        runtime,
        operation="create_custom_product_page",
        locale=None,
        target={"resource_type": "appCustomProductPage", "id": page_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_custom_product_page(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    page_id = str(arguments.get("page_id") or "").strip()
    if not page_id:
        raise ConfigurationError("page_id is required")

    attributes: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ConfigurationError("name must be a non-empty string when provided")
        attributes["name"] = name
    if "visible" in arguments:
        attributes["visible"] = bool(arguments.get("visible"))
    if not attributes:
        raise ConfigurationError("Provide at least one field to update")

    before = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    runtime.asc.update_custom_product_page(page_id, attributes)
    after = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    log_mutation(
        runtime,
        operation="update_custom_product_page",
        locale=None,
        target={"resource_type": "appCustomProductPage", "id": page_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "page_id": page_id,
        "before": before,
        "after": after,
    }


def delete_custom_product_page(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    page_id = str(arguments.get("page_id") or "").strip()
    if not page_id:
        raise ConfigurationError("page_id is required")

    before = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    runtime.asc.delete_custom_product_page(page_id)
    after = {"deleted": True, "page_id": page_id}
    log_mutation(
        runtime,
        operation="delete_custom_product_page",
        locale=None,
        target={"resource_type": "appCustomProductPage", "id": page_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "page_id": page_id,
        "deleted": True,
    }


def create_custom_product_page_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    page_id = str(arguments.get("page_id") or "").strip()
    if not page_id:
        raise ConfigurationError("page_id is required")
    deep_link = str(arguments.get("deep_link") or "").strip() or None

    before = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    created = runtime.asc.create_custom_product_page_version(page_id, deep_link=deep_link)
    after = _get_custom_product_page_snapshot(runtime, page_id, include_screenshots=False)
    log_mutation(
        runtime,
        operation="create_custom_product_page_version",
        locale=None,
        target={"resource_type": "appCustomProductPage", "id": page_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_custom_product_page_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("page_version_id") or arguments.get("version_id") or "").strip()
    if not version_id:
        raise ConfigurationError("page_version_id is required")

    attributes: dict[str, Any] = {}
    if "deep_link" in arguments:
        deep_link = arguments.get("deep_link")
        attributes["deepLink"] = None if deep_link is None else str(deep_link).strip() or None
    if not attributes:
        raise ConfigurationError("Provide at least one field to update")

    before = _get_custom_product_page_version_snapshot(runtime, version_id, include_screenshots=False)
    runtime.asc.update_custom_product_page_version(version_id, attributes)
    after = _get_custom_product_page_version_snapshot(runtime, version_id, include_screenshots=False)
    log_mutation(
        runtime,
        operation="update_custom_product_page_version",
        locale=None,
        target={"resource_type": "appCustomProductPageVersion", "id": version_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "page_version_id": version_id,
        "before": before,
        "after": after,
    }


def create_custom_product_page_localization(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("page_version_id") or arguments.get("version_id") or "").strip()
    if not version_id:
        raise ConfigurationError("page_version_id is required")
    locale = require_locale(arguments)
    promotional_text = arguments.get("promotional_text")
    value = None if promotional_text is None else str(promotional_text).strip() or None

    before = _get_custom_product_page_version_snapshot(runtime, version_id, include_screenshots=False)
    created = runtime.asc.create_custom_product_page_localization(
        version_id=version_id,
        locale=locale,
        promotional_text=value,
    )
    localization_id = created["data"]["id"]
    after = {
        "version": before["version"],
        "localization": _serialize_custom_product_page_localization(
            runtime,
            runtime.asc.get_custom_product_page_localization(localization_id),
            include_screenshots=False,
        ),
    }
    log_mutation(
        runtime,
        operation="create_custom_product_page_localization",
        locale=locale,
        target={"resource_type": "appCustomProductPageLocalization", "id": localization_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_custom_product_page_localization(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    localization = _resolve_cpp_localization(runtime, arguments)
    localization_id = localization["id"]

    if "promotional_text" not in arguments:
        raise ConfigurationError("promotional_text is required for localization updates")
    promotional_text = arguments.get("promotional_text")
    value = None if promotional_text is None else str(promotional_text).strip() or None

    before = _serialize_custom_product_page_localization(
        runtime,
        localization,
        include_screenshots=False,
    )
    runtime.asc.update_custom_product_page_localization(
        localization_id,
        {"promotionalText": value},
    )
    after = _serialize_custom_product_page_localization(
        runtime,
        runtime.asc.get_custom_product_page_localization(localization_id),
        include_screenshots=False,
    )
    log_mutation(
        runtime,
        operation="update_custom_product_page_localization",
        locale=after.get("locale"),
        target={"resource_type": "appCustomProductPageLocalization", "id": localization_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "localization_id": localization_id,
        "before": before,
        "after": after,
    }


def delete_custom_product_page_localization(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    localization = _resolve_cpp_localization(runtime, arguments)
    localization_id = localization["id"]

    before = _serialize_custom_product_page_localization(
        runtime,
        localization,
        include_screenshots=False,
    )
    runtime.asc.delete_custom_product_page_localization(localization_id)
    after = {"deleted": True, "localization_id": localization_id}
    log_mutation(
        runtime,
        operation="delete_custom_product_page_localization",
        locale=before.get("locale"),
        target={"resource_type": "appCustomProductPageLocalization", "id": localization_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "localization_id": localization_id,
        "deleted": True,
    }


def upload_custom_product_page_screenshot(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    localization = _resolve_cpp_localization(runtime, arguments)
    localization_id = localization["id"]
    display_type = str(arguments.get("display_type") or "").strip()
    if not display_type:
        raise ConfigurationError("display_type is required, for example APP_IPHONE_67")
    file_path = require_file_path(arguments)

    before = _serialize_custom_product_page_localization(
        runtime,
        runtime.asc.get_custom_product_page_localization(localization_id),
        include_screenshots=True,
    )
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
        created_set = runtime.asc.create_cpp_screenshot_set(localization_id, display_type)
        target_set_id = created_set["data"]["id"]
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
    after = _serialize_custom_product_page_localization(
        runtime,
        runtime.asc.get_custom_product_page_localization(localization_id),
        include_screenshots=True,
    )
    log_mutation(
        runtime,
        operation="upload_custom_product_page_screenshot",
        locale=after.get("locale"),
        target={
            "resource_type": "appCustomProductPageLocalization",
            "id": localization_id,
            "display_type": display_type,
            "file_name": file_name,
        },
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "localization_id": localization_id,
        "display_type": display_type,
        "reservation": reservation,
        "upload_results": upload_results,
        "finalized": finalized,
        "after": after,
    }


CPP_TOOLS = [
    ToolDefinition(
        name="list_custom_product_pages",
        description="List Custom Product Pages for the configured app, optionally including version summaries.",
        input_schema={
            "type": "object",
            "properties": {
                "include_versions": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        handler=list_custom_product_pages,
    ),
    ToolDefinition(
        name="get_custom_product_page",
        description="Fetch a full Custom Product Page snapshot, including versions, localizations, and optional screenshot summaries.",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "include_screenshots": {"type": "boolean"},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
        handler=get_custom_product_page,
    ),
    ToolDefinition(
        name="create_custom_product_page",
        description="Create a new Custom Product Page for experimentation. Visibility defaults to false for safe drafting.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "locale": {"type": "string"},
                "promotional_text": {"type": ["string", "null"]},
                "deep_link": {"type": ["string", "null"]},
                "visible": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=create_custom_product_page,
    ),
    ToolDefinition(
        name="update_custom_product_page",
        description="Update the name or visibility of an existing Custom Product Page.",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "name": {"type": "string"},
                "visible": {"type": "boolean"},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
        handler=update_custom_product_page,
    ),
    ToolDefinition(
        name="delete_custom_product_page",
        description="Delete a Custom Product Page.",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
        handler=delete_custom_product_page,
    ),
    ToolDefinition(
        name="create_custom_product_page_version",
        description="Create a new version for an existing Custom Product Page.",
        input_schema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "deep_link": {"type": "string"},
            },
            "required": ["page_id"],
            "additionalProperties": False,
        },
        handler=create_custom_product_page_version,
    ),
    ToolDefinition(
        name="update_custom_product_page_version",
        description="Update metadata on a Custom Product Page version, such as its deep link.",
        input_schema={
            "type": "object",
            "properties": {
                "page_version_id": {"type": "string"},
                "deep_link": {"type": ["string", "null"]},
            },
            "required": ["page_version_id"],
            "additionalProperties": False,
        },
        handler=update_custom_product_page_version,
    ),
    ToolDefinition(
        name="create_custom_product_page_localization",
        description="Create a locale-specific Custom Product Page localization.",
        input_schema={
            "type": "object",
            "properties": {
                "page_version_id": {"type": "string"},
                "locale": {"type": "string"},
                "promotional_text": {"type": ["string", "null"]},
            },
            "required": ["page_version_id", "locale"],
            "additionalProperties": False,
        },
        handler=create_custom_product_page_localization,
    ),
    ToolDefinition(
        name="update_custom_product_page_localization",
        description="Update promotional text on a Custom Product Page localization.",
        input_schema={
            "type": "object",
            "properties": {
                "localization_id": {"type": "string"},
                "page_version_id": {"type": "string"},
                "locale": {"type": "string"},
                "promotional_text": {"type": ["string", "null"]},
            },
            "required": ["promotional_text"],
            "additionalProperties": False,
        },
        handler=update_custom_product_page_localization,
    ),
    ToolDefinition(
        name="delete_custom_product_page_localization",
        description="Delete a Custom Product Page localization.",
        input_schema={
            "type": "object",
            "properties": {
                "localization_id": {"type": "string"},
                "page_version_id": {"type": "string"},
                "locale": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=delete_custom_product_page_localization,
    ),
    ToolDefinition(
        name="upload_custom_product_page_screenshot",
        description="Upload a screenshot into a Custom Product Page localization screenshot set.",
        input_schema={
            "type": "object",
            "properties": {
                "localization_id": {"type": "string"},
                "page_version_id": {"type": "string"},
                "locale": {"type": "string"},
                "display_type": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["display_type", "file_path"],
            "additionalProperties": False,
        },
        handler=upload_custom_product_page_screenshot,
    ),
]
