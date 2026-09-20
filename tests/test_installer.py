"""Guards for the Windows installer (Inno Setup).

The release ships LimpiaProSetup.exe: a per-user install with an uninstall
entry, built from the OneDir payload. These tests pin the pieces that
silently broke releases before (missing data files, missing uninstall
entry, an asset that never gets uploaded).
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISS = ROOT / "installer" / "LimpiaPro.iss"


def test_installer_script_exists_and_installs_the_portable_payload():
    text = ISS.read_text(encoding="utf-8")
    # The OneDir payload must be installed as-is (exe + _internal).
    assert 'SourceDir "..\\dist\\LimpiaProPortable"' in text
    assert '{#SourceDir}\\{#AppExeName}"; DestDir: "{app}"' in text
    assert '{#SourceDir}\\_internal\\*"; DestDir: "{app}\\_internal"' in text


def test_installer_registers_an_uninstaller_and_shortcuts():
    text = ISS.read_text(encoding="utf-8")
    assert "UninstallDisplayName=" in text
    assert "UninstallDisplayIcon={app}\\{#AppExeName}" in text
    assert "{autodesktop}" in text          # optional desktop shortcut
    assert "{group}" in text                # start-menu entry
    assert "desktopicon" in text and "startupicon" in text


def test_installer_is_per_user_and_never_deletes_user_data():
    """A per-user install avoids UAC; uninstalling must keep settings/logs."""
    text = ISS.read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in text
    # Only the install folder is removed; the data purge is opt-in.
    assert 'Type: filesandordirs; Name: "{app}"' in text
    assert "PURGEDATA" in text


def test_release_publishes_the_installer_asset():
    sys_path = str(ROOT)
    import importlib
    import sys

    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    upload_release = importlib.import_module("upload_release")
    names = {p.name for p in upload_release.release_assets()}
    assert "LimpiaProSetup.exe" in names
    assert "SHA256SUMS.txt" in names
    # The installer is built from the portable payload.
    assert upload_release.INSTALLER.name == "LimpiaProSetup.exe"


@pytest.mark.skipif(
    not ISS.exists(), reason="installer script not present")
def test_installer_version_is_injected_not_hardcoded():
    """The version comes from /DAppVersion (upload_release passes it), so a
    version bump can never publish an installer stamped with an old one."""
    text = ISS.read_text(encoding="utf-8")
    assert '#define AppVersion "0.0.0"' in text
    assert "AppVersion={#AppVersion}" in text
    assert "Updating version info" not in text  # not a compiled output
