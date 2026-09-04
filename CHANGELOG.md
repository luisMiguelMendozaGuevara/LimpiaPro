# Changelog

Todos los cambios notables de este proyecto se documentarán en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [2.8] - 2026-09-03

### Added

#### Lote D1: CI endurecido + lint determinista
- **9 acciones de GitHub pineadas por SHA completo** (`.github/workflows/ci.yml`):
  `checkout`, `setup-python`, `upload-artifact` referenciadas por commit de 40 hex
- **Lint determinista**: `pip install -r requirements-dev.txt` (S7 pins exactos)
  en vez de `pip install ruff pyright bandit` flotante

#### Lote D2: Crash-safety del worker de limpieza
- `CleanWorker.run` envuelto en try/except: emite `failed` + `operation_error`
  y suelta `_release_busy` ante cualquier excepción no prevista (antes dejaba
  la UI bloqueada para siempre)

#### Lote D3: Caché post-limpieza persistida
- `LimpiaProController._save_results_cache()`: tras cada limpieza se
  persisten los tamaños actualizados para que el siguiente arranque (<6 h)
  muestre las cifras correctas y no las pre-limpieza

#### Lote D4: Trazabilidad del log de errores
- `_ERRLOG_LOCK` a nivel de módulo: serializa rotación + append del
  `limpiapro_error.log` entre workers concurrentes (evita entrelazado y
  pérdida de líneas)

#### Lote D5: Deny-list de archivos críticos del SO
- **Basenames críticos rechazados** en cualquier ubicación (p. ej. `ntoskrnl.exe`,
  `hal.dll`, `kernel32.dll`, `lsass.exe`, etc.)
- **Descendientes de `System32/SysWOW64/Boot` rechazados** (ficheros y carpetas)
- **Whitelist operativa**: `LogFiles`, `spool\PRINTERS`, `winevt\Logs` sí limpiables
- Ficheros sueltos de `C:\Windows` protegidos (Temp/Prefetch/SoftwareDistribution
  siguen limpiables), `%SystemRoot%` respetado, integración con
  `_delete_measured(kind="safety")`

#### Lote D6: Auditoría con batching de escrituras
- `AuditLogger.batched()`: buffer en memoria, flush cada 64 registros y
  al salir del contexto (incluso en excepción via finally); JSONL válido
- `categories.clean()`, `duplicates.delete_duplicates()`,
  `uninstall.delete_leftover_items()` usan batching y emiten `summary`
  (removed/errors/freed_bytes/modo) + fallos por fichero solo en error

#### Lote D7: Escaneo paralelo de raíces
- `_parallel_map` recorre rules y locations de categorías multi-raíz en
  paralelo (cachés de navegador 6 perfiles x 13 subcarpetas, winapp2 decenas
  de FileKeys); progreso determinista por raíz, cancelación cooperativa,
  tolerancia a worker crash (`None` ignorado)

### Fixed

- `delete_registry_path` (restos de desinstalador) ahora registra el
  motivo del fallo en `limpiapro_error.log` (antes se tragaba la excepción)
- Test `test_redact_needs_boundary` aislado de `USERPROFILE`/`HOME` reales

#### Lote E1.1: compatibilidad Python 3.10/3.11 restaurada
- **`os.path.isjunction()` es API de Python 3.12** pero el proyecto declara
  `requires-python = ">=3.10"`: en 3.10/3.11 TODO el núcleo de borrado y el
  escaneo winapp2 lanzaban `AttributeError` (9 llamadas en `utils.py` + 1 en
  `categories.py`, sin fallback)
- Nueva abstracción única `utils.is_junction()`: nativa en 3.12+, fallback
  Windows 3.10/3.11 que lee el reparse tag con stat sin seguir enlaces
  (detecta junctions rotas; NO es un sustituto de `islink()` — la garantía
  de no descender por junctions/symlinks queda intacta), `False` en POSIX
- Guarda de test: ningún módulo fuera del shim puede referenciar
  `os.path.isjunction` directamente

### Changed

#### Lote E1.2: versión única y coherente
- `pyproject.toml` decía `2.5` mientras `APP_VERSION` era `2.7` (el tag
  v2.7 ya existe): sincronizado a `2.7` + guarda de test que exige
  `pyproject version == APP_VERSION`

