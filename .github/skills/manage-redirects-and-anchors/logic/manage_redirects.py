"""Append-only redirect record management for wiki/redirects.md."""

from __future__ import annotations

import argparse
from datetime import date
import re
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    JsonArgumentParser,
    LOCK_PATH,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    approval_required_result,
    base_path_rules,
    invalid_input_result,
    lock_unavailable_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)
from scripts.kb import write_utils
from scripts.kb.write_utils import LockUnavailableError

SURFACE = ".github/skills/manage-redirects-and-anchors/logic/manage_redirects.py"
SUPPORTED_MODES: tuple[str, ...] = ("propose", "apply")
REDIRECTS_FILE = "wiki/redirects.md"
_REDIRECTS_HEADER = "| old_slug | new_slug | redirected_at | reason |\n|----------|----------|----------------|--------|\n"


def _normalize_slug(value: str) -> str:
    """Derive a canonical slug per ADR-009 normalization rules."""
    slug = value.lower().strip()
    slug = re.sub(r"[ _]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=[REDIRECTS_FILE],
        allowed_suffixes=[".md"],
    )
    rules["lock_path"] = LOCK_PATH
    rules["direct_writes_declared"] = True
    rules["output_root"] = REDIRECTS_FILE
    return rules


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Record redirect from old_slug to new_slug in wiki/redirects.md."
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default="propose",
        help="propose (preview) or apply (write).",
    )
    parser.add_argument("--old-slug", required=True, help="The old canonical page slug.")
    parser.add_argument("--new-slug", required=True, help="The new canonical slug, or REMOVED.")
    parser.add_argument("--reason", default="", help="Short description of why the redirect was created.")
    parser.add_argument(
        "--approval",
        default=APPROVAL_NONE,
        help="Set to 'approved' to enable apply mode writes.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    return parser


def run_manage_redirects(
    *,
    repo_root: str | Path = ".",
    mode: str,
    old_slug: str,
    new_slug: str,
    reason: str = "",
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)

    norm_old = _normalize_slug(old_slug)
    norm_new = new_slug.upper() if new_slug.upper() == "REMOVED" else _normalize_slug(new_slug)
    today = date.today().isoformat()
    clean_reason = (reason.strip() or "no reason provided").replace("|", "-")

    if not norm_old or (norm_new != "REMOVED" and not norm_new):
        return invalid_input_result(
            surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules,
            message="old_slug and new_slug must normalize to non-empty values",
        )

    new_row = f"| {norm_old} | {norm_new} | {today} | {clean_reason} |\n"

    if mode == "propose":
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="redirect proposal generated; use apply mode to persist",
            approval=approval,
            path_rules=path_rules,
            items=({"proposed_row": new_row.strip(), "old_slug": norm_old, "new_slug": norm_new},),
            summary={"old_slug": norm_old, "new_slug": norm_new, "redirected_at": today},
        )

    # apply mode
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE,
            mode=mode,
            path_rules=path_rules,
            lock_required=True,
        )

    redirects_path = normalized_repo_root / REDIRECTS_FILE
    redirects_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with write_utils.exclusive_write_lock(normalized_repo_root):
            if not redirects_path.exists():
                redirects_path.write_text(
                    "# Wiki Redirects\n\n" + _REDIRECTS_HEADER + new_row,
                    encoding="utf-8",
                )
            else:
                existing = redirects_path.read_text(encoding="utf-8")
                # Anchor to line-start to avoid false positives when norm_old also
                # appears as a new_slug in an earlier row.
                if re.search(rf"(?m)^\| {re.escape(norm_old)} \|", existing):
                    return SurfaceResult(
                        surface=SURFACE,
                        mode=mode,
                        status=STATUS_FAIL,
                        reason_code="duplicate_redirect",
                        message=f"redirect from '{norm_old}' already recorded",
                        approval=approval,
                        lock_path=LOCK_PATH,
                        lock_required=True,
                        path_rules=path_rules,
                        items=(),
                        summary={},
                    )
                # Ensure the table header exists; if not, append a section header + header row
                if "| old_slug |" not in existing:
                    redirects_path.write_text(
                        existing.rstrip() + "\n\n## Redirect Table\n\n" + _REDIRECTS_HEADER + new_row,
                        encoding="utf-8",
                    )
                else:
                    redirects_path.write_text(existing + new_row, encoding="utf-8")
    except LockUnavailableError as exc:
        return lock_unavailable_result(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules, exc=exc)

    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_PASS,
        reason_code=REASON_CODE_OK,
        message=f"redirect recorded: {norm_old} → {norm_new}",
        approval=approval,
        lock_path=LOCK_PATH,
        lock_required=True,
        path_rules=path_rules,
        items=({"written_row": new_row.strip(), "old_slug": norm_old, "new_slug": norm_new},),
        summary={"old_slug": norm_old, "new_slug": norm_new, "redirected_at": today},
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_manage_redirects,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "old_slug": a.old_slug,
            "new_slug": a.new_slug,
            "reason": a.reason,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "REDIRECTS_FILE",
    "run_manage_redirects",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
