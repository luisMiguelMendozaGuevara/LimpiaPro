#!/usr/bin/env python3
"""Lineas base de rendimiento para el Lote E (medir ANTES de optimizar).

Mide en este contenedor (Linux, python3.13):
  1. Parseo + deteccion de winapp2.ini (el coste que hoy paga el arranque
     en el hilo UI antes de la primera pintura).
  2. Creacion del controlador completo (build_categories incluido).
  3. Overhead de creacion de ThreadPoolExecutor en _parallel_map.
  4. ExcludeKey.matches con fnmatch vs precompilado (hot path de escaneo).
  5. Walk de un arbol sintetico (extrapolacion a WinSxS).
"""
import os
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

REPO = "/home/z/my-project/limpia-pro-analysis"
sys.path.insert(0, REPO)
# Stub de winreg (mismo que usan los tests en Linux) ANTES de importar limpiapro:
SCRIPTS = "/home/z/my-project/scripts"
sys.path.insert(0, SCRIPTS)
import winreg_stub_plugin as _winreg_stub  # noqa: E402
sys.modules.setdefault("winreg", _winreg_stub)
os.chdir(REPO)


def bench(fn, repeat=5):
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return min(ts), statistics.median(ts)


print("=== 1. parse_winapp_rules(winapp2.ini) ===")
from limpiapro.winapp2 import parse_winapp_rules, invalidate_detect_cache, default_winapp_file

ini = default_winapp_file()
print(f"  ini: {ini} ({os.path.getsize(ini):,} bytes)")
t_min, t_med = bench(lambda: (invalidate_detect_cache(),
                              parse_winapp_rules(ini)), repeat=5)
print(f"  parse+detect: min={t_min*1000:.1f} ms, mediana={t_med*1000:.1f} ms")

print("=== 2. build_categories() completo ===")
from limpiapro.categories import build_categories
t_min, t_med = bench(build_categories, repeat=3)
print(f"  build_categories: min={t_min*1000:.1f} ms, mediana={t_med*1000:.1f} ms")

print("=== 3. overhead ThreadPoolExecutor (pool por llamada) ===")
def f(x):
    return x
def pool_cost():
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(f, range(4)))
t_min, t_med = bench(pool_cost, repeat=200)
print(f"  crear pool+4 tareas+shutdown: min={t_min*1000:.2f} ms, mediana={t_med*1000:.2f} ms")
t_min, t_med = bench(lambda: list(map(f, range(4))), repeat=200)
print(f"  equivalente serie:            min={t_min*1000:.3f} ms")

print("=== 4. ExcludeKey: fnmatch vs precompilado ===")
from limpiapro.winapp2 import ExcludeKey
sections = parse_winapp_rules(ini)
excludes = [ex for s in sections for r in s.rules for ex in r.excludes]
print(f"  ExcludeKeys reales en el ini (detect activo en Linux): {len(excludes)}")
root_ex = [e for e in excludes if e.root and not e.exact]
if len(root_ex) < 10:
    # Con el stub de winreg casi nada se detecta; sintetizamos una carga
    # equivalente a la de un Windows real (~86 excludes, mezcla recursive).
    root_ex = [
        ExcludeKey(root=f"C:\\Program Files\\App{i%17}",
                   patterns=("*.log", "*.tmp", "*.bak") if i % 3 else ("*",),
                   recursive=bool(i % 2))
        for i in range(86)
    ]
print(f"  con root+masks (reales+synth): {len(root_ex)}")
cands = [os.path.join(root_ex[0].root, f"file_{i}.tmp") for i in range(20000)]
import fnmatch as _fn
def with_fnmatch():
    n = 0
    for c in cands:
        norm = os.path.normcase(c)
        parent = os.path.dirname(norm)
        name = os.path.basename(norm)
        for ex in root_ex:
            if ex.recursive:
                inside = parent == ex.root or parent.startswith(ex.root + os.sep)
            else:
                inside = parent == ex.root
            if inside and any(_fn.fnmatch(name, p) for p in ex.patterns):
                n += 1
    return n
n1 = with_fnmatch()
t_min, t_med = bench(with_fnmatch, repeat=3)
print(f"  fnmatch actual: {t_med*1000:.1f} ms / 20k candidatos x {len(root_ex)} excludes (hits={n1})")
# precompilado equivalente
import re
compiled = [(ex, re.compile(_fn.translate(p), re.IGNORECASE))
            for ex in root_ex for p in ex.patterns]
def with_re():
    n = 0
    for c in cands:
        norm = os.path.normcase(c)
        parent = os.path.dirname(norm)
        name = os.path.basename(norm)
        for ex, rx in compiled:
            if ex.recursive:
                inside = parent == ex.root or parent.startswith(ex.root + os.sep)
            else:
                inside = parent == ex.root
            if inside and rx.match(name):
                n += 1
    return n
n2 = with_re()
assert n1 == n2, f"semantica cambia! {n1} vs {n2}"
t_min, t_med = bench(with_re, repeat=3)
print(f"  precompilado:   {t_med*1000:.1f} ms  (semantica identica, hits={n2})")

print("=== 5. walk sintetico (extrapolacion WinSxS) ===")
with tempfile.TemporaryDirectory() as tmp:
    n_files = 5000
    for d in range(20):
        sub = os.path.join(tmp, f"d{d}")
        os.mkdir(sub)
        for i in range(n_files // 20):
            open(os.path.join(sub, f"f{i}.dat"), "wb").close()
    from limpiapro.utils import _folder_size
    t_min, t_med = bench(lambda: _folder_size(tmp), repeat=3)
    print(f"  {n_files} ficheros: {t_med*1000:.1f} ms -> {t_med/n_files*1e6:.1f} us/fichero")
    for total in (60000, 120000):
        print(f"  extrapolacion WinSxS ({total:,} ficheros): "
              f"{total * t_med / n_files:.1f} s")
