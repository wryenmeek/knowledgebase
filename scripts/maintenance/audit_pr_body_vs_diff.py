"""Post-merge PR body-vs-diff drift audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence, TextIO

if __package__ in (
    None,
    "",
):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_OK,
    STATUS_FAIL,
    STATUS_PASS,
    SurfaceResult,
    add_common_surface_args,
    base_path_rules,
    invalid_input_result,
    looks_like_repo_root,
    repo_root_failure,
    run_surface_cli,
)

SURFACE = "scripts/maintenance/audit_pr_body_vs_diff.py"
SUPPORTED_MODES: tuple[str, ...] = ("audit",)
GH_COMMAND_TIMEOUT_SECONDS = 30
PATH_EXTENSIONS: tuple[str, ...] = (
    "py",
    "ts",
    "md",
    "yml",
    "yaml",
    "json",
    "sh",
    "tsx",
    "js",
    "toml",
    "txt",
)
REASON_CODE_GH_CLI_FAILED = "gh_cli_failed"
REASON_CODE_BODY_DIFF_DRIFT = "body_diff_drift_detected"
REASON_CODE_EMPTY_DIFF_TYPE_C = "severity_1_empty_diff_type_c"
REASON_CODE_UNMET_BODY_CLAIM = "unmet_body_claim"
REASON_CODE_CLAIM_SATISFIED = "claim_satisfied"
REASON_CODE_COMMENT_POST_FAILED = "comment_post_failed"

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_URL_PATTERN = re.compile(r"https?://[^\s)\]>}]+", re.IGNORECASE)
_CODE_SPAN_PATTERN = re.compile(r"`([^`\n]+)`")
_PATH_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"(\.?[A-Za-z_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)*\."
    rf"(?:{'|'.join(PATH_EXTENSIONS)}))"
    r"(?![A-Za-z0-9_./-])"
)
_STRIP_CHARS = "'\"“”‘’,;:()[]{}<>"


class GhCommandError(RuntimeError):
    """Raised when a gh CLI command cannot complete."""


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Audit a merged PR body against its actual diff file list."
    )
    add_common_surface_args(
        parser,
        modes=SUPPORTED_MODES,
        default_mode="audit",
        include_path=False,
        include_approval=False,
    )
    parser.add_argument(
        "--pr",
        dest="pr_number",
        required=True,
        type=int,
        help="Pull request number to audit.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional owner/repo. Defaults to gh's current repository.",
    )
    parser.add_argument(
        "--no-comment",
        action="store_true",
        default=False,
        help="Skip advisory GitHub comments.",
    )
    parser.add_argument(
        "--issues-json",
        dest="issues_json_path",
        default=None,
        help=(
            "Optional repo-relative JSON fixture containing PR body and diff files. "
            "When supplied, no gh CLI calls are made."
        ),
    )
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(allowed_roots=["."], allowed_suffixes=[".json"])
    rules["read_only"] = True
    rules["source"] = "gh_cli_or_repo_fixture"
    rules["external_side_effects"] = "optional gh issue comment advisory only"
    return rules


def _resolve_repo_json_path(repo_root: Path, raw_path: str) -> Path:
    normalized = raw_path.strip()
    if not normalized:
        raise ValueError("--issues-json must be a non-empty repo-relative JSON path")
    candidate = Path(normalized)
    if candidate.is_absolute():
        raise ValueError("--issues-json must be repo-relative")
    resolved = (repo_root / candidate).resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError("--issues-json escapes repository root")
    if not resolved.is_file() or resolved.suffix.lower() != ".json":
        raise ValueError(
            "--issues-json must reference an existing .json file in the repository"
        )
    return resolved


def _normalize_path_claim(raw_path: str) -> str | None:
    normalized = raw_path.strip().strip(_STRIP_CHARS).rstrip(".")
    normalized = normalized.removeprefix("./")
    if (
        not normalized
        or "://" in normalized
        or normalized.lower().startswith(("http:", "https:"))
    ):
        return None
    if " " in normalized or "\t" in normalized or "\n" in normalized:
        return None
    if not _PATH_TOKEN_PATTERN.fullmatch(normalized):
        return None
    return normalized


def extract_file_mentions(body: str) -> tuple[str, ...]:
    """Return distinct repo-relative file mentions from a PR body."""

    claims: set[str] = set()
    for match in _CODE_SPAN_PATTERN.finditer(body):
        raw_span = match.group(1)
        for token in re.split(r"\s+", raw_span):
            normalized = _normalize_path_claim(token)
            if normalized is not None:
                claims.add(normalized)

    body_without_urls = _URL_PATTERN.sub(" ", body)
    for match in _PATH_TOKEN_PATTERN.finditer(body_without_urls):
        normalized = _normalize_path_claim(match.group(1))
        if normalized is not None:
            claims.add(normalized)
    return tuple(sorted(claims))


def _coerce_int(
    value: Any, *, field_name: str, default: int | None = None
) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"PR fixture field '{field_name}' must be an integer")
    return value


def _coerce_file_list(raw_files: Any) -> tuple[str, ...]:
    if raw_files is None:
        return ()
    if not isinstance(raw_files, list):
        raise ValueError("PR fixture files must be a list")
    files: set[str] = set()
    for entry in raw_files:
        raw_path: Any
        if isinstance(entry, str):
            raw_path = entry
        elif isinstance(entry, Mapping):
            raw_path = entry.get("path") or entry.get("filename") or entry.get("name")
        else:
            raise ValueError("PR fixture files must contain strings or file objects")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("PR fixture file paths must be non-empty strings")
        normalized = raw_path.strip().removeprefix("./")
        if normalized.startswith("/") or "\x00" in normalized or "://" in normalized:
            raise ValueError(f"invalid PR fixture file path: {raw_path}")
        files.add(normalized)
    return tuple(sorted(files))


def _normalize_pr_payload(raw_pr: Any) -> dict[str, Any]:
    if not isinstance(raw_pr, Mapping):
        raise ValueError("PR fixture entries must be objects")
    number_raw = raw_pr.get("number")
    if isinstance(number_raw, str) and number_raw.isdigit():
        number_raw = int(number_raw)
    if isinstance(number_raw, bool) or not isinstance(number_raw, int):
        raise ValueError("PR fixture number must be an integer")
    body_raw = raw_pr.get("body", "")
    if body_raw is None:
        body_raw = ""
    if not isinstance(body_raw, str):
        raise ValueError(f"PR #{number_raw} body must be a string")
    title_raw = raw_pr.get("title", "")
    if not isinstance(title_raw, str):
        raise ValueError(f"PR #{number_raw} title must be a string")
    url_raw = raw_pr.get("url", "")
    if not isinstance(url_raw, str):
        raise ValueError(f"PR #{number_raw} url must be a string")
    raw_files = raw_pr.get(
        "files", raw_pr.get("diff_files", raw_pr.get("changed_files", []))
    )
    diff_files = _coerce_file_list(raw_files)
    changed_files = _coerce_int(
        raw_pr.get("changedFiles", raw_pr.get("changed_files_count")),
        field_name="changedFiles",
        default=len(diff_files),
    )
    additions = _coerce_int(raw_pr.get("additions"), field_name="additions", default=0)
    deletions = _coerce_int(raw_pr.get("deletions"), field_name="deletions", default=0)
    return {
        "number": number_raw,
        "title": title_raw,
        "url": url_raw,
        "body": body_raw,
        "diff_files": diff_files,
        "changed_files": changed_files,
        "additions": additions,
        "deletions": deletions,
    }


def _parse_pr_fixture_payload(payload: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(payload, Mapping):
        if "pull_requests" in payload:
            entries = payload["pull_requests"]
        elif "prs" in payload:
            entries = payload["prs"]
        elif "number" in payload:
            entries = [payload]
        else:
            raise ValueError(
                "PR fixture payload must contain 'pull_requests', 'prs', or a single PR object"
            )
    else:
        entries = payload
    if not isinstance(entries, list):
        raise ValueError(
            "PR fixture payload must be a list or object containing a PR list"
        )
    return tuple(_normalize_pr_payload(entry) for entry in entries)


def _load_pr_from_fixture(
    repo_root: Path, issues_json_path: str, pr_number: int
) -> dict[str, Any]:
    resolved = _resolve_repo_json_path(repo_root, issues_json_path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"could not parse --issues-json fixture: {exc}") from exc
    prs = _parse_pr_fixture_payload(payload)
    for pr in prs:
        if pr["number"] == pr_number:
            return pr
    raise ValueError(f"--issues-json fixture does not contain PR #{pr_number}")


def _run_gh(
    command: Sequence[str], *, repo_root: Path, input_text: str | None = None
) -> str:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            input=input_text,
            text=True,
            timeout=GH_COMMAND_TIMEOUT_SECONDS,
            cwd=repo_root,
        )
    except FileNotFoundError as exc:
        raise GhCommandError("gh CLI is required but not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise GhCommandError(
            f"gh command timed out after {GH_COMMAND_TIMEOUT_SECONDS} seconds"
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip().splitlines()
        stderr_snippet = stderr[0] if stderr else "unknown gh error"
        raise GhCommandError(f"gh command failed: {stderr_snippet}")
    return completed.stdout


def _append_repo_flag(command: list[str], repo: str | None) -> list[str]:
    if repo is not None:
        command.extend(["--repo", repo])
    return command


def _load_pr_from_gh(
    repo_root: Path, pr_number: int, repo: str | None
) -> dict[str, Any]:
    view_command = _append_repo_flag(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "number,title,url,body,additions,deletions,changedFiles",
        ],
        repo,
    )
    raw_view = _run_gh(view_command, repo_root=repo_root)
    try:
        view_payload = json.loads(raw_view)
    except json.JSONDecodeError as exc:
        raise GhCommandError("gh pr view returned malformed JSON") from exc
    pr = _normalize_pr_payload({**view_payload, "files": []})

    diff_command = _append_repo_flag(
        ["gh", "pr", "diff", str(pr_number), "--name-only"], repo
    )
    diff_output = _run_gh(diff_command, repo_root=repo_root)
    pr["diff_files"] = tuple(
        sorted({line.strip() for line in diff_output.splitlines() if line.strip()})
    )
    pr["changed_files"] = len(pr["diff_files"])
    return pr


def _severity_comment(pr: Mapping[str, Any]) -> str:
    return f"""### Severity 1: empty merged PR diff detected

