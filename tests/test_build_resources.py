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


def test_stylesheet_has_no_unsubstituted_tokens():
    from limpiapro.ui.theme import build_stylesheet
    rendered = build_stylesheet(accent="#0067c0", dark=True)
    import re
    leftovers = re.findall(r"%[A-Z_]+%", rendered)
    assert not leftovers, f"unsubstituted tokens in rendered stylesheet: {leftovers}"
    assert "Segoe UI Variable" in rendered
    assert "#0067c0" in rendered
