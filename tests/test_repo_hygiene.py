"""Guards repo text files against encoding corruption.

A CI workflow saved as UTF-16 (PowerShell `>` / `Set-Content` default in
PS 5.1) or containing stray non-UTF-8 bytes makes GitHub reject the whole
workflow: every run fails instantly with "workflow file issue" while the
code itself is fine. That exact failure shipped once, so it is pinned here.

These tests are cheap and read files directly (no imports of the app).
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# Files that must stay plain UTF-8: build inputs and CI config.
CRITICAL_TEXT_FILES = [
    ".github/workflows/ci.yml",
    "LimpiaPro.spec",
    "LimpiaProDebug.spec",
    "LimpiaProPortable.spec",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "limpiapro/ui/resources/style.qss",
]


@pytest.mark.parametrize("relpath", CRITICAL_TEXT_FILES)
def test_critical_file_is_valid_utf8(relpath: str) -> None:
    raw = (ROOT / relpath).read_bytes()
    assert not raw.startswith((b"\xff\xfe", b"\xfe\xff")), (
        f"{relpath} is UTF-16 (likely written by a PowerShell redirect); "
        "rewrite it as UTF-8")
    raw.decode("utf-8")  # raises UnicodeDecodeError when corrupted


def test_ci_workflow_parses_as_yaml() -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and jobs, "workflow declares no jobs"
    for name, job in jobs.items():
        steps = job.get("steps")
        assert isinstance(steps, list) and steps, \
            f"job '{name}' has no steps (indentation broken?)"


def test_ci_workflow_pins_actions_by_sha() -> None:
    """A mutable tag (@v4) would let a compromised action run in CI."""
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    refs = [line.split("@", 1)[1].split()[0]
            for line in text.splitlines()
            if line.strip().startswith("- uses:") and "@" in line]
    assert refs, "no pinned actions found"
    for ref in refs:
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), \
            f"action not pinned by full commit SHA: {ref}"
