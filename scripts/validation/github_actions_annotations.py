"""Helpers for safely emitting GitHub Actions workflow annotations.

Workflow-command properties also escape ``:`` and ``,`` because they delimit
annotation properties; message data only escapes percent signs and line breaks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["escape_message", "escape_property", "load_report_entries"]


def escape_property(value: str) -> str:
    """Escape a workflow-command property value."""
    return (
        value.replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def escape_message(value: str) -> str:
    """Escape a workflow-command message value."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def load_report_entries(path: str | Path, key: str) -> tuple[dict[str, Any], ...]:
    """Load validated mapping entries from a workflow report."""
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"report missing or malformed: {exc}") from exc
    if not isinstance(report, dict) or not isinstance(report.get(key), list):
        raise ValueError(f"report must contain a {key} array")
    return tuple(entry for entry in report[key] if isinstance(entry, dict))
