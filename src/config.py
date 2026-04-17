"""Configuration loading for the App Store Connect MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from errors import ConfigurationError

SERVER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGE_LOG_PATH = SERVER_ROOT / "data" / "changes.jsonl"
DEFAULT_REVENUECAT_EVENT_LOG_PATH = SERVER_ROOT / "data" / "revenuecat-events.jsonl"
DEFAULT_REVENUECAT_SNAPSHOT_PATH = SERVER_ROOT / "data" / "revenuecat-snapshot.json"
DEFAULT_REVENUECAT_OVERVIEW_HISTORY_PATH = (
    SERVER_ROOT / "data" / "revenuecat-overview-history.jsonl"
)
ENV_FILE_OVERRIDE_NAMES = (
    "APP_STORE_CONNECT_MCP_ENV",
    "ASC_LISTING_MANAGER_ENV",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    paths.append(SERVER_ROOT / ".env")
    for name in ENV_FILE_OVERRIDE_NAMES:
        override = os.getenv(name, "").strip()
        if override:
            paths.append(Path(override).expanduser())
    return paths


def _first_value(values: dict[str, str], *names: str) -> str | None:
    for name in names:
        raw = values.get(name)
        if raw is not None and raw != "":
            return raw
    return None


def _load_private_key(raw_value: str | None) -> str:
    if not raw_value:
        raise ConfigurationError("Missing App Store private key value")

    expanded = Path(raw_value).expanduser()
    if expanded.exists():
        return expanded.read_text(encoding="utf-8").strip()

    return raw_value.replace("\\n", "\n").strip()


@dataclass(slots=True)
class Settings:
    """Runtime configuration for the MCP server."""

    app_store_key_id: str
    app_store_issuer_id: str
    app_store_private_key: str
    app_store_bundle_id: str
    app_store_sku: str | None
    app_store_apple_id: str | None
    app_store_name: str | None
    revenuecat_api_key: str | None
    revenuecat_project_id: str | None
    change_log_path: Path
    revenuecat_event_log_path: Path = DEFAULT_REVENUECAT_EVENT_LOG_PATH
    revenuecat_snapshot_path: Path = DEFAULT_REVENUECAT_SNAPSHOT_PATH
    revenuecat_overview_history_path: Path = DEFAULT_REVENUECAT_OVERVIEW_HISTORY_PATH
    revenuecat_webhook_auth_header: str | None = None
    revenuecat_webhook_host: str = "127.0.0.1"
    revenuecat_webhook_port: int = 8787
    revenuecat_webhook_path: str = "/revenuecat"
    app_store_base_url: str = "https://api.appstoreconnect.apple.com"
    revenuecat_base_url: str = "https://api.revenuecat.com"

    @classmethod
    def load(cls) -> Settings:
        merged: dict[str, str] = {}
        for path in _candidate_env_paths():
            merged.update(_parse_env_file(path))
        merged.update(os.environ)

        key_id = _first_value(merged, "APP_STORE_KEY_ID", "APPSTORE_KEY_ID")
        issuer_id = _first_value(merged, "APP_STORE_ISSUER_ID", "APPSTORE_ISSUER_ID")
        private_key_raw = _first_value(
            merged,
            "APP_STORE_PRIVATE_KEY",
            "APPSTORE_PRIVATE_KEY",
        )
        bundle_id = _first_value(merged, "APP_STORE_BUNDLE_ID", "APPSTORE_BUNDLE_ID")

        missing = []
        if not key_id:
            missing.append("APP_STORE_KEY_ID")
        if not issuer_id:
            missing.append("APP_STORE_ISSUER_ID")
        if not private_key_raw:
            missing.append("APP_STORE_PRIVATE_KEY")
        if not bundle_id:
            missing.append("APP_STORE_BUNDLE_ID")
        if missing:
            raise ConfigurationError(
                "Missing required App Store Connect configuration",
                details={"missing": missing},
            )

        change_log_raw = _first_value(
            merged,
            "APP_STORE_CONNECT_CHANGE_LOG_PATH",
            "ASC_LISTING_CHANGE_LOG_PATH",
        )
        change_log_path = (
            Path(change_log_raw).expanduser()
            if change_log_raw
            else DEFAULT_CHANGE_LOG_PATH
        )
        revenuecat_event_log_raw = _first_value(merged, "REVENUECAT_EVENT_LOG_PATH")
        revenuecat_snapshot_raw = _first_value(merged, "REVENUECAT_SNAPSHOT_PATH")
        revenuecat_overview_history_raw = _first_value(
            merged,
            "REVENUECAT_OVERVIEW_HISTORY_PATH",
        )
        revenuecat_webhook_host = _first_value(merged, "REVENUECAT_WEBHOOK_HOST") or "127.0.0.1"
        revenuecat_webhook_path = (
            _first_value(merged, "REVENUECAT_WEBHOOK_PATH") or "/revenuecat"
        ).strip()
        if not revenuecat_webhook_path.startswith("/"):
            raise ConfigurationError(
                "REVENUECAT_WEBHOOK_PATH must start with '/'",
                details={"path": revenuecat_webhook_path},
            )
        revenuecat_webhook_port_raw = _first_value(merged, "REVENUECAT_WEBHOOK_PORT")
        try:
            revenuecat_webhook_port = int(revenuecat_webhook_port_raw or 8787)
        except ValueError as exc:
            raise ConfigurationError(
                "REVENUECAT_WEBHOOK_PORT must be an integer",
                details={"value": revenuecat_webhook_port_raw},
            ) from exc

        return cls(
            app_store_key_id=key_id,
            app_store_issuer_id=issuer_id,
            app_store_private_key=_load_private_key(private_key_raw),
            app_store_bundle_id=bundle_id,
            app_store_sku=_first_value(merged, "APP_STORE_SKU", "APPSTORE_SKU"),
            app_store_apple_id=_first_value(
                merged,
                "APP_STORE_APPLE_ID",
                "APPSTORE_APPLE_ID",
                "APP_STORE_APP_ID",
            ),
            app_store_name=_first_value(merged, "APP_STORE_NAME", "APPSTORE_NAME"),
            revenuecat_api_key=_first_value(
                merged,
                "REVENUECAT_API_KEY_V2",
                "REVENUECAT_API_KEY",
            ),
            revenuecat_project_id=_first_value(
                merged,
                "REVENUECAT_PROJECT_ID",
            ),
            change_log_path=change_log_path,
            revenuecat_event_log_path=(
                Path(revenuecat_event_log_raw).expanduser()
                if revenuecat_event_log_raw
                else DEFAULT_REVENUECAT_EVENT_LOG_PATH
            ),
            revenuecat_snapshot_path=(
                Path(revenuecat_snapshot_raw).expanduser()
                if revenuecat_snapshot_raw
                else DEFAULT_REVENUECAT_SNAPSHOT_PATH
            ),
            revenuecat_overview_history_path=(
                Path(revenuecat_overview_history_raw).expanduser()
                if revenuecat_overview_history_raw
                else DEFAULT_REVENUECAT_OVERVIEW_HISTORY_PATH
            ),
            revenuecat_webhook_auth_header=_first_value(
                merged,
                "REVENUECAT_WEBHOOK_AUTH_HEADER",
            ),
            revenuecat_webhook_host=revenuecat_webhook_host,
            revenuecat_webhook_port=revenuecat_webhook_port,
            revenuecat_webhook_path=revenuecat_webhook_path,
        )
