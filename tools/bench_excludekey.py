#!/usr/bin/env python3
"""Benchmark JUSTO de ExcludeKey: fnmatch (actual) vs precompilado.

Ambos lados con short-circuit por exclude (any() sobre los patrones de UN
exclude), como el codigo real. Mide tambien el coste de compilacion 1x.
"""
import os
import statistics
import sys
import time

REPO = "/home/z/my-project/limpia-pro-analysis"
sys.path.insert(0, REPO)
SCRIPTS = "/home/z/my-project/scripts"
sys.path.insert(0, SCRIPTS)
import winreg_stub_plugin as _winreg_stub  # noqa: E402
sys.modules.setdefault("winreg", _winreg_stub)
os.chdir(REPO)

import fnmatch as _fn  # noqa: E402
import re  # noqa: E402

from limpiapro.winapp2 import ExcludeKey  # noqa: E402

base = os.path.normpath(os.path.abspath("bench_root"))
root_ex = [
    ExcludeKey(root=os.path.join(base, f"App{i % 17}"),
               patterns=("*.log", "*.tmp", "*.bak") if i % 3 else ("*",),
               recursive=bool(i % 2))
    for i in range(86)
]
N = 50000
cands = [os.path.join(base, f"App{i % 17}" if i % 2 else f"Otro{i % 5}",
                      f"file_{i}.log") for i in range(N)]

PRE = [tuple(re.compile(_fn.translate(p), re.IGNORECASE)
             for p in ex.patterns) for ex in root_ex]


def scan_idx(fn_match):
    n = 0
    for c in cands:
        norm = os.path.normcase(c)
        parent = os.path.dirname(norm)
        name = os.path.basename(norm)
        for i, ex in enumerate(root_ex):
            if ex.recursive:
                inside = parent == ex.root or parent.startswith(ex.root + os.sep)
            else:
                inside = parent == ex.root
            if inside and fn_match(i, ex, name):
                n += 1
                break
    return n


def via_fnmatch(_i, ex, name):
    return any(_fn.fnmatch(name, p) for p in ex.patterns)


def via_re(i, _ex, name):
    return any(rx.match(name) for rx in PRE[i])


n1 = scan_idx(via_fnmatch)
n2 = scan_idx(via_re)
assert n1 == n2, f"SEMANTICA DISTINTA: {n1} vs {n2}"


def bench(fn, repeat=5):
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts)


t_fn = bench(lambda: scan_idx(via_fnmatch))
t_re = bench(lambda: scan_idx(via_re))
t_comp = bench(lambda: [tuple(re.compile(_fn.translate(p), re.IGNORECASE)
                              for p in ex.patterns) for ex in root_ex],
               repeat=3)
print(f"candidatos={N} excludes={len(root_ex)} hits={n1}")
print(f"fnmatch (actual):        {t_fn*1000:7.1f} ms")
print(f"precompilado (lazy 1x):  {t_re*1000:7.1f} ms")
print(f"compilacion total 1 vez: {t_comp*1000:7.1f} ms")
print(f"ratio: {t_fn/t_re:.2f}x")
