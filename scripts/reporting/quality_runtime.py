"""Recommendation-first quality prioritization with approval-gated score/report write modes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    LOCK_PATH,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    approval_required_result,
    base_path_rules,
    count_placeholders,
    expand_repo_paths,
    invalid_input_result,
    lock_unavailable_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_report_artifact,
)
from scripts.kb import page_template_utils
from scripts.kb.write_utils import LockUnavailableError

SURFACE = "scripts/reporting/quality_runtime.py"
SUPPORTED_MODES: tuple[str, ...] = ("recommend", "score-update", "report")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("score-update", "report")
ALLOWED_CONTENT_ROOTS: tuple[str, ...] = ("docs", "wiki")
ALLOWED_CONTENT_SUFFIXES: tuple[str, ...] = (".md",)
ALLOWED_QUERY_EVIDENCE_ROOTS: tuple[str, ...] = ("docs", "wiki")
ALLOWED_QUERY_EVIDENCE_SUFFIXES: tuple[str, ...] = (".json",)


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description=(
            "Compute recommendation-only quality priorities from repo-local evidence while "
            "keeping score updates and reporting egress fail-closed."
        )
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="recommend")
    parser.add_argument("--query-evidence", action="append", default=[])
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_CONTENT_ROOTS,
        allowed_suffixes=ALLOWED_CONTENT_SUFFIXES,
    )
    rules.update(
        {
            "query_evidence_allowlisted_roots": list(ALLOWED_QUERY_EVIDENCE_ROOTS),
            "query_evidence_allowed_suffixes": list(ALLOWED_QUERY_EVIDENCE_SUFFIXES),
            "recommendation_mode": "read-only",
            "score_writeback_declared": True,
            "report_egress_declared": True,
        }
    )
    return rules


def _parse_confidence(frontmatter: dict[str, str]) -> int | None:
    raw = frontmatter.get("confidence")
    if raw is None:
        return None
    normalized = raw.strip().strip('"').strip("'")
    if not normalized:
        return None
    try:
        value = int(normalized)
    except ValueError:
        return None
    if 1 <= value <= 5:
        return value
    return None


def _resolve_query_evidence(
    repo_root: Path,
    raw_paths: Sequence[str],
) -> tuple[dict[str, dict[str, int]], int]:
    if not raw_paths:
        return {}, 0
    resolved_paths = expand_repo_paths(
        repo_root,
        list(raw_paths),
        allowed_roots=ALLOWED_QUERY_EVIDENCE_ROOTS,
        allowed_suffixes=ALLOWED_QUERY_EVIDENCE_SUFFIXES,
    )
    aggregates: dict[str, dict[str, int]] = {}
    total_entries = 0
    allowed_root_paths = tuple((repo_root / root).resolve() for root in ALLOWED_CONTENT_ROOTS)
    for path in resolved_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries = payload.get("items", payload.get("entries"))
        else:
            entries = payload
        if not isinstance(entries, list):
            raise ValueError(
                f"query evidence must be a JSON list or an object containing 'items'/'entries': {repo_relative(repo_root, path)}"
            )
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"query evidence entries must be objects: {repo_relative(repo_root, path)}")
            total_entries += 1
            if entry.get("missed") is not True:
                continue
            target_path = entry.get("target_path")
            if not isinstance(target_path, str) or not target_path.strip():
                raise ValueError(
                    f"missed query entries must declare repo-relative target_path: {repo_relative(repo_root, path)}"
                )
            target = (repo_root / target_path).resolve()
            if not target.is_relative_to(repo_root):
                raise ValueError(f"query evidence target escapes repository root: {target_path}")
            if not any(target == root or target.is_relative_to(root) for root in allowed_root_paths):
                raise ValueError(f"query evidence target is outside declared scope: {target_path}")
            demand = entry.get("demand", 1)
            if not isinstance(demand, int) or demand < 1:
                raise ValueError(f"missed query demand must be an integer >= 1: {repo_relative(repo_root, path)}")
            relative_target = repo_relative(repo_root, target)
            bucket = aggregates.setdefault(relative_target, {"missed_query_count": 0, "missed_query_demand": 0})
            bucket["missed_query_count"] += 1
            bucket["missed_query_demand"] += demand
    return aggregates, total_entries


def _recommended_next_step(item: dict[str, Any]) -> str:
    if item["missed_query_count"]:
        return "route to knowledgebase-orchestrator for discovery follow-up"
    if item["missing_sources"]:
        return "route to knowledgebase-orchestrator for evidence coverage follow-up"
    if item["placeholder_count"]:
        return "route to knowledgebase-orchestrator for governed curation follow-up"
    if item["missing_updated_at"]:
        return "route to knowledgebase-orchestrator for freshness review"
    return "monitor in recommendation-only mode"


def run_quality_runtime(
    *,
    repo_root: str | Path = ".",
    mode: str,
    paths: Sequence[str] | None = None,
    query_evidence_paths: Sequence[str] | None = None,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)

    if mode in LOCK_REQUIRED_MODES:
        if approval != APPROVAL_APPROVED:
            return approval_required_result(
                surface=SURFACE,
                mode=mode,
                path_rules=path_rules,
                lock_required=True,
            )
        # Approved — fall through to compute then write.

    try:
        resolved_paths = expand_repo_paths(
            normalized_repo_root,
            list(paths or ()),
            allowed_roots=ALLOWED_CONTENT_ROOTS,
            allowed_suffixes=ALLOWED_CONTENT_SUFFIXES,
        )
        missed_query_by_target, query_evidence_count = _resolve_query_evidence(
            normalized_repo_root,
            list(query_evidence_paths or ()),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )

    items: list[dict[str, Any]] = []
    prioritized_count = 0
    for path in resolved_paths:
        relative_path = repo_relative(normalized_repo_root, path)
        text = path.read_text(encoding="utf-8")
        frontmatter = page_template_utils.parse_page_frontmatter(text)
        confidence = _parse_confidence(frontmatter)
        missing_sources = "sources" not in frontmatter
        missing_updated_at = "updated_at" not in frontmatter
        placeholder_count = count_placeholders(text)
        query_evidence = missed_query_by_target.get(
            relative_path,
            {"missed_query_count": 0, "missed_query_demand": 0},
        )
        confidence_gap = 0 if confidence is None else max(0, 5 - confidence)
        priority_score = (
            4 * int(missing_sources)
            + 2 * int(missing_updated_at)
            + 3 * placeholder_count
            + confidence_gap
            + 5 * query_evidence["missed_query_demand"]
            + 2 * query_evidence["missed_query_count"]
        )
        prioritized_count += 1 if priority_score > 0 else 0
        item = {
            "path": relative_path,
            "priority_score": priority_score,
            "missing_sources": missing_sources,
            "missing_updated_at": missing_updated_at,
            "placeholder_count": placeholder_count,
            "confidence": confidence,
            "missed_query_count": query_evidence["missed_query_count"],
            "missed_query_demand": query_evidence["missed_query_demand"],
        }
        item["recommended_next_step"] = _recommended_next_step(item)
        items.append(item)

    items.sort(key=lambda item: (-int(item["priority_score"]), str(item["path"])))

    if mode == "recommend":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="quality recommendations computed from repo-local evidence",
            approval=approval,
            path_rules=path_rules,
            items=tuple(items),
            summary={
                "selected_count": len(resolved_paths),
                "prioritized_count": prioritized_count,
                "query_evidence_count": query_evidence_count,
                "recommendation_only": True,
                "scoring_mode": "recommendation-only",
                "gated_modes": list(LOCK_REQUIRED_MODES),
            },
        )

    # score-update or report — write approved artifact to wiki/reports/
    report_type = "quality-scores" if mode == "score-update" else "quality-report"
    artifact = {
        "report_type": report_type,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": list(paths) if paths else list(ALLOWED_CONTENT_ROOTS),
        "surface": SURFACE,
        "findings": list(items),
        "summary": {
            "selected_count": len(resolved_paths),
            "prioritized_count": prioritized_count,
            "query_evidence_count": query_evidence_count,
            "recommendation_only": False,
            "scoring_mode": mode,
        },
    }
    try:
        written_path = write_report_artifact(normalized_repo_root, report_type, artifact)
    except LockUnavailableError as exc:
        return lock_unavailable_result(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules, exc=exc)
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE, mode=mode, status=STATUS_FAIL,
            reason_code="write_failed",
            message=f"report write failed: {exc}",
            approval=approval, lock_path=LOCK_PATH, lock_required=True,
            path_rules=path_rules,
        )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=f"quality {mode} persisted to {repo_relative(normalized_repo_root, written_path)}",
        approval=approval,
        lock_path=LOCK_PATH,
        lock_required=True,
        path_rules=path_rules,
        items=tuple(items),
        summary={
            "selected_count": len(resolved_paths),
            "prioritized_count": prioritized_count,
            "query_evidence_count": query_evidence_count,
            "recommendation_only": False,
            "scoring_mode": mode,
            "written_path": repo_relative(normalized_repo_root, written_path),
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_quality_runtime,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "paths": a.path,
            "query_evidence_paths": a.query_evidence,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
