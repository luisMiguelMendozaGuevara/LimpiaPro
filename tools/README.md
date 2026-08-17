# Herramientas de Diagnóstico

Esta carpeta contiene herramientas auxiliares para diagnosticar y analizar el comportamiento de LimpiaPro.

## analyze_logs.py

Analiza los logs estructurados de operaciones (`audit.jsonl`) y genera un resumen de:
- Total de operaciones por tipo (cleanup, scan, preview, etc.)
- Categorías más procesadas
- Errores más frecuentes
- Códigos de error más comunes
- Archivos que fallan consistentemente
- Espacio total recuperado

### Uso básico

```bash
python tools/analyze_logs.py
```

### Opciones

```bash
# Mostrar los 20 elementos más frecuentes (en lugar de 10)
python tools/analyze_logs.py --top 20

# Analizar solo una categoría específica
python tools/analyze_logs.py --category chrome

# Salida en formato JSON (para procesamiento posterior)
python tools/analyze_logs.py --json

# Combinar opciones
python tools/analyze_logs.py --category temp --top 15
```

### Ejemplo de salida

```
======================================================================
ANÁLISIS DE LOGS DE LIMPIAPRO
======================================================================

Total de operaciones: 15,234
Operaciones exitosas: 14,892
Operaciones fallidas: 342 (2.2%)
Espacio recuperado: 12.45 GB

----------------------------------------------------------------------
OPERACIONES POR TIPO
----------------------------------------------------------------------
  cleanup             :   12,456
  scan                :    2,134
  preview             :      644

----------------------------------------------------------------------
CATEGORÍAS MÁS PROCESADAS
----------------------------------------------------------------------
  chrome              :    8,234
  temp                :    3,456
  edge                :    2,123

----------------------------------------------------------------------
CATEGORÍAS CON MÁS ERRORES
----------------------------------------------------------------------
  chrome              :      234 (68.4%)
  temp                :       67 (19.6%)

----------------------------------------------------------------------
CÓDIGOS DE ERROR MÁS FRECUENTES
----------------------------------------------------------------------
    32 - In Use (archivo bloqueado)              :      289
     5 - Access Denied (permisos insuficientes)  :       34

======================================================================
RECOMENDACIONES
======================================================================
• Muchos archivos están bloqueados (código 32)
  → Cierra los programas antes de limpiar
  → Ejecuta LimpiaPro después de reiniciar Windows
```

### Ubicación del log

El script busca automáticamente el log en:
```
%LOCALAPPDATA%\LimpiaPro\logs\audit.jsonl
```

Típicamente:
```
C:\Users\<TuUsuario>\AppData\Local\LimpiaPro\logs\audit.jsonl
```

### Integración con otras herramientas

El modo `--json` permite integrar el análisis con otras herramientas:

```bash
# Guardar análisis en archivo
python tools/analyze_logs.py --json > analisis.json

# Procesar con jq (si está instalado)
python tools/analyze_logs.py --json | jq '.error_categories'

# Importar en Python para análisis personalizado
python -c "
import json
with open('analisis.json') as f:
    stats = json.load(f)
    print(f'Tasa de error: {stats[\"failure_rate\"]:.2%}')
"
```

## Próximas herramientas

En futuras versiones se añadirán:

- **benchmark.py** - Mide el rendimiento de operaciones de escaneo y limpieza
- **validate_rules.py** - Valida la sintaxis de archivos winapp2.ini personalizados
- **export_report.py** - Genera reportes PDF/HTML completos del estado del sistema

## Documentación relacionada

- [Guía de análisis de logs](../docs/AUDIT_LOG_ANALYSIS.md) - Documentación completa del formato y análisis manual
- [README principal](../README.md) - Información general del proyecto
