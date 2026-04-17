# App Store Connect MCP

> AI-native App Store Connect management. Open-source MCP server with revenue-correlation built in.

Two ways to run it:

- **Self-hosted (free, MIT)**: Run `python3 src/index.py`, register with any MCP client (Claude Desktop, Cursor, Codex, n8n…), done. See [docs/quick-start.md](docs/quick-start.md).
- **Hosted cloud ($29–$199/mo)**: Managed endpoint, Stripe billing, weekly health reports, Slack/Discord alerts, audit log UI. See [docs/cloud-setup.md](docs/cloud-setup.md).

## What It Does

- **Read & mutate listings** — description, keywords, subtitle, promo text, What's New, screenshots.
- **Manage versions** — create, assign builds, submit for review, release.
- **Custom Product Pages** — full CRUD with version/localization/screenshot lifecycle.
- **Product Page Optimization** — experiments and treatments without opening ASC.
- **Revenue-correlation moat** — `asc_get_change_impact_analysis` correlates every listing mutation with your RevenueCat metrics. See [docs/change-impact.md](docs/change-impact.md).
- **Scheduled weekly reports** — health score + revenue trend + change impact, piped to email/Slack.
- **Slack/Discord alerts** — MRR shifts, health score drops, review state transitions.
- **Diagnostics** — `asc_test_connection` isolates which upstream is broken when something fails.
- **Google Play Console** (Phase 3 scaffold) — cross-platform parity coming in `gpc_*` tools.
- **Generic ASC verbs** — `asc_api_get/post/patch/delete` for any endpoint we don't wrap yet.
- **Audit trail** — every mutation logs before/after diff + RevenueCat snapshot to `data/changes.jsonl`.
- **Agentic-ready** — every response includes `completion_state` and `should_continue`.

All tool names are prefixed with `asc_` (or `gpc_` for Play) to prevent collisions when used alongside other MCP servers. Every tool includes MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) so clients can auto-approve reads and gate destructive operations.

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
| `APP_STORE_BUNDLE_ID` | Bundle ID of the app to manage |

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

60+ tools, all prefixed with `asc_` (or `gpc_` for Play scaffolds) and all include MCP annotations. Key categories:

**Listing reads:** `asc_get_app_info`, `asc_get_app_listing`, `asc_get_app_versions`, `asc_get_app_screenshots`, `asc_get_app_pricing`

**Listing writes:** `asc_update_description`, `asc_update_keywords`, `asc_update_subtitle`, `asc_update_promotional_text`, `asc_update_whats_new`, `asc_upload_screenshot`, `asc_submit_for_review`

**Versioning:** `asc_get_version_transition_state`, `asc_list_build_candidates`, `asc_create_app_store_version`, `asc_update_app_store_version`, `asc_assign_build_to_version`, `asc_release_app_store_version`

**Review:** `asc_get_review_submissions`, `asc_create_review_submission`, `asc_add_custom_product_page_version_to_review_submission`

**Experiments:** `asc_get_product_page_optimization_experiments`, `asc_create_product_page_optimization_experiment`, `asc_update_product_page_optimization_experiment`, `asc_delete_product_page_optimization_experiment`, plus treatment CRUD

**Custom Product Pages:** `asc_list_custom_product_pages`, `asc_get_custom_product_page`, `asc_create_custom_product_page`, plus version, localization, and screenshot operations

**Generic API:** `get_asc_api_capabilities`, `asc_api_get`, `asc_api_list`, `asc_api_post`, `asc_api_patch`, `asc_api_delete`

**Analysis:** `asc_get_listing_health`, `asc_suggest_keyword_updates`

**Change impact (revenue correlation):** `asc_get_change_impact_analysis`

**Diagnostics:** `asc_test_connection`

**Google Play (scaffold, Phase 3):** `gpc_get_app_listing`, `gpc_update_listing`, `gpc_get_listing_health`, `gpc_get_reviews`, `gpc_upload_screenshot`

**Subscriber:** `asc_refresh_subscriber_overview`, `asc_get_subscriber_snapshot`, `asc_list_subscriber_events`, `asc_list_subscriber_overview_history`

## ASC API Behavioral Notes

- `asc_create_review_submission` can create a fresh submission even when one is already waiting for review. Agents should read current review state first.
- `asc_create_custom_product_page` creates the initial draft version and localization inline. `asc_create_custom_product_page_version` will return a `409` until the current version is no longer inflight.
- Generic mutation tools (`asc_api_post`, `asc_api_patch`, `asc_api_delete`) log before/after snapshots and RevenueCat metrics to the change log.

## Running the Cloud Gateway (self-hosting the hosted tier)

If you want to host the multi-tenant cloud mode yourself:

```bash
python3 src/cloud/server.py
```

This launches the HTTP/SSE gateway on `0.0.0.0:8080` (configurable via
`ASCMCP_CLOUD_HOST` / `ASCMCP_CLOUD_PORT`). Tenants and API keys persist
to `./data/cloud/`. See [docs/cloud-setup.md](docs/cloud-setup.md) for
the full protocol and billing hookup.

## Roadmap

- **Phase 1** (shipped): Core MCP server, RevenueCat integration, analysis, CPP, experiments, generic verbs, **change impact analysis**, **diagnostics**, **cloud gateway**, **multi-tenant runtime**, **Stripe billing scaffolding**, **Slack/Discord notifications**, **weekly health reports**.
- **Phase 2**: Hosted cloud GA, Product Hunt launch, docs site, content flywheel.
- **Phase 3**: Google Play Console integration, SSO + audit log UI, enterprise RBAC, annual plans + referrals.

See [docs/90-DAY-SAAS-PROFITABILITY-PLAN.md](docs/90-DAY-SAAS-PROFITABILITY-PLAN.md) for the detailed roadmap.

## License

MIT
