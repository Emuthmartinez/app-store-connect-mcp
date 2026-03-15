"""Tests for App Store JWT caching."""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from auth import AppStoreJwtProvider
from config import Settings


def _settings(private_key: str) -> Settings:
    return Settings(
        app_store_key_id="KEY1234567",
        app_store_issuer_id="issuer-id",
        app_store_private_key=private_key,
        app_store_bundle_id="example.bundle",
        app_store_sku="example.bundle",
        app_store_apple_id="123456789",
        app_store_name="Example",
        revenuecat_api_key=None,
        revenuecat_project_id=None,
        change_log_path=Path("/tmp/changes.jsonl"),
    )


def _private_key() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def test_token_is_cached_until_refresh_window() -> None:
    timestamps = {"value": 1_000}
    provider = AppStoreJwtProvider(
        _settings(_private_key()),
        time_fn=lambda: timestamps["value"],
    )

    first = provider.get_token()
    second = provider.get_token()

    assert first == second

    timestamps["value"] = 2_101
    third = provider.get_token()

    assert third != first
