"""Guards against the frozen-build regression where bundled data files
(style.qss, winapp2.ini, icon) were missing from the PyInstaller specs,
making the packaged exe run completely unstyled."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ["LimpiaPro.spec", "LimpiaProDebug.spec", "LimpiaProPortable.spec"]
DATAS = [
    ("limpiapro/ui/resources/style.qss", "limpiapro/ui/resources"),
    ("winapp2.ini", "."),
    ("assets/limpiadora.ico", "assets"),
]


def test_every_spec_bundles_the_stylesheet_and_data():
    for spec_name in SPECS:
        text = (ROOT / spec_name).read_text(encoding="utf-8")
        for source, dest in DATAS:
            assert f"'{source}', '{dest}'" in text or \
                f"('{source}', '{dest}')" in text, \
                f"{spec_name} is missing data file {source} -> {dest}"


def test_no_spec_enables_upx():
    """UPX must stay OFF in every spec: packed exes are a well-known
    antivirus false-positive trigger for an unsigned app, which costs
    more users than the size saving buys."""
    for spec_name in SPECS:
        text = (ROOT / spec_name).read_text(encoding="utf-8")
        assert "upx=True" not in text, \
            f"{spec_name} re-enabled UPX (AV false-positive regression)"
        assert "upx=False" in text, f"{spec_name} does not pin upx=False"


def test_every_spec_embeds_a_version_resource():
    """Every spec must pass version=write_version_file(...) to EXE().

    A frozen exe with an empty version resource looks anonymous to
    Windows Explorer and antivirus heuristics (this shipped unnoticed
    once); pinning it here keeps the metadata in sync with APP_VERSION.
    """
    for spec_name in SPECS:
        text = (ROOT / spec_name).read_text(encoding="utf-8")
        assert "write_version_file" in text, \
            f"{spec_name} does not generate a version resource"
        assert "version=write_version_file" in text, \
            f"{spec_name} does not pass version= to EXE()"


def test_specs_use_pyinstaller_globals_only():
    """A spec runs inside PyInstaller's restricted namespace, which exposes
    ``workpath``/``DISTPATH``/``SPECPATH`` but NOT ``WORKPATH``. Referencing
    an undefined global aborts the build with NameError, so pin the casing."""
    for spec_name in SPECS:
        text = (ROOT / spec_name).read_text(encoding="utf-8")
        assert "WORKPATH" not in text, \
            f"{spec_name} uses WORKPATH; PyInstaller defines lowercase workpath"
        assert "os.path.join(workpath," in text, \
            f"{spec_name} does not write the version file under workpath"


def test_debug_spec_is_a_console_build_without_bootloader_debug():
    """The troubleshooting variant only needs ``console=True``; the EXE
    bootloader debug path (``debug=True``) aborts the PyInstaller 6.22.2
    build on this toolchain (exit -1), so it must stay off."""
    text = (ROOT / "LimpiaProDebug.spec").read_text(encoding="utf-8")
    assert "console=True" in text, "LimpiaProDebug.spec is not a console build"
    assert "\n    debug=False," in text, \
        "LimpiaProDebug.spec re-enabled the crashing EXE bootloader debug path"


def test_version_resource_matches_app_version():
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "installer"))
    from pyinstaller_common import parse_version, version_file_text

    from limpiapro import APP_VERSION

    assert parse_version("2.11.3") == (2, 11, 3, 0)
    assert parse_version(APP_VERSION)[:3] == tuple(
        int(p) for p in APP_VERSION.split(".")[:3])
    text = version_file_text("LimpiaPro", APP_VERSION, "LimpiaPro.exe")
    assert APP_VERSION in text
    assert "CompanyName" in text and "FileVersion" in text


def test_stylesheet_has_no_unsubstituted_tokens():
    from limpiapro.ui.theme import build_stylesheet
    rendered = build_stylesheet(accent="#0067c0", dark=True)
    import re
    leftovers = re.findall(r"%[A-Z_]+%", rendered)
    assert not leftovers, f"unsubstituted tokens in rendered stylesheet: {leftovers}"
    assert "Segoe UI Variable" in rendered
    assert "#0067c0" in rendered
