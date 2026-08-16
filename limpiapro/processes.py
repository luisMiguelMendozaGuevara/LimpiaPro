"""Running processes (tasklist / taskkill)."""

import csv
import io

from .utils import _errlog, run_system_cmd


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


def kill_process(pid):
    """Force-end a process. Returns (ok, msg)."""
    try:
        result = run_system_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
