"""Running processes (tasklist / taskkill)."""

import csv
import io

from .utils import _errlog, run_system_cmd

# System-critical processes that must never be killed: ending them leaves
# the session unusable (desktop/dwm) or crashes the machine outright.
# taskkill runs as admin in this app, so lsass/smss/wininit are reachable
# and therefore genuinely dangerous.
PROTECTED_PROCESSES = frozenset(name.lower() for name in (
    "system idle process", "system", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "lsm.exe", "winlogon.exe",
    "logonui.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe",
    "conhost.exe", "svchost.exe"))


def is_protected(name: str) -> bool:
    """True when a process name is on the never-kill list."""
    return (name or "").strip().lower() in PROTECTED_PROCESSES


def _name_for(pid):
    """Process name for a pid via get_processes(); "" when unknown."""
    target = str(pid)
    for p in get_processes():
        if p["pid"] == target:
            return p["name"]
    return ""


def get_processes():
    """List running processes: {name, pid, mem, session, title}.

    One batched tasklist query feeds the whole list; parse failures and
    command errors are logged and yield []."""
    procs = []
    try:
        result = run_system_cmd(["tasklist", "/fo", "CSV", "/v"])
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) < 6:
                continue
            name, pid, session, snum, mem, status, user, cpu, title = (row + [""] * 9)[:9]
            procs.append({
                "name": name.strip(),
                "pid": pid.strip(),
                "session": session.strip(),
                "mem": mem.strip(),
                "user": user.strip(),
                "title": title.strip(),
            })
    except Exception as e:
        _errlog(f"tasklist failed: {e!r}")
    return procs


def kill_process(pid, name=None):
    """Force-end a process. Returns (ok, msg).

    Refuses to kill system-critical processes (is_protected). The name is
    resolved from the process list when not supplied, so the guard also
    works for callers that only have a pid."""
    name = (name or "").strip()
    if not name:
        name = _name_for(pid)
    if is_protected(name):
        return False, f"protected: {name}"
    try:
        result = run_system_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
