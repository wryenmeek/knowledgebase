"""Policy-gated persistence for high-value query outputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sys
from typing import Sequence, TextIO

from scripts.kb import contracts, sourceref, update_index, write_utils
from scripts.kb.path_utils import RepoRelativePathError, resolve_within_repo
from scripts.kb.write_utils import read_optional_text, write_text_if_changed


DEFAULT_MIN_CONFIDENCE = 4
DEFAULT_MIN_SOURCES = 2
DEFAULT_UPDATED_AT = "1970-01-01T00:00:00Z"

_POLICY_IDS: tuple[str, ...] = (
    contracts.PolicyId.AUTO_PERSIST_WHEN_HIGH_VALUE.value,
    contracts.PolicyId.LOG_ONLY_STATE_CHANGES.value,
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class PersistQueryInputError(ValueError):
    """Raised when persist-query input validation fails."""


@dataclass(frozen=True, slots=True)
class _PersistenceOutcome:
    """Grouped persistence result fields."""

    analysis_path: str | None = None
    index_updated: bool = False
    log_appended: bool = False


@dataclass(frozen=True, slots=True)
class PersistRequest:
    """Normalized, validated persist-query inputs."""

    normalized_query: str
    summary: str
    confidence: int
    sources: tuple[str, ...]
    unresolved_contradiction: bool
    min_confidence: int
    min_sources: int
    require_no_contradiction: bool
    updated_at: str
    sensitivity: str
    wiki_root: Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Persist high-value query results to wiki/analyses/** when policy passes.",
    )
    parser.add_argument("--query", required=True, help="Query text used for synthesis.")
    parser.add_argument(
        "--result-summary",
        default="",
        help="Optional synthesized result summary to persist in the analysis page.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Canonical SourceRef citation. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--confidence",
        type=int,
        required=True,
        help="Synthesis confidence score (1..5).",
    )
    parser.add_argument(
        "--has-unresolved-contradiction",
        "--unresolved-contradiction",
        dest="unresolved_contradiction",
        action="store_true",
        help="Mark this result as containing unresolved contradiction evidence.",
    )
    parser.add_argument(
        "--wiki-root",
        default="wiki",
        help="Wiki root directory (must resolve to repository wiki/).",
    )
    parser.add_argument(
        "--schema",
        default="AGENTS.md",
        help="Schema/contract file path for validation.",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=DEFAULT_MIN_CONFIDENCE,
        help=f"Minimum confidence threshold (default: {DEFAULT_MIN_CONFIDENCE}).",
    )
    parser.add_argument(
        "--min-sources",
        type=int,
        default=DEFAULT_MIN_SOURCES,
        help=f"Minimum source count threshold (default: {DEFAULT_MIN_SOURCES}).",
    )
    parser.add_argument(
        "--require-no-contradiction",
        action="store_true",
        default=True,
        help="Require unresolved_contradiction == false for persistence (default policy).",
    )
    parser.add_argument(
        "--result-json",
        action="store_true",
        help="Compatibility flag for automation; JSON envelope is emitted for all runs.",
    )
    parser.add_argument(
        "--updated-at",
        default=DEFAULT_UPDATED_AT,
        help=f"Deterministic updated_at timestamp (default: {DEFAULT_UPDATED_AT}).",
    )
    parser.add_argument(
        "--sensitivity",
        choices=("public", "internal", "restricted"),
        default="internal",
        help="Frontmatter sensitivity value.",
    )
    return parser


def _resolve_within_repo(repo_root: Path, raw_path: str, *, label: str) -> Path:
    try:
        return resolve_within_repo(repo_root, raw_path)
    except RepoRelativePathError:
        raise PersistQueryInputError(f"{label} escapes repository boundary: {raw_path}")


def _normalize_query(query: str) -> str:
    return " ".join(query.split()).casefold()


def _normalize_summary(summary: str) -> str:
    return " ".join(summary.split())


def _slugify(normalized_query: str) -> str:
    collapsed = _SLUG_RE.sub("-", normalized_query).strip("-")
    if not collapsed:
        return "query"
    return collapsed[:80].rstrip("-")


def _validate_request(args: argparse.Namespace, repo_root: Path) -> PersistRequest:
    normalized_query = _normalize_query(args.query)
    if not normalized_query:
        raise PersistQueryInputError("query must not be empty after normalization")

    if args.confidence < 1 or args.confidence > 5:
        raise PersistQueryInputError("confidence must be an integer in the range 1..5")

    if args.min_confidence < 1 or args.min_confidence > 5:
        raise PersistQueryInputError("min-confidence must be an integer in the range 1..5")

    if args.min_sources < 1:
        raise PersistQueryInputError("min-sources must be >= 1")

    wiki_root = _resolve_within_repo(repo_root, args.wiki_root, label="wiki-root")
    if wiki_root.relative_to(repo_root).as_posix() != "wiki":
        raise PersistQueryInputError("wiki-root must resolve to repository path 'wiki'")
    if not wiki_root.exists() or not wiki_root.is_dir():
        raise PersistQueryInputError(f"wiki-root does not exist or is not a directory: {wiki_root}")

    schema_path = _resolve_within_repo(repo_root, args.schema, label="schema")
    if not schema_path.exists() or not schema_path.is_file():
        raise PersistQueryInputError(f"schema file does not exist: {schema_path}")

    canonical_sources: list[str] = []
    for source_value in args.source:
        try:
            canonical_sources.append(sourceref.parse_sourceref(source_value).to_canonical())
        except sourceref.SourceRefValidationError as exc:
            raise PersistQueryInputError(f"invalid SourceRef: {exc}") from exc

    normalized_sources = tuple(sorted(set(canonical_sources)))
    summary = _normalize_summary(args.result_summary)

    return PersistRequest(
        normalized_query=normalized_query,
        summary=summary,
        confidence=args.confidence,
        sources=normalized_sources,
        unresolved_contradiction=bool(args.unresolved_contradiction),
        min_confidence=args.min_confidence,
        min_sources=args.min_sources,
        require_no_contradiction=bool(args.require_no_contradiction),
        updated_at=args.updated_at,
        sensitivity=args.sensitivity,
        wiki_root=wiki_root,
    )


def _evaluate_policy(request: PersistRequest) -> tuple[bool, str]:
    if request.confidence < request.min_confidence:
        return False, contracts.ReasonCode.POLICY_CONFIDENCE_BELOW_MIN.value
    if len(request.sources) < request.min_sources:
        return False, contracts.ReasonCode.POLICY_SOURCES_BELOW_MIN.value
    if request.require_no_contradiction and request.unresolved_contradiction:
        return False, contracts.ReasonCode.POLICY_UNRESOLVED_CONTRADICTION.value
    return True, contracts.ReasonCode.OK.value


def _analysis_relative_path(request: PersistRequest, repo_root: Path) -> Path:
    fingerprint_payload = "\n".join((request.normalized_query, *request.sources))
    fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:16]
    file_name = f"{_slugify(request.normalized_query)}-{fingerprint}.md"
    return request.wiki_root.relative_to(repo_root) / "analyses" / file_name


def _render_analysis_markdown(request: PersistRequest, analysis_path: str) -> str:
    title = f"Query Analysis: {request.normalized_query}"
    escaped_title = title.replace('"', '\\"')
    summary = request.summary if request.summary else "No summary provided."

    lines: list[str] = [
        "---",
        "type: analysis",
        f'title: "{escaped_title}"',
        "status: active",
        "sources:",
    ]
    for source in request.sources:
        lines.append(f"  - {source}")

    lines.extend(
        [
            "open_questions: []",
            f"confidence: {request.confidence}",
            f"sensitivity: {request.sensitivity}",
            f'updated_at: "{request.updated_at}"',
            "tags:",
            "  - analysis",
            "  - query-persist",
            "---",
            "",
            f"# {title}",
            "",
            "## Query",
            f"`{request.normalized_query}`",
            "",
            "## Summary",
            summary,
            "",
            "## Evidence",
        ]
    )
    if request.sources:
        for source in request.sources:
            lines.append(f"- {source}")
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Open Questions",
            "- None.",
            "",
            "## Persistence Metadata",
            f"- Analysis path: `{analysis_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _update_index_if_changed(wiki_root: Path) -> bool:
    generated_index = update_index.generate_index_content(wiki_root)
    return write_text_if_changed(wiki_root / "index.md", generated_index)


def _restore_optional_text(path: Path, previous_content: str | None) -> None:
    if previous_content is None:
        if path.exists():
            path.unlink()
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(previous_content)


def _rollback_file_state(snapshots: Sequence[tuple[Path, str | None]]) -> None:
    rollback_errors: list[str] = []
    for path, previous_content in reversed(tuple(snapshots)):
        try:
            _restore_optional_text(path, previous_content)
        except OSError as exc:
            rollback_errors.append(f"{path}: {exc}")

    if rollback_errors:
        joined_errors = "; ".join(rollback_errors)
        raise OSError(f"rollback failed: {joined_errors}")


def _build_log_entry(analysis_path: str) -> str:
    return f"- persist_query: {analysis_path}"


def _envelope(
    *,
    status: contracts.ResultStatus | str,
    reason_code: contracts.ReasonCode | str,
    request: PersistRequest | None = None,
    outcome: _PersistenceOutcome | None = None,
) -> contracts.ResultEnvelope:
    return contracts.ResultEnvelope(
        status=status,
        reason_code=reason_code,
        policy=_POLICY_IDS,
        analysis_path=outcome.analysis_path if outcome else None,
        index_updated=outcome.index_updated if outcome else False,
        log_appended=outcome.log_appended if outcome else False,
        sources=request.sources if request else (),
    )


def _execute(args: argparse.Namespace, repo_root: Path) -> tuple[contracts.ResultEnvelope, int, str | None]:
    try:
        request = _validate_request(args, repo_root)
    except PersistQueryInputError as exc:
        return (
            _envelope(
                status=contracts.ResultStatus.FAILED,
                reason_code=contracts.ReasonCode.INVALID_INPUT,
            ),
            1,
            str(exc),
        )

    policy_passed, policy_reason = _evaluate_policy(request)
    if not policy_passed:
        return (
            _envelope(
                status=contracts.ResultStatus.NO_WRITE_POLICY,
                reason_code=policy_reason,
                request=request,
            ),
            0,
            None,
        )

    analysis_relative = _analysis_relative_path(request, repo_root)
    analysis_absolute = repo_root / analysis_relative
    index_path = request.wiki_root / "index.md"
    log_path = repo_root / write_utils.LOG_PATH
    analysis_markdown = _render_analysis_markdown(request, analysis_relative.as_posix())

    try:
        with write_utils.exclusive_write_lock(repo_root):
            snapshots: tuple[tuple[Path, str | None], ...] = (
                (analysis_absolute, read_optional_text(analysis_absolute)),
                (index_path, read_optional_text(index_path)),
                (log_path, read_optional_text(log_path)),
            )
            try:
                analysis_changed = write_text_if_changed(analysis_absolute, analysis_markdown)
                index_updated = _update_index_if_changed(request.wiki_root)
                state_changed = analysis_changed or index_updated
                log_appended = write_utils.append_log_only_state_changes(
                    repo_root,
                    _build_log_entry(analysis_relative.as_posix()),
                    state_changed=state_changed,
                )
            except (OSError, update_index.IndexGenerationError) as exc:
                try:
                    _rollback_file_state(snapshots)
                except OSError as rollback_exc:
                    raise OSError(f"{exc}; {rollback_exc}") from rollback_exc
                raise
    except write_utils.LockUnavailableError as exc:
        return (
            _envelope(
                status=contracts.ResultStatus.FAILED,
                reason_code=contracts.ReasonCode.LOCK_UNAVAILABLE,
                request=request,
            ),
            1,
            exc.failure_reason,
        )
    except (OSError, update_index.IndexGenerationError) as exc:
        return (
            _envelope(
                status=contracts.ResultStatus.FAILED,
                reason_code=contracts.ReasonCode.WRITE_FAILED,
                request=request,
            ),
            1,
            str(exc),
        )

    return (
        _envelope(
            status=contracts.ResultStatus.WRITTEN,
            reason_code=contracts.ReasonCode.OK,
            request=request,
            outcome=_PersistenceOutcome(
                analysis_path=analysis_relative.as_posix(),
                index_updated=index_updated,
                log_appended=log_appended,
            ),
        ),
        0,
        None,
    )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
    repo_root: str | Path = ".",
) -> int:
    """CLI wrapper for policy-gated query persistence."""
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        if int(exc.code) == 0:
            return 0
        envelope = _envelope(
            status=contracts.ResultStatus.FAILED,
            reason_code=contracts.ReasonCode.INVALID_INPUT,
        )
        output_stream.write(envelope.to_json())
        output_stream.write("\n")
        return 1

    envelope, exit_code, error_message = _execute(args, Path(repo_root).resolve())
    output_stream.write(envelope.to_json())
    output_stream.write("\n")

    if error_message:
        error_stream.write(f"error: {error_message}\n")

    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
