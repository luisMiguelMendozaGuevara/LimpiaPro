# Migración de LimpiaPro a PySide6 — Auditoría y Plan

Documento de trabajo para la migración de la interfaz customtkinter a
PySide6 + Qt Widgets. Fase 1 (auditoría) + decisiones de diseño tomadas
durante el proceso.

---

## 1. Estado actual del repositorio

| Componente | Ubicación | Rol |
| --- | --- | --- |
| Entry point | `limpiador.py` (12 líneas) | Stub → `limpiapro.app.main()`; compatible con `LimpiaPro.bat` y `LimpiaPro.spec` |
| App / UI raíz | `limpiapro/app.py` (`CleanerApp`, 608 l.) | Ventana customtkinter: sidebar + 6 páginas, estado busy, flujos analyze/clean |
| Páginas UI (legacy) | `limpiapro/ui/*.py` | `clean_page`, `duplicates_page`, `startup_page`, `update_page`, `uninstall_page`, `log_page`, `widgets`, `theme` |
| Scanner | `limpiapro/categories.py` (`CleanCategory`) | `scan()` / `_scan_rules()`; estadísticas con `os.scandir` |
| Cleaner | `limpiapro/categories.py` + `utils.py` | `clean()` → `_parallel_map(_delete_one)` → `_delete_measured()` |
| Winapp2 | `limpiapro/winapp2.py` | Parser FileKey/ExcludeKey/Detect; 13 993 FileKey en `winapp2.ini`, 86 ExcludeKey, 0 FolderKey |
| Generación de targets | `categories.py::_iter_targets()` | Una única recorrida compartida por scan/preview/delete; snapshot en `list_files()` |
| Eliminación | `utils.py::_delete_measured/_delete_path` | Borrado medido en una sola pasada; puerta central `is_safe_delete_target()` |
| Seguridad (actual) | `utils.py::is_safe_delete_target` | Lista exacta de raíces protegidas + raíces de unidad (ver §4) |
| Workers | `ui/widgets.py::run_async/post_ui/start_ui_poller` + `threading` | Hilos daemon + cola `queue.Queue` drenada por un poller en el hilo UI |
| Caché | `services/cache_service.py::CacheService` | JSON versionado en `%LOCALAPPDATA%\LimpiaPro\limpiador_cache.json` |
| Configuración | — (no existe) | Solo tema claro/oscuro en runtime; sin persistencia |
| Servicios | `services/cleanup_service.py::CleanupService` | Orquestación analyze/preview/clean independiente de la UI (ya existe) |
| Contratos | `limpiapro/contracts.py` | Protocolos `CleanCategoryProtocol`, `UiDispatcherProtocol`, `CleanerAppProtocol` |
| Tests | `tests/` (12 archivos, pytest) | Parser, categorías, duplicados, i18n, utils, widgets, sistema, servicios, startup, desinstalador, rutas destructivas |
| Logs | `audit_log.py` + `utils.py::_errlog` | Audit JSONL (`%LOCALAPPDATA%\LimpiaPro\logs\audit.jsonl`) + error log |

Entorno: Python 3.12.10 (`C:\Users\asus\AppData\Local\Programs\Python\Python312\python.exe`).
Instalado: `customtkinter`, `pytest`. **`PySide6` NO está instalado** (requiere `pip install PySide6`).

---

## 2. Flujo actual

```
UI (CleanPage: checkboxes por categoría, total, progreso)
   │  analyze_all()                      [hilo principal: solo lanza hilos]
   ▼
_analyze_worker (hilo coordinador)
   │  1 hilo por categoría (threading.Thread)
   ▼
CleanCategory.scan()  ── winapp2? ──> _scan_rules() → _iter_targets() (os.walk) → _safe_size()
   │                    plain?    ──> _fast_folder_stats() (os.scandir) → (size, files)
   ▼
post_ui(...) → _analyze_progress / _analyze_one_done   [cola + poller → hilo UI]
   │  _save_cache() (CacheService)
   ▼
update_total(): Σ sizes de categorías marcadas
   │
   │  confirm_clean() [messagebox.askyesno]
   ▼
_clean_worker (hilo)
   │  por categoría:
   │    recycle_bin → recycle_bin_size() + empty_recycle_bin()
   │    resto       → category.clean(target_bytes=size)
   │                     _collect() → snapshot de list_files() o recorrida fresca
   │                     _parallel_map(_delete_one) → _delete_measured(path)  [SafetyGuard]
   ▼
_clean_done → set_busy(False) → after(300, analyze_all)   ← RE-ANÁLISIS COMPLETO
```

