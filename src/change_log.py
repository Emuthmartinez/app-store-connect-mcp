"""Change logging for listing mutations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ChangeLogger:
    """Append structured mutation logs for before/after analysis."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def record(
        self,
        *,
        operation: str,
        locale: str | None,
        target: dict[str, Any],
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        revenuecat_metrics: dict[str, Any] | None,
    ) -> None:
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "locale": locale,
            "target": target,
            "before": before,
            "after": after,
            "revenuecat_metrics": revenuecat_metrics,
        }
        with self._output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True))
            handle.write("\n")
