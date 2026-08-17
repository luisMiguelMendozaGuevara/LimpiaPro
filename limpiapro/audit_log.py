"""Structured audit logging for operations (P1-16).

This module provides a JSONL-based audit log for all significant operations
(cleanup, scan, preview, uninstall, etc.) that complements the user-facing
visual log. The structured log enables:
  - Filtering by operation type (cleanup, scan, preview)
  - Grouping by category (chrome, windows_update, etc.)
  - Identifying error patterns (which categories fail most often)
  - Exporting to external monitoring systems

Each record is a JSON object with:
  - ts: ISO timestamp
  - operation: "cleanup" | "scan" | "preview" | "uninstall" | "startup" | ...
  - category: "chrome" | "temp" | "windows_update" | ...
  - action: "delete" | "hash" | "detect" | ...
  - path: target path (when applicable)
  - result: "success" | "failed" | "skipped"
  - error_code: winerror or errno (when result is "failed")
  - error_msg: human-readable error description
  - details: optional dict with extra context

Usage:
    from .audit_log import audit
    
    audit.log_operation(
        operation="cleanup",
        category="chrome",
        action="delete",
        path=r"C:\Users\...\Cache\data_0",
        result="success"
    )
"""

import json
import os
import time
from pathlib import Path
from typing import Literal

from .paths import get_logs_dir


Operation = Literal["cleanup", "scan", "preview", "uninstall", "startup", 
                    "duplicates", "tasks", "processes", "update"]
Result = Literal["success", "failed", "skipped"]


class AuditLogger:
    """Structured audit logger for operations.
    
    Writes JSONL records to %LOCALAPPDATA%/LimpiaPro/logs/audit.jsonl
    Each line is a complete JSON object, making the file easy to parse
    and analyze with standard tools (jq, pandas, etc.)."""
    
    def __init__(self):
        self._log_path = None
    
    @property
    def log_path(self) -> Path:
        """Path to the audit log file (created on first use)."""
        if self._log_path is None:
            logs_dir = Path(get_logs_dir())
            logs_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = logs_dir / "audit.jsonl"
        return self._log_path
    
    def log_operation(
        self,
        operation: Operation,
        category: str = "",
        action: str = "",
        path: str = "",
        result: Result = "success",
        error_code: int = 0,
        error_msg: str = "",
        details: dict | None = None
    ) -> None:
        """Log a single operation.
        
        Args:
            operation: High-level operation type (cleanup, scan, etc.)
            category: Category being processed (chrome, temp, etc.)
            action: Specific action (delete, hash, detect, etc.)
            path: Target file/directory path (when applicable)
            result: Outcome (success, failed, skipped)
            error_code: Windows error code or errno (when failed)
            error_msg: Human-readable error description
            details: Optional extra context (dict)
        
        Example:
            audit.log_operation(
                operation="cleanup",
                category="chrome",
                action="delete",
                path=r"C:\Users\...\Cache\data_0",
                result="failed",
                error_code=32,
                error_msg="The process cannot access the file because it is being used"
            )
        """
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "operation": operation,
            "category": category,
            "action": action,
            "path": path,
            "result": result,
            "error_code": error_code,
            "error_msg": error_msg,
        }
        if details:
            record["details"] = details
        
        line = json.dumps(record, ensure_ascii=False)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            # Audit logging must never fail the main operation
            pass
    
    def analyze_errors(self) -> dict:
        """Analyze the audit log to identify error patterns.
        
        Returns:
            Dict with error statistics:
            {
                "total_operations": int,
                "failures_by_category": {category: count},
                "failures_by_error_code": {code: count},
                "most_problematic_categories": [(category, count), ...]
            }
        """
        if not self.log_path.exists():
            return {"total_operations": 0}
        
        failures_by_category = {}
        failures_by_error_code = {}
        total_ops = 0
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        total_ops += 1
                        if record.get("result") == "failed":
                            cat = record.get("category", "unknown")
                            code = record.get("error_code", 0)
                            
                            failures_by_category[cat] = failures_by_category.get(cat, 0) + 1
                            failures_by_error_code[code] = failures_by_error_code.get(code, 0) + 1
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            pass
        
        # Sort by frequency
        most_problematic = sorted(
            failures_by_category.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            "total_operations": total_ops,
            "failures_by_category": failures_by_category,
            "failures_by_error_code": failures_by_error_code,
            "most_problematic_categories": most_problematic[:10],
        }


# Singleton instance
audit = AuditLogger()