### Trabajo pesado real (dónde ocurre)

1. **`build_categories()` en el arranque** (`app.__init__`): parsea `winapp2.ini`
   completo (13 993 reglas) y lista perfiles de navegadores (`browser_cache_folders`).
2. **`_iter_targets()`** (reglas winapp2): `os.walk` por raíz de cada regla activa;
   recorrida completa del árbol. **`os.walk` sigue junctions** (no son symlinks),
   con lo que una raíz de regla puede atravesar un junction hacia zonas protegidas.
3. **`_safe_size()` por archivo**: un `getsize` por target en `_scan_rules`.
4. **`_fast_folder_stats` / `iter_file_sizes`**: recorrida completa de carpetas
   (temp, cachés de navegador) con `os.scandir` iterativo.
5. **`_delete_measured()`**: borrado medido en una sola pasada (I/O intensiva pero necesaria).
6. **Duplicación de recorridos**:
   - `scan()` recorre todo; `list_files()` (preview) recorre de nuevo (aunque hace
     snapshot para `clean()`); si no hubo preview, `clean()` recorre una vez más.
   - **`_clean_done` relanza `analyze_all()` completo** tras limpiar: re-escanea
     TODAS las categorías (incluidas las recién limpiadas, cuyo tamaño ya se conoce
     post-borrado: `self.size = max(0, size - freed)`). ← objetivo de Fase 6/7.
7. **Dos implementaciones de recorrida** distintas (`os.walk` en reglas vs
   `os.scandir` iterativo en carpetas planas) — oportunidad de unificar (Fase 7).

---

## 3. Seguridad: cómo viaja una ruta hasta el borrado (Fase 2)

Ruta de una ruta desde la fuente hasta el disco:

```
Winapp2 (FileKey root|mask|RECURSE|REMOVESELF) o location plana (%ENV% + globs)
   ↓  _iter_targets()  (una sola recorrida para scan/preview/delete)
target  (archivo o entrada de nivel superior de una location)
   ↓  CleanCategory.clean() → _parallel_map → _delete_one()
   ↓  _delete_measured(path) / _delete_path(path)
   ↓  is_safe_delete_target(path)   ← PUERTA ACTUAL (chequeo de igualdad exacta)
delete (os.remove / shutil.rmtree / os.rmdir REMOVESELF)
```

