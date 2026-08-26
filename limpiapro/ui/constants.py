"""Shared UI constants: single source for magic numbers used across pages."""

# Global progress bar range (0..PROGRESS_MAX).
PROGRESS_MAX = 1000

# Defer before starting the first auto-analysis after the window paints.
ANALYZE_DEFER_MS = 250

# Defer before grabbing the --screenshot render (lets the window settle).
SCREENSHOT_DEFER_MS = 2500

# Tree population batch size (row-by-row inserts would freeze the UI).
TREE_CHUNK = 200

# DISM /StartComponentCleanup timeout (WinSxS can take a long time).
DISM_TIMEOUT_S = 1800
