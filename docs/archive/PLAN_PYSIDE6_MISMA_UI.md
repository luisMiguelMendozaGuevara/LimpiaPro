# Plan: migración a PySide6 manteniendo la MISMA interfaz

Objetivo: sustituir **solo** la tecnología de la interfaz (customtkinter →
PySide6 + Qt Widgets) dejando **idéntica** la interfaz y **todas** las
funcionalidades actuales. No es un rediseño.

El intento anterior (`experiment/pyside6-ui`) rediseñó la UI (páginas
Inicio/Resultados/Configuración nuevas y perdió pestañas). Este plan parte
de esa rama para **reutilizar todo lo que es Core** (seguridad, controller,
rendimiento) y **reconstruye la capa UI como réplica 1:1 de la actual**.

---

## 1. Restricciones

1. Misma interfaz: mismas 6 pestañas, mismo layout, mismos textos (claves i18n actuales).
2. Mismas funcionalidades: cada botón/acción de la app actual sigue existiendo.
3. Qt Widgets (nada de QML ni QtWebEngine).
4. No tocar el motor (scanner/cleaner/winapp2/procesos/startup/tasks/uninstall) salvo lo ya aplicado y validado en el experimento.
5. Prioridad: seguridad → estabilidad → paridad visual → paridad funcional.
6. Trabajo pesado SIEMPRE fuera del hilo UI (equivalente al `run_async` actual).
7. UI nunca decide rutas seguras (SafetyGuard en el Core, antes del borrado).

## 2. Base de partida

Nueva rama `pyside6-same-ui` desde `experiment/pyside6-ui`.

**Se reutiliza (Core, ya validado en el experimento):**
- `limpiapro/safety.py` — SafetyGuard (protección de Documents/Desktop/… y descendientes, junctions, known folders).
- `limpiapro/controller.py` — `LimpiaProController` y workers `QThread` (eventos started/progress/result/finished/error/cancelled); se amplía para las demás páginas o se usa un helper `run_async` con QThread.
- `limpiapro/settings.py` — persistencia (tema/idioma/auto-análisis/confirmación). **No se añade pestaña nueva**: se usa solo como soporte (el toggle de tema ya existe en la sidebar).
- `limpiapro/winapp2.py` — `patterns_re` (regex perezosas) y `limpiapro/utils.py::_iter_tree_files` (rendimiento medido: análisis 15.4 s → 4.06 s).
- `limpiapro/app_qt.py` — bootstrap QApplication + auto-elevación + icono.

**Se descarta (rediseño):** `ui/pages/{home,results,settings}_page.py`, los dialogs nuevos, y el QSS/theme rediseñado. Se reescriben como réplica de la UI legacy.

## 3. Mapeo 1:1 de componentes

