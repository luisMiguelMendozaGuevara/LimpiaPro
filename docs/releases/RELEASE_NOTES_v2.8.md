# LimpiaPro v2.8 — Release Notes

## Lote E — Compatibilidad, arranque y rendimiento

### E1: Compatibilidad Python 3.10/3.11 y limpieza de código muerto
- **E1.1** `utils.is_junction` shim: reemplaza `os.path.isjunction` (solo 3.12+) por fallback de reparse-tag en 3.10/3.11 Windows; siempre-Falso en POSIX. Guard que prohíbe usos directos fuera del shim.
- **E1.2** Versión única: `pyproject.toml` `version` sincronizada con `APP_VERSION` (guard de test).
- **E1.3/E1.4** Código muerto eliminado: `CleanupService`, `confirm_destructive`, `PROGRESS_RULES`, `ui.widgets` y referencias muertas; guard que impide reintroducirlos.
- **E1.5** Locale sin APIs deprecadas: `i18n` ya no usa `getdefaultlocale` deprecado.
- **E1.6** Matriz CI 3.10-3.14: el test job cubre 3.10 y 3.11 (floor prometido por `requires-python`).

### E2: Arranque y pestañas sin bloqueos
- **E2.1** Parseo `winapp2.ini` ya no retrasa la primera ventana: carga perezosa y cacheada; benchmark `bench_baseline_lote_e.py` demuestra el ahorro.
- **E2.2** Pestaña Update ya no recorre `WinSxS` en el hilo UI; escaneo diferido.
- **E2.3** `schtasks` en dos niveles: tabla rápida (5 columnas, sin `/v`) + estados async por lote; la lista aparece al instante.

### E3: Memo LRU y ExcludeKey medidos
- **E3.1** LRU en `SafetyGuard._parent_clean`: evicción de 1 entrada más antigua (OrderedDict) en lugar de `clear()` al llegar a 4096; preserva hit-rate en limpiezas grandes (~14k FileKeys).
- **E3.2/E3.3** Medidos y **RECHAZADOS** (sin cambio): precompilar ExcludeKey con `fnmatch` (+4%) y reusar pool `_parallel_map` (~0.2 ms) no justifican complejidad — ver `bench_excludekey.py`.

## Lote F — Seguridad del desinstalador, auditoría y contratos

### F1: Seguridad (S1, S5, S6)
- **S1** `uninstall_risk` / `launch_uninstaller`: UninstallString en `TEMP` es `refused` (ejecución admin a ciegas desde HKCU); `user` vs `system` con confirmación; `Popen` nunca se invoca para `temp`.
- **S5** Redacción de perfiles hermanos: `redact_user_paths` enmascara `Users\juan` y `Users\ana` por separado sin mangling de prefijos; ignora raíces no-Users.
- **S6** `kill_process` re-verifica identidad justo antes del `taskkill`: si el PID reciclado ahora resuelve a otro nombre, se rechaza; acepta nombres sin extensión.

### F3: Estructura (O1-lite, O2, O3, O4)
- **O1-lite** `CleanCategory.scan` no filtra tamaños intermedios al hilo UI: commit único al final.
- **O2** Contratos sincronizados: `CacheStore` expone `age_seconds`/`is_fresh`, `CleanCategoryProtocol` refleja `clean(to_recycle)` y doc de `scan`.
- **O3** Matcher unificado: `_iter_root_targets` es la única fuente de verdad para preview/snapshot y medición; `_iter_targets` y `scan` comparten el mismo traverser.
- **O4** Etiquetas de origen estables en inglés: `startup.RUN_KEYS` usa `User`/`System`; mapeo `_SOURCE_KEYS` traducido vía `i18n` (ES/EN).

### F2: Rendimiento (P3, P4)
- **P3** Hashing de duplicados vía `hashlib.file_digest` (Python 3.11+) con fallback a lectura por bloques; más rápido y con menos syscalls.
- **P4** Iconos de inicio no bloquean la tabla: carga asíncrona/lazy; la lista aparece sin esperar `ExtractIcon`.

## Correcciones de compatibilidad (Windows)
- `SafetyGuard._parent_chain_is_clean` normaliza ambos lados de la comparación (case/separadores) para que el LRU funcione en Windows con paths POSIX de tests.
- `test_is_junction` salta con `pytest.skip` si faltan privilegios de symlink (WinError 1314).
- `test_iter_targets_and_scan_agree` compara con `normcase` para tolerar root lowercased en Windows.
- `test_uninstall_risk_system_location` aísla `TMP` para no heredar el `TEMP` real del sistema.

## Distribución
- Release estable `v2.8` con binarios `LimpiaPro.exe`, `LimpiaProDebug.exe` y `LimpiaProPortable.zip`.
- Suite completa: 268 tests pasando, 2 skipped (privilegio symlink); ruff/pyright/bandit sin errores en gates CI.