#### Lote E1.5: locale sin APIs deprecadas
- `locale.getdefaultlocale()` (deprecado desde 3.11) sustituido por
  `GetUserDefaultLocaleName` (Win32) + variables `LC_ALL`/`LC_MESSAGES`/
  `LANG` (orden gettext, `C`/`POSIX` tratados como neutrales, igual que
  hacía la API sustituida); prioridad de detección sin cambios
- Los 3 tests de detección que solo pasaban en Windows ahora son
  cross-platform (windll falso vía monkeypatch) — el baseline histórico
  de fallos en Linux baja de 15 a 12

#### Lote E1.6: matriz CI de Python 3.10 a 3.14
- El job `test` solo probaba 3.12: la promesa `>=3.10` no se verificaba
  en ningún sitio (así se coló el hueco de `isjunction`)
- Nueva matriz `["3.10", "3.11", "3.12", "3.13", "3.14"]` (PySide6 6.11.2
  soporta las 5), `fail-fast: false`; lint/build siguen en 3.12
- `upload-artifact` se mantiene en v4: la v5 cambia semántica de
  artefactos y no puede validarse desde este entorno

### Removed

#### Lote E1.3/E1.4: código muerto demostrado
- `CleanupService`: instanciado en el controller y NUNCA consumido (los
  workers llaman a las categorías directamente) y con contrato desfasado
  (`clean()` sin `to_recycle` desde el Lote B2)
- `confirm_destructive` (diálogo estilo pre-Qt6 sin llamadores) + el shim
  transitorio `ui/widgets.py` (único importador restante: el smoke test,
  ahora importa de `ui.workers`)
- `PROGRESS_RULES` (constante sin uso desde D7), checks imposibles
  `if scandir(...) is not None` (x2: `os.scandir` lanza o devuelve
  iterador, nunca None), `from typing import Optional` en winapp2
  (el archivo ya usa sintaxis `X | None`), `split(":")` → `split(":", 4)`
  en el log de limpieza (un label con `:` rompía el desempaquetado)

### Security

#### Lote F1/S1: el desinstalador de HKCU ya no es ejecución admin a ciegas
- La app corre ELEVADA: un UninstallString manipulado en HKCU ejecutaba
  código elegido por un atacante COMO ADMIN (vector de elevación UAC)
- `split_command` ya verificaba existencia; ahora `uninstall_risk()`
  clasifica la ubicación del ejecutable: bajo **TEMP** se RECHAZA en el
  lanzamiento (patrón clásico de abuso, nunca legítimo), dentro del
  **perfil de usuario** (escribible por cualquier programa) la
  confirmación añade un AVISO explícito, y la página de desinstalación
  cablea ambos veredictos
- La des-elevación real (token de explorer) exige WinAPI no probable
  desde este entorno y queda documentada como mejora futura

#### Lote F1/S5: los perfiles hermanos también se redactan en los logs
- `redact_user_paths()` solo enmascaraba el home del usuario ACTUAL: una
  línea de auditoría mencionando otro perfil (C:\Users\Ana desde una
  sesión de C:\Users\Ana2) iba en texto claro
- Ahora los prefijos `<raiz-de-usuarios>\<otro-perfil>` se enmascaran
  como `~<perfil>`; la regla se limita a raíces literalmente llamadas
  Users/home (C:\Users, /home, /Users) para que layouts exóticos
  (home=/, /root, carpetas redirigidas) nunca conviertan esto en un
  enmascarado total del disco; la frontera de prefijo se conserva

#### Lote F1/S6: kill_process re-verifica la identidad justo antes del kill
- TOCTOU: entre el listado (o el nombre suministrado) y `taskkill /PID`
  el PID podía haberse RECICLADO y el kill habría matado OTRO proceso
- Ahora se re-resuelve el nombre vivo inmediatamente antes del taskkill
  y se exige coincidencia (sin .exe e insensible a mayúsculas); un PID
  salido o cambiado ⇒ rechazo fail-closed con el nombre actual en el
  mensaje

### Changed

#### Lote F3/O1-lite: el escaneo no filtra tamaños intermedios al hilo UI
- `_scan_rules()` y el escaneo de locations mutaban `self.size/self.files`
  tras CADA raíz mientras el hilo UI los leía (O1): totales a medio día
  visibles en la UI
- Ahora acumulan en variables locales y hacen UN solo commit al final;
  durante el escaneo la UI ve los valores pre-scan estables y después los
  finales consistentes (la ventana de mutación se reduce a una
  asignación; el refactor completo de estado inmutable queda documentado
  como no factible sin arquitectura nueva)

