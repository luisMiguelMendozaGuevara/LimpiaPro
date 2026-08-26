"""PySide6 interface package.

Kept a lightweight marker (no heavy imports): the interface is imported
from its own paths (main_window, pages/, widgets/, resources/), so
importing `limpiapro.ui` never triggers Qt or the controller and cannot
create import cycles.

Design Principle:
    This package serves as a namespace container. It intentionally does
    not import any heavy modules to prevent circular dependencies and
    to keep the package lightweight for introspection tools.
"""
