"""Deterministic source ingest CLI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence, TextIO

from scripts.kb import contracts, page_template_utils, update_index
from scripts.kb.ingest_render import (
    SourceProvenance,
    _PROVISIONAL_GIT_SHA,
    _build_provisional_source_provenance,
    _build_source_ref,
    _escape_quotes,
    _render_source_page,
)
from scripts.kb.path_utils import RepoRelativePathError, resolve_within_repo
from scripts.kb.sourceref import SourceRefValidationError
from scripts.kb.write_utils import (
    LockUnavailableError,
    append_log_only_state_changes,
    check_no_symlink_path,
    exclusive_write_lock,
    read_optional_text,
    write_text_capturing_previous_safe,
)


_ALLOWED_SOURCE_PREFIX = ("raw", "inbox")
_REQUIRED_BATCH_POLICY = contracts.PolicyId.CONTINUE_AND_REPORT_PER_SOURCE.value
_APPLIED_POLICIES = (
    contracts.PolicyId.CONTINUE_AND_REPORT_PER_SOURCE.value,
    contracts.PolicyId.LOG_ONLY_STATE_CHANGES.value,
)


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """Per-source ingest result payload."""

    source: str
    status: str
    reason_code: str
    message: str
    source_page: str | None = None
    processed_path: str | None = None
    source_ref: str | None = None
    provenance: SourceProvenance | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
            "source_page": self.source_page,
            "processed_path": self.processed_path,
            "source_ref": self.source_ref,
            "provenance": None if self.provenance is None else self.provenance.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _SourceMutation:
    source: str
    source_page: str
    processed_path: str
    source_page_changed: bool
    source_page_previous_content: str | None


@dataclass(frozen=True, slots=True)
class _SourceIngestAttempt:
    outcome: SourceOutcome
    mutation: _SourceMutation | None = None


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Top-level ingest execution result."""

    status: str
    reason_code: str
    exit_code: int
    outcomes: tuple[SourceOutcome, ...]
    source_refs: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]
    index_updated: bool
    log_appended: bool
    message: str | None = None

    def to_payload(self) -> dict[str, object]:
        envelope = contracts.ResultEnvelope(
            status=self.status,
            reason_code=self.reason_code,
            policy=_APPLIED_POLICIES,
            analysis_path=None,
            index_updated=self.index_updated,
            log_appended=self.log_appended,
            sources=self.source_refs,
        ).to_dict()
        envelope["per_source"] = [outcome.to_dict() for outcome in self.outcomes]
        envelope["source_provenance"] = [
            provenance.to_dict() for provenance in self.source_provenance
        ]
        if self.message:
            envelope["message"] = self.message
        return envelope


