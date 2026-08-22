"""PySide6 interface package.

Kept a lightweight marker (no heavy imports): the legacy customtkinter
pages live under `legacy_tk` and the new replica interface is imported
from its own paths (main_window, pages/, widgets/, resources/), so
importing `limpiapro.ui` never triggers Qt or the controller and cannot
create import cycles.

The legacy app (`limpiador.py --legacy`) still works through
`limpiapro.app`; the PySide6 replica runs by default via
`limpiapro.app_qt`."""