#### Lote F3/O2: contratos sincronizados con el núcleo real
- `CacheStore` ahora declara `age_seconds`/`is_fresh` (que main_window ya
  consume desde B1), `CleanCategoryProtocol.clean` refleja la firma real
  (`on_file`, `to_recycle`) y `scan` documenta que devuelve BYTES (decía
  "número de ficheros")
- O5 (rutas de categorías) verificado y RECHAZADO: ya están centralizadas
  en `user_dirs()` — moverlas sería churn sin beneficio

#### Lote F3/O4: el núcleo ya no devuelve etiquetas en español
- `startup.py` retornaba "Usuario (HKCU Run)"/"Sistema (HKLM Run)" contra
  la regla backend-English del repo; ahora devuelve tags estables
  ("User (HKCU Run)"...) y la página de Inicio los traduce vía i18n
  (español idéntico al anterior en pantalla); O6 (funciones largas)
  pospuesto: refactor de puro estilo con riesgo de regresión alto

### Performance

#### Lote F2/P3: hashing de duplicados via hashlib.file_digest
- El bucle manual de chunks (BLAKE2b) pasaba por Python por cada 1 MiB;
  `hashlib.file_digest` (3.11+) ejecuta lectura+update en C con buffer
  mayor — mismo digest, menos overhead por byte
- `getattr(hashlib, "file_digest", None)` con el bucle manual como
  fallback: `requires-python >=3.10` sigue prometido (misma disciplina
  que el shim `is_junction` del E1.1); tests de equivalencia de digest
  en ambas rutas + guarda de que la vía C se ejercita en 3.11+

#### Lote F2/P4: los iconos de inicio ya no bloquean la tabla
- La extracción de iconos de shell (~10-50 ms fríos por entrada, 15-40
  entradas) corría ANTES de pintar las filas: hasta ~1,5 s de tabla
  congelada o vacía
- Ahora las filas se pintan inmediatamente y los iconos se extraen UNO
  por tick del bucle de eventos (la UI respira entre extracciones),
  con caché por ruta de ejecutable: los refrescos siguientes son
  instantáneos; QIcon se crea solo en el hilo GUI (QPixmap no es
  thread-safe, descartada la extracción en worker)

#### Lote E2.1: el parseo de winapp2.ini ya no retrasa la primera ventana
- `build_categories(load_winapp=)` + `LimpiaProController(defer_winapp=)`:
  la categoría winapp se crea VACÍA y el ini bundled (~1,8 MB, ~3.400
  condiciones de registro/fichero, 0,2-0,5 s en Windows) se carga por el
  pipeline TaskWorker existente JUSTO DESPUÉS de la primera pintura
- Secuenciado sin carreras: si la caché está vigente se pinta de inmediato
  (la carga de reglas sigue en background); si hay que escanear, el
  auto-análisis espera a `winapp_loaded`/`winapp_error` (flag
  `_auto_analyze_pending`); `auto_analyze=False` no fuerza ningún escaneo
- La carga manual desde la página Limpieza conserva su comportamiento
  histórico (refilas + análisis); reintentos acotados si algo se puso busy
  antes; error del ini ⇒ aviso crítico + análisis sin reglas winapp
  (antes un ini roto mataba el arranque)

#### Lote E2.2: visitar la pestaña Update ya no recorre WinSxS
- El walk de `C:\Windows\WinSxS` (decenas de miles de ficheros, segundos
  de I/O) solo corre cuando el usuario pulsa Analizar, una vez por
  sesión (`_measured`); estado inicial del label "No analizado"
- La capacidad de limpiar (DISM) no cambia; un fallo de medición permite
  reintento en el siguiente clic y ya no toca el busy global (lo posee
  DISM)

#### Lote E2.3: schtasks en dos niveles (tabla rápida + estados async)
- `get_scheduled_tasks()` usa la query NO verbose (4 columnas): rellenar
  la tabla pasa de 3-15 s (resolución de ~12 campos x 200-800 tareas) a
  ~1-2 s — alinea tasks.py con la decisión B3 de tasklist
- Nuevo `get_task_states()`: la única vía hacia el estado
  habilitada/deshabilitada sigue siendo /v, ahora aislada y asíncrona;
  el merge respeta un token de secuencia (un resultado viejo no toca
  datos nuevos) y preserva la selección del árbol
