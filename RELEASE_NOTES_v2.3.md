# LimpiaPro v2.3 — Release Notes

## Calidad y estabilidad

- Corrige el bloqueo de arranque causado por rutas Windows sin escapar en `audit_log.py`.
- Mueve cache y logs a `%LOCALAPPDATA%\LimpiaPro`.
- Añade `CacheService`, `CleanupService` y un dispatcher de UI basado en cola thread-safe.
- Añade contratos Protocol para páginas, categorías, cache y dispatcher.
- Protege la limpieza frente a symlinks, archivos readonly, archivos desaparecidos y reglas solapadas.
- Añade tests aislados para operaciones del registro de Windows.

## Validación y distribución

- Ruff, Pyright y Bandit integrados como validaciones bloqueantes.
- Build de PyInstaller validado en CI.
- Añade `--version` y `--smoke-test` al ejecutable.
- El release usa el tag estable `v2.3`, actualiza releases existentes y reemplaza assets duplicados de forma idempotente.
