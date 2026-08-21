# Root conftest: ensures pytest can import the limpiapro package and
# provides a single shared QApplication for the Qt tests (creating a
# second application object would make Qt fail-fast).

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    # Closing a test window must not put the whole app into quit state:
    # later tests keep processing events.
    app.setQuitOnLastWindowClosed(False)
    yield app
