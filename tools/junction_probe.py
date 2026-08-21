"""Evidence experiment: Python 3.12 junction behavior on Windows.

Answers three questions that shape SafetyGuard:
  1. Does os.walk(followlinks=False) descend into junctions?
  2. Does shutil.rmtree on a junction delete the junction's TARGET contents?
  3. Does os.path.realpath resolve junctions?

Usage: python junction_probe.py <scratch_dir>
"""
import os
import shutil
import subprocess
import sys


def make_junction(link: str, target: str) -> bool:
    try:
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def main(scratch: str) -> None:
    base = os.path.abspath(scratch)
    target = os.path.join(base, "target")
    os.makedirs(os.path.join(target, "sub"), exist_ok=True)
    with open(os.path.join(target, "precious.txt"), "w", encoding="utf-8") as f:
        f.write("keep me")
    with open(os.path.join(target, "sub", "nested.txt"), "w", encoding="utf-8") as f:
        f.write("nested")

    link = os.path.join(base, "link")
    if not make_junction(link, target):
        print("RESULT: cannot create junction; skipping")
        return

    print(f"isjunction(link)       = {os.path.isjunction(link)}")
    print(f"islink(link)           = {os.path.islink(link)}")

    # 1. os.walk descent
    walked = []
    for cur, dirs, fnames in os.walk(link, followlinks=False):
        walked.extend(os.path.join(cur, n) for n in fnames)
    print(f"1. os.walk(followlinks=False) found files under junction: {sorted(walked)}")

    # 2. realpath resolution
    print(f"3. realpath(link)      = {os.path.realpath(link)}")
    print(f"   realpath target     = {os.path.realpath(target)}")
    child = os.path.join(link, "precious.txt")
    print(f"   realpath(child)     = {os.path.realpath(child)}")

    # 3. rmtree on the junction itself: does the TARGET survive?
    link2 = os.path.join(base, "link2")
    make_junction(link2, target)
    shutil.rmtree(link2, ignore_errors=True)
    print(f"2. after rmtree(link2): target exists = {os.path.exists(target)}, "
          f"precious.txt exists = {os.path.exists(os.path.join(target, 'precious.txt'))}")

    # 4. rmdir on a junction: removes only the link?
    link3 = os.path.join(base, "link3")
    make_junction(link3, target)
    try:
        os.rmdir(link3)
        print(f"4. os.rmdir(link3) ok; target exists = {os.path.exists(target)}")
    except OSError as e:
        print(f"4. os.rmdir(link3) failed: {e!r}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
