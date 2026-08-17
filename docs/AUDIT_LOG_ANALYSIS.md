# Guía de Análisis de Logs Estructurados

LimpiaPro registra todas las operaciones importantes en un archivo JSONL estructurado para facilitar el diagnóstico de problemas y el análisis de patrones de error.

## Ubicación del log

```
%LOCALAPPDATA%\LimpiaPro\logs\audit.jsonl
```

Típicamente:
```
C:\Users\<TuUsuario>\AppData\Local\LimpiaPro\logs\audit.jsonl
```

## Formato del log

Cada línea es un objeto JSON independiente (JSONL - JSON Lines):

```json
{"ts": "2026-01-15T14:32:10", "operation": "cleanup", "category": "chrome", "action": "delete", "path": "C:\\Users\\asus\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache\\data_0", "result": "success", "error_code": 0, "error_msg": "", "details": {"freed_bytes": 1048576}}
{"ts": "2026-01-15T14:32:11", "operation": "cleanup", "category": "chrome", "action": "delete", "path": "C:\\Users\\asus\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache\\data_1", "result": "failed", "error_code": 32, "error_msg": "[WinError 32] El proceso no tiene acceso al archivo porque está siendo utilizado en otro proceso", "details": {"operation": "remove", "kind": "in_use"}}
```

## Campos disponibles

| Campo | Descripción |
|-------|-------------|
| `ts` | Timestamp ISO (YYYY-MM-DDTHH:MM:SS) |
| `operation` | Tipo de operación: `cleanup`, `scan`, `preview`, `uninstall`, `startup`, `duplicates`, `tasks`, `processes`, `update` |
| `category` | Categoría procesada: `chrome`, `temp`, `windows_update`, etc. |
| `action` | Acción específica: `delete`, `hash`, `detect`, `start`, `complete` |
| `path` | Ruta del archivo/directorio afectado |
| `result` | Resultado: `success`, `failed`, `skipped` |
| `error_code` | Código de error Windows (winerror) o errno |
| `error_msg` | Mensaje de error legible |
| `details` | Contexto adicional (dict opcional) |

## Códigos de error comunes

| Código | Tipo | Descripción |
|--------|------|-------------|
| 5 | `access_denied` | Acceso denegado (permisos insuficientes) |
| 32 | `in_use` | Archivo en uso por otro proceso |
| 2 | `not_found` | Archivo no encontrado |
| 3 | `not_found` | Ruta no encontrada |
| 145 | `dir_not_empty` | Directorio no vacío |

## Análisis con herramientas de línea de comandos

### Contar operaciones por categoría

```bash
# En PowerShell
Get-Content "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl" | 
  ForEach-Object { $_ | ConvertFrom-Json } | 
  Group-Object category | 
  Sort-Object Count -Descending |
  Format-Table Name, Count
```

### Encontrar errores más frecuentes

```bash
# En PowerShell
Get-Content "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl" | 
  ForEach-Object { $_ | ConvertFrom-Json } | 
  Where-Object { $_.result -eq "failed" } | 
  Group-Object error_code | 
  Sort-Object Count -Descending |
  Select-Object -First 10
```

### Filtrar por categoría específica

```bash
# Mostrar solo errores de Chrome
Get-Content "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl" | 
  ForEach-Object { $_ | ConvertFrom-Json } | 
  Where-Object { $_.category -eq "chrome" -and $_.result -eq "failed" } |
  Select-Object ts, path, error_msg |
  Format-List
```

## Análisis con Python

```python
import json
from pathlib import Path
from collections import Counter

log_path = Path.home() / "AppData" / "Local" / "LimpiaPro" / "logs" / "audit.jsonl"

# Cargar todos los registros
records = []
with open(log_path, encoding="utf-8") as f:
    for line in f:
        records.append(json.loads(line))

# Análisis de errores por categoría
error_counts = Counter(
    r["category"] for r in records if r["result"] == "failed"
)

print("Errores por categoría:")
for cat, count in error_counts.most_common(10):
    print(f"  {cat}: {count}")

# Análisis de códigos de error
error_codes = Counter(
    r["error_code"] for r in records if r["result"] == "failed"
)

print("\nCódigos de error más frecuentes:")
for code, count in error_codes.most_common(5):
    print(f"  {code}: {count} veces")
```

## Análisis con pandas

```python
import pandas as pd

# Cargar el log
df = pd.read_json(log_path, lines=True)

# Filtrar solo operaciones fallidas
failures = df[df["result"] == "failed"]

# Agrupar por categoría y código de error
summary = failures.groupby(["category", "error_code"]).size().reset_index(name="count")
summary = summary.sort_values("count", ascending=False)

print(summary.head(20))

# Visualizar errores por categoría
failures["category"].value_counts().plot(kind="bar")
```

## Ejemplos de consultas útiles

### ¿Qué categorías fallan más?

```python
failures_by_cat = failures["category"].value_counts()
print(failures_by_cat)
```

### ¿Cuántos archivos se eliminaron exitosamente?

```python
success_count = len(df[df["result"] == "success"])
print(f"Total eliminados: {success_count}")
```

### ¿Qué archivos están siempre bloqueados?

```python
# Archivos que fallaron más de 3 veces
frequent_failures = (
    failures["path"]
    .value_counts()
    .where(lambda x: x > 3)
    .dropna()
)
print(frequent_failures)
```

### Resumen de espacio recuperado

```python
# Solo para operaciones de cleanup exitosas
cleanup_success = df[
    (df["operation"] == "cleanup") & 
    (df["result"] == "success")
]

total_freed = sum(
    r.get("details", {}).get("freed_bytes", 0) 
    for _, r in cleanup_success.iterrows()
)

print(f"Espacio total recuperado: {total_freed / (1024**3):.2f} GB")
```

## Interpretación de patrones

### Patrón: Muchos errores `in_use` (código 32)

**Causa**: Archivos bloqueados por procesos activos (navegadores, aplicaciones)

**Solución**: 
- Cerrar los programas antes de limpiar
- Ejecutar LimpiaPro después de reiniciar Windows
- Usar la opción de "Limpiar al iniciar Windows" (futuro)

### Patrón: Muchos errores `access_denied` (código 5)

**Causa**: Permisos insuficientes

**Solución**:
- Asegurarse de que LimpiaPro se ejecutó como administrador
- Verificar que el usuario tiene permisos sobre las carpetas

### Patrón: Categoría específica falla consistentemente

**Causa**: Configuración incorrecta de la categoría o reglas winapp2 desactualizadas

**Solución**:
- Revisar las rutas en `categories.py`
- Actualizar `winapp2.ini` desde el repositorio oficial
- Reportar el problema en GitHub con el log adjunto

## Rotación de logs

Actualmente el log no tiene rotación automática. Si el archivo crece mucho:

```python
# Truncar el log (PowerShell)
Clear-Content "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl"

# O eliminarlo
Remove-Item "$env:LOCALAPPDATA\LimpiaPro\logs\audit.jsonl"
```

En futuras versiones se implementará rotación automática con retención configurable.

## Reportar problemas

Al abrir un issue en GitHub, incluye:
1. El archivo `audit.jsonl` (últimas 1000 líneas)
2. El archivo `limpiapro_error.log` si existe
3. Descripción de los pasos para reproducir el problema

Esto permite a los desarrolladores diagnosticar el problema rápidamente.
