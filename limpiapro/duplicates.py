"""Buscador de archivos duplicados."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import BLOCK_SIZE
from .utils import iter_file_sizes


class DuplicateScanner:
    """Buscador de duplicados al estilo czkawka: 1) agrupar por tamano,
    2) prehash de los primeros 4KB para descartar candidatos barato,
    3) hash completo solo del resto. Hashing en paralelo con blake2b
    (mas rapido que md5 en CPython)."""
    PREHASH_SIZE = 4096

    def __init__(self, folder, min_size_mb=2, workers=6):
        self.folder = folder
        self.min_size = min_size_mb * 1024 * 1024
        self.cancel = False
        self.groups = []
        self._workers = workers

    @staticmethod
    def _hasher(path, full=False):
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
        try:
            return DuplicateScanner._hasher(path, full=False)
        except OSError:
            return None

    @staticmethod
    def _full_hash(path):
        try:
            return DuplicateScanner._hasher(path, full=True)
        except OSError:
            return None

    def _hash_paths(self, paths, hasher, pool):
        """Hasea paths en paralelo usando `pool` (que el scan crea una sola
        vez). Devoluciones {hash: [paths]} o None si se cancela."""
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
            if h is not None:
                results.setdefault(h, []).append(p)
        return results

    def scan(self):
        self.groups = []
        by_size = {}
        for path, size in iter_file_sizes(self.folder):
            if self.cancel:
                return []
            if size >= self.min_size:
                by_size.setdefault(size, []).append(path)

        # Un unico pool reutilizado en todas las fases (evita cientos de
        # pools creados/destruidos y el polling de _future_wait).
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            for size, paths in by_size.items():
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
                for h, group in full.items():
                    if len(group) > 1:
                        self.groups.append(group)
        return self.groups