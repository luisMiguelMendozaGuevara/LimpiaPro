"""Tests for CleanCategory over temporary folders."""

import os


def _make_cat(tmp_path):
    from limpiapro.categories import CleanCategory
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "cache" / "b.bin").write_bytes(b"y" * 50)
    (tmp_path / "loose.txt").write_bytes(b"z" * 10)
    return CleanCategory("t", "Test", "", [str(tmp_path / "cache"),
                                           str(tmp_path / "loose.txt")])


def test_scan_counts_size_and_files(tmp_path):
    cat = _make_cat(tmp_path)
    cat.scan()
    # cache/ has 2 files (a.bin=100 + b.bin=50), loose.txt=10 => 3 files
    assert cat.files == 3
    assert cat.size == 160


def test_list_files_without_rules_returns_top_level(tmp_path):
    cat = _make_cat(tmp_path)
    files, scanned = cat.list_files()
    names = sorted(os.path.basename(f) for f in files)
    # folders are deleted whole when cleaning: the preview shows the top
    # level, not every internal file
    assert names == ["a.bin", "b.bin", "loose.txt"]
    assert scanned == 3


def test_clean_deletes_location_contents(tmp_path):
    cat = _make_cat(tmp_path)
    removed, errors, freed = cat.clean()
    assert errors == 0
    assert removed == 3
    assert freed == 160
    assert not (tmp_path / "cache" / "a.bin").exists()
    assert not (tmp_path / "loose.txt").exists()


def test_missing_location_is_ignored(tmp_path):
    from limpiapro.categories import CleanCategory
    cat = CleanCategory("t", "Test", "", [str(tmp_path / "does_not_exist")])
    cat.scan()
    assert cat.files == 0
    assert cat.size == 0


def test_clean_uses_preview_snapshot_not_rewalk(tmp_path):
    """P0-3: after list_files, clean() deletes exactly the snapshotted
    targets; files created in between are NOT picked up."""
    cat = _make_cat(tmp_path)
    _files_before, total = cat.list_files()
    assert total == 3
    # A new file appears after the preview (e.g. a running browser).
    late = tmp_path / "cache" / "late.bin"
    late.write_bytes(b"z" * 5)
    removed, errors, freed = cat.clean()
    assert errors == 0
    assert removed == 3
    assert freed == 160
    assert late.exists() is True  # created after the snapshot: untouched
    assert not (tmp_path / "loose.txt").exists()


def test_clean_without_preview_still_works(tmp_path):
    """Without a prior list_files snapshot, clean() re-walks (old path)."""
    cat = _make_cat(tmp_path)
    extra = tmp_path / "cache" / "late.bin"
    extra.write_bytes(b"z" * 5)
    removed, _errors, freed = cat.clean()
    assert removed == 4
    assert freed == 165


def test_user_dirs_are_expandable_templates():
    """Windows paths must be %ENV% templates, not hardcoded C:\\Windows:
    Windows can be installed on another drive or relocated."""
    from limpiapro.categories import user_dirs

    dirs = user_dirs()
    for key in ("win_temp", "prefetch", "update_cache", "cbs_logs"):
        assert "%SystemRoot%" in dirs[key], f"{key} is hardcoded"
        assert "C:\\Windows" not in dirs[key].upper().replace(
            "%SYSTEMROOT%", ""), f"{key} still hardcodes C:\\Windows"


def test_scan_and_preview_skip_targets_refused_by_safety(tmp_path, monkeypatch):
    """The analyzer must not show a file the safety gate will refuse, or
    the user sees "files that are not deleted"."""
    import os

    import limpiapro.categories as cats

    loc = tmp_path / "loc"
    loc.mkdir()
    (loc / "ok.bin").write_bytes(b"x" * 10)
    (loc / "bad.bin").write_bytes(b"y" * 999)

    real = cats.is_safe_delete_target
    monkeypatch.setattr(
        cats, "is_safe_delete_target",
        lambda p, is_dir=None: real(p, is_dir)
        and os.path.basename(p) != "bad.bin")

    cat = cats.CleanCategory("plain", "P", "d", [str(loc)])
    files, scanned = cat.list_files()
    assert [os.path.basename(f) for f in files] == ["ok.bin"]
    assert scanned == 1
    cat.scan()
    assert cat.files == 1 and cat.size == 10


def test_winapp_preview_and_scan_skip_safety_refused(tmp_path, monkeypatch):
    """Same for rule-based categories: a matched file the gate refuses is
    neither previewed nor measured."""
    import os

    import limpiapro.categories as cats
    from limpiapro.winapp2 import WinAppRule

    (tmp_path / "ok.log").write_text("a", encoding="utf-8")
    (tmp_path / "bad.log").write_text("bbbb", encoding="utf-8")

    real = cats.is_safe_delete_target
    monkeypatch.setattr(
        cats, "is_safe_delete_target",
        lambda p, is_dir=None: real(p, is_dir)
        and os.path.basename(p) != "bad.log")

    cat = cats.CleanCategory("winapp", "W", "d", [])
    cat.rules = [WinAppRule(root=str(tmp_path), recurse=True,
                            patterns=("*.log",))]
    files, scanned = cat.list_files()
    assert [os.path.basename(f) for f in files] == ["ok.log"]
    assert scanned == 1
    assert cat.scan() == 1 and cat.files == 1