- Columna muerta "Task To Run" retirada; filtros de filas basura y
  fail-safe de errores idénticos al diseño P0

#### Lote E3.1: LRU en la memo de padres de SafetyGuard
- La caché de cadenas de padres (`_parent_clean`, cap 4096) se VACIABA
  ENTERA al alcanzar el cap: una limpieza winapp2 grande (~14k FileKeys
  que tocan decenas de miles de padres distintos) colapsaba el hit-rate
  a cero a mitad de limpieza y forzaba miles de `realpath` extra
- Ahora OrderedDict con eviction LRU de UNA entrada (O(1), mismo cap,
  mismos valores); tests: eviction conserva los recientes, hit refresca
  recencia, veredicto False memoizado con un solo realpath, invalidate

#### Lote E3.2/E3.3: medidos y RECHAZADOS (sin cambio de código)
- `ExcludeKey` precompilado vs `fnmatch.fnmatch` actual: 4% de diferencia
  en un benchmark de 50k candidatos x 86 excludes — fnmatch ya cachea los
  patrones compilados internamente; no justifica tocar el hot path de
  matching (script: `tools/bench_excludekey.py`)
- Reutilizar el pool de `_parallel_map`: crear ThreadPoolExecutor cuesta
  ~0,2 ms por llamada (~30 llamadas/sesión = ~6 ms); el threshold serie
  para lotes pequeños ya existía; DEFAULT_WORKERS=4 se mantiene por la
  estabilidad en HDD (script: `tools/bench_baseline_lote_e.py`)

### Tests

#### Lote F3: +7 tests nuevos
- `tests/test_lote_f3.py`: paridad matcher unificado (preview==medición),
  exclusiones activas en el generador, commit único del estado de scan en
  ambas rúas (rules/locations), superficie de contratos (CacheStore con
  frescura, clean con on_file/to_recycle), tags core en inglés ASCII y su
  mapeo i18n completo en ambas tablas

#### Lote F2: +4 tests nuevos
- `tests/test_lote_f2.py`: digest BLAKE2b idéntico entre file_digest y el
  bucle manual 3.10 (hash multi-chunk y prehash), guarda de que la vía C
  se ejercita en 3.11+ y guarda de render-antes-que-iconos con caché

#### Lote E3: +4 tests nuevos
- `tests/test_lote_e3.py`: eviction LRU conserva los recientes y respeta
  el cap, hit refresca recencia, veredicto negativo memoizado con un solo
  realpath, cap nunca excedido + invalidate limpia

#### Lote E2: +8 tests nuevos
- `tests/test_lote_e2.py`: query rápida sin /v (guarda anti-regresión) con
  CSV no-verbose ES realista (cabeceras localizadas, filas basura y
  malformadas), query verbose para estados, errores fail-safe,
  `build_categories` diferido que NUNCA parsea / por defecto SÍ parsea,
  controller con `defer_winapp`, y guardas de cableado (main_window
  diferido y secuenciado, Update midiendo solo bajo demanda)
- `tests/test_p0_regressions.py`: fixture de fila malformada adaptada a la
  norma de 4 columnas de la query rápida (la intención P0 no cambia)

#### Lote E1: +13 tests nuevos
- `tests/test_lote_e.py` (10): semántica de `is_junction` (fichero/dir/
  symlink/symlink roto/inexistente), fallback reparse-tag (mount point
  detectado, symlink-tag rechazado, sin tag, OSError), guardas anti-regresión
  (isjunction solo en el shim, código muerto, versión sincronizada, matriz
  CI con 3.10/3.11) y sanity end-to-end de borrado a través del shim
- `tests/test_i18n.py`: 3 tests de detección hechos cross-platform + 2
  nuevos (fallback por variables de entorno y su precedencia)

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

#### Lote D6: cobertura de auditoría completa + batching de escrituras
- **`AuditLogger.batched()`**: las operaciones masivas ya no pagan un
  open/append/close + comprobación de rotación POR REGISTRO; los
  registros se bufferizan en memoria y se vuelcan en una sola escritura
  cada 64 registros y al salir del contexto (también en excepción, via
  finally). Peaje documentado: si el proceso muere a mitad de lote se
  pierden como máximo los últimos 64 registros de auditoría
