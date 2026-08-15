"""Procesos activos (tasklist / taskkill)."""

import csv
import io
import subprocess


def get_processes():
    """Lista de procesos: {name, pid, mem, session, title}."""
    procs = []
    try:
        result = subprocess.run(
            ["tasklist", "/fo", "CSV", "/v"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
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
    except Exception:
        pass
    return procs


def kill_process(pid):
    """Termina un proceso. Devuelve (ok, msg)."""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
