"""Read-only KPI aggregation over wiki/reports/quality-scores-*.json artifacts."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_PASS,
    SurfaceResult,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)

SURFACE = ".github/skills/compute-kpis/logic/compute_kpis.py"
SUPPORTED_MODES: tuple[str, ...] = ("snapshot",)
SCORES_GLOB = "wiki/reports/quality-scores-*.json"


def _path_rules() -> dict[str, object]:
    return {
        "allowed_roots": ["wiki/reports"],
        "direct_writes_declared": False,
        "read_only": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Aggregate KPI metrics from quality-scores report artifacts."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="snapshot",
        help="snapshot: compute KPI snapshot from available score artifacts.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--approval",
        default=APPROVAL_NONE,
        help="Unused; reserved for future writeback authorization.",
    )
    return parser


def _compute_kpis_from_scores(score_files: list[Path]) -> dict:
    """Aggregate KPI metrics from quality-scores JSON artifacts."""
    all_findings: list[dict] = []
    for f in score_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            all_findings.extend(data.get("findings", []))
        except (json.JSONDecodeError, OSError):
            pass

    scores = [f["score"] for f in all_findings if isinstance(f.get("score"), (int, float))]
    if not scores:
        return {
            "page_count": len(all_findings),
            "avg_score": None,
            "low_score_count": 0,
            "high_score_count": 0,
            "score_coverage_pct": 0.0,
        }

    avg = sum(scores) / len(scores)
    low_threshold = 0.4
    high_threshold = 0.8
    return {
        "page_count": len(scores),
        "avg_score": round(avg, 4),
        "low_score_count": sum(1 for s in scores if s < low_threshold),
        "high_score_count": sum(1 for s in scores if s >= high_threshold),
        "score_coverage_pct": round(len(scores) / max(len(all_findings), 1) * 100, 1),
    }


def run_compute_kpis(
    *,
    repo_root: str | Path = ".",
    mode: str = "snapshot",
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)

    score_files = sorted(
        Path(p) for p in glob.glob(str(normalized_repo_root / SCORES_GLOB))
    )
    if not score_files:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="no quality-scores artifacts found; KPI snapshot is empty",
            approval=approval,
            path_rules=path_rules,
            items=(),
            summary={"artifact_count": 0, "kpis": {}},
        )

    kpis = _compute_kpis_from_scores(score_files)
    items = tuple(
        {"artifact": str(f.relative_to(normalized_repo_root))} for f in score_files
    )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=f"KPI snapshot computed from {len(score_files)} artifact(s)",
        approval=approval,
        path_rules=path_rules,
        items=items,
        summary={"artifact_count": len(score_files), "kpis": kpis},
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_compute_kpis,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "SCORES_GLOB",
    "run_compute_kpis",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
