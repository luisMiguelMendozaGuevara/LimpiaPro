"""Tests for Lote E3: LRU parent-chain cache in SafetyGuard.

The old policy cleared the WHOLE 4096-entry memo when the cap was hit,
which collapsed the hit-rate mid-clean on large winapp2 runs (~14k
FileKeys touch far more than 4096 distinct parents) and forced thousands
of extra realpath syscalls. E3.1 evicts exactly one OLDEST entry (LRU).

E3.2 (ExcludeKey precompilation) and E3.3 (_parallel_map pool reuse)
were measured and REJECTED: fnmatch already caches compiled patterns
internally (4% delta on a 50k-candidate benchmark) and pool creation
costs ~0.2 ms per call. No code change justified — see
scripts/bench_excludekey.py and scripts/baseline_lote_e.py.
"""

from limpiapro import safety as safety_mod
from limpiapro.safety import SafetyGuard


def _guard_with_cap(monkeypatch, cap=4):
    monkeypatch.setattr(safety_mod, "_PARENT_CACHE_CAP", cap)
    monkeypatch.setattr(safety_mod.os.path, "realpath", lambda p: p)
    return SafetyGuard()


def test_lru_eviction_keeps_cap_and_newest(monkeypatch):
    guard = _guard_with_cap(monkeypatch, cap=4)
    for i in range(6):
        assert guard._parent_chain_is_clean(f"/dirs/dir{i}/f.txt") is True
    assert len(guard._parent_clean) == 4
    assert "/dirs/dir0" not in guard._parent_clean
    assert "/dirs/dir1" not in guard._parent_clean
    assert "/dirs/dir5" in guard._parent_clean


def test_hit_refreshes_recency(monkeypatch):
    guard = _guard_with_cap(monkeypatch, cap=4)
    for i in range(4):
        guard._parent_chain_is_clean(f"/dirs/dir{i}/f.txt")
    # Touch the OLDEST entry: it must survive the next eviction.
    assert guard._parent_chain_is_clean("/dirs/dir0/again.txt") is True
    guard._parent_chain_is_clean("/dirs/dir4/f.txt")
    assert "/dirs/dir0" in guard._parent_clean
    assert "/dirs/dir1" not in guard._parent_clean


def test_negative_result_is_cached_with_one_realpath(monkeypatch):
    calls = []

    def fake_realpath(p):
        calls.append(p)
        # A junction resolves OUTSIDE its literal location.
        return p if p != "/dirs/junction" else "/other/place"

    monkeypatch.setattr(safety_mod, "_PARENT_CACHE_CAP", 4096)
    monkeypatch.setattr(safety_mod.os.path, "realpath", fake_realpath)
    guard = SafetyGuard()

    first = guard._parent_chain_is_clean("/dirs/junction/f.txt")
    second = guard._parent_chain_is_clean("/dirs/junction/other.txt")
    assert first is False and second is False
    assert calls == ["/dirs/junction"], "the False verdict must be memoized"


def test_cache_never_exceeds_cap_and_invalidate_clears(monkeypatch):
    guard = _guard_with_cap(monkeypatch, cap=4)
    for i in range(50):
        guard._parent_chain_is_clean(f"/dirs/d{i}/f.txt")
    assert len(guard._parent_clean) == 4

    guard.invalidate()
    assert len(guard._parent_clean) == 0
    # After invalidation the same parent is recomputed (realpath called).
    assert guard._parent_chain_is_clean("/dirs/d49/f.txt") is True