class IngestError(RuntimeError):
    """Error that maps to a stable reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest source files into deterministic wiki pages.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", help="Single source file under raw/inbox/**.")
    source_group.add_argument(
        "--sources-manifest",
        help="Manifest under raw/inbox/** containing newline-delimited source paths.",
    )
    parser.add_argument(
        "--batch-policy",
        default=_REQUIRED_BATCH_POLICY,
        help="Must be continue_and_report_per_source.",
    )
    parser.add_argument("--wiki-root", default="wiki", help="Wiki root directory (default: wiki).")
    parser.add_argument("--schema", default="AGENTS.md", help="Schema path (default: AGENTS.md).")
    parser.add_argument(
        "--report-json",
        action="store_true",
        help="Emit deterministic JSON report to stdout.",
    )
    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    repo_root: str | Path = ".",
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
) -> int:
    """CLI runner with injectable repository root/output streams for tests."""
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    repo_root_path = Path(repo_root).resolve()

    try:
        result = _execute_ingest(args, repo_root_path)
    except IngestError as exc:
        result = IngestResult(
            status=contracts.ResultStatus.FAILED.value,
            reason_code=exc.reason_code,
            exit_code=1,
            outcomes=tuple(),
            source_refs=tuple(),
            source_provenance=tuple(),
            index_updated=False,
            log_appended=False,
            message=str(exc),
        )
    except LockUnavailableError as exc:
        result = IngestResult(
            status=contracts.ResultStatus.FAILED.value,
            reason_code=exc.reason_code,
            exit_code=1,
            outcomes=tuple(),
            source_refs=tuple(),
            source_provenance=tuple(),
            index_updated=False,
            log_appended=False,
            message=exc.failure_reason,
        )

    if args.report_json:
        output_stream.write(json.dumps(result.to_payload(), sort_keys=True))
        output_stream.write("\n")
    elif result.message and result.exit_code != 0:
        error_stream.write(f"error: {result.message}\n")

    return result.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    return run_cli(argv=argv)


def _execute_ingest(args: argparse.Namespace, repo_root: Path) -> IngestResult:
    # --- Phase 1: Validate CLI inputs ---
    if args.batch_policy != _REQUIRED_BATCH_POLICY:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"batch policy must be {_REQUIRED_BATCH_POLICY}",
        )

    wiki_root_path, wiki_root_relative = _resolve_path_within_repo(repo_root, args.wiki_root)
    if not _is_under_wiki_root(Path(wiki_root_relative)):
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"wiki root must resolve under wiki/**: {args.wiki_root} (pass --wiki-root wiki)",
        )

    schema_path, _schema_relative = _resolve_path_within_repo(repo_root, args.schema)
    if not schema_path.exists() or not schema_path.is_file():
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"schema file does not exist: {args.schema}",
        )

    source_inputs = _resolve_source_inputs(args, repo_root)

    # --- Phase 2: Execute per-source ingests ---
    with exclusive_write_lock(repo_root):
        _ensure_wiki_tree(wiki_root_path)

        outcomes: list[SourceOutcome] = []
        successful_outcomes: list[SourceOutcome] = []
        source_mutations: list[_SourceMutation] = []
        for source_input in source_inputs:
            attempt = _ingest_source(repo_root, source_input)
            outcome = attempt.outcome
            outcomes.append(outcome)
            if outcome.status == contracts.ResultStatus.WRITTEN.value:
                successful_outcomes.append(outcome)
                if attempt.mutation is not None:
                    source_mutations.append(attempt.mutation)

        # --- Phase 3: Update index and append log ---
        index_updated = False
        log_appended = False
        index_path = wiki_root_path / "index.md"
        index_snapshot_captured = False
        index_previous_content: str | None = None
        log_path = repo_root / "wiki" / "log.md"
        log_snapshot_captured = False
        log_previous_content: str | None = None

        try:
            if successful_outcomes:
                try:
                    index_previous_content = read_optional_text(index_path)
                except OSError as exc:
                    raise IngestError(
                        contracts.ReasonCode.WRITE_FAILED.value,
                        f"unable to read existing index: {index_path} ({exc})",
                    ) from exc
                index_snapshot_captured = True
                index_updated = _write_index_if_changed(wiki_root_path)

            state_changed = bool(successful_outcomes) or index_updated
            if state_changed:
                try:
                    log_previous_content = read_optional_text(log_path)
                except OSError as exc:
                    raise IngestError(
                        contracts.ReasonCode.WRITE_FAILED.value,
                        f"unable to read existing log: {log_path} ({exc})",
                    ) from exc
                log_snapshot_captured = True

            log_entry = _render_log_entry(successful_outcomes)
            try:
                log_appended = append_log_only_state_changes(
                    repo_root,
                    log_entry,
                    state_changed=state_changed,
                )
            except OSError as exc:
                raise IngestError(
                    contracts.ReasonCode.WRITE_FAILED.value,
                    f"unable to append log: {log_path} ({exc})",
                ) from exc
        except IngestError as exc:
            rollback_error = _rollback_ingest_mutations(
                repo_root=repo_root,
                source_mutations=source_mutations,
                index_path=index_path,
                index_snapshot_captured=index_snapshot_captured,
                index_previous_content=index_previous_content,
                log_path=log_path,
                log_snapshot_captured=log_snapshot_captured,
                log_previous_content=log_previous_content,
            )
            failure_message = str(exc)
            if rollback_error is not None:
                failure_message = f"{failure_message}; rollback failed: {rollback_error}"
            return IngestResult(
                status=contracts.ResultStatus.FAILED.value,
                reason_code=exc.reason_code,
                exit_code=1,
                outcomes=tuple(
                    _mark_written_outcomes_rolled_back(
                        outcomes,
                        failure_reason=str(exc),
                        failure_reason_code=exc.reason_code,
                        rollback_error=rollback_error,
                    )
                ),
                source_refs=tuple(),
                source_provenance=tuple(),
                index_updated=False,
                log_appended=False,
                message=failure_message,
            )

    source_refs = tuple(
        outcome.source_ref
        for outcome in successful_outcomes
        if outcome.source_ref is not None
    )
    source_provenance = tuple(
        outcome.provenance
        for outcome in successful_outcomes
        if outcome.provenance is not None
    )
    failures = [
        outcome for outcome in outcomes if outcome.status == contracts.ResultStatus.FAILED.value
    ]

    if failures:
        return IngestResult(
            status=contracts.ResultStatus.PARTIAL_SUCCESS.value,
            reason_code=contracts.ReasonCode.PER_SOURCE_FAILURES.value,
            exit_code=2,
            outcomes=tuple(outcomes),
            source_refs=source_refs,
            source_provenance=source_provenance,
            index_updated=index_updated,
            log_appended=log_appended,
            message=f"{len(failures)} source(s) failed",
        )

    return IngestResult(
        status=contracts.ResultStatus.WRITTEN.value,
        reason_code=contracts.ReasonCode.OK.value,
        exit_code=0,
        outcomes=tuple(outcomes),
        source_refs=source_refs,
        source_provenance=source_provenance,
        index_updated=index_updated,
        log_appended=log_appended,
    )


def _resolve_source_inputs(args: argparse.Namespace, repo_root: Path) -> list[str]:
    if args.source:
        _source_path, _source_relative = _resolve_inbox_path(repo_root, args.source)
        return [args.source]

    manifest_path, _manifest_relative = _resolve_inbox_path(repo_root, args.sources_manifest)
    if not manifest_path.exists() or not manifest_path.is_file():
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"sources manifest does not exist: {args.sources_manifest}",
        )

    try:
        manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"unable to read sources manifest: {args.sources_manifest} ({exc})",
        ) from exc

    entries = [line.strip() for line in manifest_lines if line.strip()]
    if not entries:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            "sources manifest is empty (add at least one source path, one per line, to the manifest file)",
        )
    return entries


def _resolve_path_within_repo(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    try:
        resolved = resolve_within_repo(repo_root, raw_path)
    except RepoRelativePathError as exc:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"path escapes repository boundary: {raw_path} (use a path relative to the repo root, e.g. wiki/sources)",
        ) from exc
    return resolved, resolved.relative_to(repo_root).as_posix()


def _resolve_inbox_path(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    requested_path = Path(raw_path)
    lexical_path = requested_path if requested_path.is_absolute() else repo_root / requested_path
    try:
        check_no_symlink_path(lexical_path)
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"path must not use symlinks: {raw_path} ({exc})",
        ) from exc
    resolved, relative = _resolve_path_within_repo(repo_root, raw_path)
    relative_path = Path(relative)
    if not _is_under_inbox(relative_path):
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"path must resolve under raw/inbox/**: {raw_path}",
        )
    return resolved, relative


def _is_under_inbox(relative_path: Path) -> bool:
    parts = relative_path.parts
    if len(parts) < 3:
        return False
    return parts[0] == _ALLOWED_SOURCE_PREFIX[0] and parts[1] == _ALLOWED_SOURCE_PREFIX[1]


def _is_under_wiki_root(relative_path: Path) -> bool:
    parts = relative_path.parts
    if len(parts) < 1:
        return False
    return parts[0] == "wiki"


def _load_source_bytes(
    repo_root: Path, source_input: str
) -> tuple[Path, str, bytes]:
    """Resolve, check, and read the source file from the inbox.

    Returns (source_path, source_relative, source_bytes). Raises IngestError
    if the path is invalid, the file does not exist, or the file cannot be read.
    """
    source_path, source_relative = _resolve_inbox_path(repo_root, source_input)

    if not source_path.exists() or not source_path.is_file():
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"source file does not exist: {source_relative}",
        )

    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to read source file: {source_relative} ({exc})",
        ) from exc

    return source_path, source_relative, source_bytes


def _ingest_source(repo_root: Path, source_input: str) -> _SourceIngestAttempt:
    # --- Phase 1: Resolve path and read source file ---
    try:
        source_path, source_relative, source_bytes = _load_source_bytes(repo_root, source_input)
    except IngestError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_input,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=exc.reason_code,
                message=str(exc),
            )
        )

    # --- Phase 2: Compute destination paths and validate ingest preconditions ---
    source_relative_path = Path(source_relative)
    inbox_suffix = Path(*source_relative_path.parts[2:])
    processed_relative = (Path("raw/processed") / inbox_suffix).as_posix()
    processed_path = repo_root / processed_relative
    try:
        check_no_symlink_path(source_path)
        check_no_symlink_path(processed_path)
    except OSError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"unsafe ingest path: {source_relative} ({exc})",
                processed_path=processed_relative,
            )
        )
    if processed_path.exists() or processed_path.is_symlink():
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"processed destination already exists: {processed_relative}",
                processed_path=processed_relative,
            )
        )

    source_page_relative = (Path("wiki/sources") / inbox_suffix).with_suffix(".md").as_posix()
    source_page_path = repo_root / source_page_relative
    checksum = hashlib.sha256(source_bytes).hexdigest()

    try:
        source_ref = _build_source_ref(repo_root, processed_relative, checksum)
    except SourceRefValidationError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"generated SourceRef failed validation: {exc}",
                source_page=source_page_relative,
                processed_path=processed_relative,
            )
        )
    provenance = _build_provisional_source_provenance()

    # --- Phase 3: Write source page and move file to processed ---
    source_page_content = _render_source_page(
        source_relative=source_relative,
        processed_relative=processed_relative,
        source_ref=source_ref,
        provenance=provenance,
        source_bytes=source_bytes,
        checksum=checksum,
    )

    try:
        page_changed, previous_content = write_text_capturing_previous_safe(source_page_path, source_page_content)
    except OSError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"unable to write source page: {source_page_relative} ({exc})",
                source_page=source_page_relative,
                processed_path=processed_relative,
                source_ref=source_ref,
                provenance=provenance,
            )
        )

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_path.replace(processed_path)
    except OSError as exc:
        if page_changed:
            try:
                _restore_previous_content(source_page_path, previous_content)
            except OSError as rollback_exc:
                return _SourceIngestAttempt(
                    outcome=SourceOutcome(
                        source=source_relative,
                        status=contracts.ResultStatus.FAILED.value,
                        reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                        message=(
                            "failed moving source and rollback failed: "
                            f"{source_relative} ({exc}); rollback error ({rollback_exc})"
                        ),
                        source_page=source_page_relative,
                        processed_path=processed_relative,
                        source_ref=source_ref,
                        provenance=provenance,
                    )
                )

        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"unable to move source into raw/processed: {source_relative} ({exc})",
                source_page=source_page_relative,
                processed_path=processed_relative,
                source_ref=source_ref,
                provenance=provenance,
            )
        )

    return _SourceIngestAttempt(
        outcome=SourceOutcome(
            source=source_relative,
            status=contracts.ResultStatus.WRITTEN.value,
            reason_code=contracts.ReasonCode.OK.value,
            message="ingested",
            source_page=source_page_relative,
            processed_path=processed_relative,
            source_ref=source_ref,
            provenance=provenance,
        ),
        mutation=_SourceMutation(
            source=source_relative,
            source_page=source_page_relative,
            processed_path=processed_relative,
            source_page_changed=page_changed,
            source_page_previous_content=previous_content,
        ),
    )


def _restore_previous_content(path: Path, previous_content: str | None) -> None:
    if previous_content is None:
        if path.exists() or path.is_symlink():
            check_no_symlink_path(path)
            path.unlink()
        return

    write_text_capturing_previous_safe(path, previous_content)


def _rollback_ingest_mutations(
    *,
    repo_root: Path,
    source_mutations: list[_SourceMutation],
    index_path: Path,
    index_snapshot_captured: bool,
    index_previous_content: str | None,
    log_path: Path,
    log_snapshot_captured: bool,
    log_previous_content: str | None,
) -> str | None:
    errors: list[str] = []

    for mutation in reversed(source_mutations):
        source_path = repo_root / mutation.source
        processed_path = repo_root / mutation.processed_path
        try:
            check_no_symlink_path(source_path)
            check_no_symlink_path(processed_path)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.exists() or source_path.is_symlink():
                raise OSError(f"source path already exists during rollback: {mutation.source}")
            if processed_path.is_symlink():
                raise OSError(
                    f"processed path must not be symlinked during rollback: {mutation.processed_path}"
                )
            if not processed_path.exists():
                raise OSError(
                    f"processed file missing during rollback: {mutation.processed_path}"
                )
            processed_path.replace(source_path)
        except OSError as exc:
            errors.append(str(exc))

        if mutation.source_page_changed:
            source_page_path = repo_root / mutation.source_page
            try:
                _restore_previous_content(
                    source_page_path,
                    mutation.source_page_previous_content,
                )
            except OSError as exc:
                errors.append(
                    f"unable to restore source page during rollback: {mutation.source_page} ({exc})"
                )

    if index_snapshot_captured:
        try:
            _restore_previous_content(index_path, index_previous_content)
        except OSError as exc:
            errors.append(f"unable to restore index during rollback: {index_path} ({exc})")

    if log_snapshot_captured:
        try:
            _restore_previous_content(log_path, log_previous_content)
        except OSError as exc:
            errors.append(f"unable to restore log during rollback: {log_path} ({exc})")

    if errors:
        return "; ".join(errors)
    return None


def _mark_written_outcomes_rolled_back(
    outcomes: list[SourceOutcome],
    *,
    failure_reason: str,
    failure_reason_code: str,
    rollback_error: str | None,
) -> list[SourceOutcome]:
    if rollback_error is None:
        failure_message = f"rolled back due fatal ingest failure: {failure_reason}"
    else:
        failure_message = (
            "fatal ingest failure with rollback error: "
            f"{failure_reason}; rollback failed: {rollback_error}"
        )

    rewritten: list[SourceOutcome] = []
    for outcome in outcomes:
        if outcome.status != contracts.ResultStatus.WRITTEN.value:
            rewritten.append(outcome)
            continue

        rewritten.append(
            SourceOutcome(
                source=outcome.source,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=failure_reason_code,
                message=failure_message,
                source_page=outcome.source_page,
                processed_path=outcome.processed_path,
                source_ref=outcome.source_ref,
                provenance=outcome.provenance,
            )
        )
    return rewritten


def _write_index_if_changed(wiki_root: Path) -> bool:
    try:
        return update_index.generate_and_write_index(wiki_root)
    except update_index.IndexGenerationError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to generate index: {exc}",
        ) from exc
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to write index: {wiki_root / 'index.md'} ({exc})",
        ) from exc


def _render_log_entry(outcomes: list[SourceOutcome]) -> str:
    if not outcomes:
        return "- ingest: no-op"

    details = ", ".join(
        f"{outcome.source}->{outcome.processed_path}"
        for outcome in outcomes
        if outcome.processed_path is not None
    )
    return f"- ingest: processed {len(outcomes)} source(s): {details}"


def _ensure_wiki_tree(wiki_root: Path) -> None:
    for directory in page_template_utils.TOPICAL_NAMESPACES:
        (wiki_root / directory).mkdir(parents=True, exist_ok=True)


__all__ = ["run_cli", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
