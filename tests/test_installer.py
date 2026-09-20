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


def _app_guid() -> str:
    """The GUID shared by [Setup] AppId and the uninstall-key constant."""
    import re

    text = ISS.read_text(encoding="utf-8")
    app_id = re.search(r"^AppId=\{\{([0-9A-Fa-f-]{36})", text, re.M)
    assert app_id, "AppId not found in [Setup]"
    return app_id.group(1)


def test_dir_page_is_always_shown_and_reuses_the_previous_folder():
    """Inno hides the destination page on an upgrade by default, which is
    what made it look 'missing'."""
    text = ISS.read_text(encoding="utf-8")
    assert "DisableDirPage=no" in text
    assert "UsePreviousAppDir=yes" in text


def test_detects_an_installed_version_and_tells_the_user():
    text = ISS.read_text(encoding="utf-8")
    guid = _app_guid()
    # The registry lookup must use the SAME AppId, or an existing install
    # would not be recognized.
    assert f"Uninstall\\{{{guid}}}_is1" in text
    assert "GetInstalledValue('DisplayVersion')" in text
    assert "GetInstalledValue('InstallLocation')" in text
    assert "CustomMessage('PreviousVersion')" in text
    assert "CustomMessage('AlreadyCurrent')" in text
    # Both languages define the messages.
    for key in ("PreviousVersion", "AlreadyCurrent", "RemoveOld"):
        assert f"spanish.{key}=" in text
        assert f"english.{key}=" in text


def test_removing_an_old_installation_left_in_another_folder():
    text = ISS.read_text(encoding="utf-8")
    assert "CustomMessage('RemoveOld')" in text
    assert "DelTree(PreviousInstallDir, True, True, True)" in text


def test_running_app_is_closed_through_restart_manager():
    text = ISS.read_text(encoding="utf-8")
    assert "CloseApplications=yes" in text
    assert "CloseApplicationsFilter={#AppExeName}" in text


def test_code_section_lines_never_start_with_a_bracket():
    """Inno's [Code] parser reads a line starting with '[' as a section
    header; that broke the build with "Invalid section tag"."""
    text = ISS.read_text(encoding="utf-8")
    code = text.split("[Code]", 1)[1]
    offenders = [line for line in code.splitlines() if line.startswith("[")]
    assert not offenders, f"lines starting with '[': {offenders}"


def test_release_notes_explain_every_download():
    """Every release body must explain what each asset is for: users were
    left guessing which of the six files to pick."""
    import importlib
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    upload_release = importlib.import_module("upload_release")

    guide = (ROOT / "docs" / "releases" / "DOWNLOADS.md").read_text(
        encoding="utf-8")
    for asset in ("LimpiaProSetup.exe", "LimpiaProPortable.zip",
                  "LimpiaPro.zip", "LimpiaPro.exe", "LimpiaProDebug.exe",
                  "SHA256SUMS.txt"):
        assert asset in guide, f"{asset} is not explained in DOWNLOADS.md"
    # The guide is appended to the per-version notes automatically.
    notes = upload_release._release_notes()
    assert "Que descargar" in notes
    assert "Comparativa rapida" in notes
    assert "LimpiaProSetup.exe" in notes
    # Maintainer comments stay out of the published body.
    assert "<!--" not in notes



@pytest.mark.skipif(
    not ISS.exists(), reason="installer script not present")
def test_installer_version_is_injected_not_hardcoded():
    """The version comes from /DAppVersion (upload_release passes it), so a
    version bump can never publish an installer stamped with an old one."""
    text = ISS.read_text(encoding="utf-8")
    assert '#define AppVersion "0.0.0"' in text
    assert "AppVersion={#AppVersion}" in text
    assert "Updating version info" not in text  # not a compiled output
