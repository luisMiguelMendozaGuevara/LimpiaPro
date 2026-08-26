"""Compatibility shim: re-exports the split UI helper modules.

The helpers now live in dedicated modules:
  - ui/workers.py       run_async (daemon thread + signal bridge)
  - ui/dialogs.py       styled alerts, confirmations, readonly dialogs
  - ui/tree_helpers.py  make_tree / fill_tree / selected_*
  - ui/layouts.py       FlowLayout
  - ui/empty_state.py   EmptyState

New code should import from those modules directly; this module exists
only so existing imports keep working during the transition.
"""

from .dialogs import (  # noqa: F401
    app_confirm,
    app_info,
    confirm_destructive,
    readonly_scrolled,
    readonly_toplevel,
    structured_confirm,
)
from .empty_state import EmptyState  # noqa: F401
from .layouts import FlowLayout  # noqa: F401
from .tree_helpers import (  # noqa: F401
    fill_tree,
    item_data,
    make_tree,
    selected_many,
    selected_one,
)
from .workers import run_async  # noqa: F401
