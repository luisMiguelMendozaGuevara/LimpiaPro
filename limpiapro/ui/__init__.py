"""PySide6 interface package.

Kept a lightweight marker (no heavy imports): the legacy customtkinter
pages live under `legacy_tk` and the new interface modules are imported
from their own paths (main_window, pages/, widgets/, dialogs/,
resources/), so importing `limpiapro.ui` never triggers Qt or the
controller and cannot create import cycles.

The legacy app (`limpiador.py` without --qt) still works through
`limpiapro.app`; the PySide6 interface runs via `limpiador.py --qt`
(`limpiapro.app_qt`)."""
