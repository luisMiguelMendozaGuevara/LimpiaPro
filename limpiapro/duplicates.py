"""Buscador de archivos duplicados."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait as _future_wait

from . import BLOCK_SIZE


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

    def _hash_paths(self, paths, hasher):
        """Hasea paths en paralelo (hasta _workers hilos) comprobando cancel.
        Devuelve {hash: [paths]} o None si se cancela."""
        results = {}
        it = iter(paths)
        pending = []
        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            def _refill():
                while len(pending) < self._workers * 2:
                    p = next(it, None)
                    if p is None:
                        return
                    pending.append((p, pool.submit(hasher, p)))

            _refill()
            while pending:
                if self.cancel:
                    for _, f in pending:
                        f.cancel()
                    return None
                done, _ = _future_wait([f for _, f in pending], timeout=0.2,
                                       return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for f in done:
                    for i in range(len(pending)):
                        if pending[i][1] is f:
                            p = pending[i][0]
                            h = f.result()
                            if h is not None:
                                results.setdefault(h, []).append(p)
                            pending.pop(i)
                            break
                _refill()
        return results

    def scan(self):
        self.groups = []
        by_size = {}
        for root, dirs, files in os.walk(self.folder):
            if self.cancel:
                return []
            for name in files:
                if self.cancel:
                    return []
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size >= self.min_size:
                    by_size.setdefault(size, []).append(path)

        for size, paths in by_size.items():
            if self.cancel:
                break
            if len(paths) < 2:
                continue
            pre = self._hash_paths(paths, self._prehash)
            if pre is None:
                break
            cands = [p for grp in pre.values() if len(grp) > 1 for p in grp]
            if not cands:
                continue
            if self.cancel:
                break
            full = self._hash_paths(cands, self._full_hash)
            if full is None:
                break
            for h, group in full.items():
                if len(group) > 1:
                    self.groups.append(group)
        return self.groups
