"""Structured error types for the App Store Connect MCP server."""

from __future__ import annotations

from typing import Any


class AppStoreConnectMcpError(Exception):
    """Base error with structured payload support."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_store_connect_mcp_error",
        status_code: int | None = None,
        retryable: bool = False,
        details: Any | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details
        self.hint = hint

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            },
        }
        if self.status_code is not None:
            payload["error"]["status_code"] = self.status_code
        if self.details is not None:
            payload["error"]["details"] = self.details
        if self.hint:
            payload["error"]["hint"] = self.hint
        return payload


AscListingManagerError = AppStoreConnectMcpError


class ConfigurationError(AppStoreConnectMcpError):
    """Raised when required configuration is missing or malformed."""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            code="configuration_error",
            status_code=400,
            retryable=False,
            details=details,
        )


class ResourceNotFoundError(AppStoreConnectMcpError):
    """Raised when App Store Connect does not contain the requested entity."""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(
            message,
            code="resource_not_found",
            status_code=404,
            retryable=False,
            details=details,
        )


class AscApiError(AppStoreConnectMcpError):
    """Structured App Store Connect API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retryable: bool,
        details: Any | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="asc_api_error",
            status_code=status_code,
            retryable=retryable,
            details=details,
            hint=hint,
        )


class RevenueCatApiError(AppStoreConnectMcpError):
    """Structured RevenueCat API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retryable: bool,
        details: Any | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            code="revenuecat_api_error",
            status_code=status_code,
            retryable=retryable,
            details=details,
            hint=hint,
        )


def serialize_error(exc: Exception) -> dict[str, Any]:
    """Convert known exceptions into a structured JSON payload."""

    if isinstance(exc, AppStoreConnectMcpError):
        return exc.as_dict()

    return {
        "ok": False,
        "error": {
            "code": "unexpected_error",
            "message": str(exc),
            "retryable": False,
        },
    }
