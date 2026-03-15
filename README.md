# App Store Connect MCP

Reusable stdio MCP server for App Store Connect listing automation.

## What It Does

- Reads App Store listing state for the configured app.
- Updates description, keywords, subtitle, promotional text, and What’s New.
- Uploads screenshots into an existing or newly created screenshot set.
- Submits the current editable version for review.
- Creates and updates App Store versions, assigns builds, inspects review submissions, and triggers manual release requests.
- Creates and manages Custom Product Pages, Custom Product Page versions, localizations, and CPP screenshot uploads.
- Attaches a Custom Product Page version to an existing App Review submission so experiments do not dead-end at draft state.
- Pulls RevenueCat overview metrics alongside listing data for analysis.
- Exposes product page optimization experiment reads alongside Custom Product Page reads so agents can see both major ASC experimentation surfaces.
- Exposes generic App Store Connect API verbs so agents can work across the wider `/v1` surface without waiting for dedicated wrappers.
- Persists local subscriber freshness state from RevenueCat overview polling and optional webhook ingestion.
- Writes mutation logs to `data/changes.jsonl`.
- Returns explicit `completion_state` and `should_continue` fields in tool responses.

## Configuration

The server loads configuration in this order:

1. repo-local `.env`
2. `APP_STORE_CONNECT_MCP_ENV` if set
3. legacy `ASC_LISTING_MANAGER_ENV` if set
4. process environment

Required App Store keys:

- `APP_STORE_KEY_ID`
- `APP_STORE_ISSUER_ID`
- `APP_STORE_PRIVATE_KEY`
- `APP_STORE_BUNDLE_ID`

Optional RevenueCat keys:

- `REVENUECAT_API_KEY_V2` or `REVENUECAT_API_KEY`
- `REVENUECAT_PROJECT_ID`
- `REVENUECAT_WEBHOOK_AUTH_HEADER`
- `REVENUECAT_WEBHOOK_HOST` default `127.0.0.1`
- `REVENUECAT_WEBHOOK_PORT` default `8787`
- `REVENUECAT_WEBHOOK_PATH` default `/revenuecat`
- `REVENUECAT_EVENT_LOG_PATH`
- `REVENUECAT_SNAPSHOT_PATH`
- `REVENUECAT_OVERVIEW_HISTORY_PATH`
- `APP_STORE_CONNECT_CHANGE_LOG_PATH` or legacy `ASC_LISTING_CHANGE_LOG_PATH`

`APP_STORE_PRIVATE_KEY` can be either inline PEM content or a filesystem path to the `.p8` file.

This server is app-agnostic. Point it at a different business or app by
supplying a different environment file or process environment.

## Local Run

```bash
python3 src/index.py
```

## Portable RevenueCat Webhook Listener

This package includes a local webhook listener that can run on a Mac mini or any other always-on box:

```bash
python3 src/subscriber_webhook.py
```

It stores:

- event log: `data/revenuecat-events.jsonl`
- snapshot: `data/revenuecat-snapshot.json`
- overview history: `data/revenuecat-overview-history.jsonl`

If you want RevenueCat to deliver events directly to the machine, expose the listener with your preferred reverse proxy or tunnel and set `REVENUECAT_WEBHOOK_AUTH_HEADER`.

The local subscriber layer is now:

- idempotent for duplicate `event.id` deliveries
- transfer-aware across `app_user_id`, `original_app_user_id`, `aliases`, `transferred_to`, and `transferred_from`
- append-only for overview polling history so agents can compare pre/post rollout baselines without separate manual exports

## Generic ASC API Coverage

The MCP server now includes generic primitives:

- `get_asc_api_capabilities`
- `asc_api_get`
- `asc_api_list`
- `asc_api_post`
- `asc_api_patch`
- `asc_api_delete`

`get_asc_api_capabilities` returns:

- JSON:API request and relationship hints
- a machine-readable endpoint catalog for the most common listing/version/screenshot/pricing flows
- live runtime anchors for the configured app, app info, current version, and version localizations

Generic mutations are no longer fire-and-forget. `asc_api_post`, `asc_api_patch`, and `asc_api_delete` now log:

- request path and body
- best-effort before and after snapshots
- the raw mutation response
- RevenueCat overview metrics at mutation time

These tools are the portability layer for endpoints that are not wrapped yet, including future Custom Product Page operations.

## Dedicated Experimentation Wrappers

The MCP server now has dedicated agent-facing tools for the ASC surfaces most useful for experimentation:

- Version transitions:
  - `get_version_transition_state`
  - `list_build_candidates`
  - `create_app_store_version`
  - `update_app_store_version`
  - `assign_build_to_version`
  - `release_app_store_version`
  - `get_review_submissions`
  - `create_review_submission`
  - `add_custom_product_page_version_to_review_submission`
- Experiment surfaces:
  - `get_product_page_optimization_experiment`
  - `create_product_page_optimization_experiment`
  - `update_product_page_optimization_experiment`
  - `delete_product_page_optimization_experiment`
  - `list_product_page_optimization_treatments`
  - `get_product_page_optimization_treatment`
  - `create_product_page_optimization_treatment`
  - `update_product_page_optimization_treatment`
  - `delete_product_page_optimization_treatment`
  - `get_product_page_optimization_experiments`
  - `list_custom_product_pages`
  - `get_custom_product_page`
  - `create_custom_product_page`
  - `update_custom_product_page`
  - `delete_custom_product_page`
  - `create_custom_product_page_version`
  - `update_custom_product_page_version`
  - `create_custom_product_page_localization`
  - `update_custom_product_page_localization`
  - `delete_custom_product_page_localization`
  - `upload_custom_product_page_screenshot`

These wrappers keep the workflow agent-native:

- atomic enough for prompt-driven composition
- auditable through the same change log used by listing mutations
- portable to a Mac mini or any other host running the stdio MCP server

Live ASC behavior to account for in agents:

- `create_review_submission` can create a fresh submission even when a different submission is already waiting for review, so agents should read current review state before assuming there is only one.
- `create_custom_product_page` creates the initial CPP draft version and localization inline. That means `create_custom_product_page_version` will return a structured `409` conflict until the current CPP version is no longer inflight.

## Tests

```bash
pytest tests -q
```

## MCP Registration

Example registration:

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

Point the server at an app-specific env file with `APP_STORE_CONNECT_MCP_ENV`
when you need per-business credentials without duplicating the repo.
