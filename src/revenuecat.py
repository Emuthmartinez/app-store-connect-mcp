"""RevenueCat analytics helpers for listing analysis."""

from __future__ import annotations

import time
from typing import Any

import requests

from config import Settings
from errors import ConfigurationError, RevenueCatApiError


JsonDict = dict[str, Any]


class RevenueCatMetricsClient:
    """Read-only RevenueCat API client for listing analysis."""

    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        sleep_fn: callable = time.sleep,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._sleep_fn = sleep_fn

    @property
    def configured(self) -> bool:
        return bool(self._settings.revenuecat_api_key and self._settings.revenuecat_project_id)

    def get_overview(self) -> JsonDict | None:
        """Return normalized overview metrics when RevenueCat is configured."""

        if not self.configured:
            return None

        api_key = self._settings.revenuecat_api_key
        project_id = self._settings.revenuecat_project_id
        if not api_key or not project_id:
            raise ConfigurationError("RevenueCat configuration is incomplete")

        payload = self._request(
            "GET",
            f"{self._settings.revenuecat_base_url}/v2/projects/{project_id}/metrics/overview",
            api_key=api_key,
        )
        metrics = payload.get("metrics", []) if isinstance(payload, dict) else []
        normalized = {
            "project_id": project_id,
            "metrics": {
                metric.get("id"): metric.get("value")
                for metric in metrics
                if isinstance(metric, dict) and metric.get("id")
            },
            "raw": payload,
        }
        return normalized

    def _request(self, method: str, url: str, *, api_key: str) -> JsonDict:
        rate_limit_attempts = 0
        while True:
            response = self._session.request(
                method=method,
                url=url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if 200 <= response.status_code < 300:
                return response.json()

            if response.status_code == 429 and rate_limit_attempts < 3:
                rate_limit_attempts += 1
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2 ** (rate_limit_attempts - 1))
                self._sleep_fn(delay)
                continue

            hint: str | None = None
            if response.status_code == 403:
                hint = (
                    "The RevenueCat key is missing the project_configuration or metrics "
                    "read permission needed for overview metrics."
                )

            details: Any = {"body": response.text[:1000]}
            try:
                details = response.json()
            except ValueError:
                pass

            raise RevenueCatApiError(
                "RevenueCat metrics request failed",
                status_code=response.status_code,
                retryable=response.status_code in {429, 500, 502, 503, 504},
                details=details,
                hint=hint,
            )
