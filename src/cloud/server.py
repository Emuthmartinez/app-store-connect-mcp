"""Entrypoint for the hosted MCP service.

Run with:
  python3 src/cloud/server.py

Reads config from env:
  ASCMCP_CLOUD_HOST          default 0.0.0.0
  ASCMCP_CLOUD_PORT          default 8080
  ASCMCP_CLOUD_DATA_DIR      directory for tenant data (default: ./data/cloud)

This entrypoint is deliberately minimal. Production deployments should
front this with a real reverse proxy (Caddy, Nginx, Cloudflare) for TLS.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from cloud.auth import ApiKeyRegistry  # noqa: E402
from cloud.gateway import build_gateway, serve_forever  # noqa: E402
from cloud.tenants import TenantRegistry  # noqa: E402

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> None:
    host = os.environ.get("ASCMCP_CLOUD_HOST", "0.0.0.0")
    port = int(os.environ.get("ASCMCP_CLOUD_PORT", "8080"))
    data_dir = Path(os.environ.get("ASCMCP_CLOUD_DATA_DIR", "./data/cloud")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    tenant_registry = TenantRegistry(
        storage_path=data_dir / "tenants.json",
        data_root=data_dir / "tenants",
    )
    api_key_registry = ApiKeyRegistry(
        storage_path=data_dir / "api_keys.json",
    )

    gateway = build_gateway(
        tenant_registry=tenant_registry,
        api_key_registry=api_key_registry,
        host=host,
        port=port,
    )
    try:
        serve_forever(gateway)
    except KeyboardInterrupt:
        gateway.shutdown()


if __name__ == "__main__":
    main()
