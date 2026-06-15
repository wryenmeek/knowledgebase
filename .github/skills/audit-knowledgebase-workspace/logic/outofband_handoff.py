"""Read-only OutOfBand handoff routing for audit-workspace findings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any


AUDIT_SKILL_NAME = "audit-knowledgebase-workspace"
AUDIT_SKILL_DIR = f".github/skills/{AUDIT_SKILL_NAME}"
OUT_OF_BAND_TARGET_PERSONA = "framework-engineer"
HANDOFF_RECORD_FIELDS: tuple[str, ...] = (
    "finding_id",
    "source_file",
    "source_section",
    "suggested_artifact_path",
    "rationale",
    "target_persona",
)
SUPPORTED_FINDING_CATEGORIES: frozenset[str] = frozenset(
    {
        "Delete",
        "Locality 0",
        "Locality 1",
        "Locality 2",
        "Locality 3a",
        "Locality 3b",
        "Locality 3c",
        "Locality 3d",
        "Locality 3e",
        "Locality 4",
    }
)
OUT_OF_BAND_TARGETS_BY_SCOPE: dict[str, str] = {
    "other_skill": OUT_OF_BAND_TARGET_PERSONA,
    "agent": OUT_OF_BAND_TARGET_PERSONA,
    "prompt": OUT_OF_BAND_TARGET_PERSONA,
}
_REQUIRED_FINDING_FIELDS = (
    "source_file",
    "source_section",
    "proposed_destination",
    "suggested_artifact_path",
    "rationale",
)


class OutOfBandRoutingError(ValueError):
    """Raised when a finding cannot be routed safely."""


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Findings separated into self-owned work and OutOfBand handoff records."""

    eligible_findings: tuple[dict[str, Any], ...]
    out_of_band_handoffs: tuple[dict[str, str], ...]


def route_findings(
    findings: Sequence[Mapping[str, Any]],
    *,
    repo_root: str | Path = ".",
) -> RoutingResult:
    """Route cross-skill findings to deterministic framework-engineer handoffs."""

    repo_root_path = Path(repo_root).resolve()
    eligible_findings: list[dict[str, Any]] = []
    out_of_band_handoffs: list[dict[str, str]] = []

    for finding in findings:
        normalized = _normalize_finding(finding, repo_root_path=repo_root_path)
        route_scope = _route_scope(normalized["suggested_artifact_path"])
        if route_scope is None:
            eligible_findings.append(normalized)
            continue

        target_persona = OUT_OF_BAND_TARGETS_BY_SCOPE.get(route_scope)
        if target_persona is None:
            raise OutOfBandRoutingError(f"unsupported OutOfBand route scope: {route_scope}")
        out_of_band_handoffs.append(
            _handoff_record(
                normalized,
                target_persona=target_persona,
            )
        )

    return RoutingResult(
        eligible_findings=tuple(eligible_findings),
        out_of_band_handoffs=tuple(out_of_band_handoffs),
    )


def _normalize_finding(
    finding: Mapping[str, Any],
    *,
    repo_root_path: Path,
) -> dict[str, Any]:
    for field_name in _REQUIRED_FINDING_FIELDS:
        if field_name not in finding:
            raise OutOfBandRoutingError(f"finding missing required field: {field_name}")

    proposed_destination = finding["proposed_destination"]
    if (
        not isinstance(proposed_destination, str)
        or proposed_destination not in SUPPORTED_FINDING_CATEGORIES
    ):
        raise OutOfBandRoutingError(
            f"unsupported proposed_destination: {proposed_destination!r}"
        )

    source_section = _required_text(finding["source_section"], "source_section")
    rationale = _required_text(finding["rationale"], "rationale")
    normalized = dict(finding)
    normalized["source_file"] = _repo_relative_resolved_path(
        finding["source_file"],
        repo_root_path=repo_root_path,
        field_name="source_file",
    )
    normalized["source_section"] = source_section
    normalized["suggested_artifact_path"] = _repo_relative_resolved_path(
        finding["suggested_artifact_path"],
        repo_root_path=repo_root_path,
        field_name="suggested_artifact_path",
    )
    normalized["rationale"] = rationale
    return normalized


def _handoff_record(
    finding: Mapping[str, Any],
    *,
    target_persona: str,
) -> dict[str, str]:
    record = {
        "finding_id": _finding_id(
            source_file=finding["source_file"],
            source_section=finding["source_section"],
            suggested_artifact_path=finding["suggested_artifact_path"],
        ),
        "source_file": str(finding["source_file"]),
        "source_section": str(finding["source_section"]),
        "suggested_artifact_path": str(finding["suggested_artifact_path"]),
        "rationale": str(finding["rationale"]),
        "target_persona": target_persona,
    }
    if tuple(record) != HANDOFF_RECORD_FIELDS:
        raise OutOfBandRoutingError("handoff record schema drift")
    return record


def _finding_id(
    *,
    source_file: Any,
    source_section: Any,
    suggested_artifact_path: Any,
) -> str:
    material = "\0".join(
        (
            str(source_file),
            str(source_section),
            str(suggested_artifact_path),
        )
    )
    return f"outofband-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}"


def _route_scope(repo_relative_path: str) -> str | None:
    parts = Path(repo_relative_path).parts
    if _is_under(parts, (".github", "agents")):
        return "agent"
    if _is_under(parts, (".github", "prompts")):
        return "prompt"
    if _is_under(parts, (".github", "skills")) and len(parts) >= 3:
        skill_name = parts[2]
        if skill_name != AUDIT_SKILL_NAME:
            return "other_skill"
    return None


def _is_under(parts: tuple[str, ...], root_parts: tuple[str, ...]) -> bool:
    return len(parts) > len(root_parts) and parts[: len(root_parts)] == root_parts


def _repo_relative_resolved_path(
    raw_path: Any,
    *,
    repo_root_path: Path,
    field_name: str,
) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise OutOfBandRoutingError(f"{field_name} must be a non-empty string")
    path = Path(raw_path)
    resolved = (path if path.is_absolute() else repo_root_path / path).resolve()
    if not resolved.is_relative_to(repo_root_path):
        raise OutOfBandRoutingError(f"{field_name} escapes repository root: {raw_path!r}")
    relative_path = resolved.relative_to(repo_root_path).as_posix()
    if not relative_path or relative_path == ".":
        raise OutOfBandRoutingError(f"{field_name} must resolve to a repo-relative path")
    return relative_path


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutOfBandRoutingError(f"{field_name} must be a non-empty string")
    return value


__all__ = [
    "AUDIT_SKILL_DIR",
    "AUDIT_SKILL_NAME",
    "HANDOFF_RECORD_FIELDS",
    "OUT_OF_BAND_TARGET_PERSONA",
    "OUT_OF_BAND_TARGETS_BY_SCOPE",
    "OutOfBandRoutingError",
    "RoutingResult",
    "SUPPORTED_FINDING_CATEGORIES",
    "route_findings",
]
