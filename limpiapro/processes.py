"""Procesos activos (tasklist / taskkill)."""

import csv
import io

from .utils import _errlog, run_system_cmd


def get_processes():
    """Lista de procesos: {name, pid, mem, session, title}."""
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
        _errlog(f"tasklist fallo: {e!r}")
    return procs


def kill_process(pid):
    """Termina un proceso. Devuelve (ok, msg)."""
    try:
        result = run_system_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)