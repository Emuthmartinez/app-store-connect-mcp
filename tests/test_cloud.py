"""Tests for the cloud package: tenants, api keys, billing."""

from __future__ import annotations

from pathlib import Path

from cloud.auth import ApiKeyRegistry, generate_api_key, hash_api_key, obfuscate_api_key
from cloud.billing import (
    StripeWebhookVerificationError,
    parse_subscription_event,
    verify_stripe_signature,
)
from cloud.tenants import TenantPlan, TenantRegistry


def test_tenant_plan_from_name() -> None:
    assert TenantPlan.from_name("free").max_apps == 1
    assert TenantPlan.from_name("pro").max_apps == 3
    assert TenantPlan.from_name("team").slack_alerts is True
    assert TenantPlan.from_name("enterprise").scheduled_reports is True


def test_tenant_registry_roundtrip(tmp_path: Path) -> None:
    storage = tmp_path / "tenants.json"
    registry = TenantRegistry(
        storage_path=storage,
        data_root=tmp_path / "tenants",
    )
    tenant = registry.upsert(
        tenant_id="t1",
        plan="pro",
        credentials={
            "app_store_key_id": "K",
            "app_store_issuer_id": "I",
            "app_store_private_key": "P",
            "app_store_bundle_id": "com.example.app",
        },
    )
    assert tenant.plan.name == "pro"
    assert tenant.data_dir.exists()

    # Persistence roundtrip
    registry2 = TenantRegistry(
        storage_path=storage,
        data_root=tmp_path / "tenants",
    )
    found = registry2.get("t1")
    assert found is not None
    assert found.plan.name == "pro"
    assert registry2.delete("t1") is True


def test_api_key_issue_and_authenticate(tmp_path: Path) -> None:
    registry = ApiKeyRegistry(storage_path=tmp_path / "keys.json")
    raw_key = registry.issue(tenant_id="t1", label="ci")
    assert raw_key.startswith("ascmcp_")

    record = registry.authenticate(raw_key)
    assert record is not None
    assert record.tenant_id == "t1"

    # Wrong key
    assert registry.authenticate("ascmcp_not-real") is None
    assert registry.authenticate("") is None
    assert registry.authenticate("bearer-not-ours") is None


def test_api_key_obfuscation() -> None:
    key = generate_api_key()
    masked = obfuscate_api_key(key)
    assert "…" in masked
    assert masked != key
    # Short keys fall through to short mask
    assert "…" in obfuscate_api_key("short")


def test_api_key_hash_stable() -> None:
    assert hash_api_key("x") == hash_api_key("x")
    assert hash_api_key("x") != hash_api_key("y")


def test_api_key_revoke(tmp_path: Path) -> None:
    registry = ApiKeyRegistry(storage_path=tmp_path / "keys.json")
    raw_key = registry.issue(tenant_id="t1")
    assert registry.revoke(raw_key) is True
    assert registry.authenticate(raw_key) is None


def test_stripe_signature_verification() -> None:
    import hashlib
    import hmac
    import time

    secret = "whsec_test"
    payload = b'{"id":"evt_1"}'
    ts = int(time.time())
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{payload.decode()}".encode(),
        hashlib.sha256,
    ).hexdigest()
    header = f"t={ts},v1={sig}"
    # Should not raise
    verify_stripe_signature(payload_bytes=payload, signature_header=header, secret=secret)


def test_stripe_signature_rejects_bad_sig() -> None:
    import time

    header = f"t={int(time.time())},v1=deadbeef"
    try:
        verify_stripe_signature(payload_bytes=b"{}", signature_header=header, secret="whsec")
    except StripeWebhookVerificationError:
        return
    raise AssertionError("Expected StripeWebhookVerificationError")


def test_parse_subscription_event_deleted_downgrades_to_free() -> None:
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_1", "id": "sub_1", "status": "canceled"}},
    }
    update = parse_subscription_event(event)
    assert update is not None
    assert update.plan_name == "free"
    assert update.customer_id == "cus_1"


def test_parse_subscription_event_mapped_price() -> None:
    event = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "customer": "cus_2",
                "id": "sub_2",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            }
        },
    }
    update = parse_subscription_event(event, price_map={"price_pro": "pro"})
    assert update is not None
    assert update.plan_name == "pro"
    assert update.price_id == "price_pro"


def test_parse_subscription_event_ignores_unrelated() -> None:
    assert parse_subscription_event({"type": "charge.refunded", "data": {}}) is None
