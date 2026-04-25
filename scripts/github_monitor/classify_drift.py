"""Classify drifted entries as HITL or AFK (Phase 2.5 — read-only).

Reads the drift report produced by ``check_drift.py`` and classifies every
drifted entry as either AFK (automatable, suitable for unattended synthesis)
or HITL (requires human review).  Outputs ``afk-entries.json`` and
``hitl-entries.json`` as transient CI artifacts, and optionally sets GitHub
Actions step outputs.

Usage::

    python -m scripts.github_monitor.classify_drift \\
        --drift-report drift-report.json \\
        [--output-dir .]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from scripts._optional_surface_common import (
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    invalid_input_result,
    run_surface_cli,
)

SURFACE = "github_monitor.classify_drift"
MODE = "classify"


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["raw/github-sources"],
        allowed_suffixes=[".json"],
    )


def _write_github_output(has_afk: bool, has_hitl: bool) -> None:
    """Write step outputs to ``$GITHUB_OUTPUT`` if running inside Actions."""
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if not gh_output:
        return
    with open(gh_output, "a") as fh:
        fh.write(f"has_afk={'true' if has_afk else 'false'}\n")
        fh.write(f"has_hitl={'true' if has_hitl else 'false'}\n")


def classify_drift(
    drift_report_path: Path,
    output_dir: Path,
) -> SurfaceResult:
    """Classify drifted entries from a drift report as HITL or AFK.

    Returns a ``SurfaceResult`` with the classification summary.
    """
    try:
        raw = drift_report_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Cannot read drift report: {exc}",
            path_rules=_path_rules(),
        )

    try:
        report = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Malformed drift report JSON: {exc}",
            path_rules=_path_rules(),
        )

    drifted = report.get("drifted", [])

    # Deny-by-default (ADR-014): all drifted entries classify as HITL.
    # When line-level diff metrics become available in the drift report,
    # add --afk-max-lines threshold logic here (Phase 2).
    afk_entries: list[dict[str, Any]] = []
    hitl_entries: list[dict[str, Any]] = list(drifted)

    has_afk = len(afk_entries) > 0
    has_hitl = len(hitl_entries) > 0

    _write_github_output(has_afk, has_hitl)

    output_dir.mkdir(parents=True, exist_ok=True)
    afk_path = output_dir / "afk-entries.json"
    hitl_path = output_dir / "hitl-entries.json"
    afk_path.write_text(json.dumps({"entries": afk_entries}, indent=2), encoding="utf-8")
    hitl_path.write_text(json.dumps({"entries": hitl_entries}, indent=2), encoding="utf-8")

    message = f"Classification: {len(afk_entries)} AFK, {len(hitl_entries)} HITL"
    print(message)

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS,
        reason_code="ok",
        message=message,
        path_rules=_path_rules(),
        summary={
            "afk_count": len(afk_entries),
            "hitl_count": len(hitl_entries),
            "has_afk": has_afk,
            "has_hitl": has_hitl,
        },
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Classify drifted entries as HITL or AFK."
    )
    parser.add_argument(
        "--drift-report",
        metavar="PATH",
        required=True,
        help="Path to the drift report JSON produced by check_drift.",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        default=".",
        help="Directory to write afk-entries.json and hitl-entries.json (default: current directory).",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    return {
        "drift_report_path": Path(args.drift_report),
        "output_dir": Path(args.output_dir),
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return classify_drift(
        drift_report_path=kwargs["drift_report_path"],
        output_dir=kwargs["output_dir"],
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: Any = sys.stdout,
) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=_runner,
        args_to_kwargs=_args_to_kwargs,
        output_stream=output_stream,
    )


if __name__ == "__main__":
    sys.exit(run_cli())
