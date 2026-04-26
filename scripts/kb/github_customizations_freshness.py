"""Drift detection for .github/ customization cross-references.

Imports the graph engine to run all four reference checks, fuzzy-matches
broken references against existing skills, and outputs a structured JSON
drift report split into two buckets:

- ``resolvable``: broken reference with a suggested replacement (auto-fixable)
- ``ambiguous``: broken reference that needs human judgment

Exit codes:
    0 — no drift detected
    1 — drift detected (resolvable or ambiguous entries present)
    2 — unexpected error (broken environment, I/O failure, import error)

Usage::

    python3 -m scripts.kb.github_customizations_freshness [--output PATH]
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

from scripts.kb.github_customizations_graph import (
    extract_agent_skill_refs,
    extract_copilot_instruction_refs,
    extract_prompt_links,
    validate_hooks_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = REPO_ROOT / ".github" / "agents"
SKILLS_ROOT = REPO_ROOT / ".github" / "skills"
HOOKS_JSON = REPO_ROOT / ".github" / "hooks" / "hooks.json"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"
PROMPTS_DIR = REPO_ROOT / ".github" / "prompts"

_FUZZY_CUTOFF = 0.7


def _all_skill_names() -> list[str]:
    """Return list of all skill directory names that have a SKILL.md."""
    return sorted(
        d.name
        for d in SKILLS_ROOT.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    )


def _suggest_replacement(broken: str, candidates: list[str]) -> str | None:
    """Return a candidate replacement for *broken*, or None if none found.

    Strategy 1: substring containment (broken is a substring of a candidate
    or vice versa) — handles renames like ``validate-wiki`` → ``validate-wiki-governance``.

    Strategy 2: ``difflib.get_close_matches`` Levenshtein fallback — handles
    typos and minor spelling differences.
    """
    if not broken:
        return None
    for c in candidates:
        if broken in c or c in broken:
            return c
    matches = difflib.get_close_matches(broken, candidates, n=1, cutoff=_FUZZY_CUTOFF)
    return matches[0] if matches else None


def _collect_agent_drift(
    skill_names: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    resolvable: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    for persona, skills in extract_agent_skill_refs(AGENTS_ROOT).items():
        for skill in skills:
            if skill in skill_names:
                continue
            entry: dict[str, str] = {
                "file": f".github/agents/{persona}.md",
                "ref_broken": skill,
            }
            suggestion = _suggest_replacement(skill, skill_names)
            if suggestion:
                resolvable.append({**entry, "ref_suggested": suggestion})
            else:
                ambiguous.append(
                    {**entry, "context": "Required skills / Related skill section"}
                )
    return resolvable, ambiguous


def _collect_copilot_drift(
    skill_names: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    resolvable: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    refs = extract_copilot_instruction_refs(COPILOT_INSTRUCTIONS)
    for skill in refs["skills"]:
        if skill in skill_names:
            continue
        entry: dict[str, str] = {
            "file": ".github/copilot-instructions.md",
            "ref_broken": skill,
        }
        suggestion = _suggest_replacement(skill, skill_names)
        if suggestion:
            resolvable.append({**entry, "ref_suggested": suggestion})
        else:
            ambiguous.append({**entry, "context": "skill reference in instructions"})
    for script_path in refs["scripts"]:
        if not (REPO_ROOT / script_path).is_file():
            ambiguous.append(
                {
                    "file": ".github/copilot-instructions.md",
                    "ref_broken": script_path,
                    "context": "python3 script command reference",
                }
            )
    return resolvable, ambiguous


def _collect_hooks_drift() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    errors = validate_hooks_json(HOOKS_JSON, REPO_ROOT)
    ambiguous = [
        {
            "file": str(HOOKS_JSON.relative_to(REPO_ROOT)),
            "ref_broken": err,
            "context": "hooks.json validation error",
        }
        for err in errors
    ]
    return [], ambiguous


def _collect_prompt_drift() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ambiguous: list[dict[str, str]] = []
    for filename, links in extract_prompt_links(PROMPTS_DIR, REPO_ROOT).items():
        for target, ok in links:
            if not ok:
                ambiguous.append(
                    {
                        "file": f".github/prompts/{filename}",
                        "ref_broken": target,
                        "context": "broken markdown link",
                    }
                )
    return [], ambiguous


def run(output_path: Path | None = None) -> int:
    """Run all drift checks and write/print the JSON report.

    Returns:
        0 — repo is clean (no drift)
        1 — drift detected (resolvable or ambiguous entries present)
        2 — unexpected error (I/O failure, broken environment)
    """
    skill_names = _all_skill_names()
    all_resolvable: list[dict[str, str]] = []
    all_ambiguous: list[dict[str, str]] = []

    for collector in (
        lambda: _collect_agent_drift(skill_names),
        lambda: _collect_copilot_drift(skill_names),
        _collect_hooks_drift,
        _collect_prompt_drift,
    ):
        r, a = collector()
        all_resolvable.extend(r)
        all_ambiguous.extend(a)

    report = {"resolvable": all_resolvable, "ambiguous": all_ambiguous}
    serialized = json.dumps(report, indent=2)

    if output_path:
        try:
            output_path.write_text(serialized, encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write report to {output_path}: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(serialized + "\n")

    return 1 if (all_resolvable or all_ambiguous) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect drift in .github/ customization cross-references."
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Write JSON drift report to PATH (default: stdout)",
    )
    args = parser.parse_args(argv)
    try:
        return run(Path(args.output) if args.output else None)
    except Exception as exc:
        print(f"error: unexpected failure: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
