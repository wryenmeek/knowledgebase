"""Deterministic AFK safety-net validator (Phase 3 — read-only).

Validates that an AFK-classified wiki page update stays within the
AFK-allowed change boundary.  Rejects any update that touches citations,
claims, topology links, entity identity, or body text.

Usage::

    python -m scripts.validation.validate_afk_output \\
        --original wiki/pages/topic/some-page.md \\
        --proposed /path/to/proposed-page.md

This is the safety-net that must pass before any AFK-classified write
proceeds.  It implements the semantic whitelist from ADR-014.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence

import re
import yaml

from scripts._optional_surface_common import (
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    run_surface_cli,
)
from scripts.kb.sourceref import SOURCEREF_RE

SURFACE = "validation.validate_afk_output"
MODE = "validate"

# Frontmatter fields that AFK updates may change.
# For ``quality_assessment``, only the ``freshness_date`` sub-field may change
# per ADR-014 §4.  The ``updated_at`` field records the AFK timestamp.
_AFK_ALLOWED_FIELDS: frozenset[str] = frozenset({
    "updated_at",
    "quality_assessment",
})

_WIKI_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+\.md(?:#[^)]*)?)\)")


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=["wiki"],
        allowed_suffixes=[".md"],
    )


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from body.  Returns (fields, body).

    Uses ``yaml.safe_load`` to correctly handle multi-line values such as
    ``quality_assessment`` block scalars, ``aliases`` lists, and other
    structured fields.
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[4:end]
    body = text[end + 4:].strip()
    try:
        fields = yaml.safe_load(fm_block) or {}
        if not isinstance(fields, dict):
            fields = {}
    except yaml.YAMLError:
        fields = {}
    return fields, body


def _normalize_yaml_whitespace(text: str) -> str:
    """Normalize YAML-insignificant whitespace for comparison."""
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)


def validate_afk_output(
    original_path: Path,
    proposed_path: Path,
) -> SurfaceResult:
    """Validate that a proposed AFK update stays within allowed bounds."""
    checks: list[dict[str, Any]] = []

    try:
        original_text = original_path.read_text(encoding="utf-8")
        proposed_text = proposed_path.read_text(encoding="utf-8")
    except OSError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=MODE,
            status=STATUS_FAIL,
            reason_code="invalid_input",
            message=f"Cannot read file: {exc}",
            path_rules=_path_rules(),
        )

    orig_fm, orig_body = _parse_frontmatter(original_text)
    prop_fm, prop_body = _parse_frontmatter(proposed_text)

    # Check 1: Only allowed frontmatter fields changed.
    # ``quality_assessment`` is allowed but only its ``freshness_date``
    # sub-field may change per ADR-014 §4.
    changed_fields: list[str] = []
    disallowed: list[str] = []
    all_keys = set(orig_fm) | set(prop_fm)
    for key in all_keys:
        if orig_fm.get(key) != prop_fm.get(key):
            changed_fields.append(key)
            if key == "quality_assessment":
                orig_qa = orig_fm.get("quality_assessment")
                prop_qa = prop_fm.get("quality_assessment")
                if not isinstance(orig_qa, dict):
                    orig_qa = {}
                if not isinstance(prop_qa, dict):
                    prop_qa = {}
                for qa_key in set(orig_qa) | set(prop_qa):
                    if qa_key != "freshness_date" and orig_qa.get(qa_key) != prop_qa.get(qa_key):
                        disallowed.append(f"quality_assessment.{qa_key}")
            elif key not in _AFK_ALLOWED_FIELDS:
                disallowed.append(key)
    checks.append({
        "check": "frontmatter_fields",
        "pass": len(disallowed) == 0,
        "changed": changed_fields,
        "disallowed": disallowed,
    })

    # Check 2: No body text changes (after YAML whitespace normalization).
    orig_normalized = _normalize_yaml_whitespace(orig_body)
    prop_normalized = _normalize_yaml_whitespace(prop_body)
    body_unchanged = orig_normalized == prop_normalized
    checks.append({
        "check": "body_unchanged",
        "pass": body_unchanged,
    })

    # Check 3: No citation/SourceRef changes.
    orig_refs = set(SOURCEREF_RE.findall(orig_body))
    prop_refs = set(SOURCEREF_RE.findall(prop_body))
    refs_unchanged = orig_refs == prop_refs
    checks.append({
        "check": "citations_unchanged",
        "pass": refs_unchanged,
        "added": sorted(prop_refs - orig_refs),
        "removed": sorted(orig_refs - prop_refs),
    })

    # Check 4: No link/topology changes.
    orig_links = set(_WIKI_LINK_RE.findall(orig_body))
    prop_links = set(_WIKI_LINK_RE.findall(prop_body))
    links_unchanged = orig_links == prop_links
    checks.append({
        "check": "links_unchanged",
        "pass": links_unchanged,
    })

    # Check 5: No entity/alias/title changes.
    # With proper YAML parsing, compare title and aliases directly.
    title_unchanged = orig_fm.get("title") == prop_fm.get("title")
    aliases_unchanged = orig_fm.get("aliases") == prop_fm.get("aliases")
    checks.append({
        "check": "identity_unchanged",
        "pass": title_unchanged and aliases_unchanged,
    })

    all_passed = all(c["pass"] for c in checks)
    failed_checks = [c["check"] for c in checks if not c["pass"]]

    return SurfaceResult(
        surface=SURFACE,
        mode=MODE,
        status=STATUS_PASS if all_passed else STATUS_FAIL,
        reason_code="ok" if all_passed else "afk_bounds_violated",
        message=(
            "AFK output validated: all checks passed"
            if all_passed
            else f"AFK bounds violated: {', '.join(failed_checks)}"
        ),
        path_rules=_path_rules(),
        summary={"checks": checks, "all_passed": all_passed},
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(
        description="Validate AFK-classified wiki page update against semantic whitelist."
    )
    parser.add_argument(
        "--original",
        metavar="PATH",
        required=True,
        help="Path to the original wiki page.",
    )
    parser.add_argument(
        "--proposed",
        metavar="PATH",
        required=True,
        help="Path to the proposed updated page.",
    )
    return parser


def _args_to_kwargs(args: Any) -> dict[str, Any]:
    original_path = Path(args.original)
    proposed_path = Path(args.proposed)
    # Bounds-check --original against wiki/ per canonical path-safety pattern
    # (docs/architecture.md §Write and safety controls).  --proposed is allowed
    # outside wiki/ to support staged / temp file invocation.
    wiki_root = (Path(".") / "wiki").resolve()
    try:
        resolved_original = original_path.resolve()
        if not resolved_original.is_relative_to(wiki_root):
            raise ValueError(
                f"--original must be within wiki/: {original_path}"
            )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "original_path": original_path,
        "proposed_path": proposed_path,
    }


def _runner(**kwargs: Any) -> SurfaceResult:
    return validate_afk_output(
        original_path=kwargs["original_path"],
        proposed_path=kwargs["proposed_path"],
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
