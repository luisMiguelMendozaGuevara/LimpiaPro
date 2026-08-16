"""Tareas programadas (schtasks)."""

import csv
import io

from .utils import _errlog, run_system_cmd

# Indices de columna de `schtasks /query /fo CSV /v` (estandar de Windows):
# 0 host, 1 tarea, 2 proxima, 3 estado, 8 tarea_a_ejecutar,
# 11 estado_tarea_programada
_NAME = 1
_NEXT = 2
_STATUS = 3
_PATH = 8
_SCHEDULED = 11


def get_scheduled_tasks():
    """Lista de tareas programadas: {name, status, next, path}.
    Se usa la posicion de columna (no el nombre) porque schtasks
    emite las cabeceras en el idioma del sistema."""
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
            # saltar filas basura (cabeceras repetidas o celdas vacias)
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
        _errlog(f"schtasks query fallo: {e!r}")
    return tasks


def set_task_enabled(task_name, enable):
    """Activa/desactiva una tarea programada. Devuelve (ok, msg)."""
    arg = "/enable" if enable else "/disable"
    try:
        result = run_system_cmd(
            ["schtasks", "/change", "/tn", task_name, arg], timeout=30)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)