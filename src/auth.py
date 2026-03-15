"""JWT caching for App Store Connect."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import jwt

from config import Settings


@dataclass(slots=True)
class CachedToken:
    """Cached bearer token with a unix expiry."""

    token: str
    expires_at: int


class AppStoreJwtProvider:
    """Mint and cache App Store Connect JWTs."""

    def __init__(
        self,
        settings: Settings,
        *,
        time_fn: callable = time.time,
        refresh_window_seconds: int = 120,
    ) -> None:
        self._settings = settings
        self._time_fn = time_fn
        self._refresh_window_seconds = refresh_window_seconds
        self._lock = threading.Lock()
        self._cached: CachedToken | None = None

    def invalidate(self) -> None:
        """Drop the cached token so the next call mints a new one."""

        with self._lock:
            self._cached = None

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a cached token unless it is close to expiry."""

        with self._lock:
            now = int(self._time_fn())
            if (
                not force_refresh
                and self._cached is not None
                and now < self._cached.expires_at - self._refresh_window_seconds
            ):
                return self._cached.token

            token = self._build_token(now)
            self._cached = CachedToken(token=token, expires_at=now + 20 * 60)
            return token

    def _build_token(self, issued_at: int) -> str:
        payload = {
            "iss": self._settings.app_store_issuer_id,
            "iat": issued_at,
            "exp": issued_at + 20 * 60,
            "aud": "appstoreconnect-v1",
        }
        headers = {
            "alg": "ES256",
            "kid": self._settings.app_store_key_id,
            "typ": "JWT",
        }
        token = jwt.encode(
            payload,
            self._settings.app_store_private_key,
            algorithm="ES256",
            headers=headers,
        )
        return token.decode("utf-8") if isinstance(token, bytes) else token
