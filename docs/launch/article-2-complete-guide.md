# The Complete Guide to the App Store Connect MCP Server

*Target audience: technical — indie iOS devs, MCP tool builders, agent enthusiasts. Channels: Dev.to, Hashnode, Reddit r/iOSProgramming, Hacker News.*

---

This is a deep technical tour of StorePilot, an open-source MCP server that lets AI agents manage Apple App Store Connect listings. We'll cover every tool category, the RevenueCat integration that makes it different, and a quick-start you can follow in 10 minutes.

## What is an MCP server, briefly

The Model Context Protocol (MCP) is a standardized way for AI assistants to talk to external tools. An MCP server exposes a catalog of tools, each with a name, JSON schema, and handler. An MCP client (Claude Desktop, Cursor, n8n, custom agent, …) discovers those tools and calls them on behalf of the model.

StorePilot runs as a stdio MCP server: the client launches a Python process, sends JSON-RPC requests over stdin/stdout, and gets results back.

## Tool categories

### Listing reads (5 tools)
Pull the current state of your listing: app info, localizations, versions, screenshots, pricing.

Example: `asc_get_app_listing` returns the current version's description, subtitle, keywords, promotional text, and what's new, plus all the screenshot sets.

### Listing writes (6 tools)
Mutations with Apple's validation rules enforced client-side:
- `asc_update_keywords` — validates the 100-char limit before you waste an API call
- `asc_update_subtitle` — validates the 30-char limit
- `asc_upload_screenshot` — handles the multi-step reserve / upload / finalize dance

### Versioning (10 tools)
The full lifecycle: create a new version, list available builds, assign a build, submit for review, release. Also handles review submissions and rejection state transitions.

### Custom Product Pages (11 tools)
Full CRUD for CPPs, including localization + screenshot management. Useful for ad campaigns that want different first impressions.

### Product Page Optimization (6 tools)
Create / update / delete PPO experiments and treatments. Run A/B tests without touching the dashboard.

### Analysis (2 tools)
`asc_get_listing_health` — heuristic scoring of your current listing, surfaces gaps (empty promo text, missing target keywords, stale screenshots, etc.). Configurable via env vars.

`asc_suggest_keyword_updates` — proposes new keyword sets drawn from your preferred-keyword list, packed to stay under the 100-char limit.

### Change impact analysis (the moat)
`asc_get_change_impact_analysis` correlates your listing mutations with your RevenueCat metrics. For each recent change, it averages active_subscriptions, active_trials, and MRR in the N days before vs. after the change, and returns percent deltas.

This is the reason I built StorePilot. No other ASO tool does this. It turns "I shipped a keyword change" into "I shipped a keyword change and my trials went up 12% the following week."

### Diagnostics (1 tool)
`asc_test_connection` verifies every upstream: credentials, JWT mint, ASC app lookup, RevenueCat overview. Run this first if anything's acting up.

### Generic ASC API (6 tools)
`asc_api_get`, `asc_api_post`, `asc_api_patch`, `asc_api_delete`, `asc_api_list`, `get_asc_api_capabilities`. Escape hatches for when you need an endpoint we haven't wrapped yet. Every mutation goes through the same mutation log.

### RevenueCat subscriber tools (4 tools)
Read the current overview snapshot, list recent webhook events, fetch overview history. Fully optional — every tool degrades gracefully if RevenueCat is not configured.

### Google Play Console (5 tools, scaffold)
Stubs for `gpc_get_app_listing`, `gpc_update_listing`, `gpc_get_listing_health`, `gpc_get_reviews`, `gpc_upload_screenshot`. Coming in Phase 3.

## The mutation log

Every write tool logs a JSONL record to `data/changes.jsonl`:

```json
{
  "timestamp": "2026-03-15T14:22:00+00:00",
  "operation": "update_keywords",
  "locale": "en-US",
  "target": {"id": "version-loc-id"},
  "before": {"keywords": "foo,bar"},
  "after": {"keywords": "ai,foo,bar"},
  "revenuecat_metrics": {"metrics": {"mrr": 1200, "active_subscriptions": 85}}
}
```

This log is the input to `asc_get_change_impact_analysis`. It's also a perfect audit trail for teams — everything your agent does is recorded, with a diff.

## Quick start (10 minutes)

```bash
git clone https://github.com/Emuthmartinez/app-store-connect-mcp
cd app-store-connect-mcp
pip install -e .
cp .env.example .env
# Fill in APP_STORE_KEY_ID, APP_STORE_ISSUER_ID, APP_STORE_PRIVATE_KEY,
# APP_STORE_BUNDLE_ID. See docs/asc-api-key-setup.md for how to mint the key.
```

Add it to Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "app-store-connect-mcp": {
      "command": "python3",
      "args": ["/abs/path/to/app-store-connect-mcp/src/index.py"]
    }
  }
}
```

Restart Claude Desktop, and ask: "What's my current App Store listing look like?" You're off.

## What's next

Phase 3 adds Google Play Console parity, SSO, audit log UI, and the hosted cloud tier with managed JWT, Stripe billing, and scheduled reports. Follow the repo for updates.

**Repo:** https://github.com/Emuthmartinez/app-store-connect-mcp
**License:** MIT
