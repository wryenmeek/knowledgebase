"""Commit-scope check: gate B (sensitive-paths) and gate C (deletion-ratio).

Gate B — sensitive-paths acknowledgement
    Fires when a PR touches a path in SENSITIVE_PATHS and neither the PR title
    nor the PR body's first line names the surface via word-boundary token match.

Gate C — deletion-ratio guard
    Fires when (deletions - insertions) > 50 and the PR carries neither a
    verified ``Reverts:`` trailer nor a ``Cleanup: <reason>`` trailer (>= 10
    chars) in the last commit message footer or the last paragraph of the PR
    body.

Both gates run independently; either failing blocks merge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

if __package__ in (None, ""):  # supports both ``python -m`` and direct invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.kb.contracts import SENSITIVE_PATHS

SURFACE = "scripts/validation/check_commit_scope.py"

# ---------------------------------------------------------------------------
# Gate B — sensitive-paths acknowledgement
# ---------------------------------------------------------------------------

# Canonical token set for gate B word-boundary matching.
# Each token maps to one or more sensitive path prefixes (see _PATH_TO_TOKENS).
# Pure substring matching is intentionally rejected to prevent false negatives
# such as ``wikipedia`` matching ``wiki`` or ``Adrian`` matching ``adr``.
GATE_B_TOKENS: frozenset[str] = frozenset(
    {
        "wiki",
        "schema",
        "adr",
        "adrs",
        "agents",
        "copilot",
        "contracts",
        "write_utils",
        "spec",
        "workflows",
        "pre-commit",
    }
)

# Build the regex from the token set (longest tokens first to avoid partial
# shadowing; the alternation is anchored by \b so ordering is irrelevant for
# correctness, but longest-first is conventional).
_GATE_B_TOKEN_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(t) for t in sorted(GATE_B_TOKENS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Map: sensitive path prefix → tuple of gate B tokens that satisfy the check.
# A PR touching ``prefix`` passes gate B when any of its tokens appears in the
# PR title or body first line (word-boundary matched).
_PATH_TO_TOKENS: dict[str, tuple[str, ...]] = {
    "wiki/": ("wiki",),
    "schema/": ("schema",),
    "docs/decisions/": ("adr", "adrs"),
    "AGENTS.md": ("agents",),
    ".github/copilot-instructions.md": ("copilot",),
    "scripts/kb/contracts.py": ("contracts",),
    "scripts/kb/write_utils.py": ("write_utils",),
    "raw/processed/SPEC.md": ("spec",),
    ".pre-commit-config.yaml": ("pre-commit",),
    ".github/workflows/": ("workflows",),
}


def _sensitive_surface_for(path: str) -> str | None:
    """Return the SENSITIVE_PATHS prefix that *path* falls under, or ``None``."""
    for prefix in SENSITIVE_PATHS:
        if path == prefix or path.startswith(prefix):
            return prefix
    return None


def _present_tokens(text: str) -> frozenset[str]:
    """Return lowercased gate-B tokens found in *text* (word-boundary matched)."""
    return frozenset(m.lower() for m in _GATE_B_TOKEN_RE.findall(text))


def check_gate_b(
    pr_title: str,
    pr_body: str,
    changed_paths: Sequence[str],
) -> tuple[bool, list[str]]:
    """Gate B: sensitive-paths acknowledgement check.

    Returns ``(passed, error_messages)``.

    Passes when every sensitive surface touched by the diff is named — via a
    word-boundary token match — in the PR title or the first line of the PR
    body.
    """
    body_first_line = (pr_body or "").splitlines()[0].strip() if pr_body else ""
    combined = f"{pr_title}\n{body_first_line}"
    tokens = _present_tokens(combined)

    uncovered: set[str] = set()
    for path in changed_paths:
        surface = _sensitive_surface_for(path)
        if surface is None:
            continue
        covering = _PATH_TO_TOKENS.get(surface, ())
        if not any(tok.lower() in tokens for tok in covering):
            uncovered.add(surface)

    if not uncovered:
        return True, []

    needed_tokens = sorted(
        {tok for surf in uncovered for tok in _PATH_TO_TOKENS.get(surf, ())}
    )
    surfaces_str = ", ".join(f"'{s}'" for s in sorted(uncovered))
    return False, [
        f"Gate B failed: PR touches sensitive path(s) {surfaces_str} but neither "
        f"the PR title nor the PR body's first line contains a word-boundary token "
        f"naming the surface. Add one of: {', '.join(needed_tokens)}. "
        f"See docs/conventions/commit-trailers.md for guidance."
    ]


# ---------------------------------------------------------------------------
# Gate C — deletion-ratio guard
# ---------------------------------------------------------------------------

GATE_C_NET_DELETION_THRESHOLD = 50

# Git footer trailer: ``Token: Value`` at the start of a line.
_TRAILER_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s+(.+)$")

# Valid ``Reverts:`` target formats.
_REVERTS_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
# Matches ``#N`` or ``owner/repo#N`` (cross-repo references to this repo).
_REVERTS_REF_RE = re.compile(r"^(?:[^/\s]+/[^#\s]+)?#(\d+)$")


def _last_paragraph(text: str) -> str:
    """Return the last paragraph of *text* (blocks separated by blank lines)."""
    paragraphs = re.split(r"\n[ \t]*\n", (text or "").strip())
    return paragraphs[-1].strip() if paragraphs else ""


def _extract_trailers(text: str) -> list[tuple[str, str]]:
    """Extract Git-style footer trailers (``Token: Value``) from a text block."""
    trailers = []
    for line in text.splitlines():
        m = _TRAILER_LINE_RE.match(line)
        if m:
            trailers.append((m.group(1), m.group(2).strip()))
    return trailers


def _trailers_in_last_paragraph(text: str) -> list[tuple[str, str]]:
    """Return trailers found in the last paragraph of *text*."""
    return _extract_trailers(_last_paragraph(text))


def _default_reverts_validator(value: str) -> bool:
    """Validate a ``Reverts:`` trailer value using ``gh`` CLI and ``git``.

    Accepts ``#N``, ``owner/repo#N``, or a 40-hex commit SHA.
    Returns ``True`` if the reference is verifiable in this repo, ``False``
    otherwise.
    """
    value = value.strip()

    # SHA form: must be a commit reachable from main.
    if _REVERTS_SHA_RE.match(value):
        try:
            subprocess.run(
                ["git", "cat-file", "-e", f"{value}^{{commit}}"],
                check=True,
                capture_output=True,
                timeout=15,
            )
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", value, "main"],
                check=True,
                capture_output=True,
                timeout=15,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False

    # ``#N`` or ``owner/repo#N`` form: check issue or PR exists in this repo.
    m = _REVERTS_REF_RE.match(value)
    if m:
        issue_num = m.group(1)
        for subcmd in ("issue", "pr"):
            try:
                result = subprocess.run(
                    ["gh", subcmd, "view", issue_num, "--json", "number"],
                    capture_output=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass
        return False

    return False  # unknown or unsupported format


def check_gate_c(
    insertions: int,
    deletions: int,
    pr_body: str,
    last_commit_msg: str,
    *,
    reverts_validator: Callable[[str], bool] | None = None,
) -> tuple[bool, list[str]]:
    """Gate C: deletion-ratio check.

    Returns ``(passed, error_messages)``.

    Passes when ``(deletions - insertions) <= 50``, or when a valid
    ``Reverts:`` or ``Cleanup:`` trailer appears in the last commit message
    footer or the last paragraph of the PR body.
    """
    net = deletions - insertions
    if net <= GATE_C_NET_DELETION_THRESHOLD:
        return True, []

    if reverts_validator is None:
        reverts_validator = _default_reverts_validator

    # Collect trailers from the last paragraph of each text source.
    commit_trailers = _trailers_in_last_paragraph(last_commit_msg)
    body_trailers = _trailers_in_last_paragraph(pr_body)

    for key, val in commit_trailers + body_trailers:
        if key.lower() == "reverts":
            val_stripped = val.strip()
            if _REVERTS_SHA_RE.match(val_stripped) or _REVERTS_REF_RE.match(
                val_stripped
            ):
                if reverts_validator(val_stripped):
                    return True, []
        elif key.lower() == "cleanup":
            if len(val.strip()) >= 10:
                return True, []

    return False, [
        f"Gate C failed: net deletion of {net} lines (deletions={deletions}, "
        f"insertions={insertions}) exceeds threshold (>{GATE_C_NET_DELETION_THRESHOLD}). "
        f"Add a verified 'Reverts: #N' or 'Reverts: <40-hex-SHA>' Git footer trailer "
        f"to the last commit message or the last paragraph of the PR body, OR add "
        f"'Cleanup: <reason>' (>= 10 chars) to explain the deletion. "
        f"See docs/conventions/commit-trailers.md for guidance."
    ]


# ---------------------------------------------------------------------------
# Subprocess helpers for CI entry point
# ---------------------------------------------------------------------------


def _get_pr_files(pr_number: str) -> list[dict[str, object]]:
    """Return list of changed files with additions/deletions for *pr_number*."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--json", "files"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(
                f"::warning::gh pr view failed (exit {result.returncode}): "
                f"{result.stderr.strip()}",
            )
            return []
        data = json.loads(result.stdout)
        return data.get("files", [])
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        print(f"::warning::Could not fetch PR files: {exc}")
        return []


