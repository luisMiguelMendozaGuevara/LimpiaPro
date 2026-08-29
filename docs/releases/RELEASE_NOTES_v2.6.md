# LimpiaPro v2.6 — Release Notes

## Correcciones de seguridad (P0)

- **Tareas programadas**: el listado ocultaba tareas legítimas en Windows en español (el filtro usaba la palabra "tarea"). Ahora la regla es independiente del idioma.
- **Entradas de inicio**: reactivar una entrada desactivada la borraba en vez de restaurarla. Nuevo mapa inverso `RUN_KEY_FROM_DISABLED`; pares desconocidos se rechazan.
- **Registro (Run↔RunDisabled)**: los traslados corrompían el tipo del valor (`REG_EXPAND_SZ`/`BINARY`/`DWORD` se reescribían como `REG_SZ`). Ahora se preserva íntegro, incluido el rollback.
- **Matar procesos**: `kill_process` mataba un PID sin verificar su nombre (fail-open). Ahora es fail-closed: identidad no resoluble ⇒ rechazo explícito.
- **Cancelación de análisis**: los iteradores `os.scandir` abiertos se cierran siempre, evitando handles que bloquean borrar/renombrar carpetas.
- **Frescura de caché**: `is_fresh()` usaba comparación `<=`, marcando una caché recién escrita como vigente con ventana de 0s (test intermitente). Comparación estricta `<`.

## Nuevas funciones

- **Modo papelera de reciclaje**: nueva preferencia "Mover a la papelera en vez de borrar" (persistida en settings). SafetyGuard corre siempre; un reciclaje fallido deja el objetivo intacto y reporta error estructurado `kind="recycle"`.
- **Análisis incremental al inicio**: con caché de menos de 6 horas el arranque muestra los tamaños cacheados sin recorrer el disco. El botón Analizar siempre reescanea.

## Rendimiento

- **tasklist sin `/v`**: la tabla de procesos ya no consulta títulos de ventana (elimina segundos de latencia y cuelgues con procesos colgados).
- **UPX desactivado** en los 3 specs: evita falsos positivos de antivirus en el exe compilado.

## Privacidad y seguridad

- **Logs redactados**: las rutas del perfil de usuario se enmascaran como `~` antes de serializar; rotación automática por tamaño (auditoría 5 MB, errores 2 MB, 2 generaciones).
- **AuditLogger thread-safe** con lock interno para QThread workers concurrentes.
- **CI endurecido**: `GITHUB_TOKEN` con permiso mínimo (`contents: read`); el job build publica checksums SHA256 junto al ejecutable.
- **Dependencias fijadas** a versión exacta (reproducibilidad de builds compilados).

## Distribución

- Release estable `v2.6` con binarios `LimpiaPro.exe`, `LimpiaProDebug.exe` y `LimpiaProPortable.zip`.
- Suite completa en verde: 188 tests pasando; ruff/pyright/bandit sin errores en los gates del CI.
