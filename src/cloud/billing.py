"""Stripe billing integration scaffolding.

Responsibilities:
- Map Stripe price IDs to TenantPlan names.
- Verify Stripe webhook signatures.
- Translate subscription lifecycle events (customer.subscription.created,
  customer.subscription.updated, customer.subscription.deleted,
  invoice.payment_failed) into TenantRegistry updates.

This module is wire-compatible with Stripe's webhook payloads but
intentionally avoids a hard dependency on the `stripe` Python library.
Signature verification uses stdlib hmac to keep the surface area small.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Default price ID -> plan mapping. Override via env var STRIPE_PRICE_MAP
# (JSON object mapping price_id -> plan name).
DEFAULT_PRICE_MAP: dict[str, str] = {
    # Fill in after you create Stripe products:
    # "price_1ProMonthly...": "pro",
    # "price_1TeamMonthly...": "team",
    # "price_1EnterpriseMonthly...": "enterprise",
}


@dataclass(slots=True)
class SubscriptionUpdate:
    event_type: str
    customer_id: str
    subscription_id: str | None
    price_id: str | None
    plan_name: str
    status: str


class StripeWebhookVerificationError(Exception):
    """Raised when a Stripe webhook signature fails verification."""


def verify_stripe_signature(
    *,
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300,
) -> None:
    """Verify a Stripe-Signature header. Raises on failure.

    Implements Stripe's documented scheme:
      t=<unix_ts>,v1=<hex_hmac>,v0=<legacy>,...
    Signed payload is f"{t}.{payload_bytes}".
    """
    if not signature_header:
        raise StripeWebhookVerificationError("Missing signature header")

    parts = dict(
        kv.split("=", 1) for kv in signature_header.split(",") if "=" in kv
    )
    timestamp_raw = parts.get("t")
    provided_sig = parts.get("v1")
    if not timestamp_raw or not provided_sig:
        raise StripeWebhookVerificationError("Malformed signature header")

    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise StripeWebhookVerificationError("Invalid timestamp") from exc

    if abs(time.time() - timestamp) > tolerance_seconds:
        raise StripeWebhookVerificationError("Signature timestamp outside tolerance")

    signed_payload = f"{timestamp}.{payload_bytes.decode('utf-8')}".encode()
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise StripeWebhookVerificationError("Signature mismatch")


def parse_subscription_event(
    event: dict,
    *,
    price_map: dict[str, str] | None = None,
) -> SubscriptionUpdate | None:
    """Extract the fields we care about from a Stripe event.

    Returns None for events we don't act on.
    """
    price_map = price_map or DEFAULT_PRICE_MAP
    event_type = event.get("type", "")
    if not event_type.startswith("customer.subscription.") and event_type != "invoice.payment_failed":
        return None

    data_object = (event.get("data") or {}).get("object") or {}
    customer_id = data_object.get("customer") or ""
    subscription_id = (
        data_object.get("id")
        if event_type.startswith("customer.subscription.")
        else data_object.get("subscription")
    )
    status = data_object.get("status") or ""

    # Price id is nested under items.data[0].price.id for subscriptions.
    price_id: str | None = None
    items = (data_object.get("items") or {}).get("data") or []
    if items:
        price_id = ((items[0] or {}).get("price") or {}).get("id")

    # Map to plan: deleted -> free (downgrade), else look up or default to free.
    if event_type == "customer.subscription.deleted":
        plan_name = "free"
    elif event_type == "invoice.payment_failed":
        plan_name = "free"  # conservative: downgrade on payment failure
    else:
        plan_name = price_map.get(price_id or "", "free")

    return SubscriptionUpdate(
        event_type=event_type,
        customer_id=customer_id,
        subscription_id=subscription_id,
        price_id=price_id,
        plan_name=plan_name,
        status=status,
    )


def load_price_map_from_env(raw: str | None) -> dict[str, str]:
    if not raw:
        return dict(DEFAULT_PRICE_MAP)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except json.JSONDecodeError:
        logger.warning("STRIPE_PRICE_MAP is not valid JSON; using defaults.")
    return dict(DEFAULT_PRICE_MAP)
