# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A reusable stdio MCP server for App Store Connect listing automation with RevenueCat metrics integration. App-agnostic — switch apps by pointing to a different env file.

## Commands

```bash
# Run the MCP server
python3 src/index.py

# Run the RevenueCat webhook listener
python3 src/subscriber_webhook.py

# Run all tests
pytest tests -q

# Run a single test file
pytest tests/test_auth.py -q

# Run a single test by name
pytest tests/test_auth.py -k "test_name" -q

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

No build step. Python 3.11+ required.

## Architecture

**Entrypoint**: `src/index.py` — creates an MCP `Server` (name: `app_store_connect_mcp`), lazily initializes a `Runtime` dataclass that holds all shared dependencies, and dispatches tool calls by name. Sync tool handlers are wrapped with `asyncio.to_thread()` to avoid blocking the event loop. All logging goes to stderr to keep the stdio protocol clean.

**Tool system**: Tools are `ToolDefinition` instances (defined in `src/tooling.py`) — each pairs a name, JSON schema, handler function, and MCP annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`). Handlers receive `(runtime, arguments)` and return a dict payload. The entrypoint adds `completion_state` and `should_continue` fields to every response. All tool names are prefixed with `asc_` for namespace safety. Tools are organized by domain in `src/tools/`:
- `read.py` — listing state reads
- `write.py` — listing mutations (description, keywords, screenshots, etc.)
- `versioning.py` — version lifecycle (create, assign build, submit for review, release)
- `cpp.py` — Custom Product Pages CRUD and screenshot uploads
- `analysis.py` — configurable listing health heuristics (via `ASC_COPY_TERMS`, `ASC_BENCHMARK_NOTES`, `ASC_PREFERRED_KEYWORDS` env vars)
- `generic.py` — raw ASC API verbs (`asc_api_get`, `asc_api_post`, etc.)
- `subscriber.py` — RevenueCat subscriber state and webhook data

All tool lists are aggregated in `src/tools/__init__.py` as `ALL_TOOLS`.

**Key modules**:
- `src/client.py` — `AppStoreConnectClient`, thin wrapper around the ASC REST API with retry logic and JSON:API helpers
- `src/auth.py` — `AppStoreJwtProvider`, thread-safe JWT minting with caching and auto-refresh
- `src/config.py` — `Settings.load()` merges `.env` → env file overrides → process env; supports legacy env var names
- `src/errors.py` — structured error hierarchy (`AppStoreConnectMcpError` base) with `serialize_error()` for consistent JSON error payloads
- `src/change_log.py` — append-only JSONL mutation log
- `src/subscriber_state.py` — idempotent, transfer-aware RevenueCat subscriber snapshot store

**Mutation logging**: All write operations (both dedicated tools and generic API verbs) log before/after snapshots plus RevenueCat metrics to `data/changes.jsonl` via `log_mutation()` in `src/tools/shared.py`.

## Configuration

Loaded by `Settings.load()` in priority order: `.env` → `APP_STORE_CONNECT_MCP_ENV` path → process environment. Required keys: `APP_STORE_KEY_ID`, `APP_STORE_ISSUER_ID`, `APP_STORE_PRIVATE_KEY`, `APP_STORE_BUNDLE_ID`. `APP_STORE_PRIVATE_KEY` accepts inline PEM or a `.p8` file path. Profile-specific env files go in `profiles/`.

Analysis heuristics are configurable via env vars (JSON):
- `ASC_COPY_TERMS` — subtitle/keyword/description gap detection terms
- `ASC_BENCHMARK_NOTES` — business benchmark notes surfaced in health reports
- `ASC_PREFERRED_KEYWORDS` — keyword suggestions for `asc_suggest_keyword_updates`

## Testing

Tests use `conftest.py` to add `src/` to `sys.path`. No fixtures beyond path setup — tests construct their own mocks/stubs. The test suite runs offline without real API credentials.

## Conventions

- Imports within `src/` are flat (e.g., `from config import Settings`, not `from src.config`), enabled by `sys.path` manipulation in `index.py` and `conftest.py`.
- Tool handlers are pure sync functions `(Runtime, dict) → dict`. Side effects go through `runtime.*` dependencies. They run in a thread pool via `asyncio.to_thread()`.
- All tool names must start with `asc_` to prevent namespace collisions with other MCP servers.
- All `ToolDefinition` entries must include `annotations` with `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.
- All input schema properties must include a `description` string.
- All tool responses must include `ok: bool` at minimum. Error payloads use `code`, `message`, `retryable` fields.
- Client config example files live in `clients/` for Codex, Claude, and generic MCP registration.

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs ruff lint/format and pytest on Python 3.11-3.13.
