"""Duplicate file finder."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import BLOCK_SIZE
from .utils import iter_file_sizes


class DuplicateScanner:
    """czkawka-style duplicate finder: 1) group by size, 2) prehash the
    first 4KB to discard candidates cheaply, 3) full hash only the rest.
    Hashing runs in parallel with blake2b (faster than md5 in CPython;
    hashlib releases the GIL during update so threads overlap I/O)."""

    PREHASH_SIZE = 4096

    def __init__(self, folder, min_size_mb=2, workers=6):
        self.folder = folder
        self.min_size = min_size_mb * 1024 * 1024
        self.cancel = False
        self.groups = []
        self.skipped = 0
        # path -> (size, mtime_ns) captured when the file was scanned.
        # Deletion re-validates that the on-disk file still matches, so a
        # file modified (or replaced) after the scan is not destroyed.
        self.snapshot = {}
        self._workers = workers

    @staticmethod
    def _hasher(path, full=False):
        """blake2b digest of one file: first PREHASH_SIZE bytes only, or
        the whole file in BLOCK_SIZE chunks when full=True."""
        h = hashlib.blake2b(digest_size=16)
        with open(path, "rb") as f:
            if not full:
                h.update(f.read(DuplicateScanner.PREHASH_SIZE))
            else:
                while True:
                    block = f.read(BLOCK_SIZE)
                    if not block:
                        break
                    h.update(block)
        return h.hexdigest()

    @staticmethod
    def _prehash(path):
        """Partial hash (first 4KB); None on OSError (file unreadable or
        gone mid-scan; such files silently drop out of the results)."""
        try:
            return DuplicateScanner._hasher(path, full=False)
        except OSError:
            return None

    @staticmethod
    def _full_hash(path):
        """Whole-file hash; None on OSError."""
        try:
            return DuplicateScanner._hasher(path, full=True)
        except OSError:
            return None

    def _hash_paths(self, paths, hasher, pool):
        """Hash paths in parallel through `pool` (created once per scan).
        Returns {hash: [paths]} or None when cancelled.

        Paths whose hash is None (unreadable / deleted mid-scan) are not
        silently dropped: they are counted in self.skipped so the caller
        can report how many files could not be inspected."""
        results = {}
        fut_to_path = {}
        for p in paths:
            fut_to_path[pool.submit(hasher, p)] = p
        for fut in as_completed(fut_to_path):
            if self.cancel:
                for f in fut_to_path:
                    f.cancel()
                return None
            p = fut_to_path[fut]
            h = fut.result()
            if h is None:
                self.skipped += 1
            else:
                results.setdefault(h, []).append(p)
        return results

    def scan(self):
        """Run the three phases; fills self.groups with lists of duplicate
        paths (each list has 2+ identical files).

        Phase 1 uses the scandir walker (iter_file_sizes) so grouping by
        size costs one stat per file. Phases 2-3 share a single thread
        pool, avoiding hundreds of pool creations/destructions and the
        200ms polling the old implementation had."""
        self.groups = []
        by_size = {}
        for path, size in iter_file_sizes(self.folder):
            if self.cancel:
                return []
            if size >= self.min_size:
                by_size.setdefault(size, []).append(path)
                try:
                    st = os.stat(path)
                    self.snapshot[path] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    self.snapshot[path] = (size, 0)

        # One pool reused across all phases and groups.
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            for _size, paths in by_size.items():
                if self.cancel:
                    break
                if len(paths) < 2:
                    continue
                pre = self._hash_paths(paths, self._prehash, pool)
                if pre is None:
                    break
                cands = [p for grp in pre.values() if len(grp) > 1 for p in grp]
                if not cands:
                    continue
                if self.cancel:
                    break
                full = self._hash_paths(cands, self._full_hash, pool)
                if full is None:
                    break
                for _h, group in full.items():
                    if len(group) > 1:
                        self.groups.append(group)
        return self.groups
