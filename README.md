# App Store Connect MCP

Reusable stdio MCP server for App Store Connect listing automation.

App-agnostic — configure one default app, then target any other app visible to the same API key per tool call.

## What It Does

- Reads and updates App Store listing metadata (description, keywords, subtitle, promotional text, What's New).
- Uploads screenshots into existing or newly created screenshot sets.
- Manages App Store versions: create, assign builds, submit for review, release.
- Full Custom Product Page lifecycle: create, version, localize, upload screenshots, attach to review submissions.
- Product page optimization experiments: create, configure treatments, start/stop.
- Generic App Store Connect API verbs (`asc_api_get`, `asc_api_post`, etc.) for endpoints without dedicated wrappers.
- Every mutation is logged with before/after snapshots to `data/changes.jsonl`.
- All tool responses include `completion_state` and `should_continue` for agentic workflows.

All tool names are prefixed with `asc_` to prevent collisions when used alongside other MCP servers.
Every tool includes MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) so clients can auto-approve reads and gate destructive operations.

## Why RevenueCat?

RevenueCat integration is **optional** — the server works fully without it.

When configured, RevenueCat provides the monetization signal that closes the loop between listing changes and business outcomes. Agents can see active subscriptions, trials, and MRR alongside listing metadata, which lets them correlate a keyword change or screenshot swap with subscriber movement. Without this signal, listing optimization is copy-driven only; with it, agents can make data-informed decisions about what to test next.

The integration includes:
- Overview metrics polling (active subscriptions, trials, MRR) surfaced in listing health reports.
- Local webhook listener for real-time subscriber event ingestion.
- Append-only overview history so agents can compare pre/post rollout baselines.

If you don't use RevenueCat, simply omit the `REVENUECAT_*` keys. All RevenueCat-dependent tools degrade gracefully and return `null` metrics.

## Configuration

The server loads configuration in this order:

1. repo-local `.env`
2. `APP_STORE_CONNECT_MCP_ENV` if set (path to an env file)
3. legacy `ASC_LISTING_MANAGER_ENV` if set
4. process environment

### Required

| Variable | Description |
|----------|-------------|
| `APP_STORE_KEY_ID` | App Store Connect API key ID |
| `APP_STORE_ISSUER_ID` | App Store Connect issuer ID |
| `APP_STORE_PRIVATE_KEY` | Inline PEM content or path to `.p8` file |
| `APP_STORE_BUNDLE_ID` | Bundle ID of the default app to manage when no per-call selector is supplied |

### Optional — RevenueCat

| Variable | Description |
|----------|-------------|
| `REVENUECAT_API_KEY_V2` | RevenueCat v2 API key (or `REVENUECAT_API_KEY`) |
| `REVENUECAT_PROJECT_ID` | RevenueCat project ID |
| `REVENUECAT_WEBHOOK_AUTH_HEADER` | Auth header for webhook verification |
| `REVENUECAT_WEBHOOK_HOST` | Webhook listener host (default `127.0.0.1`) |
| `REVENUECAT_WEBHOOK_PORT` | Webhook listener port (default `8787`) |
| `REVENUECAT_WEBHOOK_PATH` | Webhook listener path (default `/revenuecat`) |

### Optional — Analysis Heuristics

Listing health and keyword suggestion tools use configurable heuristics via JSON environment variables:

| Variable | Description |
|----------|-------------|
| `ASC_COPY_TERMS` | JSON object mapping areas to search terms, e.g. `{"subtitle": ["ai", "stylist"]}` |
| `ASC_BENCHMARK_NOTES` | JSON array of benchmark objects, e.g. `[{"lever": "pricing", "benchmark": "..."}]` |
| `ASC_PREFERRED_KEYWORDS` | JSON array of keyword strings for suggestions |

If these are not set, analysis tools skip heuristic checks and return metrics-only results.

