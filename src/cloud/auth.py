"""API key authentication for the hosted MCP gateway.

API keys are stored as hashed values (SHA-256 of the raw key). On each
request we hash the inbound key and look up the matching tenant_id.

Keys are prefixed with `ascmcp_` for easy identification in logs and
server settings. Never log the raw key — only the prefix + last 4 chars.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path


def generate_api_key() -> str:
    """Return a new random API key. Show it to the user ONCE."""
    return f"ascmcp_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def obfuscate_api_key(key: str) -> str:
    if len(key) <= 10:
        return key[:3] + "…"
    return f"{key[:10]}…{key[-4:]}"


@dataclass(slots=True)
class ApiKeyRecord:
    tenant_id: str
    key_hash: str
    label: str
    created_at: float


class ApiKeyRegistry:
    """Simple JSON-backed registry. For production, use Postgres."""

    def __init__(self, *, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._records: dict[str, ApiKeyRecord] = {}  # hash -> record
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        for entry in raw.get("api_keys", []):
            record = ApiKeyRecord(
                tenant_id=entry["tenant_id"],
                key_hash=entry["key_hash"],
                label=entry.get("label", ""),
                created_at=entry.get("created_at", time.time()),
            )
            self._records[record.key_hash] = record

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "api_keys": [
                {
                    "tenant_id": r.tenant_id,
                    "key_hash": r.key_hash,
                    "label": r.label,
                    "created_at": r.created_at,
                }
                for r in self._records.values()
            ]
        }
        self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def issue(self, *, tenant_id: str, label: str = "") -> str:
        """Mint a new API key, persist its hash, return the raw key.

        The raw key is only returned from this method. Callers must show it
        to the user once and never log it.
        """
        with self._lock:
            raw_key = generate_api_key()
            record = ApiKeyRecord(
                tenant_id=tenant_id,
                key_hash=hash_api_key(raw_key),
                label=label,
                created_at=time.time(),
            )
            self._records[record.key_hash] = record
            self._persist()
            return raw_key

    def authenticate(self, raw_key: str) -> ApiKeyRecord | None:
        """Return the matching record, or None if the key is unknown."""
        if not raw_key or not raw_key.startswith("ascmcp_"):
            return None
        expected_hash = hash_api_key(raw_key)
        with self._lock:
            for key_hash, record in self._records.items():
                if hmac.compare_digest(key_hash, expected_hash):
                    return record
        return None

    def revoke(self, raw_key: str) -> bool:
        key_hash = hash_api_key(raw_key)
        with self._lock:
            removed = self._records.pop(key_hash, None) is not None
            if removed:
                self._persist()
            return removed

    def list_for_tenant(self, tenant_id: str) -> list[dict[str, str | float]]:
        with self._lock:
            return [
                {
                    "label": r.label,
                    "created_at": r.created_at,
                    "key_hash_prefix": r.key_hash[:12],
                }
                for r in self._records.values()
                if r.tenant_id == tenant_id
            ]