- **`duplicates.delete_duplicates()`**: nuevo servicio core que traslada
  la validación de snapshot + borrado de la página de duplicados al
  núcleo y registra la operación en `audit.jsonl` (antes NO se auditaba
  nada): registros por fichero SOLO de fallos + un registro `summary`
  con removed/errors/changed/freed_bytes/modo
- **`uninstall.delete_leftover_items()`**: ídem para los restos del
  desinstalador (claves de registro y ficheros), con registros de fallo
  y `summary` (operation="uninstall", category="leftovers")
- `categories.clean()` cierra ahora con un registro `summary` por
  categoría (removed/errors/freed_bytes/modo) y agrupa sus registros
  por fichero en un batch
- Las páginas de UI quedan finas: `duplicates_page._delete_worker` y
  `uninstall_page._delete_leftovers_worker` delegan en los servicios core

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

#### Escaneo paralelo de raíces (Lote D7)
- `CleanCategory._scan_rules()` y el escaneo de locations de `scan()`
  recorrían sus raíces EN SERIE: las categorías multi-raíz (cachés de
  navegador con 6 perfiles x 13 subcarpetas, winapp2 con decenas de
  FileKeys) pagaban la latencia SUMA de todos los árboles
- Ahora cada raíz/localización se recorre en un worker de
  `_parallel_map` (el mismo pool ya usado para el borrado); los workers
  no tocan estado compartido: devuelven pares (size, files) que se
  suman determinísticamente en orden de regla
- El progreso se reporta desde el hilo llamador tras completar cada
  raíz (los callbacks desde workers del pool no son thread-safe); la
  cancelación cooperativa se comprueba en cada worker y entre entradas
- Tolerante a fallos: un worker que reviente contribuye None y se
  ignora (el resto de raíces se cuentan); docstring mentiroso de
  `_scan_rules` ("scanned on its own thread") corregido
- `_iter_targets()` (preview/snapshot) sigue en serie a propósito: el
  orden estable del snapshot y del diálogo de preview se preserva

### Fixed

#### Lote D: robustez de limpieza, caché post-limpieza y trazabilidad (D2/D3/D4)
- **Un fallo inesperado durante la limpieza dejaba la UI bloqueada**
  (`controller.py`)
  - `CleanWorker.run` era el único worker sin red de excepciones ni señal
    `failed`: cualquier excepción no prevista en `cat.clean()` mataba el
    hilo sin disparar `thread.quit()` — todos los botones quedaban
    deshabilitados para siempre tras una operación destructiva
  - Ahora `run()` envuelve el cuerpo en try/except y emite `failed`,
    cableado a `operation_error` + `_release_busy` y como señal terminal
    del hilo (mismo contrato que Analysis/Preview/Task workers)
- **La caché mostraba tamaños pre-limpieza como "resultados en cache"**
  (`controller.py`)
  - Tras un clean nadie re-escribía la caché: al reabrir en <6 h el
    análisis incremental presentaba las cifras ANTES de limpiar
  - `LimpiaProController._save_results_cache()` persiste los tamaños
    post-limpieza (CleanCategory.clean ya los actualiza en memoria);
    helper `_cache_payload()` compartido con AnalysisWorker y constante
    `PLATFORM_NAME` (sustituye el magic value `"win32"`)
- **`delete_registry_path` fallaba en silencio total** (`uninstall.py`)
  - Única operación destructiva 100% opaca: se tragaba todas las
    excepciones y devolvía False sin rastro; ahora registra el motivo en
    `limpiapro_error.log` vía `_errlog`
- **`_errlog` sin serialización entre hilos** (`utils.py`)
  - Rotación + append competían entre workers concurrentes (entrelazado
    o pérdida de líneas justo cuando el log de errores más importa);
    lock a nivel de módulo alrededor de la sección crítica (D4)

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

#### Lote D (D1-D4): 9 tests nuevos
- `tests/test_lote_d.py` (7): señal `failed` de CleanWorker sin
  `finished`, crash libera busy y reporta `operation_error`, resumen de
  éxito intacto, caché post-limpieza con tamaños actualizados, forma del
  payload de caché, `_errlog` con 8 hilos × 25 líneas íntegras y
  `delete_registry_path` registrando el motivo del fallo
- `tests/test_security_hardening.py` (+2): todas las acciones del CI
  pineadas por SHA completo de 40 hex y herramientas de lint instaladas
  desde `requirements-dev.txt` (nada flotante)
