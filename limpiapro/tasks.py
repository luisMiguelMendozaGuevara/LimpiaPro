"""Scheduled tasks (schtasks).

This module provides functionality to list and enable/disable Windows
scheduled tasks by wrapping the `schtasks.exe` command-line utility.

Design Principles:
1. Language Independence: Uses column indexes instead of header names,
   because schtasks emits headers in the system language (e.g., "Estado"
   vs "Status").
2. Batched Queries: Fetches all tasks in a single command invocation
   to minimize process creation overhead.
3. Robust Parsing: Skips malformed rows and junk lines (repeated headers,
   empty cells) gracefully.
"""

import csv
import io

from .utils import _errlog, run_system_cmd

# Column indexes of `schtasks /query /fo CSV /v` (Windows standard):
# 0 host, 1 task, 2 next run, 3 status, 8 task to run,
# 11 scheduled-task state.
# These indexes are hardcoded because the CSV format is stable across
# Windows versions, but the header names are localized.
_NAME = 1
_NEXT = 2
_STATUS = 3
_PATH = 8
_SCHEDULED = 11


def get_scheduled_tasks():
    """List scheduled tasks: {name, status, next, path}.

    Column positions are used (not header names) because schtasks emits
    headers in the system language. One batched query fetches everything;
    parse failures and command errors are logged and yield [].

    Returns:
        list[dict]: A list of dictionaries, each representing a scheduled task.
                    Keys: name, path, status, next (run time), scheduled (state).
    """
    tasks = []
    try:
        # Execute schtasks with verbose CSV output.
        result = run_system_cmd(["schtasks", "/query", "/fo", "CSV", "/v"])
        rows = list(csv.reader(io.StringIO(result.stdout)))
        
        # Need at least the header row + one data row.
        if len(rows) < 2:
            return tasks
            
        for row in rows[1:]:
            if len(row) < 12:
                # Skip malformed rows.
                continue
                
            name = (row[_NAME] or "").strip()
            # Skip junk rows:
            # - Empty names
            # - Names not starting with '\' (task paths always do)
            # - Rows containing 'tarea' (Spanish for 'task', often a 
            #   repeated header in localized output)
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
    """Enable/disable a scheduled task. Returns (ok, msg).

    Args:
        task_name: The full path name of the task (e.g., "\Microsoft\Windows\...").
        enable: True to enable, False to disable.

    Returns:
        tuple: (success: bool, message: str).
    """
    arg = "/enable" if enable else "/disable"
    try:
        result = run_system_cmd(
            ["schtasks", "/change", "/tn", task_name, arg], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
