#!/usr/bin/env python3
"""Herramienta de análisis de logs estructurados de LimpiaPro.

Este script analiza el archivo audit.jsonl y genera un resumen de:
- Total de operaciones por tipo
- Errores más frecuentes por categoría
- Códigos de error más comunes
- Archivos que fallan consistentemente

Uso:
    python analyze_logs.py [--top N] [--category CATEGORIA]

Ejemplos:
    python analyze_logs.py
    python analyze_logs.py --top 20
    python analyze_logs.py --category chrome
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def get_log_path() -> Path:
    """Obtiene la ruta del log de auditoría."""
    import os
    
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        print("Error: No se pudo determinar LOCALAPPDATA", file=sys.stderr)
        sys.exit(1)
    
    return Path(local_app_data) / "LimpiaPro" / "logs" / "audit.jsonl"


def load_records(log_path: Path) -> list[dict]:
    """Carga todos los registros del log JSONL."""
    if not log_path.exists():
        print(f"Error: El archivo de log no existe: {log_path}", file=sys.stderr)
        print("Ejecuta LimpiaPro al menos una vez para generar el log.", file=sys.stderr)
        sys.exit(1)
    
    records = []
    try:
        with open(log_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Advertencia: Línea {line_num} malformada: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error al leer el log: {e}", file=sys.stderr)
        sys.exit(1)
    
    return records


def analyze_records(records: list[dict], top_n: int = 10, category_filter: str | None = None) -> dict:
    """Analiza los registros y devuelve estadísticas."""
    # Filtrar por categoría si se especificó
    if category_filter:
        records = [r for r in records if r.get("category") == category_filter]
    
    if not records:
        return {
            "total": 0,
            "message": "No hay registros para analizar" + (f" en la categoría '{category_filter}'" if category_filter else "")
        }
    
    # Contadores
    operations = Counter(r.get("operation", "unknown") for r in records)
    categories = Counter(r.get("category", "unknown") for r in records)
    results = Counter(r.get("result", "unknown") for r in records)
    
    failures = [r for r in records if r.get("result") == "failed"]
    
    # Análisis de errores
    error_categories = Counter(r.get("category", "unknown") for r in failures)
    error_codes = Counter(r.get("error_code", 0) for r in failures)
    error_messages = Counter(r.get("error_msg", "")[:100] for r in failures)
    error_paths = Counter(r.get("path", "") for r in failures)
    
    # Calcular espacio recuperado
    total_freed = 0
    for r in records:
        if r.get("result") == "success" and r.get("operation") == "cleanup":
            details = r.get("details", {})
            total_freed += details.get("freed_bytes", 0)
    
    return {
        "total": len(records),
        "operations": dict(operations.most_common()),
        "categories": dict(categories.most_common()),
        "results": dict(results),
        "failures_total": len(failures),
        "failure_rate": len(failures) / len(records) if records else 0,
        "error_categories": dict(error_categories.most_common(top_n)),
        "error_codes": dict(error_codes.most_common(top_n)),
        "error_messages": dict(error_messages.most_common(top_n)),
        "error_paths": dict(error_paths.most_common(top_n)),
        "total_freed_bytes": total_freed,
        "total_freed_gb": total_freed / (1024 ** 3),
    }


def print_report(stats: dict) -> None:
    """Imprime el reporte de análisis."""
    if "message" in stats:
        print(stats["message"])
        return
    
    print("=" * 70)
    print("ANÁLISIS DE LOGS DE LIMPIAPRO")
    print("=" * 70)
    print()
    
    print(f"Total de operaciones: {stats['total']:,}")
    print(f"Operaciones exitosas: {stats['results'].get('success', 0):,}")
    print(f"Operaciones fallidas: {stats['failures_total']:,} ({stats['failure_rate']:.1%})")
    print(f"Espacio recuperado: {stats['total_freed_gb']:.2f} GB")
    print()
    
    print("-" * 70)
    print("OPERACIONES POR TIPO")
    print("-" * 70)
    for op, count in stats["operations"].items():
        print(f"  {op:20s}: {count:>8,}")
    print()
    
    print("-" * 70)
    print("CATEGORÍAS MÁS PROCESADAS")
    print("-" * 70)
    for cat, count in stats["categories"].items():
        print(f"  {cat:20s}: {count:>8,}")
    print()
    
    if stats["failures_total"] > 0:
        print("-" * 70)
        print("CATEGORÍAS CON MÁS ERRORES")
        print("-" * 70)
        for cat, count in stats["error_categories"].items():
            pct = count / stats["failures_total"] * 100
            print(f"  {cat:20s}: {count:>8,} ({pct:.1f}%)")
        print()
        
        print("-" * 70)
        print("CÓDIGOS DE ERROR MÁS FRECUENTES")
        print("-" * 70)
        error_types = {
            5: "Access Denied (permisos insuficientes)",
            32: "In Use (archivo bloqueado)",
            2: "Not Found (archivo no encontrado)",
            3: "Path Not Found (ruta no encontrada)",
            145: "Dir Not Empty (directorio no vacío)",
        }
        for code, count in stats["error_codes"].items():
            desc = error_types.get(code, "Otro error")
            print(f"  {code:5d} - {desc:40s}: {count:>8,}")
        print()
        
        print("-" * 70)
        print("ARCHIVOS QUE FALLAN FRECUENTEMENTE")
        print("-" * 70)
        for path, count in stats["error_paths"].items():
            # Truncar rutas largas
            display_path = path if len(path) <= 60 else "..." + path[-57:]
            print(f"  {count:>3}x: {display_path}")
        print()
    
    print("=" * 70)
    print("RECOMENDACIONES")
    print("=" * 70)
    
    if stats["failures_total"] == 0:
        print("✓ No hay errores registrados. ¡Excelente!")
    else:
        top_error_code = max(stats["error_codes"].items(), key=lambda x: x[1], default=(0, 0))[0]
        
        if top_error_code == 32:
            print("• Muchos archivos están bloqueados (código 32)")
            print("  → Cierra los programas antes de limpiar")
            print("  → Ejecuta LimpiaPro después de reiniciar Windows")
        elif top_error_code == 5:
            print("• Muchos errores de permisos (código 5)")
            print("  → Asegúrate de ejecutar LimpiaPro como administrador")
        else:
            print("• Revisa los archivos que fallan frecuentemente")
            print("  → Pueden estar bloqueados por otros procesos")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Analiza los logs estructurados de LimpiaPro"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Número de elementos a mostrar en rankings (default: 10)"
    )
    parser.add_argument(
        "--category",
        type=str,
        help="Filtrar por categoría específica (ej: chrome, temp)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Salida en formato JSON en lugar de texto"
    )
    
    args = parser.parse_args()
    
    log_path = get_log_path()
    records = load_records(log_path)
    stats = analyze_records(records, top_n=args.top, category_filter=args.category)
    
    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        print_report(stats)


if __name__ == "__main__":
    main()
