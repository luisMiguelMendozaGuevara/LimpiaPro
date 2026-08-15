"""Utilidades comunes: rutas, formato, borrado y medida de carpetas."""

import ctypes
import glob as globmod
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor


def app_dir():
    """Directorio de la aplicacion (funciona tambien empaquetada con
    PyInstaller). En desarrollo es la raiz del proyecto, la carpeta que
    contiene limpiador.py, winapp2.ini, la cache y el log."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_size(num):
    if isinstance(num, int) and num < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} PB"


def glob_like(path):
    if any(ch in path for ch in "*?["):
        return globmod.glob(path)
    return [path]


def _parallel_map(func, items, workers=None):
    """Aplica func a cada item repartiendo el trabajo en hasta `workers`
    hilos (por defecto 4). Devuelve los resultados en orden; None si una
    tarea fallo. Se limita el numero de hilos para no saturar el disco."""
    items = list(items)
    if not items:
        return []
    if len(items) == 1 or workers == 1:
        try:
            return [func(items[0])]
        except Exception:
            return [None]
    w = min(len(items), workers or 4)
    with ThreadPoolExecutor(max_workers=w) as pool:
        futures = [pool.submit(func, it) for it in items]
        out = []
        for f in futures:
            try:
                out.append(f.result())
            except Exception:
                out.append(None)
        return out


def _folder_size(folder):
    total = 0
    try:
        for root, dirs, files in os.walk(folder):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _fast_folder_stats(folder, on_progress=None):
    """Recorre una carpeta con os.scandir (stat cacheado) mucho mas rapido
    que os.walk + getsize. Devuelve (tamano_bytes, num_archivos)."""
    total_size = 0
    total_files = 0
    stack = []
    try:
        stack.append(os.scandir(folder))
    except OSError:
        return 0, 0
    while stack:
        try:
            entry = next(stack[-1])
        except StopIteration:
            stack.pop().close()
            continue
        except OSError:
            stack.pop().close()
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append(sub)
            elif entry.is_file(follow_symlinks=False):
                total_size += entry.stat().st_size
                total_files += 1
        except OSError:
            continue
        if on_progress and total_files % 500 == 0:
            on_progress(total_files)
    return total_size, total_files


def _delete_path(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            return not os.path.exists(path)
        os.remove(path)
        return not os.path.exists(path)
    except OSError:
        return False


def _safe_size(path):
    try:
        if os.path.isdir(path):
            return _folder_size(path)
        return os.path.getsize(path)
    except OSError:
        return 0


def _errlog(msg):
    """Escribe en un archivo de error (app sin consola: si algo falla, que
    quede registro)."""
    try:
        with open(os.path.join(app_dir(), "limpiapro_error.log"),
                  "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
