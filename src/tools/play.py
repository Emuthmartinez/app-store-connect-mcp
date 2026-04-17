"""Google Play Console tool scaffolding.

These tools are the beachhead for cross-platform app store management.
Each tool here mirrors an ASC counterpart (e.g. gpc_get_app_listing ≈
asc_get_app_listing) so an AI agent can manage iOS + Android listings
with one tool vocabulary.

Implementations are stubs that raise NotImplementedError with a clear
"coming in Phase 3" message. The schemas are real, so agents see the
intended API shape even before the implementations land. When you
wire this up, use the Google Play Developer API v3:
  https://developers.google.com/android-publisher
"""

from __future__ import annotations

from typing import Any

from tooling import ToolDefinition

_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

_MUTATION_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": True,
}


_STUB_PAYLOAD = {
    "ok": False,
    "error": {
        "code": "not_implemented",
        "message": (
            "Google Play Console integration is scaffolded but not yet implemented. "
            "This tool is part of the Phase 3 roadmap. Self-host users: contributions "
            "welcome. Cloud users: this ships with the Team tier in Phase 3."
        ),
        "retryable": False,
    },
}


def _stub(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del runtime, arguments
    return dict(_STUB_PAYLOAD)


PLAY_TOOLS = [
    ToolDefinition(
        name="gpc_get_app_listing",
        description=(
            "[Scaffold — Phase 3] Read a localized Google Play Store listing: "
            "title, short description, full description, graphic assets. "
            "Mirrors asc_get_app_listing for cross-platform parity."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package_name": {
                    "type": "string",
                    "description": "Android package name, e.g. com.example.myapp.",
                },
                "locale": {
                    "type": "string",
                    "description": "BCP 47 locale code, e.g. en-US, ja-JP.",
                },
            },
            "required": ["package_name"],
            "additionalProperties": False,
        },
        handler=_stub,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    ToolDefinition(
        name="gpc_update_listing",
        description=(
            "[Scaffold — Phase 3] Update localized Play Store listing fields: "
            "title (max 30 chars), short description (max 80), full description (max 4000). "
            "Apply via edits API."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Android package name."},
                "locale": {"type": "string", "description": "BCP 47 locale code."},
                "title": {"type": "string", "description": "App title, ≤30 chars."},
                "short_description": {"type": "string", "description": "Short description, ≤80 chars."},
                "full_description": {"type": "string", "description": "Full description, ≤4000 chars."},
            },
            "required": ["package_name", "locale"],
            "additionalProperties": False,
        },
        handler=_stub,
        annotations=_MUTATION_ANNOTATIONS,
    ),
    ToolDefinition(
        name="gpc_get_listing_health",
        description=(
            "[Scaffold — Phase 3] Compute a Play Store listing health score "
            "(mirrors asc_get_listing_health). Combines copy completeness, asset "
            "coverage, and RevenueCat Android metrics when configured."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Android package name."},
                "locale": {"type": "string", "description": "BCP 47 locale code."},
            },
            "required": ["package_name"],
            "additionalProperties": False,
        },
        handler=_stub,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    ToolDefinition(
        name="gpc_get_reviews",
        description=(
            "[Scaffold — Phase 3] Fetch recent Play Store user reviews for an app. "
            "Useful for surfacing sentiment shifts after listing or version changes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Android package name."},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum reviews to fetch (default 25, max 100).",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["package_name"],
            "additionalProperties": False,
        },
        handler=_stub,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    ToolDefinition(
        name="gpc_upload_screenshot",
        description=(
            "[Scaffold — Phase 3] Upload a screenshot asset (PHONE, TABLET_7, "
            "TABLET_10, WEAR, TV) to a Play Store listing via the edits API. "
            "Asset must be a valid PNG/JPEG at Play Store dimension rules."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "package_name": {"type": "string", "description": "Android package name."},
                "locale": {"type": "string", "description": "BCP 47 locale code."},
                "image_type": {
                    "type": "string",
                    "description": (
                        "One of: phoneScreenshots, sevenInchScreenshots, "
                        "tenInchScreenshots, tvScreenshots, wearScreenshots."
                    ),
                },
                "file_path": {"type": "string", "description": "Absolute path to the image file."},
            },
            "required": ["package_name", "locale", "image_type", "file_path"],
            "additionalProperties": False,
        },
        handler=_stub,
        annotations=_MUTATION_ANNOTATIONS,
    ),
]
