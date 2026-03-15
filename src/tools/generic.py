"""Generic App Store Connect API tools for broad endpoint coverage."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from errors import ConfigurationError, serialize_error
from tooling import ToolDefinition


JSON_API_HINTS = {
    "request_shape": {
        "data": {
            "type": "resource type string",
            "id": "resource id for PATCH or DELETE-adjacent reads",
            "attributes": "resource-specific fields",
            "relationships": "JSON:API relationship objects when linking resources",
        }
    },
    "response_shape": {
        "data": "resource or collection payload",
        "links": "pagination and self links",
        "included": "related resources when Apple expands relationships",
    },
    "relationship_pattern": {
        "data": {
            "type": "related resource type",
            "id": "related resource id",
        }
    },
}

CURATED_CATALOG = [
    {
        "category": "core_app",
        "resource_type": "apps",
        "methods": ["GET"],
        "path_templates": ["/v1/apps", "/v1/apps/{app_id}"],
        "filters": ["filter[bundleId]", "filter[name]"],
        "relationships": [
            "/v1/apps/{app_id}/appInfos",
            "/v1/apps/{app_id}/appStoreVersions",
            "/v1/apps/{app_id}/appPriceSchedule",
        ],
        "notes": ["Use filter[bundleId] to resolve the configured app at runtime."],
    },
    {
        "category": "listing_metadata",
        "resource_type": "appInfos",
        "methods": ["GET"],
        "path_templates": ["/v1/apps/{app_id}/appInfos", "/v1/appInfos/{app_info_id}/appInfoLocalizations"],
        "relationships": ["/v1/appInfoLocalizations/{localization_id}"],
    },
    {
        "category": "listing_metadata",
        "resource_type": "appInfoLocalizations",
        "methods": ["GET", "PATCH"],
        "path_templates": ["/v1/appInfoLocalizations/{localization_id}"],
        "mutable_fields": ["subtitle"],
    },
    {
        "category": "versioning",
        "resource_type": "appStoreVersions",
        "methods": ["GET"],
        "path_templates": [
            "/v1/apps/{app_id}/appStoreVersions",
            "/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations",
        ],
        "relationships": ["/v1/appStoreVersionSubmissions"],
    },
    {
        "category": "listing_metadata",
        "resource_type": "appStoreVersionLocalizations",
        "methods": ["GET", "PATCH"],
        "path_templates": [
            "/v1/appStoreVersionLocalizations/{version_localization_id}",
            "/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations",
        ],
        "mutable_fields": ["description", "keywords", "promotionalText", "whatsNew"],
        "relationships": ["/v1/appStoreVersionLocalizations/{version_localization_id}/appScreenshotSets"],
    },
    {
        "category": "screenshots",
        "resource_type": "appScreenshotSets",
        "methods": ["GET", "POST"],
        "path_templates": [
            "/v1/appStoreVersionLocalizations/{version_localization_id}/appScreenshotSets",
            "/v1/appScreenshotSets",
            "/v1/appScreenshotSets/{screenshot_set_id}/appScreenshots",
        ],
    },
    {
        "category": "screenshots",
        "resource_type": "appScreenshots",
        "methods": ["GET", "POST", "PATCH"],
        "path_templates": ["/v1/appScreenshots", "/v1/appScreenshots/{screenshot_id}"],
    },
    {
        "category": "pricing",
        "resource_type": "appPriceSchedules",
        "methods": ["GET", "POST"],
        "path_templates": ["/v1/apps/{app_id}/appPriceSchedule", "/v1/appPriceSchedules"],
    },
    {
        "category": "submission",
        "resource_type": "appStoreVersionSubmissions",
        "methods": ["POST"],
        "path_templates": ["/v1/appStoreVersionSubmissions"],
    },
    {
        "category": "future_surface",
        "resource_type": "generic_v1_endpoint",
        "methods": ["GET", "POST", "PATCH", "DELETE"],
        "path_templates": ["/v1/..."],
        "notes": [
            "Use the generic ASC verbs for unsupported resources such as Custom Product Pages or state-management endpoints.",
            "When mutating an unsupported resource, the generic tools now log the request path, body, before snapshot, after snapshot, and RevenueCat metrics.",
        ],
    },
]


def _normalize_api_path(runtime: Any, raw_path: Any, query: dict[str, Any] | None = None) -> str:
    path = str(raw_path or "").strip()
    if not path:
        raise ConfigurationError("path must be a non-empty string")

    base_url = runtime.settings.app_store_base_url.rstrip("/")
    if path.startswith(base_url):
        path = path[len(base_url) :]

    if not path.startswith("/v1/"):
        raise ConfigurationError(
            "ASC API path must start with /v1/ or the configured App Store Connect base URL",
            details={"path": raw_path},
        )

    if not query:
        return path

    encoded = urlencode(_normalize_query_params(query), doseq=True)
    return f"{path}?{encoded}" if encoded else path


def _normalize_query_params(query: dict[str, Any]) -> dict[str, list[str] | str]:
    normalized: dict[str, list[str] | str] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, list):
            normalized[key] = [str(item) for item in value]
        else:
            normalized[key] = str(value)
    return normalized


def _require_body(arguments: dict[str, Any]) -> dict[str, Any]:
    body = arguments.get("body")
    if not isinstance(body, dict):
        raise ConfigurationError("body must be an object")
    return body


def _best_effort_read(runtime: Any, path: str) -> dict[str, Any]:
    try:
        return {
            "ok": True,
            "path": path,
            "response": runtime.asc.request("GET", path),
        }
    except Exception as exc:  # pragma: no cover - validated indirectly by callers
        return {
            "ok": False,
            "path": path,
            "error": serialize_error(exc)["error"],
        }


def _best_effort_revenuecat_metrics(runtime: Any) -> dict[str, Any] | None:
    try:
        return runtime.revenuecat.get_overview()
    except Exception as exc:  # pragma: no cover - defensive logging path
        return {
            "ok": False,
            "error": serialize_error(exc)["error"],
        }


def _extract_self_path(runtime: Any, response: dict[str, Any]) -> str | None:
    data = response.get("data")
    if not isinstance(data, dict):
        return None
    links = data.get("links")
    if not isinstance(links, dict):
        return None
    self_link = links.get("self")
    if not isinstance(self_link, str) or not self_link.strip():
        return None
    try:
        return _normalize_api_path(runtime, self_link)
    except ConfigurationError:
        return None


def _build_target(path: str, method: str, body: dict[str, Any] | None, response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response, dict) else None
    request_data = body.get("data") if isinstance(body, dict) else None
    target: dict[str, Any] = {
        "resource_type": "genericAscMutation",
        "path": path,
        "method": method,
    }
    if isinstance(request_data, dict):
        if request_data.get("type"):
            target["request_type"] = request_data.get("type")
        if request_data.get("id"):
            target["request_id"] = request_data.get("id")
    if isinstance(data, dict):
        if data.get("type"):
            target["response_type"] = data.get("type")
        if data.get("id"):
            target["response_id"] = data.get("id")
    return target


def _record_generic_mutation(
    runtime: Any,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    response: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    runtime.change_logger.record(
        operation=f"asc_api_{method.lower()}",
        locale=None,
        target=_build_target(path, method, body, response),
        before=before,
        after=after,
        revenuecat_metrics=_best_effort_revenuecat_metrics(runtime),
    )


def _generic_mutation(
    runtime: Any,
    *,
    method: str,
    arguments: dict[str, Any],
    require_body: bool,
) -> dict[str, Any]:
    path = _normalize_api_path(runtime, arguments.get("path"), arguments.get("query"))
    body = _require_body(arguments) if require_body else None
    capture_state = bool(arguments.get("capture_state", True))

    before = _best_effort_read(runtime, path) if capture_state else None
    response = runtime.asc.request(method, path, json_body=body)

    after: dict[str, Any] | None = None
    if capture_state:
        after = {
            "path_snapshot": _best_effort_read(runtime, path),
            "response": response,
        }
        created_path = _extract_self_path(runtime, response)
        if created_path and created_path != path:
            after["created_resource_snapshot"] = _best_effort_read(runtime, created_path)
    else:
        after = {"response": response}

    _record_generic_mutation(
        runtime,
        method=method,
        path=path,
        body=body,
        response=response,
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "path": path,
        "response": response,
        "before": before,
        "after": after,
    }


def _discover_runtime_entities(runtime: Any) -> dict[str, Any]:
    app = runtime.asc.get_configured_app()
    app_id = str(app["id"])

    primary_app_info = runtime.asc.get_primary_app_info()
    app_info_localizations = runtime.asc.get_app_info_localizations(primary_app_info["id"])
    current_version = runtime.asc.get_current_version()
    version_localizations = runtime.asc.get_version_localizations(current_version["id"])

    return {
        "ok": True,
        "configured_app": {
            "id": app_id,
            "bundle_id": app.get("attributes", {}).get("bundleId"),
            "name": app.get("attributes", {}).get("name"),
            "paths": {
                "self": f"/v1/apps/{app_id}",
                "app_infos": f"/v1/apps/{app_id}/appInfos",
                "versions": f"/v1/apps/{app_id}/appStoreVersions",
                "price_schedule": f"/v1/apps/{app_id}/appPriceSchedule",
            },
        },
        "primary_app_info": {
            "id": primary_app_info["id"],
            "paths": {
                "self": f"/v1/appInfos/{primary_app_info['id']}",
                "localizations": f"/v1/appInfos/{primary_app_info['id']}/appInfoLocalizations",
            },
        },
        "app_info_localizations": [
            {
                "id": localization["id"],
                "locale": localization.get("attributes", {}).get("locale"),
                "path": f"/v1/appInfoLocalizations/{localization['id']}",
            }
            for localization in app_info_localizations
        ],
        "current_version": {
            "id": current_version["id"],
            "version_string": current_version.get("attributes", {}).get("versionString"),
            "state": current_version.get("attributes", {}).get("appVersionState"),
            "paths": {
                "self": f"/v1/appStoreVersions/{current_version['id']}",
                "localizations": (
                    f"/v1/appStoreVersions/{current_version['id']}/appStoreVersionLocalizations"
                ),
                "submit_for_review": "/v1/appStoreVersionSubmissions",
            },
        },
        "version_localizations": [
            {
                "id": localization["id"],
                "locale": localization.get("attributes", {}).get("locale"),
                "path": f"/v1/appStoreVersionLocalizations/{localization['id']}",
                "relationships": {
                    "screenshot_sets": (
                        f"/v1/appStoreVersionLocalizations/{localization['id']}/appScreenshotSets"
                    )
                },
            }
            for localization in version_localizations
        ],
    }


def asc_api_get(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    path = _normalize_api_path(runtime, arguments.get("path"), arguments.get("query"))
    return {
        "ok": True,
        "path": path,
        "response": runtime.asc.request("GET", path),
    }


def asc_api_list(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    path = _normalize_api_path(runtime, arguments.get("path"), arguments.get("query"))
    items = runtime.asc.get_collection(path)
    return {
        "ok": True,
        "path": path,
        "count": len(items),
        "items": items,
    }


def asc_api_post(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return _generic_mutation(runtime, method="POST", arguments=arguments, require_body=True)


def asc_api_patch(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return _generic_mutation(runtime, method="PATCH", arguments=arguments, require_body=True)


def asc_api_delete(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    return _generic_mutation(runtime, method="DELETE", arguments=arguments, require_body=False)


def get_asc_api_capabilities(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    include_runtime_entities = bool(arguments.get("include_runtime_entities", True))
    search = str(arguments.get("search") or "").strip().lower()

    catalog = CURATED_CATALOG
    if search:
        catalog = [
            entry
            for entry in CURATED_CATALOG
            if search in entry["resource_type"].lower()
            or search in entry["category"].lower()
            or any(search in path.lower() for path in entry["path_templates"])
            or any(search in note.lower() for note in entry.get("notes", []))
        ]

    runtime_entities: dict[str, Any] | None = None
    if include_runtime_entities:
        try:
            runtime_entities = _discover_runtime_entities(runtime)
        except Exception as exc:  # pragma: no cover - defensive discovery path
            runtime_entities = {
                "ok": False,
                "error": serialize_error(exc)["error"],
            }

    return {
        "ok": True,
        "base_url": runtime.settings.app_store_base_url,
        "generic_tools": [
            {
                "name": "asc_api_get",
                "methods": ["GET"],
                "supports_runtime_discovery": True,
                "logs_mutations": False,
            },
            {
                "name": "asc_api_list",
                "methods": ["GET"],
                "supports_runtime_discovery": True,
                "logs_mutations": False,
            },
            {
                "name": "asc_api_post",
                "methods": ["POST"],
                "supports_runtime_discovery": True,
                "logs_mutations": True,
            },
            {
                "name": "asc_api_patch",
                "methods": ["PATCH"],
                "supports_runtime_discovery": True,
                "logs_mutations": True,
            },
            {
                "name": "asc_api_delete",
                "methods": ["DELETE"],
                "supports_runtime_discovery": True,
                "logs_mutations": True,
            },
        ],
        "json_api_hints": JSON_API_HINTS,
        "catalog": catalog,
        "runtime_entities": runtime_entities,
        "notes": [
            "Use /v1/... paths or full URLs under the configured App Store Connect base URL.",
            "Use asc_api_list for paginated collection endpoints.",
            "Generic mutations now append a change log entry with request path, body, before snapshot, after snapshot, and RevenueCat metrics.",
            "Set search to narrow the catalog to a specific surface such as screenshots, pricing, or appStoreVersionLocalizations.",
        ],
    }


GENERIC_TOOLS = [
    ToolDefinition(
        name="get_asc_api_capabilities",
        description="Describe the generic App Store Connect primitives, JSON:API patterns, curated endpoint catalog, and live runtime resource anchors.",
        input_schema={
            "type": "object",
            "properties": {
                "include_runtime_entities": {"type": "boolean", "description": "Include live runtime resource anchors. Defaults to true."},
                "search": {"type": "string", "description": "Filter the endpoint catalog by resource type, category, or path keyword."},
            },
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=get_asc_api_capabilities,
    ),
    ToolDefinition(
        name="asc_api_get",
        description="Perform a generic GET against the App Store Connect /v1 API.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "App Store Connect API path starting with /v1/."},
                "query": {"type": "object", "additionalProperties": True, "description": "Query parameters as key-value pairs for filtering or pagination."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=asc_api_get,
    ),
    ToolDefinition(
        name="asc_api_list",
        description="Perform a paginated collection read against the App Store Connect /v1 API.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "App Store Connect API path starting with /v1/."},
                "query": {"type": "object", "additionalProperties": True, "description": "Query parameters as key-value pairs for filtering or pagination."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=asc_api_list,
    ),
    ToolDefinition(
        name="asc_api_post",
        description="Perform a generic POST against the App Store Connect /v1 API and log the mutation.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "App Store Connect API path starting with /v1/."},
                "query": {"type": "object", "additionalProperties": True, "description": "Query parameters as key-value pairs for filtering or pagination."},
                "body": {"type": "object", "additionalProperties": True, "description": "JSON:API request body with data.type, data.attributes, and optional data.relationships."},
                "capture_state": {"type": "boolean", "description": "Capture before/after snapshots for the mutation log. Defaults to true."},
            },
            "required": ["path", "body"],
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': True},
        handler=asc_api_post,
    ),
    ToolDefinition(
        name="asc_api_patch",
        description="Perform a generic PATCH against the App Store Connect /v1 API and log the mutation.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "App Store Connect API path starting with /v1/."},
                "query": {"type": "object", "additionalProperties": True, "description": "Query parameters as key-value pairs for filtering or pagination."},
                "body": {"type": "object", "additionalProperties": True, "description": "JSON:API request body with data.type, data.attributes, and optional data.relationships."},
                "capture_state": {"type": "boolean", "description": "Capture before/after snapshots for the mutation log. Defaults to true."},
            },
            "required": ["path", "body"],
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': True},
        handler=asc_api_patch,
    ),
    ToolDefinition(
        name="asc_api_delete",
        description="Perform a generic DELETE against the App Store Connect /v1 API and log the mutation.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "App Store Connect API path starting with /v1/."},
                "query": {"type": "object", "additionalProperties": True, "description": "Query parameters as key-value pairs for filtering or pagination."},
                "capture_state": {"type": "boolean", "description": "Capture before/after snapshots for the mutation log. Defaults to true."},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        annotations={'readOnlyHint': False, 'destructiveHint': True, 'idempotentHint': True, 'openWorldHint': True},
        handler=asc_api_delete,
    ),
]
