"""Tests for Lote F3: structure — matcher unification (O3), single-commit
scan state (O1-lite), synced contracts (O2) and i18n'd startup sources (O4)."""

import ast
import inspect
from pathlib import Path

from limpiapro import startup
from limpiapro.categories import CleanCategory
from limpiapro.contracts import CacheStore, CleanCategoryProtocol
from limpiapro.winapp2 import ExcludeKey, WinAppRule

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- O3


def _rule_category(tmp_path, exclude_tmp=False):
    target = tmp_path / "sub"
    target.mkdir()
    kept = target / "c.tmp"
    kept.write_bytes(b"1234")
    noise = tmp_path / "b.log"
    noise.write_bytes(b"x")
    cat = CleanCategory("t", "T", "desc", [])
    rule = WinAppRule(root=str(tmp_path), recurse=True, patterns=("*.tmp",))
    if exclude_tmp:
        rule.excludes = (ExcludeKey(exact=str(kept)),)
    cat.rules = [rule]
    return cat, rule, kept


def test_iter_root_targets_matches_and_excludes(tmp_path):
    cat, rule, kept = _rule_category(tmp_path)
    root = rule.root
    got = list(cat._iter_root_targets(rule, root))
    assert len(got) == 1
    path, entry = got[0]
    assert path == str(kept) and entry is not None
    assert entry.stat().st_size == 4


def test_iter_targets_and_scan_agree(tmp_path):
    """Parity guard for O3: preview and measurement must see the exact
    same target set now that they share one matcher."""
    cat, _rule, kept = _rule_category(tmp_path)
    targets = [p for _r, p in cat._iter_targets()]
    # Windows normcase lowercases the root, so entry.path is lowercased
    # while str(kept) preserves the original case. Compare normcased.
    import os
    assert [os.path.normcase(p) for p in targets] == [
        os.path.normcase(str(kept))]
    assert cat.scan() == 4
    assert cat.files == 1


# ------------------------------------------------------------- O1-lite


def test_scan_commits_state_only_at_the_end(tmp_path):
    """The UI thread must never observe intermediate sizes: during the
    whole scan the category keeps its PRE-scan values; the commit lands
    once, at the end."""
    cat, _rule, _kept = _rule_category(tmp_path)
    cat.size = 999  # pre-scan sentinel
    cat.files = 11
    seen_sizes = []
    size = cat.scan(on_progress=lambda _files: seen_sizes.append(cat.size))
    assert size == 4 and cat.size == 4 and cat.files == 1
    assert seen_sizes and all(s == 999 for s in seen_sizes), (
        "scan must not leak intermediate sizes through the shared state")


def test_plain_category_scan_commits_once(tmp_path):
    loc = tmp_path / "loc"
    loc.mkdir()
    (loc / "f.bin").write_bytes(b"z" * 10)
    cat = CleanCategory("plain", "P", "desc", [str(loc)])
    cat.size = 999
    seen = []
    cat.scan(on_progress=lambda _f: seen.append(cat.size))
    assert cat.size == 10 and cat.files == 1
    assert all(s == 999 for s in seen)


# ---------------------------------------------------------------- O2


def test_cache_store_protocol_has_freshness_surface():
    assert hasattr(CacheStore, "age_seconds")
    assert hasattr(CacheStore, "is_fresh")


def test_clean_protocol_mirrors_core_signature():
    params = inspect.signature(CleanCategoryProtocol.clean).parameters
    assert "on_file" in params
    assert "to_recycle" in params
    scan_doc = inspect.getdoc(CleanCategoryProtocol.scan)
    assert "BYTES" in scan_doc.upper()


# ---------------------------------------------------------------- O4


def test_core_source_tags_are_stable_english():
    """The backend convention: no localized (Spanish) strings in core
    data. Tags start with User/System and are pure ASCII."""
    tags = [src for _h, _a, src in startup.RUN_KEYS]
    tags += [src for _h, _k, src in startup.RUN_KEYS_DISABLED]
    assert all(t.isascii() for t in tags)
    assert all(t.startswith(("User", "System")) for t in tags)


def test_source_tags_are_mapped_and_translated(monkeypatch):
    """O4: every stable core tag has a UI mapping whose i18n key exists in
    BOTH language tables. Parsed via AST: importing the page would need
    a Qt display stack (libEGL), which this environment lacks."""
    from limpiapro import i18n

    src = (REPO / "limpiapro" / "ui" / "pages" / "startup_page.py").read_text(
        encoding="utf-8")
    mapping = None
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_SOURCE_KEYS"):
            mapping = {ast.literal_eval(k): ast.literal_eval(v)
                       for k, v in zip(node.value.keys,
                                       node.value.values, strict=True)}
    assert mapping is not None, "_SOURCE_KEYS not found"

    core_tags = [src_tag for _h, _a, src_tag in startup.RUN_KEYS]
    core_tags += [src_tag for _h, _k, src_tag in startup.RUN_KEYS_DISABLED]
    assert set(core_tags) <= set(mapping), "core tag sin traduccion en la UI"
    for key in mapping.values():
        assert key in i18n._STRINGS["es"] and key in i18n._STRINGS["en"]