def _get_last_commit_msg() -> str:
    """Return the message of the HEAD commit (last commit of the PR head ref)."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%B", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    pr_number = os.environ.get("PR_NUMBER", "").strip()
    pr_title = os.environ.get("PR_TITLE", "").strip()
    pr_body = os.environ.get("PR_BODY", "")

    if not pr_number:
        print("::error::PR_NUMBER environment variable is required.", file=sys.stderr)
        return 1

    files = _get_pr_files(pr_number)
    changed_paths = [str(f.get("filename", "")) for f in files]
    insertions = sum(int(f.get("additions", 0)) for f in files)
    deletions = sum(int(f.get("deletions", 0)) for f in files)
    last_commit = _get_last_commit_msg()

    b_passed, b_errors = check_gate_b(pr_title, pr_body, changed_paths)
    c_passed, c_errors = check_gate_c(insertions, deletions, pr_body, last_commit)

    all_errors = b_errors + c_errors
    if all_errors:
        for err in all_errors:
            print(f"::error::{err}")
        gate_labels = []
        if not b_passed:
            gate_labels.append("B")
        if not c_passed:
            gate_labels.append("C")
        print(
            f"\n{SURFACE}: gate(s) {', '.join(gate_labels)} failed. "
            f"See docs/conventions/commit-trailers.md for remediation guidance.",
            file=sys.stderr,
        )
        return 1

    print(f"{SURFACE}: gates B and C both passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
