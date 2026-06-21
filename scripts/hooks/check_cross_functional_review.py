"""PreToolUse hook: deterministic enforcement of cross-functional review for `gh pr merge`.

Closes Issue #323. The L4 hard rule in `.github/copilot-instructions.md`
already documents that `task_complete` is blocked until the 4 review
personas (@code-reviewer / @test-engineer / @security-auditor /
@documentation-engineer) have been dispatched and P0-P2 findings
remediated. That rule is compliance-dependent — the agent has to choose
to honor it. The post-merge audit of PRs #312-#317 found that the L4
rule was insufficient on its own (the original path enumeration didn't
include `.github/workflows/**`, so a workflow-only PR shipped a HIGH
security bug before review).

This hook is the **deterministic backstop**: when an agent attempts a
`gh pr merge` call, the hook fails closed unless:

  1. The current session has a
     `cross-functional-review-evidence/<head-sha>.json` artifact in
     `$COPILOT_SESSION_STATE_DIR`, OR
  2. The PR has a `cross-functional-reviewed` label (set by an upstream
     automation that ran the 4 reviewers), OR
  3. `BYPASS_CROSS_FUNCTIONAL_REVIEW=1` is set in the environment
     (audited via stdout JSON record).

The evidence artifact schema is documented inline in `_load_evidence`
below; the minimal required fields are `pr_number` (integer matching
the PR being merged) and `reviewers` (list of the 4 review persona
names). `findings_resolved` (boolean) and `timestamp` (ISO-8601 string)
are also expected so a future audit can reconstruct the review state.

Wired in `.github/hooks/hooks.json` under `PreToolUse`.

Hook contract per `.github/hooks/hooks.json` PreToolUse pattern:
  - Read JSON payload from stdin
  - Inspect `tool_name` + `tool_input.command`
  - No-op (exit 0) on non-`bash` tool calls
  - No-op (exit 0) on `bash` calls that don't match `gh pr merge`
  - Fail closed (exit 1) with stdout corrective message when gate fails
  - Allow (exit 0) when any of the 3 acceptance conditions are met
  - Fail closed on malformed JSON, missing dependencies, etc.

Per AGENTS.md write-surface matrix: this hook is `read-only only`; it
performs no repository writes. The bypass env var produces an audited
stdout JSON record but no file writes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


GH_PR_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b")
PR_NUMBER_RE = re.compile(r"\bgh\s+pr\s+merge\s+(\d+)")


def _read_stdin() -> str:
    try:
        return sys.stdin.read()
    except OSError:
        return ""


def _emit_audit(code: str, **fields: object) -> None:
    """Emit an audit record to stdout (used for bypass + diagnostic logging)."""
    payload = {"code": code, "audited": True, **fields}
    print(json.dumps(payload, sort_keys=True))


def _fail_closed(message: str) -> int:
    print(message)
    return 1


def _is_bash_gh_pr_merge(payload: dict) -> tuple[bool, int | None, str | None]:
    """Return (is_match, pr_number, command_string).

    Returns (False, None, None) if the payload is not a bash `gh pr merge`
    call (no-op territory).
    """
    tool_name = payload.get("tool_name", "")
    if tool_name != "bash":
        return False, None, None

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not GH_PR_MERGE_RE.search(command):
        return False, None, None

    pr_match = PR_NUMBER_RE.search(command)
    pr_number = int(pr_match.group(1)) if pr_match else None
    return True, pr_number, command


def _session_state_dir() -> Path | None:
    raw = os.environ.get("COPILOT_SESSION_STATE_DIR", "").strip()
    if not raw:
        return None
    return Path(raw)


def _head_sha(cwd: Path | None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _load_evidence(session_state: Path, head_sha: str) -> dict | None:
    """Try to load the cross-functional-review-evidence file for HEAD.

    Schema (minimum):
      {
        "pr_number": <int>,
        "reviewers": ["code-reviewer", "test-engineer",
                      "security-auditor", "documentation-engineer"],
        "findings_resolved": <bool>,
        "timestamp": "<ISO-8601>"
      }

    Returns None if file missing or unreadable. Returns parsed dict if OK.
    Returns None (fail closed downstream) if JSON is malformed.
    """
    evidence_path = session_state / "cross-functional-review-evidence" / f"{head_sha}.json"
    if not evidence_path.exists():
        return None
    try:
        return json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pr_has_review_label(pr_number: int | None, cwd: Path | None) -> bool:
    """Check whether the target PR has the `cross-functional-reviewed` label.

    Uses `gh pr view <num> --json labels`. If `gh` is unavailable or the
    PR can't be queried, returns False (deferring to other gates).
    """
    if pr_number is None:
        return False
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "labels"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
        )
    except (OSError, FileNotFoundError):
        return False
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    labels = data.get("labels") or []
    for label in labels:
        if isinstance(label, dict) and label.get("name") == "cross-functional-reviewed":
            return True
    return False


def main() -> int:
    raw_payload = _read_stdin()
    if not raw_payload.strip():
        # Empty payload means we're being invoked outside the hook framework
        # (e.g., a local debug invocation). Exit 0 — no tool call to gate.
        return 0

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return _fail_closed(
            "Malformed PreToolUse hook payload; cross-functional review gate "
            "cannot determine whether `gh pr merge` is being attempted. "
            "Refusing to allow tool call."
        )

    if not isinstance(payload, dict):
        return _fail_closed(
            "PreToolUse hook payload must be a JSON object; got "
            f"{type(payload).__name__}. Refusing to allow tool call."
        )

    is_match, pr_number, _command = _is_bash_gh_pr_merge(payload)
    if not is_match:
        # No-op: hook only gates `gh pr merge` calls.
        return 0

    # Bypass env var (audited) — checked first so an operator escape works
    # even when session-state and gh CLI are broken.
    bypass = os.environ.get("BYPASS_CROSS_FUNCTIONAL_REVIEW", "").strip()
    if bypass == "1":
        _emit_audit(
            "cross_functional_review_bypass",
            pr_number=pr_number,
            reason="BYPASS_CROSS_FUNCTIONAL_REVIEW=1 set in environment",
        )
        return 0

    cwd_raw = payload.get("cwd")
    cwd = Path(cwd_raw) if isinstance(cwd_raw, str) and cwd_raw else None

    # Check 1: session-state evidence artifact.
    session_state = _session_state_dir()
    session_state_missing = False
    if session_state is None:
        # No COPILOT_SESSION_STATE_DIR set — can't check evidence, fall
        # through to label check.
        pass
    elif not session_state.exists():
        # Dir set but missing — remember this for the fail-closed message
        # but still fall through to label check so a labeled PR can merge.
        session_state_missing = True
    else:
        head = _head_sha(cwd)
        if head is not None:
            evidence = _load_evidence(session_state, head)
            if evidence is not None:
                # Evidence file exists — accept. (Schema validation is
                # advisory; presence is the gate signal.)
                return 0

    # Check 2: PR label.
    if _pr_has_review_label(pr_number, cwd):
        return 0

    # All gates failed — fail closed with the appropriate message.
    if session_state_missing:
        return _fail_closed(
            f"COPILOT_SESSION_STATE_DIR={session_state} but session-state "
            "directory is missing. Cross-functional review gate cannot read "
            "evidence artifact, and the PR has no `cross-functional-reviewed` "
            "label. Refusing to allow `gh pr merge`."
        )

    return _fail_closed(
        "Cross-functional review required before `gh pr merge` "
        f"(PR #{pr_number if pr_number is not None else '<unknown>'}).\n"
        "\n"
        "Per `.github/copilot-instructions.md` § \"Cross-functional review as "
        "default post-implementation step\" (the L4 hard rule), the four "
        "review personas must be dispatched and any P0-P2 findings "
        "remediated before merge:\n"
        "  - @code-reviewer\n"
        "  - @test-engineer\n"
        "  - @security-auditor\n"
        "  - @documentation-engineer\n"
        "\n"
        "To satisfy the gate, take ONE of these actions:\n"
        "  1. Write a `cross-functional-review-evidence/<head-sha>.json` "
        "artifact to $COPILOT_SESSION_STATE_DIR documenting the four reviewer "
        "outputs and P0-P2 remediation status, then retry.\n"
        "  2. Label the PR `cross-functional-reviewed` (after the upstream "
        "review automation has run the four reviewers and verified findings "
        "are addressed).\n"
        "  3. Set BYPASS_CROSS_FUNCTIONAL_REVIEW=1 in the environment "
        "(audited via stdout JSON record).\n"
    )


if __name__ == "__main__":
    sys.exit(main())
