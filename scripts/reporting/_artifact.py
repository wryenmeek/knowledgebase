"""Report artifact validation and IO helpers for scripts/reporting/.

These symbols were extracted from scripts/_optional_surface_common.py (ADR-011)
because they are used exclusively by the reporting subpackage. Every module that
imported run_surface_cli was previously also pulling in reporting-domain logic as
an unintentional side effect; this module breaks that coupling.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.kb import write_utils

__all__ = [
    "REPORT_ARTIFACT_WRITE_ROOT",
    "validate_report_artifact",
    "write_report_artifact",
]

REPORT_ARTIFACT_WRITE_ROOT = "wiki/reports"
_MAX_REPORT_COLLISIONS = 99

_REPORT_TYPE_FINDINGS_KEYS: dict[str, tuple[str, ...]] = {
    "content-quality": (
        "path",
        "missing_sources",
        "missing_updated_at",
        "placeholder_count",
    ),
    "quality-scores": (
        "path",
        "priority_score",
        "confidence",
        "missing_sources",
        "missing_updated_at",
        "placeholder_count",
        "missed_query_count",
        "missed_query_demand",
        "recommended_next_step",
    ),
    "quality-report": (
        "path",
        "priority_score",
        "confidence",
        "missing_sources",
        "missing_updated_at",
        "placeholder_count",
        "missed_query_count",
        "missed_query_demand",
        "recommended_next_step",
    ),
    "coverage-report": ("path", "namespace", "is_placeholder", "is_stale"),
}

_REPORT_TYPE_SUMMARY_KEYS: dict[str, tuple[str, ...]] = {
    "content-quality": (
        "selected_count",
        "missing_sources_count",
        "missing_updated_at_count",
        "placeholder_file_count",
    ),
    "quality-scores": (
        "selected_count",
        "prioritized_count",
        "query_evidence_count",
        "recommendation_only",
        "scoring_mode",
    ),
    "quality-report": (
        "selected_count",
        "prioritized_count",
        "query_evidence_count",
        "recommendation_only",
        "scoring_mode",
    ),
    "coverage-report": (
        "total_pages",
        "total_placeholders",
        "total_stale",
        "coverage_ratio",
        "pages_by_namespace",
        "placeholder_pages_by_namespace",
        "stale_pages_by_namespace",
        "empty_namespaces",
    ),
}

_REPORT_ENVELOPE_REQUIRED = (
    "report_type",
    "generated_at",
    "scope",
    "surface",
    "findings",
    "summary",
)


def validate_report_artifact(artifact: dict, report_type: str) -> None:
    """Raise ``ValueError`` if ``artifact`` fails the report-artifact-contract schema.

    Checks the common envelope, type-specific findings fields, and summary fields.
    """
    for key in _REPORT_ENVELOPE_REQUIRED:
        if key not in artifact:
            raise ValueError(f"report artifact missing required field: {key}")
    if artifact["report_type"] != report_type:
        raise ValueError(
            f"artifact report_type '{artifact['report_type']}' does not match expected '{report_type}'"
        )
    if report_type not in _REPORT_TYPE_FINDINGS_KEYS:
        raise ValueError(f"unknown report_type: {report_type}")
    findings = artifact["findings"]
    if not isinstance(findings, list):
        raise ValueError("report artifact 'findings' must be an array")
    required_finding_keys = _REPORT_TYPE_FINDINGS_KEYS[report_type]
    for idx, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ValueError(f"findings item {idx} must be an object")
        for key in required_finding_keys:
            if key not in item:
                raise ValueError(f"findings item {idx} missing required field: {key}")
    summary = artifact["summary"]
    if not isinstance(summary, dict):
        raise ValueError("report artifact 'summary' must be an object")
    for key in _REPORT_TYPE_SUMMARY_KEYS[report_type]:
        if key not in summary:
            raise ValueError(f"report artifact summary missing required field: {key}")


def write_report_artifact(repo_root: Path, report_type: str, artifact: dict) -> Path:
    """Write a governed report artifact to ``wiki/reports/`` under the write lock.

    Validates ``artifact`` against ``schema/report-artifact-contract.md``, acquires
    ``wiki/.kb_write.lock``, allocates a non-colliding timestamped filename *inside*
    the lock window, and writes the artifact.

    Returns the absolute path written.
    Raises ``ValueError`` on schema validation failure or if ``report_type`` contains
    path-separator characters.
    Raises ``LockUnavailableError`` if the lock cannot be acquired.
    Raises ``OSError`` on write failure or if the constructed path escapes ``wiki/reports/``.
    """
    validate_report_artifact(artifact, report_type)
    # Sanitize report_type: prevent path traversal via filename construction.
    if any(sep in report_type for sep in ("..", "/", "\\")):
        raise ValueError(
            f"report_type must not contain path separators or '..': {report_type!r}"
        )
    reports_dir = repo_root / REPORT_ARTIFACT_WRITE_ROOT
    content = json.dumps(artifact, indent=2, ensure_ascii=False) + "\n"
    with write_utils.exclusive_write_lock(repo_root):
        reports_dir.mkdir(parents=True, exist_ok=True)
        # Filename allocation must be inside the lock to prevent concurrent collision.
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_path = reports_dir / f"{report_type}-{date_str}.json"
        if output_path.exists():
            counter = 2
            while counter <= _MAX_REPORT_COLLISIONS + 1:
                output_path = reports_dir / f"{report_type}-{date_str}-{counter}.json"
                if not output_path.exists():
                    break
                counter += 1
            else:
                raise OSError(
                    f"too many {report_type} report files for {date_str}; "
                    f"manual cleanup required under {REPORT_ARTIFACT_WRITE_ROOT}"
                )
        # Defense-in-depth: verify the constructed path stays inside wiki/reports/.
        if not output_path.resolve().is_relative_to(reports_dir.resolve()):
            raise OSError(
                f"report artifact path escapes {REPORT_ARTIFACT_WRITE_ROOT}: {output_path}"
            )
        write_utils.write_text_capturing_previous_safe(output_path, content)
    return output_path
