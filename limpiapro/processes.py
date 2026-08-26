"""Running processes (tasklist / taskkill).

This module provides functionality to list and terminate running processes
by wrapping the `tasklist.exe` and `taskkill.exe` command-line utilities.

SAFETY CRITICAL:
    This module maintains a strict whitelist of system-critical processes
    that MUST NEVER be killed. Terminating these processes (especially
    with admin privileges, which this app runs with) can leave the
    desktop unusable or crash the machine outright.
"""

import csv
import io

from .utils import _errlog, run_system_cmd

# System-critical processes that must never be killed: ending them leaves
# the session unusable (desktop/dwm) or crashes the machine outright.
# taskkill runs as admin in this app, so lsass/smss/wininit are reachable
# and therefore genuinely dangerous.
# 
# MAINTAINABILITY: This list must be kept in sync with Windows critical
# processes. Adding new processes here is a safety decision, not a
# feature decision.
PROTECTED_PROCESSES = frozenset(name.lower() for name in (
    "system idle process", "system", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "lsm.exe", "winlogon.exe",
    "logonui.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe",
    "conhost.exe", "svchost.exe"))


def is_protected(name: str) -> bool:
    """True when a process name is on the never-kill list.

    Args:
        name: The process name (e.g., "explorer.exe").

    Returns:
        bool: True if the process is protected and must not be killed.
    """
    return (name or "").strip().lower() in PROTECTED_PROCESSES


def _name_for(pid):
    """Process name for a pid via get_processes(); "" when unknown.

    This is a fallback for callers that only have a PID and need to
    check if the process is protected before killing it.

    Args:
        pid: The process ID as a string.

    Returns:
        str: The process name, or empty string if not found.
    """
    target = str(pid)
    for p in get_processes():
        if p["pid"] == target:
            return p["name"]
    return ""


def get_processes():
    """List running processes: {name, pid, mem, session, title}.

    One batched tasklist query feeds the whole list; parse failures and
    command errors are logged and yield [].

    Returns:
        list[dict]: A list of dictionaries, each representing a running process.
                    Keys: name, pid, session, mem, user, title.
    """
    procs = []
    try:
        # /v = verbose (includes user, title, etc.)
        # /fo CSV = CSV output format
        result = run_system_cmd(["tasklist", "/fo", "CSV", "/v"])
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) < 6:
                continue
            # Pad the row with empty strings to ensure we can unpack safely.
            # tasklist /v typically returns 9 columns.
            name, pid, session, _snum, mem, _status, user, _cpu, title = (row + [""] * 9)[:9]
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
    works for callers that only have a pid.

    Args:
        pid: The process ID to kill.
        name: Optional process name. If not provided, it will be resolved
              from the current process list.

    Returns:
        tuple: (success: bool, message: str).
               Returns (False, "protected: <name>") if the process is
               on the protected list.
    """
    name = (name or "").strip()
    if not name:
        name = _name_for(pid)
        
    # SAFETY GATE: Check against the protected list BEFORE invoking taskkill.
    if is_protected(name):
        return False, f"protected: {name}"
        
    try:
        # /F = force termination
        # /PID = specify process by ID
        result = run_system_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