## Quick Start

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run the server
python3 src/index.py
```

## MCP Registration

```json
{
  "mcpServers": {
    "app-store-connect-mcp": {
      "command": "python3",
      "args": ["/absolute/path/to/app-store-connect-mcp/src/index.py"]
    }
  }
}
```

Point at an app-specific env file with `APP_STORE_CONNECT_MCP_ENV` when you need per-app credentials without duplicating the repo.

Ready-made client snippets for Claude, Codex, and generic MCP registration live in `clients/`.

## Managing Multiple Apps

Most tools accept one optional app selector:

- `app_id` — exact App Store Connect app id. Prefer this when you know it.
- `bundle_id` — exact bundle id, e.g. `com.example.app`.
- `app_name` — exact app name. Use this only when ids are unavailable.

Provide only one selector per call. If no selector is supplied, the server uses `APP_STORE_BUNDLE_ID` as the default app. The selected app is resolved once, cached in memory, and then all dedicated listing, screenshot, versioning, Custom Product Page, review, and analysis tools use that app's relationships for the call.

Example calls:

```json
{"bundle_id": "com.example.nextapp", "locale": "en-US"}
```

```json
{"app_id": "1234567890", "locale": "en-US", "subtitle": "Plan outfits faster"}
```

The RevenueCat subscriber tools remain profile/project-scoped and do not accept app selectors.

## RevenueCat Webhook Listener

Optional standalone webhook listener for real-time subscriber event ingestion:

```bash
python3 src/subscriber_webhook.py
```

Stores event log, snapshot, and overview history as JSONL/JSON in `data/`. Expose with a reverse proxy or tunnel if you want RevenueCat to deliver events directly.

The subscriber layer is:
- Idempotent for duplicate `event.id` deliveries.
- Transfer-aware across `app_user_id`, `original_app_user_id`, aliases, and transfer fields.
- Append-only for overview history.

## Tests

```bash
pytest tests -q
```

## CI

GitHub Actions runs `ruff check`, `ruff format --check`, and `pytest` on Python 3.11-3.13 for every push and PR to `main`.

## Tool Reference

All 54 tools are prefixed with `asc_` and include MCP annotations. Key categories:

**Listing reads:** `asc_get_app_info`, `asc_get_app_listing`, `asc_get_app_versions`, `asc_get_app_screenshots`, `asc_get_app_pricing`

**Listing writes:** `asc_update_description`, `asc_update_keywords`, `asc_update_subtitle`, `asc_update_promotional_text`, `asc_update_whats_new`, `asc_upload_screenshot`, `asc_submit_for_review`

**Versioning:** `asc_get_version_transition_state`, `asc_list_build_candidates`, `asc_create_app_store_version`, `asc_update_app_store_version`, `asc_assign_build_to_version`, `asc_release_app_store_version`

**Review:** `asc_get_review_submissions`, `asc_create_review_submission`, `asc_add_custom_product_page_version_to_review_submission`

**Experiments:** `asc_get_product_page_optimization_experiments`, `asc_create_product_page_optimization_experiment`, `asc_update_product_page_optimization_experiment`, `asc_delete_product_page_optimization_experiment`, plus treatment CRUD

**Custom Product Pages:** `asc_list_custom_product_pages`, `asc_get_custom_product_page`, `asc_create_custom_product_page`, plus version, localization, and screenshot operations

**Generic API:** `get_asc_api_capabilities`, `asc_api_get`, `asc_api_list`, `asc_api_post`, `asc_api_patch`, `asc_api_delete`

**Analysis:** `asc_get_listing_health`, `asc_suggest_keyword_updates`

**Subscriber:** `asc_refresh_subscriber_overview`, `asc_get_subscriber_snapshot`, `asc_list_subscriber_events`, `asc_list_subscriber_overview_history`

## ASC API Behavioral Notes

- `asc_create_review_submission` can create a fresh submission even when one is already waiting for review. Agents should read current review state first.
- `asc_create_custom_product_page` creates the initial draft version and localization inline. `asc_create_custom_product_page_version` will return a `409` until the current version is no longer inflight.
- Dedicated app-scoped tools accept `app_id`, `bundle_id`, or `app_name` so one MCP registration can manage all apps visible to the API key.
- Generic mutation tools (`asc_api_post`, `asc_api_patch`, `asc_api_delete`) log before/after snapshots and RevenueCat metrics to the change log.

## License

MIT
