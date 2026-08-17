# Changelog

Todos los cambios notables de este proyecto se documentarán en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

*Sin cambios pendientes.*

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
