"""Message presenters: build the content of UI dialogs from domain objects.

Keeping this formatting here (instead of inside MainWindow) makes the
wording testable and the window class focused on wiring.
"""

from __future__ import annotations

from ..i18n import t
from ..utils import format_size, is_admin


def clean_confirmation(selected, to_recycle: bool = False) -> tuple[
        str, str, list[tuple[str, str]], list[str]]:
    """Build the structured clean-confirmation dialog content.

    Args:
        selected: The checked category objects.
        to_recycle: True when cleanup will move targets to the recycle
            bin instead of deleting them; appends a note so the user
            knows the mode. The default (False) keeps the historical
            output byte-identical.

    Returns:
        (heading, subtitle, items, notes): the four inputs of
        ui.dialogs.structured_confirm.
    """
    total = sum(c.size for c in selected)
    heading = t("msg.clean_confirm_heading", n=len(selected),
                size=format_size(total))
    subtitle = t("msg.clean_confirm_sub")
    items = [
        (c.label, format_size(c.size) if c.size else
         (t("clean.recycle_empty") if c.recycle_bin else t("clean.is_clean")))
        for c in selected
    ]
    notes = [t("msg.clean_note_browsers")]
    if any(c.recycle_bin for c in selected):
        notes.append(t("msg.clean_note_recycle"))
    if any(c.key == "winapp" for c in selected):
        notes.append(t("msg.clean_note_winapp"))
    if any(c.needs_admin for c in selected) and not is_admin():
        notes.append(t("msg.clean_note_admin"))
    if to_recycle:
        notes.append(t("msg.clean_note_to_recycle"))
    return heading, subtitle, items, notes
