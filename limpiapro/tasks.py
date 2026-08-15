"""Tareas programadas (schtasks)."""

import csv
import io
import subprocess


def get_scheduled_tasks():
    """Lista de tareas programadas: {name, status, next, path}.
    Se usa la posicion de columna (no el nombre) porque schtasks
    emite las cabeceras en el idioma del sistema."""
    tasks = []
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/fo", "CSV", "/v"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        rows = list(csv.reader(io.StringIO(result.stdout)))
        if len(rows) < 2:
            return tasks
        # Posiciones segun schtasks /fo csv /v (estandar de Windows):
        # 0 host, 1 tarea, 2 proxima, 3 estado, 8 tarea_a_ejecutar,
        # 11 estado_tarea_programada
        for row in rows[1:]:
            if len(row) < 12:
                continue
            name = (row[1] or "").strip()
            # saltar filas basura (cabeceras repetidas o celdas vacias)
            if not name or not name.startswith("\\") or "tarea" in name.lower():
                continue
            tasks.append({
                "name": name,
                "path": (row[8] if len(row) > 8 else "").strip(),
                "status": (row[3] if len(row) > 3 else "").strip(),
                "next": (row[2] if len(row) > 2 else "").strip(),
                "scheduled": (row[11] if len(row) > 11 else "").strip(),
            })
    except Exception:
        pass
    return tasks


def set_task_enabled(task_name, enable):
    """Activa/desactiva una tarea programada. Devuelve (ok, msg)."""
    arg = "/enable" if enable else "/disable"
    try:
        result = subprocess.run(
            ["schtasks", "/change", "/tn", task_name, arg],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        msg = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, msg or "OK"
    except Exception as e:
        return False, str(e)
