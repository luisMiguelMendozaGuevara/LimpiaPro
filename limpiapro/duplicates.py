"""Duplicate file finder.

This module implements a czkawka-style duplicate file detector with three
optimization phases to minimize I/O overhead:

Phase 1 - Size Grouping:
    Groups files by size using os.scandir-based traversal (iter_file_sizes).
    Files with unique sizes cannot be duplicates, so they're eliminated
    immediately without any hashing. This is the cheapest filter.

Phase 2 - Prehash (4KB):
    For files with matching sizes, computes a partial hash (first 4KB only)
    using BLAKE2b. This quickly eliminates candidates that differ in their
    initial content, avoiding full-file hashing for non-duplicates.

Phase 3 - Full Hash:
    Only files that match both size and prehash undergo full-file hashing.
    This is the most expensive operation, so it's reserved for the smallest
    candidate set.

Performance Optimizations:
    - BLAKE2b: Faster than MD5 in CPython (hashlib releases the GIL during
      update, allowing threads to overlap I/O).
    - Parallel hashing: Uses ThreadPoolExecutor with configurable worker count.
    - Single pool: One ThreadPoolExecutor is reused across all phases and groups,
      avoiding hundreds of pool creations/destructions.
    - Snapshot validation: Captures (size, mtime_ns) during scanning. Deletion
      re-validates that the on-disk file still matches, preventing destruction
      of files modified after the scan.

Safety Guarantees:
    - Snapshot integrity: Files modified between scan and deletion are not deleted.
    - Cooperative cancellation: Respects the cancel flag between operations.
    - Error handling: Unreadable files are counted in self.skipped and excluded
      from results.
"""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import BLOCK_SIZE
from .utils import iter_file_sizes


class DuplicateScanner:
    """czkawka-style duplicate finder: 1) group by size, 2) prehash the
    first 4KB to discard candidates cheaply, 3) full hash only the rest.
    
    Hashing runs in parallel with blake2b (faster than md5 in CPython;
    hashlib releases the GIL during update so threads overlap I/O).
    
    Attributes:
        folder (str): Root folder to scan for duplicates.
        min_size (int): Minimum file size in bytes (files smaller are ignored).
        cancel (bool): Cooperative cancellation flag. Set to True to stop scanning.
        groups (list[list[str]]): List of duplicate groups (each group has 2+ identical files).
        skipped (int): Count of files that could not be read (OSError during hashing).
        snapshot (dict[str, tuple[int, int]]): Mapping of path -> (size, mtime_ns) captured
                                               during scanning. Used to validate files before
                                               deletion (prevents deleting modified files).
        _workers (int): Number of threads for parallel hashing.
    """

    # Size of the partial hash (first N bytes). 4KB is a good balance:
    # large enough to catch most differences, small enough to be cheap.
    PREHASH_SIZE = 4096

    def __init__(self, folder, min_size_mb=2, workers=6):
        """Initialize the DuplicateScanner.
        
        Args:
            folder (str): Root folder to scan for duplicates.
            min_size_mb (int, optional): Minimum file size in megabytes. Files
                                         smaller than this are ignored. Defaults to 2.
            workers (int, optional): Number of threads for parallel hashing.
                                     Defaults to 6.
        """
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
        """Compute BLAKE2b digest of one file.
        
        Args:
            path (str): Absolute path to the file.
            full (bool, optional): If True, hash the entire file in BLOCK_SIZE chunks.
                                   If False, hash only the first PREHASH_SIZE bytes.
                                   Defaults to False.
                                   
        Returns:
            str: Hexadecimal digest string (16-byte digest = 32 hex chars).
            
        Raises:
            OSError: If the file cannot be read (handled by callers).
            
        Notes:
            - Uses BLAKE2b with 16-byte digest for speed and collision resistance.
            - Reads in BLOCK_SIZE chunks to avoid loading entire files into memory.
            - hashlib releases the GIL during update(), allowing parallel I/O.
        """
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
        """Partial hash (first 4KB); None on OSError.
        
        Files that are unreadable or deleted mid-scan are silently dropped
        from the results (they cannot be duplicates if they don't exist).
        
        Args:
            path (str): Absolute path to the file.
            
        Returns:
            str | None: Hexadecimal digest string, or None if OSError occurred.
        """
        try:
            return DuplicateScanner._hasher(path, full=False)
        except OSError:
            return None

    @staticmethod
    def _full_hash(path):
        """Whole-file hash; None on OSError.
        
        Args:
            path (str): Absolute path to the file.
            
        Returns:
            str | None: Hexadecimal digest string, or None if OSError occurred.
        """
        try:
            return DuplicateScanner._hasher(path, full=True)
        except OSError:
            return None

    def _hash_paths(self, paths, hasher, pool):
        """Hash paths in parallel through `pool` (created once per scan).
        
        Args:
            paths (list[str]): List of absolute paths to hash.
            hasher (callable): Hashing function (_prehash or _full_hash).
            pool (ThreadPoolExecutor): Thread pool for parallel execution.
            
        Returns:
            dict[str, list[str]] | None: Mapping of hash -> [paths] for duplicate groups,
                                         or None if cancelled.
                                         
        Notes:
            - Paths whose hash is None (unreadable / deleted mid-scan) are counted
              in self.skipped so the caller can report how many files could not be inspected.
            - Cooperative cancellation: Checks self.cancel between futures.
            - Error handling: Cancelled futures are not awaited (returns None immediately).
        """
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
        """Run the three phases; fills self.groups with lists of duplicate paths.
        
        Each list in self.groups has 2+ identical files (same size, same hash).
        
        Returns:
            list[list[str]]: List of duplicate groups (empty list if cancelled or no duplicates).
            
        Notes:
            - Phase 1: Uses iter_file_sizes() (scandir-based) so grouping by size
              costs one stat per file.
            - Phase 2-3: Share a single ThreadPoolExecutor, avoiding hundreds of
              pool creations/destructions and the 200ms polling the old implementation had.
            - Snapshot capture: During Phase 1, captures (size, mtime_ns) for each file
              to validate before deletion (prevents deleting files modified after the scan).
            - Cooperative cancellation: Respects self.cancel between phases and groups.
        """
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
