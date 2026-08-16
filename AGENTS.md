# LimpiaPro

Limpiador de sistema estilo CCleaner (uso personal). Interfaz grafica moderna con customtkinter.

## Entorno

- Python 3.12 (`py -3.12`, o `python` si no existe el launcher)
- Dependencias: `customtkinter`, `PyInstaller` (6.22.0)
- Dependencias de desarrollo: `pytest` (ver `requirements-dev.txt`)
- Plataforma: Windows

## Estructura

| Ruta | Rol |
| --- | --- |
| `limpiador.py` | Punto de entrada (compatible con LimpiaPro.bat y LimpiaPro.spec) |
| `limpiapro/__init__.py` | Constantes (APP_NAME, APP_VERSION, BLOCK_SIZE) |
| `limpiapro/app.py` | CleanerApp, _errlog, main() |
| `limpiapro/utils.py` | app_dir, is_admin, format_size, glob_like, _parallel_map, _folder_size, _fast_folder_stats, _delete_path, _safe_size |
| `limpiapro/winstyle.py` | Mica, acento del sistema, fluent_font, iconos GDI+, IconCache |
| `limpiapro/winapp2.py` | Parser winapp2.ini con Detect1..N, ExcludeKey, REMOVESELF |
| `limpiapro/categories.py` | CleanCategory, user_dirs, browser_cache_folders, build_categories |
| `limpiapro/recycle.py` | recycle_bin_size, empty_recycle_bin |
| `limpiapro/duplicates.py` | DuplicateScanner (blake2b) |
| `limpiapro/startup.py` | Claves Run/RunOnce + mecanismo RunDisabled + carpetas de inicio |
| `limpiapro/tasks.py` | schtasks (get_scheduled_tasks, set_task_enabled) |
| `limpiapro/processes.py` | tasklist / taskkill |
| `limpiapro/uninstall.py` | get_installed_apps, launch_uninstaller (sin shell=True), find_leftovers, delete_registry_path |
| `limpiapro/ui/widgets.py` | make_tree, selected_one, run_async (helpers compartidos) |
| `limpiapro/ui/clean_page.py` | Pagina de limpieza |
| `limpiapro/ui/duplicates_page.py` | Pagina de duplicados |
| `limpiapro/ui/startup_page.py` | Pagina de inicio/tareas/procesos |
| `limpiapro/ui/update_page.py` | Pagina de Windows Update (DISM) |
| `limpiapro/ui/uninstall_page.py` | Pagina de desinstalador |
| `limpiapro/ui/log_page.py` | Pagina de registro de actividad |
| `limpiapro/ui/__init__.py` | Marker de subpaquete |
| `winapp2.ini` | Base de datos comunitaria de reglas winapp2 (parseada por `parse_winapp_rules`) |
| `LimpiaPro.spec` | Spec de PyInstaller (one-file, sin consola, embebe datos de customtkinter) |
| `LimpiaPro.bat` | Lanzador que ejecuta `limpiador.py` con el Python 3.12 |
| `requirements-dev.txt` | pytest |
| `tests/` | Tests de pytest (parser, categorias, duplicados, utilidades, desinstalador) |
| `limpiador_cache.json` | Cache de tamanos por categoria |
| `limpiapro_error.log` | Log de errores (siempre al lado del exe/script) |
| `limpiador.py.bak-*` | Backup del monolito original (antes del refactor) |

## Convenciones

- Codigo y docstrings en espanol (sin acentos ni caracteres especiales en strings).
- Patron de UI: `CleanerApp` como ventana raiz, paginas como clases `*Page(master, app)`.
- Trabajo pesado en hilos con `_parallel_map` / `ThreadPoolExecutor`; UI actualizada desde el hilo principal.
- Nunca bloquear el hilo de la UI con escaneos o borrados.
- `_errlog` registra todo (arranque, elevacion, excepciones).
- Se borran datos reales del sistema: nunca borrar sin confirmacion/vista previa.
- Parser winapp2: Detect1..N se combinan con AND; ExcludeKey protege archivos; sin flag RECURSE no se recurre; REMOVESELF borra carpeta si queda vacia.
- Desinstalador: nunca `shell=True`; el ejecutable se extrae, se verifica y se lanza con lista de argumentos.
- Busqueda de restos: tokens de 3+ caracteres, todos deben aparecer; claves de sistema bloqueadas.

## Comandos

### Ejecutar en desarrollo

```
py -3.12 limpiador.py
```

El script se auto-eleva a admin con `runas` si no lo es.

### Ejecutar tests

```
py -3.12 -m pytest tests/ -v
```

### Compilar con PyInstaller

```
py -3.12 -m PyInstaller --noconfirm LimpiaPro.spec
```

Genera `dist/LimpiaPro.exe` (one-file, console=False). El entry point
(`limpiador.py`) importa el paquete `limpiapro` y PyInstaller lo sigue
automaticamente, no hace falta cambiar el spec.

### Verificar errores

El log `limpiapro_error.log` contiene el historial de excepciones no capturadas.
Revisarlo al diagnosticar fallos en ejecucion, no solo en build.
