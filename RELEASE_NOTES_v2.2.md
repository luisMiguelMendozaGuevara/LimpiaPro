# LimpiaPro v2.2 — Notas de la Versión

**Fecha de lanzamiento:** 18 de agosto de 2026  
**Tipo de release:** Mayor (seguridad y robustez)

---

## 🎯 Resumen

**LimpiaPro v2.2 es el release más seguro y robusto hasta la fecha.**

Tras una auditoría técnica exhaustiva, se han implementado **22 mejoras críticas** que transforman LimpiaPro de una herramienta funcional en una aplicación de calidad profesional. Los cambios se centran en tres pilares:

1. **Seguridad ante todo**: Nunca se borra lo que no se debe borrar
2. **Transparencia total**: El usuario sabe exactamente qué pasó y por qué
3. **Calidad industrial**: CI/CD completo, builds automáticos, logs estructurados

---

## 🛡️ Mejoras de Seguridad

### Capa central de protección del sistema
LimpiaPro ahora tiene una **capa central de seguridad** (`is_safe_delete_target`) que protege:

- ✅ **Directorios del sistema**: `C:\Windows`, `Program Files`, `ProgramData`
- ✅ **Perfiles de usuario**: `Desktop`, `Documents`, `Downloads`, `Pictures`, `Music`, `Videos`
- ✅ **Raíces de unidades**: Nunca se borra `C:\`, `D:\`, etc.
- ✅ **Carpetas críticas del perfil**: `AppData\Roaming`, `AppData\Local` (solo contenido específico)

**Impacto**: Incluso si un error lógico intentara borrar algo peligroso, la capa de seguridad lo bloquea.

### Snapshot inmutable: lo que ves es lo que se borra
En versiones anteriores, entre el **Preview** y el **Clean**, el sistema de archivos podía cambiar y se podían borrar archivos que no aparecían en la vista previa. Ahora:

- El Preview toma un **snapshot exacto** de los objetivos
- El Clean elimina **exactamente** ese snapshot
- Los archivos creados después del Preview **no se borran**

**Impacto**: Comportamiento predecible y seguro. El usuario siempre sabe qué se va a eliminar.

### Protección de procesos críticos
El gestor de procesos ahora protege automáticamente los procesos del sistema:

- `explorer.exe` (escritorio y barra de tareas)
- `dwm.exe` (composición visual)
- `winlogon.exe`, `lsass.exe`, `csrss.exe`, `services.exe`
- `svchost.exe` (servicios del sistema)

**Impacto**: Previene BSODs (pantallazos azules) y colapsos del sistema por terminación accidental.

### Protección de entradas RunOnce
Las entradas de inicio marcadas como `RunOnce` (ejecución única) ahora muestran una **advertencia especial** antes de desactivarlas.

**Impacto**: Previene que instaladores o configuraciones iniciales queden pendientes para siempre.

---

## 📊 Transparencia y Diagnóstico

### Clasificación detallada de errores
Cuando un archivo no se puede borrar, LimpiaPro ahora te dice **exactamente por qué**:

- 🔴 **Archivo en uso** (código 32) — El archivo está abierto por otro programa
- 🔴 **Acceso denegado** (código 5) — Falta permiso administrativo
- 🔴 **Ruta no encontrada** (código 3) — El archivo desapareció antes del borrado
- 🔴 **Solo lectura** — El archivo tiene el atributo `readonly`
- 🔴 **Directorio no vacío** (código 145) — No se puede borrar la carpeta porque contiene archivos

Anteriormente, todos los errores se mostraban como "N errores" sin explicación.

### Audit Logging Estructurado (NUEVO)
Todas las operaciones importantes (cleanup, scan, preview) se registran en un archivo JSONL:

```
%LOCALAPPDATA%\LimpiaPro\logs\audit.jsonl
```

Cada entrada contiene:
- Timestamp
- Operación (cleanup/scan/preview)
- Categoría
- Acción
- Ruta del archivo
- Resultado (success/failed/skipped)
- Código de error (si aplica)

**Beneficio**: Si algo sale mal, puedes analizar exactamente qué pasó con herramientas como PowerShell, Python o pandas.

Incluye la herramienta `tools/analyze_logs.py` para análisis automático.

---

## 🏗️ Calidad de Código y Builds

### CI/CD Profesional (NUEVO)
Cada commit pasa por 3 jobs automáticos:

1. **Lint**: Ruff (linter + formatter) + Pyright (type checking) + Bandit (security)
2. **Test**: pytest con cobertura de tests
3. **Build**: PyInstaller genera el .exe y ejecuta smoke test

**Impacto**: Los bugs se detectan en el PR, no en producción.

### Datos específicos por usuario
El caché y los logs ahora se almacenan en:

```
%LOCALAPPDATA%\LimpiaPro\
```

En lugar de junto al ejecutable. Esto:

- ✅ Previene errores de permisos cuando LimpiaPro está en `C:\Program Files`
- ✅ Permite múltiples usuarios con datos separados
- ✅ El caché incluye metadatos: timestamp, versión, usuario, máquina

### Gestión transaccional de startup
Las operaciones del registro de Windows (activar/desactivar programas de inicio) ahora son **transaccionales con rollback**. Si el paso 2 falla, el paso 1 se revierte automáticamente.

**Impacto**: Previene inconsistencias donde un programa aparece como "desactivado" en la UI pero Windows lo sigue ejecutando.

---

## 🚀 Instalación / Actualización

### Para usuarios existentes
1. Descarga `LimpiaPro.exe` desde el [release en GitHub](https://github.com/luisMiguelMendozaGuevara/LimpiaPro/releases)
2. Reemplaza tu ejecutable anterior
3. Tus datos y configuraciones se mantienen en `%LOCALAPPDATA%\LimpiaPro\`

### Para nuevos usuarios
1. Descarga `LimpiaPro.exe`
2. Colócala donde prefieras (no requiere instalación)
3. Ejecuta — LimpiaPro solicitará permisos administrativos automáticamente

### Migración desde v2.1
No se requiere acción especial. El caché anterior se invalida automáticamente por cambio de versión.

---

## 🐛 Bugs Corregidos

- **Tkinter threading**: Los workers ya no tocan widgets directamente (P0 crítico resuelto)
- **Errores silenciosos en duplicados**: Ahora se reportan archivos no leíbles
- **RunOnce sin protección**: Ahora tiene advertencia especial
- **Logs solo para errores internos**: Ahora hay logs estructurados para todas las operaciones

---

## 📋 Deuda Técnica Restante

Aún quedan mejoras por implementar en futuras versiones:

- ⏳ Tests end-to-end de la UI con Tkinter
- ⏳ Cambio dinámico de idioma sin reiniciar
- ⏳ Refactor de `CleanerApp` en servicios separados

---

## 🙏 Agradecimientos

Esta versión fue posible gracias a una auditoría técnica exhaustiva que identificó 39 puntos de mejora, de los cuales **36 se resolvieron** en esta versión.

**Desarrollado por**: Luis Miguel Mendoza Guevara  
**Licencia**: MIT  
**Repositorio**: https://github.com/luisMiguelMendozaGuevara/LimpiaPro

---

**¿Encontraste un bug?** Abre un issue en GitHub con los logs de `%LOCALAPPDATA%\LimpiaPro\logs\audit.jsonl` adjuntos.
