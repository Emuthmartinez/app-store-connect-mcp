"""Diagnostic tools for verifying the MCP server can reach its upstreams."""

from __future__ import annotations

from typing import Any

from tooling import ToolDefinition

_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


def test_connection(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    checks: list[dict[str, Any]] = []
    overall_ok = True

    # Check 1: ASC credentials configured
    settings = runtime.settings
    cred_ok = bool(
        settings.app_store_key_id
        and settings.app_store_issuer_id
        and settings.app_store_private_key
        and settings.app_store_bundle_id
    )
    checks.append(
        {
            "name": "asc_credentials_configured",
            "ok": cred_ok,
            "detail": "All required App Store Connect credentials are present."
            if cred_ok
            else "Missing one or more of APP_STORE_KEY_ID, APP_STORE_ISSUER_ID, "
            "APP_STORE_PRIVATE_KEY, APP_STORE_BUNDLE_ID.",
        }
    )
    overall_ok = overall_ok and cred_ok

    # Check 2: ASC token mint
    token_ok = False
    token_detail = "Skipped (credentials missing)."
    if cred_ok:
        try:
            # We do not expose the token; only verify it mints.
            _ = runtime.asc._token_provider.get_token(force_refresh=True)  # noqa: SLF001
            token_ok = True
            token_detail = "JWT token minted successfully."
        except Exception as exc:
            token_detail = f"JWT token mint failed: {type(exc).__name__}: {exc}"
    checks.append({"name": "asc_jwt_mint", "ok": token_ok, "detail": token_detail})
    overall_ok = overall_ok and token_ok

    # Check 3: ASC app lookup by bundle ID
    app_ok = False
    app_detail = "Skipped (token mint failed)."
    app_info: dict[str, Any] | None = None
    if token_ok:
        try:
            app = runtime.asc.get_configured_app()
            app_attrs = app.get("attributes", {}) if isinstance(app, dict) else {}
            app_info = {
                "id": app.get("id") if isinstance(app, dict) else None,
                "name": app_attrs.get("name"),
                "bundle_id": app_attrs.get("bundleId"),
                "primary_locale": app_attrs.get("primaryLocale"),
            }
            app_ok = bool(app_info["id"])
            app_detail = (
                f"Found app {app_info['name']!r} ({app_info['bundle_id']})."
                if app_ok
                else "App lookup returned no id."
            )
        except Exception as exc:
            app_detail = f"App lookup failed: {type(exc).__name__}: {exc}"
    checks.append({"name": "asc_app_lookup", "ok": app_ok, "detail": app_detail, "app": app_info})
    overall_ok = overall_ok and app_ok

    # Check 4: RevenueCat (optional)
    rc_configured = bool(settings.revenuecat_api_key and settings.revenuecat_project_id)
    rc_ok = True
    rc_detail = "Not configured (optional)."
    rc_metrics: dict[str, Any] | None = None
    if rc_configured:
        try:
            overview = runtime.revenuecat.get_overview()
            if overview is None:
                rc_ok = False
                rc_detail = "RevenueCat client returned None (unconfigured or auth rejected)."
            else:
                rc_metrics = overview.get("metrics") if isinstance(overview, dict) else None
                rc_detail = "RevenueCat overview fetched successfully."
        except Exception as exc:
            rc_ok = False
            rc_detail = f"RevenueCat fetch failed: {type(exc).__name__}: {exc}"
    checks.append(
        {
            "name": "revenuecat_overview",
            "ok": rc_ok,
            "configured": rc_configured,
            "detail": rc_detail,
            "metrics": rc_metrics,
        }
    )
    # RevenueCat is optional — only fail overall if it was configured and broke.
    if rc_configured and not rc_ok:
        overall_ok = False

    return {
        "ok": overall_ok,
        "summary": "All configured upstreams reachable." if overall_ok else "One or more checks failed.",
        "checks": checks,
    }


DIAGNOSTIC_TOOLS = [
    ToolDefinition(
        name="asc_test_connection",
        description=(
            "Verify the server can reach its configured upstreams: App Store Connect "
            "(credentials, JWT mint, app lookup) and optionally RevenueCat (overview "
            "fetch). Returns a per-check breakdown suitable for self-serve onboarding "
            "diagnostics."
        ),
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=test_connection,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
]
