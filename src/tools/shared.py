"""Shared helpers for ASC listing tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from errors import AscApiError, ConfigurationError


def require_locale(arguments: dict[str, Any], default: str = "en-US") -> str:
    locale = str(arguments.get("locale") or default).strip()
    if not locale:
        raise ConfigurationError("Locale must be a non-empty string")
    return locale


def require_file_path(arguments: dict[str, Any], key: str = "file_path") -> str:
    raw = str(arguments.get(key) or "").strip()
    if not raw:
        raise ConfigurationError(f"Missing required field: {key}")
    path = Path(raw).expanduser()
    if not path.exists() or not path.is_file():
        raise ConfigurationError(
            "Screenshot file path does not exist",
            details={"file_path": raw},
        )
    return str(path)


def keyword_length(keywords: str) -> int:
    return len(",".join(part.strip() for part in keywords.split(",") if part.strip()))


def normalize_keywords(keywords: str) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for part in keywords.split(","):
        token = part.strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(token)
    return normalized


def build_keyword_string(candidates: list[str], *, limit: int = 100) -> str:
    selected: list[str] = []
    current = ""
    for candidate in candidates:
        tentative = ",".join([*selected, candidate])
        if len(tentative) > limit:
            continue
        selected.append(candidate)
        current = tentative
    return current


def log_mutation(
    runtime: Any,
    *,
    operation: str,
    locale: str | None,
    target: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    revenuecat_metrics = runtime.revenuecat.get_overview()
    runtime.change_logger.record(
        operation=operation,
        locale=locale,
        target=target,
        before=before,
        after=after,
        revenuecat_metrics=revenuecat_metrics,
    )


def extract_screenshot_upload_contract(reservation: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    data = reservation.get("data")
    if not isinstance(data, dict):
        raise AscApiError(
            "App Store Connect returned a screenshot reservation without a data object",
            status_code=502,
            retryable=False,
            details={"reservation": reservation},
        )

    screenshot_id = data.get("id")
    if not isinstance(screenshot_id, str) or not screenshot_id.strip():
        raise AscApiError(
            "App Store Connect returned a screenshot reservation without a screenshot id",
            status_code=502,
            retryable=False,
            details={"reservation": reservation},
        )

    attributes = data.get("attributes")
    if not isinstance(attributes, dict):
        raise AscApiError(
            "App Store Connect returned a screenshot reservation without attributes",
            status_code=502,
            retryable=False,
            details={"reservation": reservation},
        )

    operations = attributes.get("uploadOperations")
    if not isinstance(operations, list) or not operations:
        raise AscApiError(
            "App Store Connect returned a screenshot reservation without upload operations",
            status_code=502,
            retryable=False,
            details={"reservation": reservation},
        )

    return screenshot_id, operations


def summarize_screenshot_resources(runtime: Any, screenshot_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for screenshot_set in screenshot_sets:
        screenshots = runtime.asc.get_screenshots(screenshot_set["id"])
        summary.append(
            {
                "id": screenshot_set["id"],
                "display_type": screenshot_set.get("attributes", {}).get(
                    "screenshotDisplayType"
                ),
                "count": len(screenshots),
                "screenshots": [
                    {
                        "id": shot.get("id"),
                        "file_name": shot.get("attributes", {}).get("fileName"),
                        "asset_delivery_state": shot.get("attributes", {})
                        .get("assetDeliveryState", {})
                        .get("state"),
                    }
                    for shot in screenshots
                ],
            }
        )
    return summary


def summarize_screenshot_sets(runtime: Any, version_localization_id: str) -> list[dict[str, Any]]:
    sets = runtime.asc.get_screenshot_sets(version_localization_id)
    return summarize_screenshot_resources(runtime, sets)


def summarize_cpp_screenshot_sets(runtime: Any, localization_id: str) -> list[dict[str, Any]]:
    sets = runtime.asc.get_cpp_screenshot_sets(localization_id)
    return summarize_screenshot_resources(runtime, sets)


def get_listing_snapshot(
    runtime: Any,
    *,
    locale: str,
    include_screenshots: bool = False,
) -> dict[str, Any]:
    app = runtime.asc.get_configured_app()
    primary_locale = app.get("attributes", {}).get("primaryLocale") or "en-US"

    app_info = runtime.asc.get_primary_app_info()
    app_info_localization = runtime.asc.find_locale(
        runtime.asc.get_app_info_localizations(app_info["id"]),
        locale,
    )

    current_version = runtime.asc.get_current_version()
    version_localization = runtime.asc.find_locale(
        runtime.asc.get_version_localizations(current_version["id"]),
        locale,
    )

    snapshot = {
        "app": {
            "id": app.get("id"),
            "name": app.get("attributes", {}).get("name"),
            "bundle_id": app.get("attributes", {}).get("bundleId"),
            "sku": app.get("attributes", {}).get("sku"),
            "primary_locale": primary_locale,
        },
        "app_info": {
            "id": app_info.get("id"),
            "app_store_state": app_info.get("attributes", {}).get("appStoreState"),
            "state": app_info.get("attributes", {}).get("state"),
        },
        "app_info_localization": {
            "id": app_info_localization.get("id"),
            **app_info_localization.get("attributes", {}),
        },
        "current_version": {
            "id": current_version.get("id"),
            **current_version.get("attributes", {}),
        },
        "version_localization": {
            "id": version_localization.get("id"),
            **version_localization.get("attributes", {}),
        },
    }

    if include_screenshots:
        snapshot["screenshot_sets"] = summarize_screenshot_sets(
            runtime,
            version_localization_id=version_localization["id"],
        )

    return snapshot
