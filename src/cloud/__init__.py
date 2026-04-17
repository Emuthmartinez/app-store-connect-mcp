"""Cloud / multi-tenant deployment layer for App Store Connect MCP.

This package converts the stdio MCP server into a hosted service that
serves many tenants (customers) from a single process. Each tenant has
their own encrypted credentials, their own mutation log, their own
RevenueCat configuration.

Layout:
  tenants.py   — Tenant model, per-tenant Runtime construction
  auth.py      — API key authentication for inbound HTTP requests
  gateway.py   — HTTP + SSE gateway that speaks the MCP protocol per-tenant
  billing.py   — Stripe integration scaffolding

This layer is opt-in. Self-hosted users can continue to run src/index.py
over stdio and ignore the cloud/ package entirely.
"""
