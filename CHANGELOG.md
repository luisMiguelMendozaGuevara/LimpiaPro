# Changelog

Todos los cambios notables de este proyecto se documentarán en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [2.6] - 2026-08-29

### Added

#### Lote B/C: modo papelera de reciclaje (borrado recuperable)
- **Nueva preferencia `delete_to_recycle_bin`** (`settings.py`, default
  `False` = comportamiento histórico de borrado permanente)
- Checkbox "Mover a la papelera en vez de borrar" en la barra de la
  página Limpieza; persistido en `settings.json`; el diálogo de
  confirmación añade una nota cuando el modo está activo (`messages.py`)
- Núcleo (`utils.py`): `recycle_path()` + `_delete_measured(to_recycle=)`
  + `_delete_path(to_recycle=)` sobre `send2trash`; la puerta SafetyGuard
  corre SIEMPRE antes del movimiento; un reciclaje fallido (papelera
  deshabilitada, volumen sin soporte, backend ausente) deja el objetivo
  INTACTO y se reporta como error estructurado `kind="recycle"` — nunca
  un fallback destructivo
- Cableado completo: `categories.clean()` → `CleanWorker` →
  `controller.clean(to_recycle=)`; también aplicado a duplicados y restos
  del desinstalador (las otras dos vías de borrado permanente)
- Nueva dependencia pinned: `send2trash==2.1.0` (backend estándar de
  papelera, Python puro, MIT)

### Performance

#### Análisis incremental al inicio (Lote B/C)
- **Saltar el escaneo completo cuando la caché está vigente**
  (`cache_service.py`, `main_window.py`)
  - Antes: cada arranque ejecutaba el análisis completo aunque la caché
    acabara de guardarse (el traveral entero del disco se pagaba en vano)
  - Ahora: con caché de menos de 6 horas (`DEFAULT_FRESH_SECONDS`) el
    arranque aplica los tamaños cacheados, muestra "Resultados en cache
    de hace X" y no toca el disco; el botón Analizar siempre reescanea
    y preview/limpieza re-recorren el filesystem, así que el riesgo de
    datos obsoletos se limita a las cifras mostradas justo tras arrancar
  - `CacheService.age_seconds()/is_fresh()` basadas en el mtime del
    fichero: compatibles con cachés de cualquier schema/version

#### tasklist sin /v (Lote B/C)
- `tasklist /v` consultaba título de ventana, usuario de sesión y CPU de
  CADA proceso: varios segundos de latencia y cuelgue efectivo cuando un
  proceso colgado no responde a la consulta de título
- `get_processes()` usa ahora `tasklist /fo CSV` simple (5 columnas) y
  filtra la cabecera localizada por PID numérico — regla independiente
  de idioma (misma lección del fix P0 de tasks.py)
- La tabla de procesos de la página Inicio retira la columna "Usuario"
  (vacía sin /v); PID/Sesión/Memoria se conservan intactos

#### UPX desactivado y checksums de release (Lote B/C)
- `LimpiaPro.spec`, `LimpiaProDebug.spec`, `LimpiaProPortable.spec`:
  `upx=True` → `upx=False`
  - exe comprimido con UPX + app sin firma = detonante clásico de
    falsos positivos de antivirus (cuarentena heurística); el ahorro de
    tamaño no compensa la fricción
- `.github/workflows/ci.yml`: el job build genera un sidecar SHA256
  (`LimpiaPro.exe.sha256` via `Get-FileHash`) y lo publica junto al
  artefacto para verificación de integridad sin descargar dos veces

### Fixed

