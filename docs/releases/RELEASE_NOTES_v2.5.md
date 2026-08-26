# LimpiaPro v2.5

## Refactor con buenas practicas

- **Eliminada la UI legacy CustomTkinter** (`--legacy`, `ui/legacy_tk/`,
  `app.py`, dependencia customtkinter). La migracion PySide6 esta validada
  en produccion; el codigo antiguo queda en el tag `legacy-tk-2.4`. Builds
  mas rapidos y ligeros, una sola superficie de bugs.
- **Modulos UI enfocados**: `workers.py` (run_async), `dialogs.py`
  (alertas/confirmaciones), `layouts.py` (FlowLayout), `empty_state.py`,
  `tree_helpers.py`, `messages.py` (contenido de los dialogos, testeable),
  `constants.py` (numeros magicos centralizados).
- **i18n dividida por idioma**: `limpiapro/i18n/` con `es.py` y `en.py`
  (282 claves por idioma, paridad verificada por test).
- **Lint estricto**: se activaron SIM, RUF y PERF en ruff; mas de 30
  simplificaciones (`contextlib.suppress`, `any`/`all`, desempaquetado,
  nombres de variables de entorno).
- **Corregidas 4 SyntaxWarnings** por secuencias de escape invalidas.
- **Tests nuevos**: guardas del build (todos los specs empaquetan
  style.qss/winapp2.ini/icono, sin %TOKEN% sin sustituir) y tests del
  presentador de confirmacion de limpieza. Total: 125 tests + 1 skip.

## Descargas

- **LimpiaPro.exe** — one-file.
- **LimpiaProPortable.zip** — portable OneDir, arranque instantaneo
  (recomendado).
- **LimpiaProDebug.exe** — variante con consola para diagnostico.
