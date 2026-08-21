"""Persisted user settings (the legacy app had none).

Stored as JSON under the per-user data directory
(%LOCALAPPDATA%\\LimpiaPro\\settings.json) with an atomic write, same
pattern as CacheService."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

from .paths import get_user_data_dir

_SETTINGS_FILE = os.path.join(get_user_data_dir(), "settings.json")

_THEMES = ("dark", "light", "system")
_LANGUAGES = ("auto", "es", "en")


@dataclass
class Settings:
    """User preferences for the PySide6 interface."""

    theme: str = "dark"                 # dark | light | system
    language: str = "auto"              # auto | es | en
    auto_analyze: bool = True           # run a scan shortly after start
    confirm_before_clean: bool = True   # confirmation dialog before delete

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Settings:
        """Load settings from disk; unknown/missing values keep defaults."""
        path = str(path or _SETTINGS_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        valid = {f.name for f in fields(cls)}
        bool_fields = {"auto_analyze", "confirm_before_clean"}
        str_fields = {"theme", "language"}
        kwargs: dict = {}
        for key, value in raw.items():
            if key not in valid:
                continue
            if key in bool_fields and isinstance(value, bool):
                kwargs[key] = value
            elif key in str_fields and isinstance(value, str):
                kwargs[key] = value
        return cls(**kwargs)

    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Persist atomically (tmp + os.replace), ignoring write errors."""
        path = str(path or _SETTINGS_FILE)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass  # settings persistence is best-effort

    def validate(self) -> Settings:
        """Coerce fields back to the allowed values (defensive load)."""
        if self.theme not in _THEMES:
            self.theme = "dark"
        if self.language not in _LANGUAGES:
            self.language = "auto"
        return self
