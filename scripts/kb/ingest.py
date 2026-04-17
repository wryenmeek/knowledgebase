"""Deterministic source ingest CLI."""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Sequence, TextIO

from scripts.kb import contracts, update_index
from scripts.kb.sourceref import SourceRefValidationError, validate_sourceref
from scripts.kb.write_utils import (
    LockUnavailableError,
    append_log_only_state_changes,
    exclusive_write_lock,
)


_ALLOWED_SOURCE_PREFIX = ("raw", "inbox")
_REQUIRED_BATCH_POLICY = contracts.PolicyId.CONTINUE_AND_REPORT_PER_SOURCE.value
_APPLIED_POLICIES = (
    contracts.PolicyId.CONTINUE_AND_REPORT_PER_SOURCE.value,
    contracts.PolicyId.LOG_ONLY_STATE_CHANGES.value,
)
# Ingest runs before a commit exists for newly written raw/processed artifacts, so
# it emits a canonical-shape provisional git SHA. Workflows must not treat this as
# authoritative until a later commit-bound reconciliation step replaces it.
_PROVISIONAL_GIT_SHA = "0" * 40


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Structured provenance status for machine-readable ingest outputs."""

    status: str
    authoritative: bool
    review_mode: str
    reconciliation: str
    git_sha: str
    git_sha_kind: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "review_mode": self.review_mode,
            "reconciliation": self.reconciliation,
            "git_sha": self.git_sha,
            "git_sha_kind": self.git_sha_kind,
        }


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
    if args.batch_policy != _REQUIRED_BATCH_POLICY:
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"batch policy must be {_REQUIRED_BATCH_POLICY}",
        )

    wiki_root_path, wiki_root_relative = _resolve_path_within_repo(repo_root, args.wiki_root)
    if not _is_under_wiki_root(Path(wiki_root_relative)):
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"wiki root must resolve under wiki/**: {args.wiki_root}",
        )

    schema_path, _schema_relative = _resolve_path_within_repo(repo_root, args.schema)
    if not schema_path.exists() or not schema_path.is_file():
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"schema file does not exist: {args.schema}",
        )

    source_inputs = _resolve_source_inputs(args, repo_root)
    with exclusive_write_lock(repo_root):
        _ensure_wiki_tree(wiki_root_path)

        outcomes: list[SourceOutcome] = []
        successful_outcomes: list[SourceOutcome] = []
        source_mutations: list[_SourceMutation] = []
        for source_input in source_inputs:
            attempt = _ingest_source(repo_root, wiki_root_path, source_input)
            outcome = attempt.outcome
            outcomes.append(outcome)
            if outcome.status == contracts.ResultStatus.WRITTEN.value:
                successful_outcomes.append(outcome)
                if attempt.mutation is not None:
                    source_mutations.append(attempt.mutation)

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
                    index_previous_content = _read_optional_text(index_path)
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
                    log_previous_content = _read_optional_text(log_path)
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
            "sources manifest is empty",
        )
    return entries


def _resolve_path_within_repo(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    candidate = Path(raw_path)
    resolved = (candidate if candidate.is_absolute() else (repo_root / candidate)).resolve(
        strict=False
    )
    # ⚡ Bolt Optimization: Use is_relative_to instead of try/except for bounds checking
    if not resolved.is_relative_to(repo_root):
        raise IngestError(
            contracts.ReasonCode.INVALID_INPUT.value,
            f"path escapes repository boundary: {raw_path}",
        )
    return resolved, resolved.relative_to(repo_root).as_posix()


def _resolve_inbox_path(repo_root: Path, raw_path: str) -> tuple[Path, str]:
    requested_path = Path(raw_path)
    lexical_path = requested_path if requested_path.is_absolute() else repo_root / requested_path
    try:
        _ensure_not_symlink(lexical_path)
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


def _ingest_source(repo_root: Path, wiki_root: Path, source_input: str) -> _SourceIngestAttempt:
    try:
        source_path, source_relative = _resolve_inbox_path(repo_root, source_input)
    except IngestError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_input,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=exc.reason_code,
                message=str(exc),
            )
        )

    if not source_path.exists() or not source_path.is_file():
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.INVALID_INPUT.value,
                message=f"source file does not exist: {source_relative}",
            )
        )

    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        return _SourceIngestAttempt(
            outcome=SourceOutcome(
                source=source_relative,
                status=contracts.ResultStatus.FAILED.value,
                reason_code=contracts.ReasonCode.WRITE_FAILED.value,
                message=f"unable to read source file: {source_relative} ({exc})",
            )
        )

    source_relative_path = Path(source_relative)
    inbox_suffix = Path(*source_relative_path.parts[2:])
    processed_relative = (Path("raw/processed") / inbox_suffix).as_posix()
    processed_path = repo_root / processed_relative
    try:
        _ensure_not_symlink(source_path)
        _ensure_not_symlink(processed_path)
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

    source_page_content = _render_source_page(
        source_relative=source_relative,
        processed_relative=processed_relative,
        source_ref=source_ref,
        provenance=provenance,
        source_bytes=source_bytes,
        checksum=checksum,
    )

    try:
        page_changed, previous_content = _write_text_if_changed(source_page_path, source_page_content)
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


def _build_source_ref(repo_root: Path, processed_relative: str, checksum: str) -> str:
    repo_name = re.sub(r"[^A-Za-z0-9_.-]", "-", repo_root.name) or "repo"
    source_ref = (
        f"repo://local/{repo_name}/{processed_relative}@{_PROVISIONAL_GIT_SHA}"
        f"#asset?sha256={checksum}"
    )
    validate_sourceref(source_ref)
    return source_ref


def _build_provisional_source_provenance() -> SourceProvenance:
    return SourceProvenance(
        status="provisional",
        authoritative=False,
        review_mode="authoritative_review_required",
        reconciliation="commit_bound_pending",
        git_sha=_PROVISIONAL_GIT_SHA,
        git_sha_kind="placeholder",
    )


def _render_source_page(
    *,
    source_relative: str,
    processed_relative: str,
    source_ref: str,
    provenance: SourceProvenance,
    source_bytes: bytes,
    checksum: str,
) -> str:
    title_token = Path(source_relative).stem.replace("_", " ").replace("-", " ").strip()
    normalized_title = " ".join(title_token.split()).title() or Path(source_relative).name
    page_title = f"Source: {normalized_title}"

    lines = [
        "---",
        "type: source",
        f'title: "{_escape_quotes(page_title)}"',
        "status: active",
        "sources:",
        f'  - "{_escape_quotes(source_ref)}"',
        "open_questions: []",
        "confidence: 5",
        "sensitivity: internal",
        'updated_at: "1970-01-01T00:00:00Z"',
        "tags:",
        "  - source",
        "---",
        "",
        f"# {page_title}",
        "",
        f"- inbox_path: `{source_relative}`",
        f"- processed_path: `{processed_relative}`",
        f"- sourceref: `{source_ref}`",
        f"- provenance_status: `{provenance.status}`",
        f"- provenance_authoritative: `{str(provenance.authoritative).lower()}`",
        f"- provenance_review_mode: `{provenance.review_mode}`",
        f"- provenance_reconciliation: `{provenance.reconciliation}`",
        f"- provenance_git_sha_kind: `{provenance.git_sha_kind}`",
        f"- checksum_sha256: `{checksum}`",
        f"- bytes: {len(source_bytes)}",
        "",
    ]
    return "\n".join(lines)


def _escape_quotes(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_text_if_changed(path: Path, content: str) -> tuple[bool, str | None]:
    previous_content: str | None = None
    if path.exists() or path.is_symlink():
        _ensure_not_symlink(path)
        previous_content = path.read_text(encoding="utf-8")
        if previous_content == content:
            return False, previous_content

    _write_text_atomically(path, content)
    return True, previous_content


def _restore_previous_content(path: Path, previous_content: str | None) -> None:
    if previous_content is None:
        if path.exists() or path.is_symlink():
            _ensure_not_symlink(path)
            path.unlink()
        return

    _write_text_atomically(path, previous_content)


def _read_optional_text(path: Path) -> str | None:
    if path.is_symlink():
        _ensure_not_symlink(path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _ensure_not_symlink(path: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise OSError(f"symlinked path component is not allowed: {current}")
        if current.parent == current:
            return
        current = current.parent


def _write_text_atomically(path: Path, content: str) -> None:
    _ensure_not_symlink(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_name(f"{path.name}.tmp")
    temp_created = False
    try:
        with _open_temp_text_path(temp_path) as handle:
            temp_created = True
            handle.write(content)
        _ensure_not_symlink(path)
        os.replace(temp_path, path)
    except OSError:
        if temp_created:
            with contextlib.suppress(OSError):
                temp_path.unlink()
        raise


def _open_temp_text_path(temp_path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temp_path, flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="\n")


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
            _ensure_not_symlink(source_path)
            _ensure_not_symlink(processed_path)
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
        generated_content = update_index.generate_index_content(wiki_root)
    except update_index.IndexGenerationError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to generate index: {exc}",
        ) from exc

    index_path = wiki_root / "index.md"
    try:
        if index_path.exists() or index_path.is_symlink():
            _ensure_not_symlink(index_path)
            existing_content = index_path.read_text(encoding="utf-8")
        else:
            existing_content = ""
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to read existing index: {index_path} ({exc})",
        ) from exc

    if existing_content == generated_content:
        return False

    try:
        _write_text_atomically(index_path, generated_content)
    except OSError as exc:
        raise IngestError(
            contracts.ReasonCode.WRITE_FAILED.value,
            f"unable to write index: {index_path} ({exc})",
        ) from exc
    return True


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
    for directory in ("sources", "entities", "concepts", "analyses"):
        (wiki_root / directory).mkdir(parents=True, exist_ok=True)


__all__ = ["run_cli", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
