"""Audit recently closed target-labeled issues for closure-evidence comments."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence, TextIO

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._optional_surface_common import (
    APPROVAL_NONE,
    JsonArgumentParser,
    REASON_CODE_INVALID_INPUT,
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

SURFACE = "scripts/validation/check_issue_closure_evidence.py"
SUPPORTED_MODES: tuple[str, ...] = ("report",)
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_ISSUE_LIMIT = 100
MAX_ISSUE_LIMIT = 500
GH_COMMAND_TIMEOUT_SECONDS = 30
REASON_CODE_INCOMPLETE_ISSUE_SCAN = "incomplete_issue_scan"
DEFAULT_TARGET_LABELS: tuple[str, ...] = (
    "security",
    "refactor",
    "testing",
    "hardening",
)
REQUIRED_EVIDENCE_FIELDS: tuple[str, ...] = (
    "implementation_reference",
    "key_files_surfaces_changed",
    "validation_commands",
    "pass_fail_summary",
)
REQUIRED_EXEMPTION_FIELDS: tuple[str, ...] = ("exemption_rationale",)
EXEMPTION_APPROVAL_LABEL = "closure-evidence-exemption-approved"
REQUIRED_TEMPLATE_FIELDS: tuple[str, ...] = ("closure_evidence_heading", *REQUIRED_EVIDENCE_FIELDS)
REQUIRED_EXEMPTION_TEMPLATE_FIELDS: tuple[str, ...] = (
    "closure_evidence_exemption_heading",
    *REQUIRED_EXEMPTION_FIELDS,
    "closure_evidence_exemption_approval_label",
)

_IMPLEMENTATION_REFERENCE_PATTERN = re.compile(
    r"(https?://github\.com/\S+/(?:pull|commit)/\S+|#\d+|\b[0-9a-f]{7,40}\b)",
    re.IGNORECASE,
)
_COMMAND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9./_][A-Za-z0-9./_-]*$")
_COMMAND_SYNTAX_HINT_PATTERN = re.compile(r"[./=|&;<>:$()]")
_NON_COMMAND_FIRST_TOKENS: frozenset[str] = frozenset(
    {"this", "that", "these", "those", "it", "please"}
)
_SHORT_COMMAND_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {"go", "cargo", "npm", "pnpm", "yarn", "bun", "make"}
)
_SHORT_COMMAND_ACTION_ALLOWLIST: frozenset[str] = frozenset({"test", "check", "lint", "build"})
_SHORT_COMMAND_PREFIX_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {("npm", "run"), ("pnpm", "run"), ("yarn", "run"), ("bun", "run")}
)
_PASS_FAIL_PATTERN = re.compile(r"\b(pass|fail)\b", re.IGNORECASE)
_CLOSURE_EVIDENCE_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?closure evidence\s*$",
)
_CLOSURE_EXEMPTION_HEADING_PATTERN = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?closure evidence exemption\s*$",
)

_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "implementation_reference": re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?Implementation reference(?:\*\*)?\s*:\s*(.*)$",
        re.IGNORECASE,
    ),
    "key_files_surfaces_changed": re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?Key files/surfaces changed(?:\*\*)?\s*:\s*(.*)$",
        re.IGNORECASE,
    ),
    "validation_commands": re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?Validation commands(?:\*\*)?\s*:\s*(.*)$",
        re.IGNORECASE,
    ),
    "pass_fail_summary": re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?Pass/fail summary(?:\*\*)?\s*:\s*(.*)$",
        re.IGNORECASE,
    ),
    "exemption_rationale": re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?Exemption rationale(?:\*\*)?\s*:\s*(.*)$",
        re.IGNORECASE,
    ),
}


class _IssueListTruncationError(RuntimeError):
    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description=(
            "Flag recently closed security/refactor/testing/hardening issues that "
            "lack a deterministic closure-evidence comment."
        )
    )
    add_common_surface_args(
        parser,
        modes=SUPPORTED_MODES,
        default_mode="report",
        include_path=False,
        include_approval=False,
    )
    parser.add_argument(
        "--issues-json",
        help=(
            "Optional repo-relative JSON fixture with issue/comment payload "
            "(object with 'issues' array, or top-level issue array). "
            "When omitted, issues are fetched from `gh issue list/view`."
        ),
    )
    parser.add_argument(
        "--as-of",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="ISO datetime anchor for lookback-window evaluation (default: current UTC time).",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Lookback window in days for recently closed issues (default: {DEFAULT_LOOKBACK_DAYS}).",
    )
    parser.add_argument(
        "--closed-after",
        help=(
            "Optional inclusive ISO datetime lower bound for closedAt filtering. "
            "Use this to enforce policy from a specific cutover timestamp without "
            "requiring historical backfill."
        ),
    )
    parser.add_argument(
        "--target-label",
        action="append",
        default=[],
        help=(
            "Label to include in policy scope. Repeat for multiple labels. "
            f"Defaults to: {', '.join(DEFAULT_TARGET_LABELS)}."
        ),
    )
    parser.add_argument(
        "--issue-limit",
        type=int,
        default=DEFAULT_ISSUE_LIMIT,
        help=f"Maximum closed issues fetched from GitHub when --issues-json is omitted (default: {DEFAULT_ISSUE_LIMIT}).",
    )
    return parser


def _path_rules() -> dict[str, object]:
    rules = base_path_rules(allowed_roots=["."], allowed_suffixes=[".json"])
    rules["read_only"] = True
    rules["source"] = "gh_cli_or_repo_fixture"
    return rules


def _parse_iso_datetime(raw: str) -> datetime:
    normalized = raw.strip()
    if not normalized:
        raise ValueError("timestamp values must be non-empty ISO datetimes")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid ISO datetime: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_target_labels(raw_target_labels: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(
        sorted({label.strip().lower() for label in raw_target_labels if label.strip()})
    )
    return normalized if normalized else DEFAULT_TARGET_LABELS


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
        raise ValueError("--issues-json must reference an existing .json file in the repository")
    return resolved


def _run_gh_json(command: Sequence[str], *, repo_root: Path) -> Any:
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=GH_COMMAND_TIMEOUT_SECONDS,
            cwd=repo_root,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh CLI is required but not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh command timed out after {GH_COMMAND_TIMEOUT_SECONDS} seconds") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip().splitlines()
        stderr_snippet = stderr[0] if stderr else "unknown gh error"
        raise RuntimeError(f"gh command failed: {stderr_snippet}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh command returned malformed JSON") from exc


def _extract_issue_labels(raw_labels: Any) -> tuple[str, ...]:
    if not isinstance(raw_labels, list):
        return ()
    labels: set[str] = set()
    for entry in raw_labels:
        name: Any
        if isinstance(entry, Mapping):
            name = entry.get("name")
        else:
            name = entry
        if isinstance(name, str) and name.strip():
            labels.add(name.strip().lower())
    return tuple(sorted(labels))


def _extract_comment_bodies(raw_comments: Any) -> tuple[str, ...]:
    if raw_comments is None:
        return ()
    if not isinstance(raw_comments, list):
        raise ValueError("issue comments must be a list")
    comments: list[str] = []
    for entry in raw_comments:
        body: Any
        if isinstance(entry, str):
            body = entry
        elif isinstance(entry, Mapping):
            body = entry.get("body")
        else:
            raise ValueError("issue comments must be strings or objects with a body field")
        if not isinstance(body, str):
            raise ValueError("issue comment body must be a string")
        comments.append(body)
    return tuple(comments)


def _normalize_issue(raw_issue: Any) -> dict[str, Any]:
    if not isinstance(raw_issue, Mapping):
        raise ValueError("issue entries must be objects")
    number_raw = raw_issue.get("number")
    if not isinstance(number_raw, int):
        raise ValueError("issue.number must be an integer")
    closed_at_raw = raw_issue.get("closedAt")
    if not isinstance(closed_at_raw, str):
        raise ValueError(f"issue #{number_raw} missing closedAt")
    closed_at = _parse_iso_datetime(closed_at_raw)
    title_raw = raw_issue.get("title", "")
    if not isinstance(title_raw, str):
        raise ValueError(f"issue #{number_raw} title must be a string")
    url_raw = raw_issue.get("url", "")
    if not isinstance(url_raw, str):
        raise ValueError(f"issue #{number_raw} url must be a string")
    labels = _extract_issue_labels(raw_issue.get("labels", []))
    comments = _extract_comment_bodies(raw_issue.get("comments", []))
    return {
        "number": number_raw,
        "title": title_raw,
        "url": url_raw,
        "closed_at": closed_at,
        "labels": labels,
        "comments": comments,
    }


def _parse_issues_payload(payload: Any) -> tuple[dict[str, Any], ...]:
    entries: Any
    if isinstance(payload, Mapping):
        entries = payload.get("issues")
    else:
        entries = payload
    if not isinstance(entries, list):
        raise ValueError("issues payload must be a list or an object containing an 'issues' list")
    return tuple(_normalize_issue(entry) for entry in entries)


def _load_issues_from_json(repo_root: Path, issues_json_path: str) -> tuple[dict[str, Any], ...]:
    resolved = _resolve_repo_json_path(repo_root, issues_json_path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return _parse_issues_payload(payload)


def _is_within_lookback(closed_at: datetime, *, as_of: datetime, lookback_days: int) -> bool:
    window_start = as_of - timedelta(days=lookback_days)
    return window_start <= closed_at <= as_of


def _load_recent_closed_issues_from_gh(
    *,
    repo_root: Path,
    as_of: datetime,
    lookback_days: int,
    closed_after: datetime | None,
    target_labels: tuple[str, ...],
    issue_limit: int,
) -> tuple[dict[str, Any], ...]:
    raw_issues = _run_gh_json(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "closed",
            "--limit",
            str(issue_limit),
            "--json",
            "number,title,url,closedAt,labels",
        ],
        repo_root=repo_root,
    )
    if not isinstance(raw_issues, list):
        raise ValueError("gh issue list returned unexpected payload")
    if len(raw_issues) >= issue_limit:
        raise _IssueListTruncationError(
            "gh issue list reached the --issue-limit cap; results may be truncated. "
            "Increase --issue-limit or provide --issues-json for a complete check."
        )
    selected: list[dict[str, Any]] = []
    target_label_set = set(target_labels)
    for raw_issue in raw_issues:
        if not isinstance(raw_issue, Mapping):
            raise ValueError("gh issue list returned non-object issue entry")

        number_raw = raw_issue.get("number")
        if number_raw == 415:
            continue

        issue_labels = set(_extract_issue_labels(raw_issue.get("labels", [])))
        if not issue_labels.intersection(target_label_set):
            continue
        closed_at_raw = raw_issue.get("closedAt")
        if not isinstance(closed_at_raw, str):
            raise ValueError("gh issue list returned issue without closedAt")
        closed_at = _parse_iso_datetime(closed_at_raw)
        if closed_after is not None and closed_at < closed_after:
            continue
        if not _is_within_lookback(closed_at, as_of=as_of, lookback_days=lookback_days):
            continue
        number_raw = raw_issue.get("number")
        if not isinstance(number_raw, int):
            raise ValueError("gh issue list returned issue without integer number")
        comments_payload = _run_gh_json(
            ["gh", "issue", "view", str(number_raw), "--json", "comments"],
            repo_root=repo_root,
        )
        if not isinstance(comments_payload, Mapping):
            raise ValueError("gh issue view returned unexpected payload")
        comments = comments_payload.get("comments")
        if not isinstance(comments, list):
            raise ValueError("gh issue view payload missing comments list")
        selected.append(
            {
                "number": number_raw,
                "title": raw_issue.get("title", ""),
                "url": raw_issue.get("url", ""),
                "closedAt": closed_at_raw,
                "labels": raw_issue.get("labels", []),
                "comments": comments,
            }
        )
    return _parse_issues_payload(selected)


def _extract_template_sections(comment_body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {key: [] for key in _SECTION_PATTERNS}
    current_section: str | None = None
    for raw_line in comment_body.splitlines():
        matched_section: str | None = None
        for section_key, pattern in _SECTION_PATTERNS.items():
            match = pattern.match(raw_line)
            if match is None:
                continue
            matched_section = section_key
            current_section = section_key
            inline_value = match.group(1).strip()
            sections[section_key] = [inline_value] if inline_value else []
            break
        if matched_section is not None:
            continue
        if current_section is not None:
            sections[current_section].append(raw_line.strip())
    return {
        key: "\n".join(line for line in lines if line.strip()).strip()
        for key, lines in sections.items()
    }


def _has_section_content(text: str) -> bool:
    if not text.strip():
        return False
    for raw_line in text.splitlines():
        normalized = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
        if normalized:
            return True
    return False


def _normalize_validation_command_line(raw_line: str) -> str:
    normalized = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
    if not normalized or normalized.startswith("```"):
        return ""
    if normalized.startswith("`") and normalized.endswith("`"):
        normalized = normalized[1:-1].strip()
    if normalized.startswith("$"):
        normalized = normalized[1:].strip()
    return normalized


def _is_allowlisted_short_command(tokens: Sequence[str]) -> bool:
    lowered_tokens = tuple(token.lower() for token in tokens)
    if len(lowered_tokens) == 2:
        first_token, second_token = lowered_tokens
        return (
            first_token in _SHORT_COMMAND_TOOL_ALLOWLIST
            and second_token in _SHORT_COMMAND_ACTION_ALLOWLIST
        )
    if len(lowered_tokens) == 3:
        first_token, second_token, third_token = lowered_tokens
        return (
            (first_token, second_token) in _SHORT_COMMAND_PREFIX_ALLOWLIST
            and third_token in _SHORT_COMMAND_ACTION_ALLOWLIST
        )
    return False


def _is_command_like_line(raw_line: str) -> bool:
    normalized = _normalize_validation_command_line(raw_line)
    if not normalized:
        return False
    tokens = normalized.split()
    if not tokens:
        return False
    first_token = tokens[0]
    if not _COMMAND_NAME_PATTERN.fullmatch(first_token):
        return False
    if first_token.lower() in _NON_COMMAND_FIRST_TOKENS:
        return False
    trailing_tokens = tokens[1:]
    if any(token.startswith("-") for token in trailing_tokens):
        return True
    if any(_COMMAND_SYNTAX_HINT_PATTERN.search(token) for token in trailing_tokens):
        return True
    return _is_allowlisted_short_command(tokens)


def _has_command_like_content(section_text: str) -> bool:
    return any(_is_command_like_line(raw_line) for raw_line in section_text.splitlines())


def evaluate_closure_evidence_comment(
    comment_body: str,
    *,
    issue_labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    sections = _extract_template_sections(comment_body)
    normalized_issue_labels = {
        label.strip().lower()
        for label in (issue_labels or ())
        if isinstance(label, str) and label.strip()
    }

    def _evaluate_closure_evidence_template() -> dict[str, Any]:
        missing_fields: list[str] = []

        if not _CLOSURE_EVIDENCE_HEADING_PATTERN.search(comment_body):
            missing_fields.append("closure_evidence_heading")

        implementation_section = sections["implementation_reference"]
        if not _IMPLEMENTATION_REFERENCE_PATTERN.search(implementation_section):
            missing_fields.append("implementation_reference")

        key_files_section = sections["key_files_surfaces_changed"]
        if not _has_section_content(key_files_section):
            missing_fields.append("key_files_surfaces_changed")

        validation_commands_section = sections["validation_commands"]
        if not _has_command_like_content(validation_commands_section):
            missing_fields.append("validation_commands")

        pass_fail_section = sections["pass_fail_summary"]
        if not _PASS_FAIL_PATTERN.search(pass_fail_section):
            missing_fields.append("pass_fail_summary")

        return {
            "template": "closure_evidence",
            "is_compliant": len(missing_fields) == 0,
            "missing_fields": tuple(missing_fields),
        }

    def _evaluate_closure_exemption_template() -> dict[str, Any]:
        missing_fields: list[str] = []

        if not _CLOSURE_EXEMPTION_HEADING_PATTERN.search(comment_body):
            missing_fields.append("closure_evidence_exemption_heading")

        exemption_section = sections["exemption_rationale"]
        if not _has_section_content(exemption_section):
            missing_fields.append("exemption_rationale")

        if EXEMPTION_APPROVAL_LABEL not in normalized_issue_labels:
            missing_fields.append("closure_evidence_exemption_approval_label")

        return {
            "template": "closure_evidence_exemption",
            "is_compliant": len(missing_fields) == 0,
            "missing_fields": tuple(missing_fields),
        }

    evidence_result = _evaluate_closure_evidence_template()
    exemption_result = _evaluate_closure_exemption_template()

    if evidence_result["is_compliant"] or exemption_result["is_compliant"]:
        return {
            "is_compliant": True,
            "missing_fields": (),
            "sections": sections,
            "matched_template": (
                evidence_result["template"]
                if evidence_result["is_compliant"]
                else exemption_result["template"]
            ),
        }

    candidates: list[dict[str, Any]] = []
    if _CLOSURE_EVIDENCE_HEADING_PATTERN.search(comment_body):
        candidates.append(evidence_result)
    if _CLOSURE_EXEMPTION_HEADING_PATTERN.search(comment_body):
        candidates.append(exemption_result)
    if not candidates:
        candidates.append(evidence_result)
    chosen_result = min(
        candidates,
        key=lambda result: (
            len(result["missing_fields"]),
            1 if result["template"] == "closure_evidence_exemption" else 0,
        ),
    )

    return {
        "is_compliant": False,
        "missing_fields": chosen_result["missing_fields"],
        "sections": sections,
        "matched_template": chosen_result["template"],
    }


def _evaluate_issue(issue: Mapping[str, Any]) -> dict[str, Any]:
    comments = issue["comments"]
    best_missing = REQUIRED_TEMPLATE_FIELDS
    for index, comment in enumerate(comments):
        result = evaluate_closure_evidence_comment(comment, issue_labels=issue["labels"])
        if result["is_compliant"]:
            return {
                "issue_number": issue["number"],
                "title": issue["title"],
                "url": issue["url"],
                "closed_at": issue["closed_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "labels": list(issue["labels"]),
                "status": STATUS_PASS,
                "reason_code": REASON_CODE_OK,
                "message": "closure evidence comment found",
                "missing_fields": [],
                "matched_comment_index": index,
            }
        missing_fields = tuple(result["missing_fields"])
        if len(missing_fields) < len(best_missing):
            best_missing = missing_fields
    return {
        "issue_number": issue["number"],
        "title": issue["title"],
        "url": issue["url"],
        "closed_at": issue["closed_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "labels": list(issue["labels"]),
        "status": STATUS_FAIL,
        "reason_code": "missing_closure_evidence_comment",
        "message": "no compliant closure evidence comment found",
        "missing_fields": list(best_missing),
    }


def run_closure_evidence_report(
    *,
    repo_root: str | Path = ".",
    mode: str,
    issues_json_path: str | None = None,
    as_of: str,
    lookback_days: int,
    closed_after: str | None = None,
    target_labels: Sequence[str] | None = None,
    issue_limit: int = DEFAULT_ISSUE_LIMIT,
    issues_payload: Any | None = None,
) -> SurfaceResult:
    path_rules = _path_rules()
    normalized_repo_root = Path(repo_root).resolve()
    if not looks_like_repo_root(normalized_repo_root):
        return repo_root_failure(surface=SURFACE, mode=mode, approval=APPROVAL_NONE, path_rules=path_rules)
    if lookback_days < 0:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message="lookback-days must be zero or greater",
            path_rules=path_rules,
        )
    if issue_limit < 1 or issue_limit > MAX_ISSUE_LIMIT:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message=f"issue-limit must be between 1 and {MAX_ISSUE_LIMIT}",
            path_rules=path_rules,
        )
    try:
        as_of_dt = _parse_iso_datetime(as_of)
        closed_after_dt = _parse_iso_datetime(closed_after) if closed_after else None
        if closed_after_dt is not None and closed_after_dt > as_of_dt:
            raise ValueError("--closed-after must be less than or equal to --as-of")
        normalized_labels = _normalize_target_labels(tuple(target_labels or ()))
        if issues_payload is not None:
            issues = _parse_issues_payload(issues_payload)
            source = "inline_payload"
        elif issues_json_path:
            issues = _load_issues_from_json(normalized_repo_root, issues_json_path)
            source = "issues_json"
        else:
            issues = _load_recent_closed_issues_from_gh(
                repo_root=normalized_repo_root,
                as_of=as_of_dt,
                lookback_days=lookback_days,
                closed_after=closed_after_dt,
                target_labels=normalized_labels,
                issue_limit=issue_limit,
            )
            source = "gh_cli"
    except _IssueListTruncationError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code=REASON_CODE_INCOMPLETE_ISSUE_SCAN,
            message=str(exc),
            approval=APPROVAL_NONE,
            path_rules=path_rules,
        )
    except RuntimeError as exc:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_FAIL,
            reason_code="gh_cli_failed",
            message=str(exc),
            approval=APPROVAL_NONE,
            path_rules=path_rules,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return invalid_input_result(
            surface=SURFACE,
            mode=mode,
            approval=APPROVAL_NONE,
            message=str(exc),
            path_rules=path_rules,
        )

    target_label_set = set(normalized_labels)
    filtered = tuple(
        issue
        for issue in issues
        if target_label_set.intersection(issue["labels"])
        and (closed_after_dt is None or issue["closed_at"] >= closed_after_dt)
        and _is_within_lookback(issue["closed_at"], as_of=as_of_dt, lookback_days=lookback_days)
    )
    if not filtered:
        return SurfaceResult(
            surface=SURFACE,
            mode=mode,
            status=STATUS_PASS,
            reason_code=REASON_CODE_OK,
            message="no recently closed target-labeled issues matched the policy scope",
            approval=APPROVAL_NONE,
            path_rules=path_rules,
            summary={
                "checked_issue_count": 0,
                "flagged_issue_count": 0,
                "lookback_days": lookback_days,
                "as_of": as_of_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "closed_after": (
                    closed_after_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if closed_after_dt is not None
                    else None
                ),
                "target_labels": list(normalized_labels),
                "source": source,
            },
        )

    items = tuple(_evaluate_issue(issue) for issue in filtered)
    flagged_issue_count = sum(1 for item in items if item["status"] == STATUS_FAIL)
    status = STATUS_PASS if flagged_issue_count == 0 else STATUS_FAIL
    reason_code = REASON_CODE_OK if flagged_issue_count == 0 else "missing_closure_evidence"
    message = (
        "all recently closed target-labeled issues include closure evidence comments"
        if flagged_issue_count == 0
        else f"{flagged_issue_count} issue(s) missing closure evidence comments"
    )

    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=status,
        reason_code=reason_code,
        message=message,
        approval=APPROVAL_NONE,
        path_rules=path_rules,
        items=items,
        summary={
            "checked_issue_count": len(items),
            "flagged_issue_count": flagged_issue_count,
            "lookback_days": lookback_days,
            "as_of": as_of_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "closed_after": (
                closed_after_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                if closed_after_dt is not None
                else None
            ),
            "target_labels": list(normalized_labels),
            "required_fields": list(REQUIRED_EVIDENCE_FIELDS),
            "required_template_fields": list(REQUIRED_TEMPLATE_FIELDS),
            "source": source,
            "remediation_steps": [
                "Add a closure evidence comment using the template in docs/mvp-runbook.md.",
                "Include implementation reference, key files/surfaces changed, exact validation commands, and pass/fail summary.",
                "Re-run this checker and ensure flagged_issue_count is zero.",
            ],
        },
    )


def run_cli(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    return run_surface_cli(
        argv=argv,
        parser_factory=_build_parser,
        path_rules_factory=_path_rules,
        surface=SURFACE,
        runner=run_closure_evidence_report,
        args_to_kwargs=lambda args: {
            "repo_root": args.repo_root,
            "mode": args.mode,
            "issues_json_path": args.issues_json,
            "as_of": args.as_of,
            "lookback_days": args.lookback_days,
            "closed_after": args.closed_after,
            "target_labels": args.target_label,
            "issue_limit": args.issue_limit,
        },
        output_stream=output_stream,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


__all__ = [
    "SURFACE",
    "SUPPORTED_MODES",
    "DEFAULT_TARGET_LABELS",
    "DEFAULT_LOOKBACK_DAYS",
    "evaluate_closure_evidence_comment",
    "REQUIRED_EXEMPTION_FIELDS",
    "EXEMPTION_APPROVAL_LABEL",
    "REQUIRED_EXEMPTION_TEMPLATE_FIELDS",
    "REQUIRED_EVIDENCE_FIELDS",
    "REQUIRED_TEMPLATE_FIELDS",
    "run_closure_evidence_report",
    "run_cli",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
