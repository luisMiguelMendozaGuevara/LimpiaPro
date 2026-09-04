"""Tests for Lote F2: hashing via hashlib.file_digest (P3) and the
startup-page icon cache/batching (P4)."""

import hashlib
from pathlib import Path

from limpiapro import duplicates

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- P3


def test_full_hash_matches_manual_chunk_loop(tmp_path, monkeypatch):
    """file_digest (3.11+) and the manual BLOCK_SIZE loop must produce
    byte-identical BLAKE2b digests."""
    data = b"x" * (duplicates.BLOCK_SIZE * 2 + 123)
    f = tmp_path / "blob.bin"
    f.write_bytes(data)

    with open(f, "rb") as fh:
        expected = hashlib.file_digest(
            fh, lambda: hashlib.blake2b(digest_size=16)).hexdigest()

    assert duplicates.DuplicateScanner._hasher(str(f), full=True) == expected

    # 3.10 fallback path (file_digest removed) must agree.
    monkeypatch.setattr(duplicates, "_file_digest", None)
    assert duplicates.DuplicateScanner._hasher(str(f), full=True) == expected


def test_prehash_only_reads_first_bytes(tmp_path, monkeypatch):
    data = b"A" * 16 + b"B" * (duplicates.DuplicateScanner.PREHASH_SIZE * 2)
    f = tmp_path / "p.bin"
    f.write_bytes(data)

    expected = hashlib.blake2b(
        data[:duplicates.DuplicateScanner.PREHASH_SIZE],
        digest_size=16).hexdigest()

    assert duplicates.DuplicateScanner._hasher(str(f), full=False) == expected
    monkeypatch.setattr(duplicates, "_file_digest", None)
    assert duplicates.DuplicateScanner._hasher(str(f), full=False) == expected


def test_file_digest_used_when_available(monkeypatch, tmp_path):
    """Guard: on 3.11+ the C-level path must actually be taken (the
    fallback loop staying default would silently undo P3)."""
    import sys

    f = tmp_path / "flag.bin"
    f.write_bytes(b"ok")
    if sys.version_info >= (3, 11) and duplicates._file_digest is not None:
        called = []
        real = duplicates._file_digest

        def spy(fileobj, digest, **kw):
            called.append(True)
            return real(fileobj, digest, **kw)

        monkeypatch.setattr(duplicates, "_file_digest", spy)
        duplicates.DuplicateScanner._hasher(str(f), full=True)
        assert called, "file_digest path not exercised on a 3.11+ runtime"


# ---------------------------------------------------------------- P4


def test_startup_page_renders_before_icons():
    """Source guard: the rows must fill BEFORE the icon queue starts
    (the old code blocked the UI thread on shell-icon extraction), and
    the cache must exist so repeated refreshes skip extraction."""
    src = (REPO / "limpiapro" / "ui" / "pages" / "startup_page.py"
           ).read_text(encoding="utf-8")
    done = src.split("def _startup_done", 1)[1].split(
        "def _extract_next_icon", 1)[0]
    assert done.index("fill_tree") < done.index("QTimer.singleShot")
    assert "_icon_cache" in src and "_extract_next_icon" in src