- Suite Linux tras Lote D: 171 passed (+9), conjunto FAILED/ERROR
  byte-idéntico al baseline ⇒ cero regresiones

#### Lote D5-D7: 26 tests nuevos (tests/test_lote_d5_d7.py)
- D5: basenames críticos rechazados en cualquier ubicación,
  descendientes de System32/SysWOW64/Boot rechazados (ficheros y
  carpetas), whitelist LogFiles/spool PRINTERS/winevt Logs operativa,
  ficheros sueltos de C:\Windows protegidos con Temp/Prefetch/
  SoftwareDistribution limpiables, robustez ante mayúsculas/separadores,
  %SystemRoot% respetado, integración con `_delete_measured`
  (kind="safety") y política histórica intacta
- D6: batching (buffer hasta salir, auto-flush al umbral de 64, flush
  en excepción, JSONL válido, escritura inmediata fuera de batch),
  summary de `categories.clean` (modo delete/recycle),
  `delete_duplicates` con snapshot-revalidación y sin registros de
  éxito por fichero, fallos de duplicados con error_code/kind,
  `delete_leftover_items` con fallo de registro y summary
- D7: `_parallel_map` usado para rules y locations, progreso por
  raíz/localización determinista, tolerancia a worker crash (None) en
  ambos caminos, cancelación cooperativa
- Suite Linux tras Lote D5-D7: 197 passed (+26), conjunto FAILED/ERROR
  byte-idéntico al baseline ⇒ cero regresiones

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

#### Acciones de CI pineadas por SHA + lint determinista (Lote D1)
- **9 referencias `uses:` sin pin** (`.github/workflows/ci.yml`)
  - checkout/setup-python/upload-artifact se referenciaban por tag
    mutable (`@v4`/`@v5`): un compromiso del repositorio upstream
    ejecutaría código en CI con acceso al código y artefactos
  - Pineadas por SHA completo del commit de la versión (v4.2.2 / v5.6.0 /
    v4.6.2) con la versión como comentario; guarda de test impide
    regresiones
- **Herramientas de lint flotantes** (job lint)
  - `pip install ruff pyright bandit` contradecía la política S7 y ya
    rompió el gate de Bandit una vez (salto 1.7→1.9); ahora instala
    `requirements-dev.txt`, única fuente de verdad de versiones

#### Lote D5: deny-list de archivos críticos en SafetyGuard
- **Vulnerabilidad S2 cerrada**: la política de "ficheros sueltos"
  permitía borrar binarios del SO (System32, SysWOW64, Boot, hijos
  directos de C:\Windows) si un winapp2.ini cargable por el usuario lo
  pedía; las reglas de winapp2 son ahora entrada NO CONFIADA para la
  puerta de borrado
- **Deny-list por basename GLOBAL** (~60 entradas): las DLLs núcleo de
  Win32 (ntdll/kernel32/user32/gdi32/...), componentes de kernel y
  arranque (ntoskrnl, hal, win32k, bootmgr, bootmgfw.efi, winload.*),
  procesos vitales (smss/csrss/wininit/winlogon/services/lsass/svchost/
  explorer/dwm), cmd/powershell/regedit/taskmgr, pagefile/swapfile/
  hiberfil y las colmenas de registro por usuario (ntuser.dat,
  usrclass.dat) se rechazan EN CUALQUIER ubicación: una copia de
  kernel32.dll en %TEMP% es sospechosa, no limpiable
- **Árboles binarios del SO protegidos en profundidad**: todo
  descendiente (fichero o carpeta) de System32, SysWOW64 y Boot se
  rechaza, con whitelist explícita SOLO para ficheros en subárboles
  limpiables de verdad (LogFiles, spool\PRINTERS, winevt\Logs); los
  ficheros sueltos directamente bajo C:\Windows también se protegen
- `%SystemRoot%`/`%WINDIR%` resueltos en runtime: instalaciones de
  Windows en unidades distintas de C: quedan cubiertas; comparaciones
  en forma canónica (backslash + minúsculas) para ser inmune a
  mayúsculas y separadores mezclados en reglas hostiles
- Comprobación también sobre el realpath: un junction que resuelva
  dentro de un árbol crítico se rechaza igual que uno que resuelva en
  una carpeta de usuario protegida
- Coste: comprobaciones de cadena puras (sin syscalls) por objetivo de
  borrado; el escaneo no pasa por la deny-list

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