#### Bugs de seguridad y corrección (P0, verificados)
- **Listado de tareas programadas ocultaba tareas legítimas** (`tasks.py`)
  - El filtro anti-cabeceras repetidas usaba la palabra localizada `"tarea"`
  - En Windows en español desaparecía cualquier tarea con "tarea" en su ruta
    (p. ej. `\MiTareaDiaria\Ejecutar`); en francés/alemán no filtraba nada
  - Ahora solo se usa la regla independiente de idioma: las filas de datos
    empiezan por `\`, las cabeceras/junk nunca lo hacen
- **Reactivar entradas de inicio las borraba en vez de restaurarlas** (`startup.py`)
  - `get_disabled_startup()` informa coordenadas del key *Disabled*, pero el
    branch `enable=True` resolvía el origen con `RUN_KEY_TO_DISABLED` sobre
    esas coordenadas y caía al fallback *mismo key*: el traslado se convertía
    en un self-move cuyo paso de borrado eliminaba la entrada definitivamente
    (y devolvía `(True, "OK")`)
  - Nuevo mapa inverso `RUN_KEY_FROM_DISABLED`; los pares desconocidos se
    rechazan con mensaje en lugar de auto-borrarse
- **Los cambios Run↔RunDisabled corrompían el tipo del valor** (`startup.py`)
  - `_reg_transfer` reescribía siempre como `REG_SZ` con `str(value)`
  - Una entrada `REG_EXPAND_SZ` dejaba de expandir variables (`%ProgramFiles%…`)
    tras un ciclo desactivar/reactivar: el programa dejaba de arrancar;
    `REG_BINARY`/`REG_DWORD` también quedaban corrompidos
  - `_read_reg_value` ahora devuelve `(valor, tipo)` y `_reg_transfer` acepta
    `value_type` (default `REG_SZ`, retrocompatible) preservándolo íntegro,
    incluido el rollback del destino
- **`kill_process` fallaba abierto ante PID no verificable** (`processes.py`)
  - Si el nombre no se podía resolver, `is_protected("")` devolvía `False`
    y un `taskkill /F` elevado mataba el PID sin ninguna comprobación
  - Ahora es fail-closed: identidad no resoluble ⇒ rechazo explícito
    (`unresolved: …`) antes de invocar taskkill
- **Cancelación de análisis filtraba handles de directorio** (`utils.py`)
  - `_iter_tree_files` retornaba sin cerrar los iteradores `os.scandir`
    aún abiertos; en Windows un handle abierto bloquea borrar/renombrar
    esa carpeta (justo lo que sigue a una cancelación)
  - Bloque `finally` que cierra cualquier iterator vivo (cancelación o
    abandono del generador)
- **`is_fresh()` podía marcar una caché recién escrita como vigente con
  ventana de 0s** (`cache_service.py`, encontrado en verificación local)
  - `age_seconds()` clampa la edad a `0.0` cuando el mtime del fichero
    queda ligeramente en el futuro (precisión de reloj en Windows), y
    `is_fresh()` usaba `<=`: una caché de 0s cumplía `0.0 <= 0` y un
    test de ventana personalizada fallaba de forma intermitente
  - Comparación estricta (`age < max_age`), alineada con su docstring
    "younger than the limit"

### Tests

- `tests/test_security_hardening.py`: `test_redact_needs_boundary` se
  aislaba del `USERPROFILE`/`HOME` reales del entorno — en máquinas donde
  `%TEMP%` vive dentro del home real, el prefijo legítimo se enmascaraba
  y la aserción fallaba (fragilidad solo en Windows)

- Nuevo `tests/test_p0_regressions.py` (22 casos): roundtrip de tipos
  registro (`REG_EXPAND_SZ`/`BINARY`/`DWORD`), reactivado desde coords
  *Disabled*, fail-closed de `kill_process`, cierre de handles al cancelar
  y filtro de tareas independiente de idioma
- Nuevo `tests/test_security_hardening.py` (16 casos): pins exactos de
  dependencias, permisos mínimos del workflow, redacción del directorio
  personal (exacto/insensible a mayúsculas/límite de prefijo/
  `%USERPROFILE%` literal), rotación por tamaño (generaciones y casos
  borde), `_errlog` con rotación+redacción integradas y `AuditLogger`
  thread-safe con rotación y campos enmascarados
- Nuevo `tests/test_recycle_option.py` (11 casos): settings del modo
  papelera (default/roundtrip/tipo inválido), reciclaje de fichero y
  árbol con medición, puerta SafetyGuard activa también en modo
  papelera, fallo de reciclaje fail-safe, backend ausente, modo
  permanente no toca la papelera, nota del diálogo solo en modo
  papelera y `humanize_duration`
- Nuevo `tests/test_processes.py` (8 casos): sin `/v` en la línea de
  comandos (guarda anti-regresión), cabeceras localizadas ES/EN
  filtradas por PID numérico, campos parseados, filas malformadas
  descartadas, fallo del comando ⇒ lista vacía, `_name_for` resuelto
- `tests/test_services.py`: +4 casos de frescura de caché (vigente,
  retrodatada, ausente, ventana personalizada)
- `tests/test_build_resources.py`: +1 guarda anti-UPX en las 3 specs
- `tests/test_security_hardening.py`: +1 guarda de checksums SHA256 en
  el job build del CI
- Suite Linux (excluye `test_ui_smoke` por libEGL ausente del
  contenedor): 162 passed (+25), mismo conjunto FAILED/ERROR
  preexistente del entorno ⇒ cero regresiones

### Security

#### Higiene de logs (privacidad + límite de tamaño)
- **Rutas personales en texto plano** (`audit_log.py`, `utils.py`)
  - `audit.jsonl` y `limpiapro_error.log` registraban rutas absolutas del
    perfil (`C:\Users\<usuario>\...`), exponiendo actividad del usuario en
    texto claro y sin límite de crecimiento
  - `redact_user_paths()` enmascara el directorio personal como `~` ANTES
    de serializar (el escape JSON de separadores inutilizaría el
    enmascarado post-serialización); cubre `expanduser("~")`, valores de
    `USERPROFILE`/`HOME` y el token literal `%USERPROFILE%`, con matching
    insensible a mayúsculas y frontera de prefijo (`/home/z` no corrompe
    a `/home/zoe`)
  - Rotación automática: auditoría a 5 MB y errores a 2 MB conservando
    2 generaciones (`.1`/`.2`) vía `_rotate_log_file()` atómico
    (`os.replace`); huella máxima ~21 MB
  - `AuditLogger.log_operation` ahora es thread-safe (lock interno):
    varios workers de QThread emiten líneas JSONL íntegras; caps
    configurables por instancia (`max_bytes`/`backups`) para pruebas

#### Endurecimiento de CI (mínimo privilegio)
- **GITHUB_TOKEN restringido** (`.github/workflows/ci.yml`)
  - `permissions: contents: read` explícito a nivel de workflow; antes se
    heredaba la política por-defecto del repositorio

### Changed

#### Dependencias fijadas a versión exacta (reproducibilidad)
- `requirements.txt` / `requirements-dev.txt`: pins `==` verificados
  localmente con la suite completa — PySide6 6.11.2, pytest 9.1.1,
  pyinstaller 6.22.2, ruff 0.16.4, pyright 1.1.411, bandit 1.9.4
- Al ser una app compilada con PyInstaller, un float pin permitía que un
  release upstream no probado cambiara los binarios distribuidos
- Riesgo conocido documentado en cabeceras de ambos archivos: versiones
  nuevas de ruff/pyright añaden reglas silenciosamente; subirlas exige
  suite + CI en verde tras cada bump

#### Pipeline determinista y verde con los pins actuales
- Hallazgo: con las versiones recién fijadas, `ruff format --check`
  exigía normalización de espacios en blanco en 4 archivos ya vigilados
  por CI, y Bandit reportaba 3 hallazgos LOW preexistentes (presentes
  también con bandit 1.7: el gate ya estaba rojo antes de este cambio)
  - Formateados con el formateador del pin (`contracts.py`,
    `cache_service.py`, `cleanup_service.py`, `test_services.py`)
  - Los 3 hallazgos documentados bajo la convención existente del repo:
    `# nosec` inline justificados (`safety.py`, `theme.py`) y extensión
    del nosec de DISM a `B603, B607` (`update_page.py`)