**Protección actual** (`is_safe_delete_target`, `utils.py`):
- Raíces de sistema (`C:\Windows`, `System32`, `Program Files`, `ProgramData`,
  `C:\Users`, `C:\Users\Default`, `C:\Users\Public`) + raíces por entorno
  (`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `PROGRAMFILES`, ...).
- Carpetas conocidas del perfil: `Desktop, Documents, Downloads, Music, Pictures,
  Videos, Favorites, Contacts, Saved Games, Searches, Links, OneDrive`.
- Raíces de unidad (`C:\`).
- Se comprueba **inmediatamente antes de la eliminación** en `_delete_measured`,
  `_delete_path` y REMOVESELF — cumple el requisito de timing.
- Tests existentes: `tests/test_utils.py` (drive root, dirs protegidos, hijos
  permitidos, `_delete_measured` rechaza `C:\Windows`).

**Vacíos respecto a la política pedida** ("proteger Documents/Desktop/Downloads/
Pictures/Music/Videos **y sus descendientes**"):
1. **Solo coincidencia exacta**: `C:\Users\X\Documents\CualquierCarpeta` pasa la
   puerta y puede eliminarse entera con `rmtree`. El incidente reportado
   ("eliminó carpetas relacionadas con Documents") es exactamente esta clase de
   fallo: un target *carpeta descendiente* de una carpeta protegida no está protegido.
2. **Redirección de carpetas conocidas no resuelta**: si Documents vive en
   `D:\Docs` o en `%USERPROFILE%\OneDrive\Documents` (muy común), la guarda
   (`%USERPROFILE%\Documents`) no protege la ruta real.
3. **Junctions/reparse points**: `os.walk` (reglas winapp2) desciende por junctions;
   la guarda compara strings, no la ruta final real (un junction `C:\Temp\x` →
   `C:\Users\X\Documents` no se detecta).
4. **Sin distinción archivo/carpeta**: la política actual no puede distinguir
   "borrar la carpeta X entera bajo Documents" (peligroso, debe rechazarse) de
   "borrar archivos individuales bajo Documents" (limpieza legítima: winapp2 tiene
   reglas reales como `%UserProfile%\Documents\AIDA64 Reports|*|REMOVESELF`,
   `...\Adobe\...\logs|*|RECURSE` — bloqueables solo si se justifica).

**Conclusión**: el código actual NO proporciona protección equivalente a la
política pedida (los descendientes no están protegidos). Procede implementar
`SafetyGuard` (Fase 2). Las reglas winapp2 nunca borran carpetas enteras (solo
`fnames` en `_iter_targets`; 0 `FolderKey` en el ini), por lo que rechazar el
**borrado recursivo de carpetas** bajo raíces protegidas **no rompe reglas
legítimas**; el borrado de archivos individuales sigue permitido.

---

## 4. Decisiones de diseño (registro compacto)

| Problema | Decisión | Motivo | Alternativas descartadas | Impacto |
| --- | --- | --- | --- | --- |
| Dónde vive la nueva UI | `limpiapro/ui/` pasa a ser PySide6; legacy customtkinter se mueve a `limpiapro/ui/legacy_tk/` | La arquitectura pedida exige `ui/{main_window,pages,widgets,dialogs,resources}`; patchear 3 imports (`app.py`, `services/ui_dispatcher.py`, `tests/test_widgets.py`) es contenido | UI nueva en `ui_qt/` en paralelo | App legacy sigue arrancable durante la transición (estabilidad) |
| Entry point | `limpiador.py` gana `--qt`: `py -3.12 limpiador.py --qt` lanza la UI PySide6; sin flag sigue legacy | Un solo entry point compatible con `.bat`/`.spec` | Segundo entry point | Cambio mínimo hasta validar Fase 9 |
| Capa intermedia | `limpiapro/controller.py::LimpiaProController` (QObject) con `analyze()/clean()/cancel()/get_results()` + señales `started/progress/result/finished/error/cancelled` | Frontera UI↔Core exigida; reutiliza `CleanupService`/`CacheService`/`SafetyGuard` | Controller puro sin Qt | El Core (`categories`, `winapp2`, `utils`) NO se toca salvo necesidad |
| Estructura Core | Se mantiene plana (sin paquete `core/`) | Los módulos actuales ya son Scanner/Cleaner/Winapp2/Cache; renombrar tocaba todos los imports (riesgo alto, valor bajo) | Paquete `core/` | El diagrama "Core" del objetivo se cumple por equivalencia de módulos |
| Seguridad | `limpiapro/safety.py::SafetyGuard`; `is_safe_delete_target` queda como wrapper de compatibilidad | No romper tests/llamadores existentes; política extendida a descendientes | Reescribir la puerta en utils | Borrado de carpetas bajo raíces protegidas → rechazado; archivos individuales siguen limpiándose |

---

## 5. Plan de fases (estado)

- [x] **Fase 1 — Auditoría** (este documento)
- [ ] **Fase 2 — SafetyGuard** (`safety.py` + integración + `tests/test_safety_guard.py`)
- [ ] **Fase 3 — Separación Core/UI** (Controller con API analyze/clean/cancel/get_results)
- [ ] **Fase 4 — Migración PySide6** (estructura `ui/`, `QApplication`+`QMainWindow`+`QStackedWidget`)
- [ ] **Fase 5 — Workers Qt** (análisis/limpieza en hilos; eventos agrupados)
- [ ] **Fase 6 — Flujo de limpieza** (Analizar→Resultados→Confirmar→SafetyGuard→Eliminar→Resultado; sin re-escaneo)
- [ ] **Fase 7 — Rendimiento** (medir startup/análisis/Winapp2/clean/memoria; optimizar solo cuellos demostrados)
- [ ] **Fase 8 — Diseño** (sidebar, dashboard, tarjetas, progreso, estados, iconos, dark theme, DPI)
- [ ] **Fase 9 — Validación** (funcionalidad + UI sin congelarse)
