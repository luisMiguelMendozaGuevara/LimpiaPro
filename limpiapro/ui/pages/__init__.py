"""PySide6 pages package (replica of the legacy interface)."""

from .clean_page import CleanPage
from .duplicates_page import DuplicatePage
from .log_page import LogPage
from .startup_page import StartupPage
from .uninstall_page import UninstallPage
from .update_page import UpdatePage

__all__ = ["CleanPage", "DuplicatePage", "LogPage", "StartupPage",
           "UninstallPage", "UpdatePage"]
