"""Comprehensive SHA-pin regression test for GitHub workflows + composite actions.

Asserts that no workflow or composite-action file contains floating action
references (@vN, @main, @latest) so that supply-chain pinning cannot
silently regress when contributors add new steps.

Two complementary approaches are used:
  1. Denylist: flag known floating patterns (fast, human-readable error message).
  2. Allowlist: require every external uses: line to be a 40-hex-char SHA
     (catches unknown aliases like @HEAD, @release-x, or partial SHAs).

**Coverage scope** (extended 2026-06-27 per audit P2):
- `.github/workflows/*.yml`
- `.github/actions/<name>/action.yml` — composite actions carry the same
  supply-chain risk; ADR-036 § Amendment elevated `.github/actions/**` to
  formal sensitive-path status.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


WORKFLOWS_DIR = Path(".github/workflows")
ACTIONS_DIR = Path(".github/actions")

# Local/reusable workflow refs start with './' and don't need SHA pinning.
_LOCAL_REF_PATTERN = re.compile(r"^\s+uses:\s+\./")

# Matches any external uses: line that has an @ ref.
_EXTERNAL_USES_PATTERN = re.compile(r"^\s+uses:\s+\S+@")

# A pinned ref uses a 40-hex-char SHA (optionally followed by a space and comment).
_PINNED_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@[0-9a-f]{40}",
    re.MULTILINE,
)

# Known floating patterns — word-boundary anchor (\b) so trailing comments
# like `@v4  # update later` do NOT escape detection.
_FLOATING_REF_PATTERN = re.compile(
    r"^\s+uses:\s+\S+@(?:main|master|latest|v\d[\w.]*)\b",
    re.MULTILINE,
)


def _all_workflow_and_action_files() -> list[Path]:
    """Return all workflow files + composite action.yml files."""
    files: list[Path] = list(WORKFLOWS_DIR.glob("*.yml"))
    if ACTIONS_DIR.is_dir():
        files.extend(ACTIONS_DIR.glob("**/action.yml"))
    assert files, (
        f"No workflow files found in {WORKFLOWS_DIR} or {ACTIONS_DIR}"
    )
    return sorted(files)


@pytest.fixture(scope="module")
def workflow_files() -> list[Path]:
    return _all_workflow_and_action_files()


def test_no_floating_action_refs(workflow_files: list[Path]) -> None:
    """No workflow or composite action may use a known floating ref (@vN, @main, @latest).

    Supply-chain attacks exploit floating refs to inject malicious code via
    a tag move. All third-party action refs must be pinned to a full SHA.

    The \\b word boundary ensures refs like `@v4  # TODO: pin` are still caught
    even when a trailing comment follows the version token.
    """
    failures: list[str] = []
    for wf_path in workflow_files:
        text = wf_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _LOCAL_REF_PATTERN.match(line):
                continue
            if _FLOATING_REF_PATTERN.match(line):
                failures.append(
                    f"{wf_path}:{lineno} — floating action ref: {line.strip()!r}"
                )
    assert not failures, (
        "Floating action refs detected (pin to a full 40-char SHA):\n"
        + "\n".join(failures)
    )


def test_all_external_uses_are_sha_pinned(workflow_files: list[Path]) -> None:
    """Every external uses: line must reference a full 40-hex-character SHA.

    This allowlist catches aliases not covered by the denylist:
    @HEAD, @release-2026, partial SHAs (abc1234), custom tags, etc.
    """
    failures: list[str] = []
    for wf_path in workflow_files:
        text = wf_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not _EXTERNAL_USES_PATTERN.match(line):
                continue
            if _LOCAL_REF_PATTERN.match(line):
                continue
            if not _PINNED_REF_PATTERN.match(line):
                failures.append(
                    f"{wf_path}:{lineno} — not SHA-pinned: {line.strip()!r}"
                )
    assert not failures, (
        "Action refs not SHA-pinned (pin to a full 40-char SHA):\n"
        + "\n".join(failures)
    )


def test_pinned_refs_have_version_comments(workflow_files: list[Path]) -> None:
    """SHA-pinned refs should carry a # vX comment for human readability.

    Soft check — fails only when a pinned ref has no comment at all,
    since uncommented SHAs are opaque to reviewers.
    """
    failures: list[str] = []
    pat = re.compile(r"@[0-9a-f]{40}\s+#")
    for wf_path in workflow_files:
        text = wf_path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not _PINNED_REF_PATTERN.match(line):
                continue
            if _LOCAL_REF_PATTERN.match(line):
                continue
            if not pat.search(line):
                failures.append(
                    f"{wf_path}:{lineno} — SHA-pinned ref missing version comment: "
                    f"{line.strip()!r}"
                )
    assert not failures, "Missing version comments:\n" + "\n".join(failures)


def test_pages_deploy_token_not_inlined_in_run_blocks() -> None:
    """pages.yml must not inline ${{ secrets.* }} in run: shell blocks.

    Passing a token inline in a shell command exposes it in argv
    (visible in /proc/<pid>/cmdline) and git diagnostics. The modernised
    deployment uses actions/deploy-pages with OIDC — no token is needed
    in a run: block at all.

    Uses YAML parse to accurately scope the check to run: values only
    (avoids false-matches on env: blocks or step metadata).
    """
    text = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run_val = step.get("run", "")
            if run_val:
                assert "${{ secrets.GITHUB_TOKEN }}" not in str(run_val), (
                    "pages.yml must not inline ${{ secrets.GITHUB_TOKEN }} in a run: block"
                )
    # Positive assertion: deployment must use the OIDC-based actions/deploy-pages
    # (no DEPLOY_TOKEN needed — token exposure in argv/git config is eliminated).
    assert "actions/deploy-pages" in text, (
        "pages.yml must use actions/deploy-pages for OIDC-based deployment (no PAT needed)"
    )
    assert "actions/upload-pages-artifact" in text, (
        "pages.yml must upload site/ via actions/upload-pages-artifact before deploying"
    )
    # DEPLOY_TOKEN (ghp_import pattern) must be absent — replaced by OIDC deploy.
    assert "ghp_import" not in text, (
        "pages.yml must not use ghp_import — replaced by actions/deploy-pages"
    )
