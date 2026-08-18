"""Versioned JSON cache storage for per-user scan results."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class CacheService:
    """Load and atomically persist category scan results."""

    def __init__(self, path: str | os.PathLike[str], schema: int, app_version: str):
        self.path = Path(path)
        self.schema = schema
        self.app_version = app_version

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        if raw.get("schema") != self.schema or raw.get("app_version") != self.app_version:
            return {}
        data = raw.get("data")
        return data if isinstance(data, dict) else {}

    def save(self, data: dict[str, dict[str, int]], platform_name: str) -> None:
        payload = {
            "schema": self.schema,
            "app_version": self.app_version,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform_name,
            "data": data,
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
