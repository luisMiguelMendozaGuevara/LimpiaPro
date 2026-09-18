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
4. Two-tier listing (Lote E2.3): the table fills from the fast non-
   verbose query; the disabled state — which only exists in verbose
   output — arrives through get_task_states() and is merged later, so
   the UI never waits on the expensive /v resolution of a dozen fields
   per task (3-15 s with the typical 200-800 tasks).
"""

import csv
import io

from .utils import _errlog, run_system_cmd

# Column indexes of `schtasks /query /fo CSV` (fast, non-verbose):
# 0 host, 1 task name, 2 next run time, 3 status.
_FAST_NAME = 1
_FAST_NEXT = 2
_FAST_STATUS = 3

# Column indexes of `schtasks /query /fo CSV /v` (verbose): the scheduled
# state ("Enabled"/"Disabled", localized) only exists in verbose output.
_V_NAME = 1
_V_SCHEDULED = 11


def get_scheduled_tasks():
    """List scheduled tasks FAST: {name, status, next, scheduled}.

    Uses the non-verbose CSV query (E2.3): /v forces Windows to resolve
    a dozen extra fields per task just to fill the table, which used to
    block the refresh for seconds. The disabled state arrives separately
    via get_task_states(); until the merge, `scheduled` is empty and the
    UI falls back to `status` for coloring.

    Column positions are used (not header names) because schtasks emits
    headers in the system language. Parse failures and command errors
    are logged and yield [].

    Returns:
        list[dict]: A list of dictionaries, each representing a scheduled
                    task. Keys: name, status, next, scheduled.
    """
    tasks = []
    try:
        result = run_system_cmd(["schtasks", "/query", "/fo", "CSV"])
        rows = list(csv.reader(io.StringIO(result.stdout)))

        # Need at least the header row + one data row.
        if len(rows) < 2:
            return tasks

        for row in rows[1:]:
            if len(row) < 4:
                # Skip malformed rows.
                continue

            name = (row[_FAST_NAME] or "").strip()
            # Skip junk rows (language-independent):
            # - Empty names
            # - Names not starting with '\' (task paths always do; repeated
            #   localized header rows never do, whatever the UI language)
            # NOTE: do NOT filter by localized words ("tarea", "Tâche", ...):
            # that used to hide legitimate tasks whose path contains them
            # (e.g. "\MiTareaDiaria\Ejecutar" on a Spanish Windows).
            if not name or not name.startswith("\\"):
                continue

            tasks.append({
                "name": name,
                "status": row[_FAST_STATUS].strip(),
                "next": row[_FAST_NEXT].strip(),
                "scheduled": "",
            })
    except Exception as e:
        _errlog(f"schtasks query failed: {e!r}")
    return tasks


def get_task_states():
    """Return {task_name: scheduled_state} from the verbose query.

    The "Scheduled Task State" column (enabled/disabled, localized) only
    exists in /v output, so that query is kept — but isolated here and
    run asynchronously by the UI, so the table renders instantly from
    the fast query and the marks arrive when the verbose pass completes.
    Parse failures and command errors are logged and yield {} (the UI
    keeps the status-based fallback coloring).

    Returns:
        dict[str, str]: Task path name -> scheduled state string.
    """
    states = {}
    try:
        result = run_system_cmd(["schtasks", "/query", "/fo", "CSV", "/v"])
        rows = list(csv.reader(io.StringIO(result.stdout)))
        if len(rows) < 2:
            return states
        for row in rows[1:]:
            if len(row) < 12:
                # Skip malformed rows.
                continue
            name = (row[_V_NAME] or "").strip()
            if not name or not name.startswith("\\"):
                continue
            states[name] = row[_V_SCHEDULED].strip()
    except Exception as e:
        _errlog(f"schtasks verbose query failed: {e!r}")
    return states


def set_task_enabled(task_name, enable):
    """Enable/disable a scheduled task. Returns (ok, msg).

    Args:
        task_name: The full path name of the task (e.g., "\\Microsoft\\Windows\\...").
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