| Actual (customtkinter/tkinter) | PySide6 |
| --- | --- |
| `CleanerApp(ctk.CTk)` (sidebar + contenido) | `MainWindow(QMainWindow)` con sidebar (`QFrame` + `QPushButton` checkable, `QButtonGroup` exclusivo) + `QStackedWidget` |
| Botones de navegación `nav.clean/nav.startup/nav.dupes/nav.update/nav.uninstall/nav.log` | Mismos botones, mismos textos/iconos, mismo orden |
| Toggle tema (`theme.dark`/`theme.light`) | `QCheckBox`/`QPushButton` con el mismo texto; `apply_theme()` |
| Mica (`winstyle.apply_mica_backdrop`) | `DwmSetWindowAttribute` vía ctypes sobre `int(win.winId())` (best-effort; si no, QSS) |
| `fluent_font(...)` | `QFont("Segoe UI", ...)` |
| `get_system_accent()` | `DwmGetColorizationColor` vía ctypes (ya en experimento) |
| `ctk.CTkButton` | `QPushButton` estilado por QSS (colores legacy: accent #0067c0, GREEN #2e7d32, ORANGE #e65100, RED #c62828) |
| `ctk.CTkCheckBox` | `QCheckBox` |
| `ctk.CTkEntry` / `StringVar` | `QLineEdit` / `QComboBox` (min_size) |
| `ctk.CTkProgressBar` (determinate/indeterminate) | `QProgressBar` (setRange + setValue / setRange(0,0) indeterminado) |
| `ctk.CTkLabel` | `QLabel` |
| `ctk.CTkScrollableFrame` | `QScrollArea` |
| `ctk.CTkTabview` (3 sub-tabs startup) | `QTabWidget` |
| `ctk.CTkTextbox` readonly | `QPlainTextEdit` (readOnly) |
| `ctk.CTkToplevel` (preview / re-enable / leftovers) | `QDialog` |
| `ttk.Treeview` (`make_tree`, `fill_tree`, tags de color, multi-selección) | `QTreeWidget`: columnas del `spec`, `QTreeWidgetItem` con `setForeground`/`setIcon`, `setSelectionMode(ExtendedSelection)` |
| `messagebox.askyesno/showinfo/showerror/showwarning` | `QMessageBox` |
| `filedialog.askdirectory/askopenfilename` | `QFileDialog.getExistingDirectory/getOpenFileName` |
| `run_async(widget, worker, done, on_error)` | helper `run_async(host, worker, done, on_error)` con `QThread` + señal (mismo contrato) |
| Iconos GDI+ `get_file_icon_png`/`IconCache` (startup) | `QFileIconProvider` (icono de archivo nativo; si falla, sin icono) |

## 4. Página por página (réplica exacta)

**Estructura de cada página**: clase `XPage(QWidget)` con `__init__(host)` y `on_busy(bool)`, usando los mismos métodos del host que la legacy (`app.log`, `app.set_status`, `app.set_busy`, `app.busy`, etc.). El host (`MainWindow`) expone la misma superficie que `CleanerApp` (misma interfaz de "app").

1. **Limpieza (`clean_page`)** — header, toolbar (Seleccionar todo / Ninguno / Vista previa / Reglas winapp2… / Limpiar / Cancelar), lista scrollable de filas por categoría (checkbox + icono + nombre + descripción + tamaño + nº archivos), pie con total + barra de progreso + estado. Flujos: `analyze_all` (cache → worker → filas), `preview_clean` (diálogo), `confirm_clean` (diálogo → worker → re-análisis), `load_winapp_rules`. Reusa el `LimpiaProController` (o el patrón legacy `_analyze_worker`/`_clean_worker` con QThread).

2. **Registro (`log_page`)** — header + `QPlainTextEdit` readonly monospace; `log()` añade `[HH:MM:SS] msg`.

3. **Duplicados (`duplicates_page`)** — barra (Elegir carpeta + campo readonly + tamaño mínimo combo + Buscar duplicados), etiqueta info, `QTreeWidget` (grupo / copias / tamaño), pie (ayuda + resumen + Eliminar seleccionados). Flujos: scan en worker (`DuplicateScanner`), re-validación snapshot (size+mtime) antes de borrar, `_delete_path`. Mismo árbol con iids y `_item_path`.

4. **Inicio (`startup_page`)** — `QTabWidget` con 3 sub-pestañas:
   - **Apps de inicio**: Refresh / Desactivar / Reactivar; árbol (nombre / origen / comando) con iconos (`QFileIconProvider`); worker `get_startup_apps`; RunOnce con aviso; diálogo de re-activación (multi-selección).
   - **Tareas**: Refresh / Desactivar / Habilitar + contador; árbol (tarea / estado / programación / próxima) con colores enabled/disabled; `get_scheduled_tasks`/`set_task_enabled`.
   - **Procesos**: Refresh / Finalizar + filtro; árbol (proceso / PID / sesión / memoria / usuario); `get_processes`/`is_protected`/`kill_process`.

5. **Desinstalador (`uninstall_page`)** — barra (Refresh / Desinstalar / Buscar restos / Eliminar restos + contador), árbol (aplicación / editor / tamaño). Flujos: `get_installed_apps`, `launch_uninstaller` (sin shell=True), `find_leftovers` (diálogo readonly con `[tipo] ruta`), `delete_leftovers` (registry recursivo / `_delete_path`).

6. **Windows Update (`update_page`)** — barra (Analizar / Limpiar + tamaño WinSxS), `QPlainTextEdit` readonly con salida DISM. `_folder_size(WinSxS)` al construir; `dism /online /cleanup-image /AnalyzeComponentStore` y `/StartComponentCleanup` en worker (timeout 1800 s, sin shell).

## 5. Arquitectura

```
PySide6 UI (6 páginas, réplica 1:1)  →  host = MainWindow (misma superficie que CleanerApp)
        │ run_async(QThread) / LimpiaProController
        ▼
Core (sin cambios): categories · winapp2 · utils(_delete_measured/_iter_tree_files)
                    · safety(SafetyGuard) · recycle · duplicates · startup · tasks
                    · processes · uninstall · services(Cache/Cleanup)
```

- `limpiador.py` → PySide6 por defecto; `--legacy` mantiene la app actual para comparar lado a lado hasta validar.

## 6. Fases (cada una validable y commiteable)

- [x] 1. **Shell + tema + helpers** — `MainWindow` (sidebar 6 nav + toggle + QStackedWidget), `theme.py`/QSS replicando colores legacy, `widgets.py` Qt (`make_tree`, `fill_tree`, `selected_one/many`, `readonly_*`, `confirm_destructive`), helper `run_async` (hilo daemon + puente de señal, mismo contrato que legacy), `app_qt.py`.
- [x] 2. **Limpieza** (la principal) + diálogo de vista previa + carga winapp2 + papelera.
- [x] 3. **Registro**.
- [x] 4. **Duplicados**.
- [x] 5. **Inicio** (3 sub-pestañas + diálogo re-activar).
- [x] 6. **Desinstalador**.
- [x] 7. **Windows Update**.
- [x] 8. **Paridad visual** — Mica/accent/DPI, QSS réplica, i18n (mismas claves + RunOnce).
- [x] 9. **Validación** — tests headless (123 passed), boot con categorías reales (6 filas, análisis completo), build del exe y comparación con `--legacy`.

## 7. Riesgos y mitigación

| Riesgo | Mitigación |
| --- | --- |
| Fidelidad visual QSS ≠ customtkinter | Mismos colores/fuentes/radios (copiar paleta legacy); aceptar diferencias de 1–2 px |
| `ttk.Treeview` → `QTreeWidget` (tags de color, multi-selección, filas con icono) | `setForeground`/`setIcon`, `ExtendedSelection`; helper `fill_tree` preserva iids |
| Iconos GDI+ (lentos) | `QFileIconProvider` nativo (más simple); sin icono si falla |
| Mica | `DwmSetWindowAttribute` sobre HWND; best-effort |
| Workers/cancelación | mismo contrato `run_async` con QThread + señal; cancelación cooperativa |
| DISM/schtasks/tasklist/registro | subprocesos sin cambios (ya son Core); encoding OEM ya resuelto en `utils` |
| Pérdida de `set_status` global (legacy vive en clean_page) | replicar: el estado y la barra viven en la página Limpieza, igual que hoy |

## 8. Criterio de terminado

- Las 6 pestañas presentes con los mismos controles, textos y acciones que la app actual.
- Cada flujo funciona en worker (sin congelar UI) y con cancelación cooperativa.
- Seguridad intacta: `SafetyGuard` se ejecuta antes de cualquier borrado (tests de `test_safety_guard.py` siguen en verde).
- `py -3.12 -m pytest tests/` en verde (Core + seguridad + smoke tests headless por página).
- Comparación visual lado a lado con `--legacy` sin diferencias funcionales.

## 9. Fuera de alcance

- Rediseño visual, nuevas páginas, nuevas funcionalidades.
- Retirar la UI legacy (se mantiene con `--legacy` hasta validar).
- Cambios en el motor de limpieza o en winapp2 más allá de lo ya aplicado.
