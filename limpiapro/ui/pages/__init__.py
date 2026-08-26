"""PySide6 pages package 

This package contains the individual page widgets for the PySide6
interface. Each page corresponds to a tab in the main window's navigation
sidebar.

Exported Pages:
    CleanPage: System cleanup (category selection, preview, clean).
    DuplicatePage: Duplicate file finder and deleter.
    LogPage: Activity log viewer.
    StartupPage: Startup apps, scheduled tasks, and processes manager.
    UninstallPage: Application uninstaller and leftover cleaner.
    UpdatePage: Windows Update (WinSxS/DISM) analyzer and cleaner.
"""

from .clean_page import CleanPage
from .duplicates_page import DuplicatePage
from .log_page import LogPage
from .startup_page import StartupPage
from .uninstall_page import UninstallPage
from .update_page import UpdatePage

__all__ = ["CleanPage", "DuplicatePage", "LogPage", "StartupPage",
           "UninstallPage", "UpdatePage"]
