"""Persisted user settings (the legacy app had none).

Stored as JSON under the per-user data directory
(%LOCALAPPDATA%\\LimpiaPro\\settings.json) with an atomic write, same
pattern as CacheService.

Design Principles:
1. Defensive Loading: Unknown fields are ignored, missing fields get defaults.
2. Type Safety: Values are validated against expected types on load.
3. Atomic Writes: Prevents corruption from crashes during save.
4. Best-Effort: Settings persistence never crashes the app.
"""

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
    """User preferences for the PySide6 interface.

    This dataclass holds the application's user-configurable state. It is
    loaded on startup and saved whenever the user changes a preference.

    Attributes:
        theme (str): UI theme. One of "dark", "light", "system". Default "dark".
        language (str): UI language. One of "auto", "es", "en". Default "auto".
        auto_analyze (bool): Whether to automatically run a scan on startup.
        confirm_before_clean (bool): Whether to show a confirmation dialog
                                     before deleting files.
        delete_to_recycle_bin (bool): When True, cleanup moves targets to
                                     the recycle bin instead of deleting
                                     them permanently (recoverable, but
                                     disk space is not freed until the
                                     bin is emptied). Default False
                                     (legacy permanent-delete behavior).
    """

    theme: str = "dark"                 # dark | light | system
    language: str = "auto"              # auto | es | en
    auto_analyze: bool = True           # run a scan shortly after start
    confirm_before_clean: bool = True   # confirmation dialog before delete
    delete_to_recycle_bin: bool = False # recycle instead of permanent delete

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Settings:
        """Load settings from disk; unknown/missing values keep defaults.

        This method is extremely defensive. It handles:
        - Missing file (returns defaults)
        - Malformed JSON (returns defaults)
        - Wrong root type (not a dict -> returns defaults)
        - Unknown fields (ignored silently)
        - Wrong field types (ignored silently, default used)

        Args:
            path: Optional custom path. Defaults to the standard settings file.

        Returns:
            Settings: A fully populated Settings instance with safe defaults.
        """
        path = str(path or _SETTINGS_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        
        # Whitelist valid field names to prevent injection of arbitrary attributes.
        valid = {f.name for f in fields(cls)}
        bool_fields = {"auto_analyze", "confirm_before_clean",
                       "delete_to_recycle_bin"}
        str_fields = {"theme", "language"}
        
        kwargs: dict = {}
        for key, value in raw.items():
            if key not in valid:
                continue
            # Type-check each field before accepting it.
            if (key in bool_fields and isinstance(value, bool)) or (key in str_fields and isinstance(value, str)):
                kwargs[key] = value
        return cls(**kwargs)

    def save(self, path: str | os.PathLike[str] | None = None) -> None:
        """Persist atomically (tmp + os.replace), ignoring write errors.

        Args:
            path: Optional custom path. Defaults to the standard settings file.

        Note:
            This method never raises. Settings persistence is best-effort.
            A failure to save settings should never prevent the user from
            using the application.
        """
        path = str(path or _SETTINGS_FILE)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            # ATOMIC SWAP: Prevents partial writes.
            os.replace(tmp, path)
        except OSError:
            pass  # settings persistence is best-effort

    def validate(self) -> Settings:
        """Coerce fields back to the allowed values (defensive load).

        This is called after loading to ensure that even if a valid-typed
        value is out of range (e.g., theme="purple"), it is reset to a
        safe default.

        Returns:
            Settings: self, for method chaining.
        """
        if self.theme not in _THEMES:
            self.theme = "dark"
        if self.language not in _LANGUAGES:
            self.language = "auto"
        return self
