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

    PERF: `/v` was dropped deliberately. Verbose mode makes tasklist
    query window titles, session users and CPU times for EVERY process,
    which can take several seconds (and effectively hang when a hung
    process never answers the title query). The plain listing answers
    quickly and still carries everything the UI table shows.

    Header rows are skipped language-independently: the PID column of a
    data row is always numeric, a localized header row's is not.

    Returns:
        list[dict]: A list of dictionaries, each representing a running process.
                    Keys: name, pid, session, mem, user (always "" since /v
                    was dropped), title (always "").
    """
    procs = []
    try:
        # /fo CSV = CSV output format (5 columns without /v: name, pid,
        # session, session number, memory).
        result = run_system_cmd(["tasklist", "/fo", "CSV"])
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) < 5:
                continue
            # Pad the row with empty strings to ensure we can unpack safely.
            name, pid, session, _snum, mem = (row + [""] * 5)[:5]
            pid = pid.strip()
            # Language-independent junk/header filter: only data rows
            # carry a numeric PID (repeated localized headers do not).
            if not pid.isdigit():
                continue
            procs.append({
                "name": name.strip(),
                "pid": pid,
                "session": session.strip(),
                "mem": mem.strip(),
                "user": "",
                "title": "",
            })
    except Exception as e:
        _errlog(f"tasklist failed: {e!r}")
    return procs


def kill_process(pid, name=None):
    """Force-end a process. Returns (ok, msg).

    Refuses to kill system-critical processes (is_protected). The name is
    resolved from the process list when not supplied, so the guard also
    works for callers that only have a pid.

    FAIL-CLOSED: when the process identity cannot be resolved (empty name,
    e.g. transient process or tasklist failure), the kill is REFUSED.
    is_protected("") is always False, so allowing an unresolved target
    would silently bypass the safety gate for an admin-privileged taskkill.

    Args:
        pid: The process ID to kill.
        name: Optional process name. If not provided, it will be resolved
              from the current process list.

    Returns:
        tuple: (success: bool, message: str).
               Returns (False, "protected: <name>") if the process is
               on the protected list, and (False, "unresolved: ...") when
               its name could not be resolved for verification.
    """
    name = (name or "").strip()
    if not name:
        name = _name_for(pid)

    # SAFETY GATE: Check against the protected list BEFORE invoking taskkill.
    if is_protected(name):
        return False, f"protected: {name}"
    if not name:
        # Fail-closed: an unverifiable PID must never be force-killed by an
        # elevated process. A PID could have been reused between listing
        # and this call; refusing is the safe outcome.
        return False, "unresolved: could not verify process name; refusing to kill"

    # Lote F1 (S6) — TOCTOU re-verification: the identity check above may
    # run seconds after the list snapshot (or use a caller-supplied name).
    # If the PID was recycled in between, taskkill /F would hit a
    # DIFFERENT process. Re-resolve the live name right before the kill
    # and require a match (extension/case-insensitive).
    live = _name_for(pid)
    stem = lambda s: s.lower().removesuffix(".exe")  # noqa: E731
    if not live or stem(live) != stem(name):
        return False, (f"unresolved: pid {pid} now resolves to "
                       f"{live or 'nothing'}; refusing to kill")

    try:
        # /F = force termination
        # /PID = specify process by ID
        result = run_system_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
