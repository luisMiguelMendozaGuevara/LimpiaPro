"""LimpiaPro - CCleaner-style system cleaner for personal use.

The logic lives in limpiapro.* and the interface in limpiapro.ui.*.
The entry point is limpiador.py (kept compatible with LimpiaPro.bat and
LimpiaPro.spec).
"""

APP_NAME = "LimpiaPro"
APP_VERSION = "2.10.4"

# Read chunk size for full-file hashing (duplicates module). 1 MiB keeps
# the per-call Python overhead negligible while hashlib updates in C.
BLOCK_SIZE = 1024 * 1024
