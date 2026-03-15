"""Tests for generic configuration loading."""

from __future__ import annotations

from pathlib import Path

import config


def test_candidate_env_paths_use_repo_local_env_and_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    override_path = tmp_path / "custom.env"
    monkeypatch.setenv("APP_STORE_CONNECT_MCP_ENV", str(override_path))
    monkeypatch.delenv("ASC_LISTING_MANAGER_ENV", raising=False)

    paths = config._candidate_env_paths()

    assert paths[0] == config.SERVER_ROOT / ".env"
    assert paths[1] == override_path
    assert all(path.name != ".env" or "flutter" not in path.as_posix() for path in paths)


def test_legacy_override_alias_is_still_supported(monkeypatch, tmp_path: Path) -> None:
    override_path = tmp_path / "legacy.env"
    monkeypatch.delenv("APP_STORE_CONNECT_MCP_ENV", raising=False)
    monkeypatch.setenv("ASC_LISTING_MANAGER_ENV", str(override_path))

    paths = config._candidate_env_paths()

    assert paths[-1] == override_path