- Verificado localmente con los pins exactos: `ruff check` limpio,
  `ruff format --check` limpio, Bandit 0 hallazgos y Pyright 0 errores

#### Tipado defensivo en páginas Qt (pyright verde)
- Guardas de estrechamiento para 10 diagnósticos error preexistentes en
  archivos de UI que ningún cambio anterior tocaba (`main_window.py`
  propiedades tipadas sobre `_get_page() -> QWidget`; acceso a miembros
  opcionales de QTreeWidget/QLayoutItem en `duplicates_page.py`,
  `clean_page.py`; dict heterogéneo anotado en `startup_page.py`)
- Beneficio funcional: esos caminos eran AttributeError latentes ante
  items/recursos desaparecidos entre conteo y acceso

## [2.2] - 2026-08-18

### Added

#### Seguridad y Robustez (P0 - Crítico)
- **Capa central de seguridad para borrado** (`is_safe_delete_target`)
  - Protege directorios del sistema (Windows, Program Files)
  - Protege perfiles de usuario (Desktop, Documents, Downloads)
  - Previene eliminación accidental de raíces de unidades
  - Todas las operaciones destructivas pasan por esta validación
- **Snapshot inmutable entre Preview y Clean**
  - El preview crea un snapshot exacto de los objetivos
  - El cleanup elimina exactamente lo que se mostró al usuario
  - Previene eliminación de archivos creados entre preview y clean
