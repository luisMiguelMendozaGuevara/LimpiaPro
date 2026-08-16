"""Scheduled tasks (schtasks)."""

import csv
import io

from .utils import _errlog, run_system_cmd

# Column indexes of `schtasks /query /fo CSV /v` (Windows standard):
# 0 host, 1 task, 2 next run, 3 status, 8 task to run,
# 11 scheduled-task state.
_NAME = 1
_NEXT = 2
_STATUS = 3
_PATH = 8
_SCHEDULED = 11


def get_scheduled_tasks():
    """List scheduled tasks: {name, status, next, path}.

    Column positions are used (not header names) because schtasks emits
    headers in the system language. One batched query fetches everything;
    parse failures and command errors are logged and yield []."""
    tasks = []
    try:
        result = run_system_cmd(["schtasks", "/query", "/fo", "CSV", "/v"])
        rows = list(csv.reader(io.StringIO(result.stdout)))
        if len(rows) < 2:
            return tasks
        for row in rows[1:]:
            if len(row) < 12:
                continue
            name = (row[_NAME] or "").strip()
            # Skip junk rows (repeated headers or empty cells).
            if not name or not name.startswith("\\") or "tarea" in name.lower():
                continue
            tasks.append({
                "name": name,
                "path": row[_PATH].strip(),
                "status": row[_STATUS].strip(),
                "next": row[_NEXT].strip(),
                "scheduled": row[_SCHEDULED].strip(),
            })
    except Exception as e:
        _errlog(f"schtasks query failed: {e!r}")
    return tasks


def set_task_enabled(task_name, enable):
    """Enable/disable a scheduled task. Returns (ok, msg)."""
    arg = "/enable" if enable else "/disable"
    try:
        result = run_system_cmd(
            ["schtasks", "/change", "/tn", task_name, arg], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
