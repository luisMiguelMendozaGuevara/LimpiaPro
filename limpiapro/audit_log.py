r"""Structured audit logging for operations (P1-16).

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

Architecture Notes:
    - JSONL format: Each line is a complete JSON object, making the file easy
      to parse with standard tools (jq, pandas, grep).
    - Lazy file creation: The log file is created on first use, not at import.
    - Error resilience: Audit logging failures never break the main operation.
    - Singleton pattern: A single `audit` instance is used throughout the app.
"""

import json
import time
from pathlib import Path
from typing import Literal

from .paths import get_logs_dir

# Type definitions for operation and result values.
# These provide static type checking and IDE autocompletion.
Operation = Literal["cleanup", "scan", "preview", "uninstall", "startup", 
                    "duplicates", "tasks", "processes", "update"]
Result = Literal["success", "failed", "skipped"]


class AuditLogger:
    """Structured audit logger for operations.
    
    Writes JSONL records to %LOCALAPPDATA%/LimpiaPro/logs/audit.jsonl
    Each line is a complete JSON object, making the file easy to parse
    and analyze with standard tools (jq, pandas, etc.).
    
    Attributes:
        _log_path (Path | None): Cached path to the audit log file.
    """
    
    def __init__(self):
        """Initialize the AuditLogger with lazy path resolution."""
        self._log_path = None
    
    @property
    def log_path(self) -> Path:
        """Get the path to the audit log file (created on first use).
        
        The log directory is created if it doesn't exist. The file itself
        is created on first write (append mode).
        
        Returns:
            Path: Absolute path to the audit.jsonl file.
        """
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
        r"""Log a single operation.
        
        This is the primary API for recording operations. Each call writes
        one JSONL line to the audit log file.
        
        Args:
            operation (Operation): High-level operation type (cleanup, scan, etc.).
            category (str, optional): Category being processed (chrome, temp, etc.).
                                      Defaults to "".
            action (str, optional): Specific action (delete, hash, detect, etc.).
                                    Defaults to "".
            path (str, optional): Target file/directory path (when applicable).
                                  Defaults to "".
            result (Result, optional): Outcome (success, failed, skipped).
                                       Defaults to "success".
            error_code (int, optional): Windows error code or errno (when failed).
                                        Defaults to 0.
            error_msg (str, optional): Human-readable error description.
                                       Defaults to "".
            details (dict | None, optional): Optional extra context (dict).
                                             Defaults to None.
        
        Example:
            >>> audit.log_operation(
            ...     operation="cleanup",
            ...     category="chrome",
            ...     action="delete",
            ...     path=r"C:\Users\...\Cache\data_0",
            ...     result="failed",
            ...     error_code=32,
            ...     error_msg="The process cannot access the file because it is being used"
            ... )
            
        Notes:
            - Error resilience: If logging fails (disk full, permission denied),
              the exception is silently ignored to prevent breaking the main operation.
            - Thread safety: File writes are not synchronized; concurrent writes
              may interleave, but each line is atomic (single write call).
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
        except Exception:  # nosec B110 - audit logging must not break operations
            # Audit logging must never fail the main operation
            pass
    
    def analyze_errors(self) -> dict:
        """Analyze the audit log to identify error patterns.
        
        Reads the entire audit log and aggregates failure statistics by
        category and error code. Useful for identifying problematic
        categories or recurring error types.
        
        Returns:
            dict: Error statistics with keys:
                - total_operations (int): Total number of logged operations.
                - failures_by_category (dict[str, int]): Count of failures per category.
                - failures_by_error_code (dict[int, int]): Count of failures per error code.
                - most_problematic_categories (list[tuple[str, int]]): Top 10 categories
                  by failure count, sorted descending.
                  
        Notes:
            - Malformed lines: Silently skipped (JSONDecodeError, KeyError).
            - Empty log: Returns {"total_operations": 0}.
            - Performance: Reads the entire file into memory; not suitable for
              very large logs (>100MB).
        """
        if not self.log_path.exists():
            return {"total_operations": 0}
        
        failures_by_category = {}
        failures_by_error_code = {}
        total_ops = 0
        
        try:
            with open(self.log_path, encoding="utf-8") as f:
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
        except Exception:  # nosec B110 - malformed audit lines are ignored
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


# Singleton instance used throughout the application.
# Import as: from .audit_log import audit
audit = AuditLogger()
