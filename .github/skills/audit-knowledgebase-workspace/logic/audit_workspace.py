"""Read-only scaffold for auditing knowledgebase workspace customizations.

Phase 3 intentionally performs no classification and no mutation. The default
flow preserves the existing structural-lint audit contract, while the `improve`
flow remains a dry-run scaffold. It returns an empty findings list by default
and can route caller-supplied classifier findings into read-only OutOfBand
handoff records. Any write-capable behavior and `.github/.customizations.lock`
acquisition are deferred to later governed slices.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from outofband_handoff import OutOfBandRoutingError, route_findings
except ImportError:  # pragma: no cover - exercised when imported as a package
    from .outofband_handoff import OutOfBandRoutingError, route_findings

from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_INVALID_INPUT,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)

SURFACE = ".github/skills/audit-knowledgebase-workspace/logic/audit_workspace.py"
SUPPORTED_MODES: tuple[str, ...] = ("default", "improve")


def _path_rules() -> dict[str, object]:
    return {
        "allowed_roots": [
            ".github/copilot-instructions.md",
            ".github/agents",
            ".github/prompts",
            ".github/skills",
            ".github/hooks",
            "AGENTS.md",
            "tests/kb",
        ],
        "direct_writes_declared": False,
        "read_only": True,
        "writable_paths": [],
        "writes_forbidden": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Run the read-only audit-knowledgebase-workspace scaffold."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="default",
        help=(
            "default: compatibility scaffold; improve: dry-run scaffold with "
            "empty findings unless caller-supplied findings are routed."
        ),
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--approval",
        choices=(APPROVAL_NONE,),
        default=APPROVAL_NONE,
        help="Only 'none' is accepted; write approval is not supported by this scaffold.",
    )
    return parser


def audit(
    *,
    repo_root: str | Path = ".",
    mode: str = "default",
    approval: str = APPROVAL_NONE,
    classifier_findings: Sequence[Mapping[str, Any]] | None = None,
) -> SurfaceResult:
    """Return a read-only audit result with zero writes attempted."""

    path_rules = _path_rules()
    if approval != APPROVAL_NONE:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message="approval is not accepted by this read-only scaffold",
            approval=APPROVAL_NONE,
            path_rules=path_rules,
        )
    if mode not in SUPPORTED_MODES:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"unsupported mode: {mode}",
            approval=approval,
            path_rules=path_rules,
        )

    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            path_rules=path_rules,
        )

    try:
        routed_findings = route_findings(
            tuple(classifier_findings or ()),
            repo_root=normalized_repo_root,
        )
    except OutOfBandRoutingError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INVALID_INPUT,
            message=f"finding routing failed closed: {exc}",
            approval=approval,
            path_rules=path_rules,
        )

    findings = [dict(finding) for finding in routed_findings.eligible_findings]
    out_of_band_handoffs = [
        dict(handoff) for handoff in routed_findings.out_of_band_handoffs
    ]
    message = (
        "default structural lint remains external; compatibility scaffold returned empty findings"
        if mode == "default"
        else "improve dry-run scaffold completed with routed findings"
    )
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=message,
        approval=approval,
        path_rules=path_rules,
        items=(),
        summary={
            "findings": findings,
            "finding_count": len(findings),
            "out_of_band_handoffs": out_of_band_handoffs,
            "out_of_band_handoff_count": len(out_of_band_handoffs),
            "writes_attempted": 0,
            "dry_run": True,
            "read_only": True,
            "structural_lint_executed": False,
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=audit,
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
    "audit",
    "run_cli",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
