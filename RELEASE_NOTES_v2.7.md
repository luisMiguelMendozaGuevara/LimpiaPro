# LimpiaPro v2.7 — Release Notes

## Lote D1: CI endurecido y lint determinista
- **9 acciones de GitHub pineadas por SHA completo** (`checkout@v4`, `setup-python@v5`, `upload-artifact@v4`) referenciadas por commit de 40 hex: evita que un repo upstream comprometido ejecute código en CI.
- **Lint determinista**: el job de lint instala herramientas desde `requirements-dev.txt` (pins exactos `==`) en vez de `pip install ruff pyright bandit` flotante — cumple la política S7 (reproducibilidad de builds compilados).

## Lote D2: Crash-safety del worker de limpieza
- `CleanWorker.run` envuelto en `try/except`: ante cualquier excepción no prevista emite `failed` + `operation_error` y suelta el bloqueo `_release_busy`. Antes una excepción no controlada dejaba la UI bloqueada para siempre (botones deshabilitados).

## Lote D3: Caché post-limpieza persistida
- Nuevo `LimpiaProController._save_results_cache()`: tras cada limpieza se persisten los tamaños actualizados. El siguiente arranque (con caché <6 h) muestra las cifras correctas, no las pre-limpieza.

## Lote D4: Trazabilidad del log de errores
- `_ERRLOG_LOCK` a nivel de módulo serializa rotación + append del `limpiapro_error.log` entre workers concurrentes, evitando entrelazado y pérdida de líneas justo cuando más importa el log de errores.

## Lote D5: Deny-list de archivos críticos del SO
- **Basenames críticos** rechazados en cualquier ubicación (`ntoskrnl.exe`, `hal.dll`, `kernel32.dll`, `lsass.exe`, etc.).
- **Descendientes de `System32`, `SysWOW64`, `Boot`** rechazados (ficheros y carpetas).
- **Whitelist operativa**: `LogFiles`, `spool\PRINTERS`, `winevt\Logs` sí limpiables.
- Ficheros sueltos de `C:\Windows` protegidos (pero `Temp`, `Prefetch`, `SoftwareDistribution` limpiables).
- Integración con `_delete_measured(kind="safety")` y política histórica intacta.

## Lote D6: Auditoría con batching de escrituras
- `AuditLogger.batched()`: buffer en memoria, flush cada 64 registros y al salir del contexto (incluso en excepción via `finally`); JSONL válido.
- `categories.clean()`, `duplicates.delete_duplicates()`, `uninstall.delete_leftover_items()` usan batching y emiten `summary` (removed/errors/freed_bytes/modo) + fallos por fichero solo en error.
- `duplicates.delete_duplicates()`: nuevo servicio core que valida snapshot + borrado y registra en `audit.jsonl` (antes NO se auditaba nada).
- `uninstall.delete_leftover_items()`: ídem para claves de registro y ficheros.

## Lote D7: Escaneo paralelo de raíces
- `_parallel_map` recorre rules y locations de categorías multi-raíz en paralelo (cachés de navegador: 6 perfiles × 13 subcarpetas; winapp2: decenas de FileKeys).
- Progreso determinista por raíz, cancelación cooperativa, tolerancia a worker crash (`None` ignorado).

## Correcciones
- `delete_registry_path` (restos de desinstalador) registra el motivo del fallo en `limpiapro_error.log` (antes se tragaba la excepción en silencio).
- Test `test_redact_needs_boundary` aislado de `USERPROFILE`/`HOME` reales del entorno.

## Distribución
- Release estable `v2.7` con binarios `LimpiaPro.exe`, `LimpiaProDebug.exe` y `LimpiaProPortable.zip`.
- Suite completa: 223 tests pasando; ruff/pyright/bandit sin errores en los gates del CI.