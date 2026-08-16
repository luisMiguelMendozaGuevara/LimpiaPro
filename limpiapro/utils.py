"""Utilidades comunes: rutas, formato, borrado y medida de carpetas."""

import ctypes
import glob as globmod
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Generator, List, Optional, Tuple

# Progreso: cada cuantos archivos se notifica en el escaneo.
PROGRESS_STATS = 500
PROGRESS_RULES = 100
PROGRESS_DELETE = 20
DEFAULT_WORKERS = 4


def app_dir() -> str:
    """Directorio de la aplicacion (funciona tambien empaquetada con
    PyInstaller). En desarrollo es la raiz del proyecto, la carpeta que
    contiene limpiador.py, winapp2.ini, la cache y el log."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_size(num: float) -> str:
    if isinstance(num, int) and num < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} PB"


def glob_like(path: str) -> List[str]:
    if any(ch in path for ch in "*?["):
        return globmod.glob(path)
    return [path]


def _parallel_map(func: Callable, items, workers: Optional[int] = None) -> list:
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
    w = min(len(items), workers or DEFAULT_WORKERS)
    with ThreadPoolExecutor(max_workers=w) as pool:
        futures = [pool.submit(func, it) for it in items]
        out = []
        for f in futures:
            try:
                out.append(f.result())
            except Exception:
                out.append(None)
        return out


def iter_file_sizes(folder: str) -> Generator[Tuple[str, int], None, None]:
    """Generador que recorre una carpeta con os.scandir (stat cacheado) y
    produce (ruta, tamano_bytes) por cada archivo regular. Mas rapido que
    os.walk + getsize (una syscall menos por archivo)."""
    stack = []
    try:
        stack.append(os.scandir(folder))
    except OSError:
        return
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
                yield entry.path, entry.stat().st_size
        except OSError:
            continue


def _fast_folder_stats(folder: str, on_progress=None) -> Tuple[int, int]:
    """Recorre una carpeta con os.scandir (stat cacheado) mucho mas rapido
    que os.walk + getsize. Devuelve (tamano_bytes, num_archivos)."""
    total_size = 0
    total_files = 0
    for _path, size in iter_file_sizes(folder):
        total_size += size
        total_files += 1
        if on_progress and total_files % PROGRESS_STATS == 0:
            on_progress(total_files)
    return total_size, total_files


def _folder_size(folder: str) -> int:
    """Tamano total de una carpeta (scandir, stat cacheado)."""
    return _fast_folder_stats(folder)[0]


def _delete_path(path: str) -> bool:
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            return not os.path.exists(path)
        os.remove(path)
        return not os.path.exists(path)
    except OSError:
        return False


def _safe_size(path: str) -> int:
    try:
        if os.path.isdir(path):
            return _folder_size(path)
        return os.path.getsize(path)
    except OSError:
        return 0


def _errlog(msg: str) -> None:
    """Escribe en un archivo de error (app sin consola: si algo falla, que
    quede registro)."""
    try:
        with open(os.path.join(app_dir(), "limpiapro_error.log"),
                  "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _oem_cp() -> str:
    """Pagina de codigos OEM (cp850...): las herramientas de consola de
    Windows (schtasks, tasklist) emiten ahi, no en UTF-8."""
    try:
        cp = ctypes.windll.kernel32.GetOEMCP()
        return str(int(cp) or 850)
    except Exception:
        return "850"


def run_system_cmd(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Ejecuta un comando de consola de Windows sin ventana, capturando
    stdout/stderr decodificados con la pagina de codigos OEM.

    Devuelve el subprocess.CompletedProcess (fields .returncode, .stdout,
    .stderr). Corrige el mojibake de acentos en tareas/procesos."""
    return subprocess.run(
        args, capture_output=True, text=True,
        encoding=f"cp{_oem_cp()}", errors="replace",
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)