- **Clasificación detallada de errores de eliminación**
  - Errores clasificados por tipo: `in_use`, `access_denied`, `not_found`, `readonly`, `dir_not_empty`
  - La UI puede mostrar exactamente qué falló y por qué
  - Reemplaza el contador genérico de "n errores"

#### Mejoras de Seguridad (P1 - Alta Prioridad)
- **Protección de procesos críticos**
  - Lista de procesos del sistema que no pueden terminarse (explorer.exe, dwm.exe, lsass.exe, etc.)
  - Previene BSODs y colapsos del sistema
- **Gestión transaccional de startup**
  - Operaciones de registro con rollback automático
  - Si falla el paso 2, el paso 1 se revierte
  - Previene entradas duplicadas en Run/RunDisabled
- **Validación de snapshot de duplicados**
  - Antes de eliminar, se revalida tamaño y mtime
  - Previene eliminación de archivos modificados después del escaneo
- **Protección de RunOnce**
  - Advertencia especial al desactivar entradas RunOnce
  - Previene que tareas de ejecución única nunca se ejecutan
- **Invalidación de caché de detección Winapp2**
  - El caché se limpia al cargar nuevas reglas
  - Previene detecciones obsoletas

#### Logs y Diagnóstico (P1-16)
- **Sistema de audit logging estructurado**
  - Nuevo módulo `audit_log.py` con logger JSONL
  - Registra todas las operaciones: cleanup, scan, preview
  - Almacenado en `%LOCALAPPDATA%/LimpiaPro/logs/audit.jsonl`
  - Permite análisis de patrones de error
- **Herramienta de análisis de logs** (`tools/analyze_logs.py`)
  - Resume operaciones por tipo y categoría
  - Identifica errores más frecuentes
  - Muestra códigos de error comunes
  - Calcula espacio total recuperado
- **Documentación de análisis de logs** (`docs/AUDIT_LOG_ANALYSIS.md`)
  - Guía completa del formato JSONL
  - Ejemplos de consultas con PowerShell, Python y pandas
  - Interpretación de patrones de error

#### CI/CD y Calidad (P2 - Calidad Profesional)
- **Pipeline completo de CI/CD**
  - Job de linting: Ruff (linter + formatter)
  - Job de type checking: Pyright
  - Job de security scanning: Bandit
  - Job de build: PyInstaller
  - Job de smoke test: ejecuta el .exe generado
  - Jobs secuenciales: lint → test → build
- **Build automatizado del ejecutable**
  - Cada commit genera un .exe en artifacts
  - Verificación de que el .exe se generó correctamente
  - Retención de 7 días para PRs
- **Smoke test del ejecutable**
  - Ejecuta el .exe durante 5 segundos
  - Verifica que no crashee al arrancar
  - Falla el CI si el .exe no funciona

#### Almacenamiento y Permisos (P2-24)
- **Datos específicos por usuario**
  - Cache y logs en `%LOCALAPPDATA%/LimpiaPro/`
  - Previene problemas de permisos en Program Files
  - Previene conflictos entre múltiples usuarios
  - Cache incluye metadatos: timestamp, versión, usuario, máquina

### Changed

