# Root conftest: ensures pytest can import the limpiapro package and
# provides a single shared QApplication for the Qt tests (creating a
# second application object would make Qt fail-fast).
#
# ISOLATION: everything the app writes per user (cache, logs, settings)
# goes under LIMPIAPRO_DATA_DIR. It is pointed at a temp directory BEFORE
# the package is imported, so a test run can never read or pollute the
# real user data (a test-written cache used to make the installed app skip
# its analysis and show no sizes at all).

import os
import tempfile

os.environ.setdefault(
    "LIMPIAPRO_DATA_DIR",
    os.path.join(tempfile.gettempdir(), "limpiapro_pytest_data"))
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
