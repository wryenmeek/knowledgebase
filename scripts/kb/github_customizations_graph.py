"""Semantic graph engine for .github/ customization cross-reference validation.

Shared by tests/kb/test_github_customizations.py (CI gate) and
scripts/kb/github_customizations_freshness.py (drift repair workflow).

All four public functions are read-only and side-effect free.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = [
    "extract_agent_skill_refs",
    "extract_copilot_instruction_refs",
    "validate_hooks_json",
    "extract_prompt_links",
    "REPO_ROOT_PREFIXES",
]

# ── Patterns ──────────────────────────────────────────────────────────────────

# `.github/skills/<name>/SKILL.md` path occurrences in any context.
# Excludes angle-bracket placeholders like `<name>` used in documentation prose.
_SKILL_PATH_RE = re.compile(r"\.github/skills/([^/\s`\)\"'<>]+)/SKILL\.md")

# Markdown link targets: [text](target)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Shell script path in a hooks.json command string (e.g. "bash .github/hooks/foo.sh").
# Excludes leading quotes (prevents capturing `".github/hooks/foo.sh` when the path is
# quoted in JSON) and requires whitespace, shell operator, or end-of-string after .sh
# (prevents false positives on extensions like .sh.bak).
_SH_PATH_RE = re.compile(r"""(?<!['\"])(\S+?\.sh)(?=\s|[\"';|&>]|$)""")

# Required hook event names per hooks.json schema
_REQUIRED_HOOK_EVENTS: frozenset[str] = frozenset(
    {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
)

# Top-level repo-root directory prefixes used for link resolution.
# Exported so callers (e.g. test_framework_agents.py) can import rather than duplicate.
REPO_ROOT_PREFIXES: tuple[str, ...] = (
    ".github/",
    "docs/",
    "schema/",
    "scripts/",
    "tests/",
    "wiki/",
    "raw/",
)


# ── Public API ────────────────────────────────────────────────────────────────


def extract_agent_skill_refs(agents_root: Path) -> dict[str, list[str]]:
    """Return mapping of persona stem → list of referenced skill directory names.

    Multi-strategy extraction (all applicable sections are processed; refs are
    deduplicated while preserving insertion order):

    1. **Primary** — lines under ``## Required skills / upstream references``
       containing ``.github/skills/<name>/SKILL.md`` path literals.
    2. **Secondary** — ``## Related skill`` section, extracts skill names from
       markdown link targets matching the same pattern.
    3. **Fallback** — any ``.github/skills/<name>/SKILL.md`` occurrence
       anywhere in the file (catches non-standard formats).
    """
    result: dict[str, list[str]] = {}
    for agent_file in sorted(agents_root.glob("*.md")):
        persona = agent_file.stem
        text = agent_file.read_text(encoding="utf-8")
        refs: list[str] = []

        for heading in (
            "## Required skills / upstream references",
            "## Related skill",
        ):
            body = _section_body(text, heading)
            if body.strip():
                for m in _SKILL_PATH_RE.finditer(body):
                    name = m.group(1)
                    if name not in refs:
                        refs.append(name)

        if not refs:
            for m in _SKILL_PATH_RE.finditer(text):
                name = m.group(1)
                if name not in refs:
                    refs.append(name)

        result[persona] = refs
    return result


def extract_copilot_instruction_refs(
    instructions_path: Path,
) -> dict[str, list[str]]:
    """Return dict with keys ``skills`` and ``scripts``.

    - ``skills``: skill directory names referenced via
      ``.github/skills/<name>/SKILL.md`` occurrences.
    - ``scripts``: script file paths from ``python3 scripts/...`` commands.
    """
    text = instructions_path.read_text(encoding="utf-8")

    skills: list[str] = []
    for m in _SKILL_PATH_RE.finditer(text):
        name = m.group(1)
        if name not in skills:
            skills.append(name)

    scripts: list[str] = []
    for m in re.finditer(r"python3\s+(scripts/[^\s`'\"]+)", text):
        path = m.group(1).rstrip(".,;)")
        if path not in scripts:
            scripts.append(path)

    return {"skills": skills, "scripts": scripts}


def validate_hooks_json(hooks_path: Path, repo_root: Path) -> list[str]:
    """Return list of error strings; empty list means valid.

    Validates:
    1. File is readable.
    2. Valid JSON syntax.
    3. Top-level ``hooks`` key is a dict.
    4. All four required event keys present.
    5. Each event value is a list of hook-entry dicts with a ``command`` field.
    6. Each ``*.sh`` path in a command string resolves to a real file.
    """
    errors: list[str] = []

    try:
        text = hooks_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read {hooks_path}: {exc}"]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{hooks_path}: invalid JSON — {exc}"]

    if not isinstance(data, dict) or "hooks" not in data:
        return [f"{hooks_path}: missing top-level 'hooks' key"]

    hooks = data["hooks"]
    if not isinstance(hooks, dict):
        return [f"{hooks_path}: 'hooks' must be a mapping"]

    for evt in sorted(_REQUIRED_HOOK_EVENTS - hooks.keys()):
        errors.append(f"{hooks_path}: missing required hook event '{evt}'")

    for event, entries in hooks.items():
        if not isinstance(entries, list):
            errors.append(f"{hooks_path}: event '{event}' value must be a list")
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(
                    f"{hooks_path}: event '{event}' entry[{i}] must be a dict"
                )
                continue
            if "command" not in entry:
                errors.append(
                    f"{hooks_path}: event '{event}' entry[{i}]"
                    f" missing required 'command' field"
                )
                continue
            command = entry["command"]
            for sh_m in _SH_PATH_RE.finditer(command):
                sh_path = sh_m.group(1)
                resolved = (repo_root / sh_path).resolve()
                if not resolved.is_relative_to(repo_root.resolve()):
                    errors.append(
                        f"{hooks_path}: event '{event}' entry[{i}]"
                        f" script path escapes repo root: {sh_path}"
                    )
                elif not resolved.is_file():
                    errors.append(
                        f"{hooks_path}: event '{event}' entry[{i}]"
                        f" references missing script: {sh_path}"
                    )

    return errors


def extract_prompt_links(
    prompts_dir: Path,
    repo_root: Path,
) -> dict[str, list[tuple[str, bool]]]:
    """Return mapping of prompt filename → [(link_target, resolved_ok)].

    Only local links are checked (http://, https://, and mailto: are skipped).
    Anchor fragments (#section) are stripped before path resolution.
    """
    result: dict[str, list[tuple[str, bool]]] = {}
    for prompt_file in sorted(prompts_dir.glob("*.prompt.md")):
        text = prompt_file.read_text(encoding="utf-8")
        links: list[tuple[str, bool]] = []
        for m in _MD_LINK_RE.finditer(text):
            target = m.group(1)
            if "://" in target or target.startswith("mailto:"):
                continue
            target_path = target.split("#")[0].strip()
            if not target_path:
                continue
            resolved = _resolve_link(prompt_file, target_path, repo_root)
            links.append((target, resolved.exists()))
        result[prompt_file.name] = links
    return result


# ── Private helpers ───────────────────────────────────────────────────────────


def _section_body(text: str, heading: str) -> str:
    """Extract body of a markdown section from *heading* to the next ## heading."""
    start = text.find(heading)
    if start == -1:
        return ""
    body_start = start + len(heading)
    nxt = re.search(r"^#{1,2} ", text[body_start:], re.MULTILINE)
    if nxt:
        return text[body_start : body_start + nxt.start()]
    return text[body_start:]


def _resolve_link(source: Path, target: str, repo_root: Path) -> Path:
    """Resolve a markdown link *target* to an absolute Path."""
    if target.startswith("/"):
        # Absolute paths in .github/ prompt files don't make sense as cross-references.
        # Clamp to repo root so /etc/passwd doesn't resolve as an external file.
        return (repo_root / target.lstrip("/")).resolve()
    if target in {"AGENTS.md", "README.md"} or any(
        target.startswith(r) for r in REPO_ROOT_PREFIXES
    ):
        return (repo_root / target).resolve()
    # Relative to source file directory
    return (source.parent / target).resolve()