#### Arquitectura
- **Import de audit logger en categories.py**
  - Las operaciones de cleanup ahora registran cada eliminación
  - Las operaciones de scan registran inicio y fin
  - Permite análisis post-mortem de problemas

#### Documentación
- **README actualizado**
  - Removidas deudas técnicas ya resueltas (CI/tooling, startup transaccional)
  - Añadida sección "Recent improvements" con 12 mejoras documentadas
  - Documentación de deudas técnicas actuales (UI tests, i18n dinámica, CleanerApp refactor)

### Fixed

#### Bugs Críticos (P0)
- **Threading de Tkinter** (ya resuelto por IA anterior)
  - Workers usan `post_ui()` para toda comunicación con la UI
  - Previene `TclError` y congelamientos
- **Errores silenciosos en duplicados** (ya resuelto)
  - El scanner cuenta archivos no leíbles (`self.skipped`)
  - La UI muestra el contador de archivos problemáticos

#### Bugs de Seguridad (P1)
- **RunOnce sin tratamiento especial**
  - Ahora muestra advertencia fuerte antes de desactivar
  - Previene que tareas únicas nunca se ejecutan
- **Logs solo para errores internos**
  - Ahora hay logs estructurados para todas las operaciones
  - Permite diagnóstico completo de problemas

### Technical Debt Resolved

✅ **CI / tooling** - Ahora hay pipeline completo con linting, type checking, security scanning, build y smoke test
✅ **Startup manager mutation** - Ahora es transaccional con rollback
✅ **RunOnce protection** - Ahora tiene advertencia especial
✅ **Structured logging** - Audit logger JSONL implementado
✅ **User-specific storage** - Datos en %LOCALAPPDATA%
✅ **Process protection** - Procesos críticos protegidos
✅ **Duplicate validation** - Revalidación antes de eliminar
✅ **Delete safety layer** - Capa central de seguridad
✅ **Snapshot-based cleanup** - Preview y clean usan el mismo snapshot
✅ **Detailed error reporting** - Errores clasificados por tipo

### Technical Debt Remaining

⏳ **UI tests** - No hay tests end-to-end con Tkinter
⏳ **i18n dynamic refresh** - El idioma se fija al importar
⏳ **CleanerApp refactor** - God object todavía existe

## [1.0.0] - 2026-01-15

### Initial Release
- Sistema de limpieza con categorías predefinidas
- Soporte para reglas Winapp2.ini
- Buscador de duplicados con hashing BLAKE2b
- Gestor de programas de inicio
- Gestor de tareas programadas
- Gestor de procesos
- Desinstalador avanzado
- Limpieza de Windows Update
- UI moderna con CustomTkinter
- Modo oscuro y soporte de acento de Windows

---

## Notas para Desarrolladores

### Cómo contribuir

1. **Antes de añadir funcionalidades nuevas**, asegúrate de que los tests pasen:
   ```bash
   python -m pytest tests/ -v
   ```

2. **Verifica el linting**:
   ```bash
   ruff check limpiapro/ tests/
   ruff format --check limpiapro/ tests/
   ```

3. **Verifica el type checking**:
   ```bash
   pyright limpiapro/
   ```

4. **Verifica la seguridad**:
   ```bash
   bandit -r limpiapro/ -c pyproject.toml
   ```

5. **Prueba el build**:
   ```bash
   python -m PyInstaller --noconfirm LimpiaPro.spec
   ```

### Convenciones de código

- **Threading**: Todo worker que toque la UI debe usar `post_ui()`
- **Seguridad**: Toda operación destructiva debe pasar por `is_safe_delete_target()`
- **Logs**: Usa `audit.log_operation()` para operaciones importantes
- **Errores**: Usa `DeleteError` para clasificar errores de eliminación
- **Testing**: Añade tests para nuevos casos edge, especialmente filesystem

### Estructura de commits

```
feat(security): add delete safety layer for protected directories
fix(startup): implement transactional registry operations with rollback
docs(audit): add comprehensive log analysis guide
ci(pipeline): add linting, type checking and build jobs
```

---

**Mantenido por**: Luis Miguel Mendoza Guevara  
**Licencia**: MIT  
**Repositorio**: https://github.com/luisMiguelMendozaGuevara/LimpiaPro