Post-merge body-vs-diff audit found PR #{pr["number"]} has `0 added, 0 deleted, 0 files`.

This is a Type C drift signature: the PR body or squash commit may describe work that did not ship. Review the merged commit and open remediation if shipped behavior differs from the PR description.
"""


def _drift_comment(
    *,
    pr: Mapping[str, Any],
    unmet_claims: Sequence[str],
    extra_diff_files: Sequence[str],
    drift_kind: str,
) -> str:
    unmet_lines = "\n".join(f"- `{path}`" for path in unmet_claims)
    extra_lines = (
        "\n".join(f"- `{path}`" for path in extra_diff_files)
        if extra_diff_files
        else "- _None_"
    )
    return f"""### Post-merge body-vs-diff audit warning

The merged PR body mentions file paths that are not present in the actual merged diff for PR #{pr["number"]}.

- Drift classification: `{drift_kind}`
- Unmet body file claims:
{unmet_lines}
- Diff files not mentioned in the body:
{extra_lines}

Recommendation: compare the PR body, squash commit message, and merged diff. If the PR described work that did not ship, open a remediation issue or follow-up PR and correct any release notes that inherited the stale description.
"""


def _post_comment(
    *, repo_root: Path, pr_number: int, repo: str | None, body: str
) -> None:
    command = _append_repo_flag(
        ["gh", "issue", "comment", str(pr_number), "--body-file", "-"], repo
    )
    _run_gh(command, repo_root=repo_root, input_text=body)


def _resolve_claim_matches(
    claims: Sequence[str], diff_files: Sequence[str]
) -> dict[str, str]:
    diff_set = set(diff_files)
    matches: dict[str, str] = {}
    basename_index: dict[str, list[str]] = {}
    for diff_file in diff_files:
        basename_index.setdefault(Path(diff_file).name, []).append(diff_file)

    for claim in claims:
        if claim in diff_set:
            matches[claim] = claim
            continue
        if "/" in claim or claim.startswith("."):
            continue
        basename_matches = basename_index.get(claim, [])
        if len(basename_matches) == 1:
            matches[claim] = basename_matches[0]
    return matches


def _drift_kind(*, is_type_c: bool, is_type_b_drift: bool, is_type_c_full: bool) -> str:
    if is_type_c:
        return "type_c_empty_diff"
    if is_type_b_drift:
        return "type_b_revert_absorption_suspected"
    if is_type_c_full:
        return "type_c_full_hallucination"
    return "body_diff_mismatch"


def run_pr_body_vs_diff_audit(
    *,
    repo_root: str | Path = ".",
    mode: str,
    pr_number: int,
    repo: str | None = None,
    no_comment: bool = False,
    issues_json_path: str | None = None,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(
            surface=SURFACE, mode=mode, approval=APPROVAL_NONE, path_rules=path_rules
        )
    if pr_number <= 0:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message="--pr must be a positive integer",
            path_rules=path_rules,
        )
    if repo is not None and not _REPO_PATTERN.fullmatch(repo):
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message="--repo must use owner/repo form",
            path_rules=path_rules,
        )

    fixture_mode = issues_json_path is not None
    try:
        pr = (
            _load_pr_from_fixture(normalized_repo_root, issues_json_path, pr_number)
            if issues_json_path is not None
            else _load_pr_from_gh(normalized_repo_root, pr_number, repo)
        )
    except ValueError as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message=str(exc),
            path_rules=path_rules,
        )
    except GhCommandError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_GH_CLI_FAILED,
            message=str(exc),
            approval=APPROVAL_NONE,
            path_rules=path_rules,
            summary={
                "pr_number": pr_number,
                "repo": repo or "current",
                "source": "gh_cli",
            },
        )

    claims = extract_file_mentions(pr["body"])
    diff_files = tuple(pr["diff_files"])
    claim_matches = _resolve_claim_matches(claims, diff_files)
    matched_claims = tuple(sorted(claim_matches))
    unmet_claims = tuple(
        sorted(claim for claim in claims if claim not in claim_matches)
    )
    matched_diff_files = set(claim_matches.values())
    extra_diff_files = tuple(sorted(set(diff_files).difference(matched_diff_files)))
    additions = pr.get("additions")
    deletions = pr.get("deletions")
    changed_files = len(diff_files)
    is_zero_zero_zero = additions == 0 and deletions == 0 and changed_files == 0
    is_type_c = bool(is_zero_zero_zero)
    # Full hallucination means every body file claim is absent from the shipped diff.
    is_type_c_full = bool(unmet_claims and len(matched_claims) == 0 and not is_type_c)
    # Type B drift is the mixed overlap case: some body claims shipped, some did not, and other files shipped.
    is_type_b_drift = bool(
        unmet_claims and extra_diff_files and matched_claims and not is_type_c
    )
    drift_kind = _drift_kind(
        is_type_c=is_type_c,
        is_type_b_drift=is_type_b_drift,
        is_type_c_full=is_type_c_full,
    )

    items: list[dict[str, Any]] = []
    if is_type_c:
        items.append(
            {
                "path": f"pull/{pr_number}",
                "status": STATUS_FAIL,
                "reason_code": REASON_CODE_EMPTY_DIFF_TYPE_C,
                "message": "severity-1 Type C signature detected: 0 added, 0 deleted, 0 files",
                "severity": 1,
            }
        )
    for claim in claims:
        is_met = claim in claim_matches
        items.append(
            {
                "path": claim,
                "status": STATUS_PASS if is_met else STATUS_FAIL,
                "reason_code": REASON_CODE_CLAIM_SATISFIED
                if is_met
                else REASON_CODE_UNMET_BODY_CLAIM,
                "message": "body file claim appears in diff"
                if is_met
                else "body file claim is absent from diff",
                "matched_diff_path": claim_matches.get(claim),
                "severity": 2 if not is_met else 0,
            }
        )

    comments_to_post: list[str] = []
    if is_type_c:
        comments_to_post.append(_severity_comment(pr))
    if unmet_claims:
        comments_to_post.append(
            _drift_comment(
                pr=pr,
                unmet_claims=unmet_claims,
                extra_diff_files=extra_diff_files,
                drift_kind=drift_kind,
            )
        )

    comments_posted_count = 0
    comment_errors: list[str] = []
    if comments_to_post and not no_comment and not fixture_mode:
        for comment_body in comments_to_post:
            try:
                _post_comment(
                    repo_root=normalized_repo_root,
                    pr_number=pr_number,
                    repo=repo,
                    body=comment_body,
                )
                comments_posted_count += 1
            except GhCommandError as exc:
                comment_errors.append(str(exc))
                items.append(
                    {
                        "path": f"pull/{pr_number}",
                        "status": STATUS_FAIL,
                        "reason_code": REASON_CODE_COMMENT_POST_FAILED,
                        "message": str(exc),
                        "severity": 2,
                    }
                )

    summary = {
        "pr_number": pr_number,
        "repo": repo or "current",
        "source": "issues_json" if fixture_mode else "gh_cli",
        "total_claims": len(claims),
        "claims": list(claims),
        "matched_claims": list(matched_claims),
        "resolved_claim_matches": dict(sorted(claim_matches.items())),
        "unmet_claims": list(unmet_claims),
        "extra_diff_files": list(extra_diff_files),
        "diff_files": list(diff_files),
        "additions": additions,
        "deletions": deletions,
        "changed_files": changed_files,
        "diff_signature": f"{additions} added, {deletions} deleted, {changed_files} files",
        "is_type_c": is_type_c,
        "is_type_b_drift": is_type_b_drift,
        "is_type_c_full": is_type_c_full,
        "drift_kind": drift_kind,
        "would_post_comment_count": len(comments_to_post),
        "comments_posted_count": comments_posted_count,
        "comments_skipped": bool(comments_to_post and (no_comment or fixture_mode)),
        "comment_errors": comment_errors,
    }

    drift_detected = is_type_c or bool(unmet_claims) or bool(comment_errors)
    if not claims and not is_type_c:
        message = "PR body contains no file-mention claims to audit"
    elif drift_detected:
        message = "PR body-vs-diff drift detected"
    else:
        message = "PR body file claims match the merged diff"

    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=STATUS_FAIL if drift_detected else STATUS_PASS,
        reason_code=REASON_CODE_BODY_DIFF_DRIFT if drift_detected else REASON_CODE_OK,
        message=message,
        approval=APPROVAL_NONE,
        path_rules=path_rules,
        items=tuple(items),
        summary=summary,
    )


def run_cli(
    argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout
) -> int:
    run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_pr_body_vs_diff_audit,
        args_to_kwargs=lambda a: {
            "repo_root": a.repo_root,
            "mode": a.mode,
            "pr_number": a.pr_number,
            "repo": a.repo,
            "no_comment": a.no_comment,
            "issues_json_path": a.issues_json_path,
        },
        output_stream=output_stream,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "extract_file_mentions",
    "run_pr_body_vs_diff_audit",
    "run_cli",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
