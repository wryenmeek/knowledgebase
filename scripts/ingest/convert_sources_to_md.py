"""Read-only ingest conversion previews with explicit no-write gating."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys
from typing import Sequence, TextIO

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_OK,
    REASON_CODE_UNSUPPORTED_SOURCE_TYPE,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    approval_required_result,
    base_path_rules,
    expand_repo_paths,
    invalid_input_result,
    looks_like_repo_root,
    repo_relative,
    repo_root_failure,
    run_surface_cli,
    write_surface_not_declared_result,
)

SURFACE = "scripts/ingest/convert_sources_to_md.py"
SUPPORTED_MODES: tuple[str, ...] = ("inspect", "preview", "apply")
LOCK_REQUIRED_MODES: tuple[str, ...] = ("apply",)
ALLOWED_SOURCE_ROOTS: tuple[str, ...] = ("raw/inbox", "raw/assets")
ALLOWED_SOURCE_SUFFIXES: tuple[str, ...] = (".html", ".md", ".pdf", ".txt")


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Inspect or preview repo-local source conversion without mutating processed artifacts."
    )
    add_common_surface_args(parser, modes=SUPPORTED_MODES, default_mode="inspect")
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(
        allowed_roots=ALLOWED_SOURCE_ROOTS,
        allowed_suffixes=ALLOWED_SOURCE_SUFFIXES,
    )
    rules["direct_writes_declared"] = False
    return rules


def _preview_markdown(path: Path) -> tuple[str | None, str | None]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return path.read_text(encoding="utf-8"), None
    if suffix == ".txt":
        title = path.stem.replace("-", " ").replace("_", " ").title() or "Converted Source"
        body = path.read_text(encoding="utf-8").rstrip()
        return f"# {title}\n\n```text\n{body}\n```\n", None
    if suffix == ".html":
        raw = path.read_text(encoding="utf-8")
        text = re.sub(r"<[^>]+>", " ", raw)
        normalized = " ".join(text.split())
        title = path.stem.replace("-", " ").replace("_", " ").title() or "Converted Source"
        return f"# {title}\n\n{normalized}\n", None
    return None, "source type requires an external converter that is not enabled in this deterministic repo-local surface"


def run_convert_sources(
    *,
    repo_root: str | Path = ".",
    mode: str,
    paths: Sequence[str] | None = None,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=approval, path_rules=path_rules)
    try:
        resolved_paths = expand_repo_paths(
            normalized_repo_root,
            list(paths or ()),
            allowed_roots=ALLOWED_SOURCE_ROOTS,
            allowed_suffixes=ALLOWED_SOURCE_SUFFIXES,
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=approval,
            message=str(exc),
            path_rules=path_rules,
        )
    if mode == "inspect":
        items = tuple(
            {
                "path": repo_relative(normalized_repo_root, path),
                "source_type": path.suffix.lower().lstrip("."),
                "size_bytes": path.stat().st_size,
            }
            for path in resolved_paths
        )
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="source conversion inventory computed",
            approval=approval,
            path_rules=path_rules,
            items=items,
            summary={"selected_count": len(items)},
        )
    if mode == "preview":
        items = []
        unsupported = 0
        for path in resolved_paths:
            preview, failure = _preview_markdown(path)
            if failure is not None:
                unsupported += 1
                items.append(
                    {
                        "path": repo_relative(normalized_repo_root, path),
                        "status": STATUS_FAIL,
                        "reason_code": REASON_CODE_UNSUPPORTED_SOURCE_TYPE,
                        "message": failure,
                    }
                )
                continue
            items.append(
                {
                    "path": repo_relative(normalized_repo_root, path),
                    "status": STATUS_PASS,
                    "preview_markdown": preview,
                }
            )
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL if unsupported else STATUS_PASS,
            reason_code=REASON_CODE_UNSUPPORTED_SOURCE_TYPE if unsupported else REASON_CODE_OK,
            message="source conversion preview computed" if unsupported == 0 else "one or more sources require unsupported conversion tooling",
            approval=approval,
            path_rules=path_rules,
            items=tuple(items),
            summary={"selected_count": len(items), "unsupported_count": unsupported},
        )
    if approval != APPROVAL_APPROVED:
        return approval_required_result(
            surface=SURFACE,
            mode=mode,
            path_rules=path_rules,
            lock_required=False,
        )
    return write_surface_not_declared_result(
        surface=SURFACE,
        mode=mode,
        approval=approval,
        path_rules=path_rules,
        lock_required=False,
        message="scripts/ingest/** has no narrower processed-artifact write contract for conversion output yet",
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_convert_sources,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "paths": a.path,
            "approval": a.approval,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "run_convert_sources",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
