# Guía de Migración

Este documento explica los cambios importantes en LimpiaPro y cómo afectan a usuarios y desarrolladores.

## Migración desde v1.0.0 a v1.1.0 (Actual)

### Cambios en almacenamiento de datos

#### Antes (v1.0.0)
```
LimpiaPro/
├── LimpiaPro.exe
├── limpiador_cache.json      ← Cache junto al ejecutable
├── limpiapro_error.log       ← Log junto al ejecutable
└── winapp2.ini
```

**Problemas**:
- ❌ Fallos de permisos si se instala en `C:\Program Files\`
- ❌ Cache compartido entre múltiples usuarios
- ❌ Cache sin metadatos (no sabe cuándo se generó)

#### Ahora (v1.1.0)
```
C:\Users\<Usuario>\AppData\Local\LimpiaPro\
├── limpiador_cache.json      ← Cache por usuario
└── logs\
    ├── limpiapro_error.log   ← Log de errores
    └── audit.jsonl           ← Nuevo: log estructurado
```

**Ventajas**:
- ✅ Sin problemas de permisos
- ✅ Cache específico por usuario
- ✅ Cache con metadatos (timestamp, versión, usuario)

#### Acción requerida

**Ninguna**. LimpiaPro detecta automáticamente si existe un cache antiguo y lo ignora si:
- No tiene el schema correcto
- Fue generado por otra versión
- Fue generado por otro usuario

El cache antiguo junto al ejecutable puede eliminarse manualmente si se desea.

### Cambios en logs

#### Antes (v1.0.0)
```
[14:32:10] Limpiando Chrome...
[14:32:11] Eliminados 42 archivos
[14:32:12] Error al eliminar data_0
```

**Problemas**:
- ❌ No estructurado (difícil de analizar)
- ❌ Solo errores, no operaciones exitosas
- ❌ Imposible filtrar por categoría o tipo de error

#### Ahora (v1.1.0)
```json
{"ts":"2026-01-15T14:32:10","operation":"cleanup","category":"chrome","action":"delete","path":"C:\\...\\data_0","result":"success","error_code":0,"error_msg":"","details":{"freed_bytes":1048576}}
{"ts":"2026-01-15T14:32:11","operation":"cleanup","category":"chrome","action":"delete","path":"C:\\...\\data_1","result":"failed","error_code":32,"error_msg":"[WinError 32] El proceso no tiene acceso...","details":{"operation":"remove","kind":"in_use"}}
```

**Ventajas**:
- ✅ Estructurado (JSONL - una línea por registro)
- ✅ Registra todas las operaciones (éxitos y fallos)
- ✅ Filtrable por operación, categoría, código de error
- ✅ Analizable con herramientas estándar (jq, pandas, PowerShell)

#### Cómo analizar los logs

**Opción 1: Herramienta automática**
```bash
python tools/analyze_logs.py
```

**Opción 2: PowerShell**
```powershell
Get-Content "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl" | 
  ForEach-Object { $_ | ConvertFrom-Json } | 
  Where-Object { $_.result -eq "failed" } |
  Select-Object -First 10
```

**Opción 3: Python**
```python
import json
with open(r"C:\Users\...\AppData\Local\LimpiaPro\logs\audit.jsonl") as f:
    for line in f:
        record = json.loads(line)
        if record["result"] == "failed":
            print(f"{record['category']}: {record['error_msg']}")
```

Ver [Guía de análisis de logs](docs/AUDIT_LOG_ANALYSIS.md) para más detalles.

### Cambios en gestión de startup

#### Antes (v1.0.0)
- ❌ Operaciones no transaccionales
- ❌ Si fallaba el paso 2, el paso 1 ya estaba aplicado
- ❌ Posibles entradas duplicadas en Run/RunDisabled
- ❌ RunOnce tratado igual que Run

#### Ahora (v1.1.0)
- ✅ Operaciones transaccionales con rollback
- ✅ Si falla el paso 2, el paso 1 se revierte
- ✅ Imposible dejar entradas duplicadas
- ✅ RunOnce muestra advertencia especial antes de desactivar

#### Acción requerida

**Ninguna**. La mejora es transparente para el usuario.

### Cambios en seguridad

#### Antes (v1.0.0)
- ❌ Sin capa central de seguridad
- ❌ Cada categoría responsable de validar sus rutas
- ❌ Posible eliminación accidental de directorios protegidos
- ❌ Procesos críticos podían terminarse

#### Ahora (v1.1.0)
- ✅ Capa central `is_safe_delete_target()`
- ✅ Protege: Windows, Program Files, perfiles de usuario, raíces de unidades
- ✅ Todas las operaciones destructivas pasan por validación
- ✅ Procesos críticos (explorer.exe, dwm.exe, etc.) no pueden terminarse

#### Acción requerida

**Ninguna**. La mejora es transparente para el usuario.

Si intentas eliminar una ruta protegida, verás un error en el log:
```
Error: refused by delete safety policy
```

### Cambios en CI/CD

#### Antes (v1.0.0)
```yaml
jobs:
  test:
    - pytest
