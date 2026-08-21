"""Phase 7 baseline benchmark (run with the 3.12 interpreter).

Measures the suspected bottlenecks BEFORE any optimization:
  - build_categories() -> winapp2.ini parse + Detect checks (startup)
  - full analyze (all categories, one pass each)
  - preview/list_files walk for the winapp category (target generation)
  - _delete_measured on a synthetic tree (clean path)
  - is_safe_delete_target overhead per target (the new gate)

Usage: python tools/benchmark.py [--quick]
"""

import os
import shutil
import sys
import tempfile
import time

# Make the project root importable when run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def timed(label, fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    dt = time.perf_counter() - t0
    print(f"{label:<48} {dt * 1000:9.1f} ms")
    return result


def build_synthetic_tree(base, files=2000, dirs=50, size=4096):
    """A small realistic junk tree for clean-path measurements."""
    for d in range(dirs):
        folder = os.path.join(base, f"cache_{d}")
        os.makedirs(folder, exist_ok=True)
        for f in range(files // dirs):
            with open(os.path.join(folder, f"f{f}.tmp"), "wb") as fh:
                fh.write(b"x" * size)


def main(quick=False):
    from limpiapro.categories import build_categories
    from limpiapro.controller import AnalysisWorker
    from limpiapro.utils import _delete_measured, is_safe_delete_target

    print("== startup ==")
    t0 = time.perf_counter()
    cats = build_categories()
    print(f"{'build_categories (winapp2 parse+detect)':<48} "
          f"{(time.perf_counter() - t0) * 1000:9.1f} ms")
    for c in cats:
        print(f"    - {c.key:<10} rules={len(c.rules) if c.rules else '-'} "
              f"locations={len(c.locations) if c.locations else '-'}")

    print("\n== analysis (all categories, one pass) ==")
    events = {"progress": 0}
    worker = AnalysisWorker(cats, lambda: False)
    worker.progress.connect(lambda *a: events.__setitem__(
        "progress", events["progress"] + 1))
    t0 = time.perf_counter()
    worker.run()
    dt = time.perf_counter() - t0
    print(f"{'full analyze':<48} {dt * 1000:9.1f} ms  "
          f"(progress events: {events['progress']})")
    total = sum(c.size for c in cats)
    files = sum(c.files for c in cats)
    print(f"    total junk: {total / 1024 / 1024:.1f} MiB, "
          f"{files} files across {len(cats)} categories")

    print("\n== preview / target generation (winapp category) ==")
    winapp = next(c for c in cats if c.key == "winapp")
    files, scanned = timed("list_files(limit=1000) [winapp]",
                           winapp.list_files, 1000)
    print(f"    shown={len(files)} scanned={scanned}")

    print("\n== clean path ==")
    scratch = tempfile.mkdtemp(prefix="lp_bench_")
    build_synthetic_tree(scratch, files=2000 if not quick else 400)
    t0 = time.perf_counter()
    gone, freed, errors = _delete_measured(scratch)
    dt = time.perf_counter() - t0
    print(f"{'_delete_measured(synthetic tree)':<48} {dt * 1000:9.1f} ms "
          f"(gone={gone}, freed={freed}, errors={len(errors)})")
    shutil.rmtree(scratch, ignore_errors=True)

    print("\n== safety gate per-target overhead ==")
    n = 20000 if not quick else 3000
    path = os.path.join(os.environ["TEMP"], "lp_bench_gate", "file.tmp")
    t0 = time.perf_counter()
    for i in range(n):
        is_safe_delete_target(path, is_dir=False)
    dt = time.perf_counter() - t0
    print(f"{'is_safe_delete_target x' + str(n):<48} {dt * 1000:9.1f} ms "
          f"({dt / n * 1e6:6.1f} us/call)")


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
