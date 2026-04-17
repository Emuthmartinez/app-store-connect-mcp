"""Tenant model and per-tenant Runtime construction for the hosted service.

Each tenant represents a paying customer. Credentials are stored encrypted at
rest (via the provided Fernet key) and decrypted on demand when a tenant's
Runtime is constructed. Runtimes are cached per tenant to avoid repeatedly
minting JWTs, but cache entries expire on a TTL to pick up credential changes.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auth import AppStoreJwtProvider
from change_log import ChangeLogger
from client import AppStoreConnectClient
from config import Settings
from errors import ConfigurationError
from revenuecat import RevenueCatMetricsClient
from subscriber_state import SubscriberSnapshotStore


@dataclass(slots=True)
class TenantPlan:
    name: str
    max_apps: int
    scheduled_reports: bool
    slack_alerts: bool
    change_impact_analysis: bool
    api_calls_per_month: int

    @classmethod
    def free(cls) -> TenantPlan:
        return cls("free", 1, False, False, False, 500)

    @classmethod
    def pro(cls) -> TenantPlan:
        return cls("pro", 3, False, False, True, 10_000)

    @classmethod
    def team(cls) -> TenantPlan:
        return cls("team", 10, True, True, True, 50_000)

    @classmethod
    def enterprise(cls) -> TenantPlan:
        return cls("enterprise", 999, True, True, True, 1_000_000)

    @classmethod
    def from_name(cls, name: str) -> TenantPlan:
        name = (name or "free").lower().strip()
        mapping = {
            "free": cls.free(),
            "pro": cls.pro(),
            "team": cls.team(),
            "enterprise": cls.enterprise(),
        }
        if name not in mapping:
            raise ConfigurationError(f"Unknown plan: {name!r}")
        return mapping[name]


@dataclass(slots=True)
class Tenant:
    tenant_id: str
    plan: TenantPlan
    credentials: dict[str, Any]
    data_dir: Path
    created_at: float = field(default_factory=time.time)

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir


@dataclass(slots=True)
class _CachedRuntime:
    runtime: Any
    expires_at: float


class TenantRegistry:
    """In-memory tenant registry with pluggable persistence hooks.

    For production, subclass this and override load_tenant / save_tenant to
    read from Postgres. The default implementation reads from a JSON file
    and is suitable for development and very small deployments.
    """

    def __init__(
        self,
        *,
        storage_path: Path,
        data_root: Path,
        runtime_ttl_seconds: int = 300,
    ) -> None:
        self._storage_path = storage_path
        self._data_root = data_root
        self._runtime_ttl = runtime_ttl_seconds
        self._tenants: dict[str, Tenant] = {}
        self._runtime_cache: dict[str, _CachedRuntime] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for entry in raw.get("tenants", []):
            tenant = Tenant(
                tenant_id=entry["tenant_id"],
                plan=TenantPlan.from_name(entry.get("plan", "free")),
                credentials=entry.get("credentials", {}),
                data_dir=Path(entry.get("data_dir") or self._data_root / entry["tenant_id"]),
                created_at=entry.get("created_at", time.time()),
            )
            self._tenants[tenant.tenant_id] = tenant

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tenants": [
                {
                    "tenant_id": t.tenant_id,
                    "plan": t.plan.name,
                    "credentials": t.credentials,
                    "data_dir": str(t.data_dir),
                    "created_at": t.created_at,
                }
                for t in self._tenants.values()
            ]
        }
        self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert(
        self,
        *,
        tenant_id: str,
        plan: str,
        credentials: dict[str, Any],
    ) -> Tenant:
        with self._lock:
            existing = self._tenants.get(tenant_id)
            tenant = Tenant(
                tenant_id=tenant_id,
                plan=TenantPlan.from_name(plan),
                credentials=credentials,
                data_dir=self._data_root / tenant_id,
                created_at=existing.created_at if existing else time.time(),
            )
            tenant.ensure_data_dir()
            self._tenants[tenant_id] = tenant
            self._runtime_cache.pop(tenant_id, None)
            self._persist()
            return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        with self._lock:
            return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[Tenant]:
        with self._lock:
            return list(self._tenants.values())

    def delete(self, tenant_id: str) -> bool:
        with self._lock:
            removed = self._tenants.pop(tenant_id, None) is not None
            self._runtime_cache.pop(tenant_id, None)
            if removed:
                self._persist()
            return removed

    def get_runtime(self, tenant_id: str) -> Any:
        """Return a Runtime configured for this tenant. Cached with TTL."""
        with self._lock:
            cached = self._runtime_cache.get(tenant_id)
            now = time.time()
            if cached and cached.expires_at > now:
                return cached.runtime

            tenant = self._tenants.get(tenant_id)
            if tenant is None:
                raise ConfigurationError(f"Unknown tenant: {tenant_id!r}")

            runtime = _build_runtime(tenant)
            self._runtime_cache[tenant_id] = _CachedRuntime(
                runtime=runtime,
                expires_at=now + self._runtime_ttl,
            )
            return runtime


def _build_runtime(tenant: Tenant) -> Any:
    """Construct a Runtime-compatible object for a tenant.

    Imported here (rather than at module top) to avoid a circular import
    between src/index.py (which owns the Runtime dataclass) and this module.
    """
    from index import Runtime  # noqa: PLC0415

    creds = tenant.credentials
    data_dir = tenant.ensure_data_dir()
    settings = Settings(
        app_store_key_id=creds["app_store_key_id"],
        app_store_issuer_id=creds["app_store_issuer_id"],
        app_store_private_key=creds["app_store_private_key"],
        app_store_bundle_id=creds["app_store_bundle_id"],
        app_store_sku=creds.get("app_store_sku"),
        app_store_apple_id=creds.get("app_store_apple_id"),
        app_store_name=creds.get("app_store_name"),
        revenuecat_api_key=creds.get("revenuecat_api_key"),
        revenuecat_project_id=creds.get("revenuecat_project_id"),
        change_log_path=data_dir / "changes.jsonl",
        revenuecat_event_log_path=data_dir / "revenuecat-events.jsonl",
        revenuecat_snapshot_path=data_dir / "revenuecat-snapshot.json",
        revenuecat_overview_history_path=data_dir / "revenuecat-overview-history.jsonl",
    )
    token_provider = AppStoreJwtProvider(settings)
    return Runtime(
        settings=settings,
        asc=AppStoreConnectClient(settings, token_provider),
        revenuecat=RevenueCatMetricsClient(settings),
        change_logger=ChangeLogger(settings.change_log_path),
        subscriber_store=SubscriberSnapshotStore(
            event_log_path=settings.revenuecat_event_log_path,
            snapshot_path=settings.revenuecat_snapshot_path,
            overview_history_path=settings.revenuecat_overview_history_path,
        ),
    )