```

**Problemas**:
- ❌ Solo tests, sin linting
- ❌ Sin type checking
- ❌ Sin security scanning
- ❌ Sin build automatizado
- ❌ Sin smoke test del .exe

#### Ahora (v1.1.0)
```yaml
jobs:
  lint:
    - ruff check
    - ruff format --check
    - pyright
    - bandit
  
  test:
    needs: lint
    - pytest
  
  build:
    needs: test
    - pyinstaller
    - smoke test
```

**Ventajas**:
- ✅ Linting automático (Ruff)
- ✅ Type checking (Pyright)
- ✅ Security scanning (Bandit)
- ✅ Build automatizado del .exe
- ✅ Smoke test del .exe (verifica que arranca)
- ✅ Artifacts del .exe disponibles por 7 días

#### Acción requerida para desarrolladores

Si haces un PR, asegúrate de que pase el CI:

```bash
# Localmente antes de hacer push
ruff check limpiapro/ tests/
ruff format --check limpiapro/ tests/
pyright limpiapro/
bandit -r limpiapro/ -c pyproject.toml
python -m pytest tests/ -v
```

## Migración de código personalizado

### Si tienes reglas winapp2.ini personalizadas

**Sin cambios requeridos**. El parser de winapp2.ini no cambió.

### Si tienes código que llama a funciones internas

#### `_delete_measured()`

**Antes**:
```python
ok, freed = _delete_measured(path)
```

**Ahora**:
```python
ok, freed, errors = _delete_measured(path)
# errors es una lista de DeleteError con detalles
```

#### `_delete_path()`

**Sin cambios**. Sigue devolviendo `bool`.

#### `is_safe_delete_target()`

**Nueva función**. Úsala antes de cualquier operación destructiva:

```python
from limpiapro.utils import is_safe_delete_target

if is_safe_delete_target(path):
    # Seguro eliminar
    os.remove(path)
else:
    # Ruta protegida, no eliminar
    print(f"Ruta protegida: {path}")
```

### Si tienes tests personalizados

#### Tests de categorías

**Antes**:
```python
def test_cleanup():
    cat = CleanCategory(...)
    removed, errors, freed = cat.clean()
    assert errors == 0
```

**Ahora**:
```python
def test_cleanup():
    cat = CleanCategory(...)
    removed, errors, freed = cat.clean()
    assert errors == 0
    
    # Nuevo: puedes inspeccionar errores detallados
    if cat.delete_errors:
        for err in cat.delete_errors:
            print(f"{err.path}: {err.kind} - {err.message}")
```

## Problemas conocidos y workarounds

### Cache antiguo no se migra automáticamente

**Síntoma**: Después de actualizar, el análisis muestra 0 bytes en todas las categorías.

**Causa**: El cache antiguo junto al ejecutable se ignora (comportamiento correcto).

**Solución**: 
1. Ejecutar un análisis completo (toma unos minutos)
2. El nuevo cache se guarda automáticamente en `%LOCALAPPDATA%/LimpiaPro/`

### Logs antiguos no se migran

**Síntoma**: El archivo `limpiapro_error.log` antiguo sigue junto al ejecutable.

**Solución**: 
- Puede eliminarse manualmente
- Los nuevos logs se escriben en `%LOCALAPPDATA%/LimpiaPro/logs/`

### CI falla en PRs antiguos

**Síntoma**: PRs creados antes de v1.1.0 fallan el CI.

**Causa**: El CI ahora incluye linting y type checking que pueden fallar en código antiguo.

**Solución**:
```bash
# Actualizar el PR localmente
git checkout tu-rama
git rebase main

# Arreglar problemas de linting
ruff check limpiapro/ tests/ --fix
ruff format limpiapro/ tests/

# Commit y push
git commit -am "fix: apply linting fixes"
git push --force-with-lease
```

## Soporte

Si encuentras problemas durante la migración:

1. **Revisa el log de errores**: `%LOCALAPPDATA%/LimpiaPro/logs/limpiapro_error.log`
2. **Revisa el audit log**: `%LOCALAPPDATA%/LimpiaPro/logs/audit.jsonl`
3. **Analiza con la herramienta**: `python tools/analyze_logs.py`
4. **Abre un issue en GitHub** con:
   - Versión anterior de LimpiaPro
   - Versión nueva de LimpiaPro
   - Logs adjuntos
   - Pasos para reproducir el problema

---

**Última actualización**: 2026-01-15  
**Versión actual**: 1.1.0
