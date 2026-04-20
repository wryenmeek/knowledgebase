"""Read-only governance validation wrapper over approved post-MVP checks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from datetime import date
from typing import Iterable, Sequence

if __package__ in (None, ""):  # supports both 'python -m' and direct invocation without package install
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.kb import contracts, page_template_utils, path_utils, sourceref, update_index

REPO_ROOT = Path(__file__).resolve().parents[4]
REQUIRED_TEMPLATE_SECTIONS = page_template_utils.TEMPLATE_SECTION_REQUIREMENTS


class ValidationMode(StrEnum):
    SIGNAL = "signal"
    BLOCKING = "blocking"


class ValidatorName(StrEnum):
    SOURCEREF_SHAPE = "sourceref-shape"
    PAGE_TEMPLATE = "page-template"
    APPEND_ONLY_LOG = "append-only-log"
    TOPOLOGY_HYGIENE = "topology-hygiene"
    FRESHNESS_THRESHOLD = "freshness-threshold"


class FindingStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class ReasonCode(StrEnum):
    OK = "ok"
    VALIDATION_FAILED = "validation_failed"
    PREREQ_MISSING = "prereq_missing"
    PARTIAL_RESULTS = "partial_results"
    UNSUPPORTED_VALIDATOR = "unsupported_validator"
    INVALID_INPUT = "invalid_input"


SUPPORTED_VALIDATORS: tuple[ValidatorName, ...] = (
    ValidatorName.SOURCEREF_SHAPE,
    ValidatorName.PAGE_TEMPLATE,
    ValidatorName.APPEND_ONLY_LOG,
    ValidatorName.TOPOLOGY_HYGIENE,
)
# freshness-threshold is opt-in only; it must NOT be added to SUPPORTED_VALIDATORS
# (the default set) until validated safe for all existing CI callers.
OPT_IN_VALIDATORS: tuple[ValidatorName, ...] = (
    ValidatorName.FRESHNESS_THRESHOLD,
)
ALL_KNOWN_VALIDATORS: tuple[ValidatorName, ...] = SUPPORTED_VALIDATORS + OPT_IN_VALIDATORS
PROTECTED_PATH_GLOBS: tuple[str, ...] = contracts.WRITE_ALLOWLIST_PATHS + (
    contracts.WRITE_LOCK_PATH,
)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator: str
    target: str
    status: FindingStatus | str
    reason_code: ReasonCode | str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "reason_code", str(self.reason_code))

    def to_dict(self) -> dict[str, str]:
        return {
            "validator": self.validator,
            "target": self.target,
            "status": self.status,
            "reason_code": self.reason_code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class GovernanceReport:
    requested_mode: str | None
    effective_mode: ValidationMode | str
    hard_fail: bool
    protected_paths: tuple[str, ...]
    validators: tuple[str, ...]
    unsupported_validators: tuple[str, ...]
    findings: tuple[ValidationFinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "effective_mode", str(self.effective_mode))

    @property
    def has_failures(self) -> bool:
        return any(finding.status == FindingStatus.FAIL.value for finding in self.findings)

    @property
    def has_partial_results(self) -> bool:
        return bool(self.unsupported_validators) or any(
            finding.status == FindingStatus.SKIP.value for finding in self.findings
        )

    def exit_code(self) -> int:
        if self.unsupported_validators:
            return 1
        if self.has_failures or self.has_partial_results:
            return 1 if self.hard_fail else 0
        return 0

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "hard_fail": self.hard_fail,
            "protected_paths": list(self.protected_paths),
            "validators": list(self.validators),
            "unsupported_validators": list(self.unsupported_validators),
            "findings": [finding.to_dict() for finding in self.findings],
        }


class InvalidPathError(ValueError):
    pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run approved repo-local governance checks in signal or blocking mode."
        )
    )
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in ValidationMode),
        help="Validation posture. Protected/write paths default to blocking.",
    )
    parser.add_argument(
        "--validator",
        action="append",
        dest="validators",
        help="Repeat to run a subset of approved validators.",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Repeat to scope checks to repo-relative paths.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress passing findings; on a clean run emit a compact pass summary.",
    )
    return parser


def normalize_repo_relative_path(value: str | Path) -> str:
    try:
        return path_utils.normalize_repo_relative_path(value)
    except path_utils.RepoRelativePathError as exc:
        raise InvalidPathError(str(exc)) from exc


def is_protected_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return any(pure_path.match(pattern) for pattern in PROTECTED_PATH_GLOBS)


def resolve_validation_mode(
    requested_mode: ValidationMode | None,
    target_paths: Sequence[str],
) -> ValidationMode:
    if requested_mode is not None:
        return requested_mode
    if not target_paths or any(is_protected_path(path) for path in target_paths):
        return ValidationMode.BLOCKING
    return ValidationMode.SIGNAL


def resolve_validators(raw_validators: Sequence[str] | None) -> tuple[tuple[ValidatorName, ...], tuple[str, ...]]:
    if not raw_validators:
        return SUPPORTED_VALIDATORS, ()

    selected: list[ValidatorName] = []
    unsupported: list[str] = []
    seen: set[str] = set()
    for raw_name in raw_validators:
        if raw_name in seen:
            continue
        seen.add(raw_name)
        try:
            selected.append(ValidatorName(raw_name))
        except ValueError:
            unsupported.append(raw_name)
    return tuple(selected), tuple(unsupported)

def run_validation(
    *,
    requested_mode: ValidationMode | None,
    validator_names: Sequence[str] | None = None,
    target_paths: Sequence[str] | None = None,
    repo_root: str | Path = REPO_ROOT,
) -> GovernanceReport:
    normalized_repo_root = Path(repo_root).resolve()
    normalized_paths = tuple(normalize_repo_relative_path(path) for path in (target_paths or ()))
    effective_mode = resolve_validation_mode(requested_mode, normalized_paths)
    protected_paths = tuple(path for path in normalized_paths if is_protected_path(path))
    selected_validators, unsupported_validators = resolve_validators(validator_names)
    hard_fail = effective_mode == ValidationMode.BLOCKING or bool(protected_paths)

    findings: list[ValidationFinding] = []
    if unsupported_validators:
        findings.extend(
            ValidationFinding(
                validator=name,
                target="*",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.UNSUPPORTED_VALIDATOR,
                message=f"validator is not in the approved post-MVP allowlist: {name}",
            )
            for name in unsupported_validators
        )

    for validator in selected_validators:
        findings.extend(
            _run_validator(
                validator,
                repo_root=normalized_repo_root,
                target_paths=normalized_paths,
            )
        )

    return GovernanceReport(
        requested_mode=None if requested_mode is None else requested_mode.value,
        effective_mode=effective_mode,
        hard_fail=hard_fail,
        protected_paths=protected_paths,
        validators=tuple(validator.value for validator in selected_validators),
        unsupported_validators=unsupported_validators,
        findings=tuple(findings),
    )


def _run_validator(
    validator: ValidatorName,
    *,
    repo_root: Path,
    target_paths: Sequence[str],
) -> list[ValidationFinding]:
    if validator == ValidatorName.SOURCEREF_SHAPE:
        return _validate_sourceref_shape(repo_root, target_paths)
    if validator == ValidatorName.PAGE_TEMPLATE:
        return _validate_page_templates(repo_root, target_paths)
    if validator == ValidatorName.APPEND_ONLY_LOG:
        return _validate_append_only_log(repo_root, target_paths)
    if validator == ValidatorName.TOPOLOGY_HYGIENE:
        return _validate_topology_hygiene(repo_root, target_paths)
    if validator == ValidatorName.FRESHNESS_THRESHOLD:
        return _validate_freshness_threshold(repo_root, target_paths)
    raise AssertionError(f"unhandled validator: {validator}")


def _validate_sourceref_shape(repo_root: Path, target_paths: Sequence[str]) -> list[ValidationFinding]:
    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        return [_prereq_missing(ValidatorName.SOURCEREF_SHAPE, "wiki", "wiki root is required")]

    pages = _select_sourceref_targets(repo_root, target_paths)
    if pages is None:
        return [_partial_result(ValidatorName.SOURCEREF_SHAPE, tuple(target_paths))]

    findings: list[ValidationFinding] = []
    for page in pages:
        page_path = repo_root / page
        if not page_path.is_file():
            findings.append(_prereq_missing(ValidatorName.SOURCEREF_SHAPE, page, "page is required"))
            continue
        frontmatter_text, _ = page_template_utils.extract_frontmatter(page_path.read_text(encoding="utf-8"))
        if frontmatter_text is None:
            continue
        for source_value in page_template_utils.extract_sources_from_frontmatter(frontmatter_text):
            try:
                sourceref.validate_sourceref(source_value, authoritative=False)
            except sourceref.SourceRefValidationError as exc:
                findings.append(
                    ValidationFinding(
                        validator=ValidatorName.SOURCEREF_SHAPE.value,
                        target=page,
                        status=FindingStatus.FAIL,
                        reason_code=ReasonCode.VALIDATION_FAILED,
                        message=f"invalid SourceRef shape '{source_value}': {exc}. FIX: use canonical form repo://<owner>/<repo>/<path>@<git_sha>#<anchor>?sha256=<64hex>.",
                    )
                )
    if not findings:
        findings.append(_ok(ValidatorName.SOURCEREF_SHAPE, "wiki", "SourceRef shape checks passed"))
    return findings


def _validate_page_templates(repo_root: Path, target_paths: Sequence[str]) -> list[ValidationFinding]:
    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        return [_prereq_missing(ValidatorName.PAGE_TEMPLATE, "wiki", "wiki root is required")]

    pages = _select_template_targets(repo_root, target_paths)
    if pages is None:
        return [_partial_result(ValidatorName.PAGE_TEMPLATE, tuple(target_paths))]

    findings: list[ValidationFinding] = []
    for page in pages:
        findings.extend(_validate_single_page_template(repo_root, page))
    if not findings:
        findings.append(_ok(ValidatorName.PAGE_TEMPLATE, "wiki", "page-template checks passed"))
    return findings


def _validate_single_page_template(repo_root: Path, page: str) -> list[ValidationFinding]:
    normalized_page, violations = page_template_utils.validate_page_template_path(
        page,
        repo_root=repo_root,
        required_frontmatter_keys=update_index.REQUIRED_FRONTMATTER_KEYS,
        template_section_requirements=REQUIRED_TEMPLATE_SECTIONS,
    )
    if not violations:
        return []
    if violations == (("missing-page", "page does not exist"),):
        return [_prereq_missing(ValidatorName.PAGE_TEMPLATE, normalized_page, "page is required")]
    return [
        ValidationFinding(
            validator=ValidatorName.PAGE_TEMPLATE.value,
            target=normalized_page,
            status=FindingStatus.FAIL,
            reason_code=ReasonCode.VALIDATION_FAILED,
            message=f"{message}. FIX: see schema/page-template.md for the required frontmatter structure.",
        )
        for _, message in violations
    ]


def _validate_append_only_log(repo_root: Path, target_paths: Sequence[str]) -> list[ValidationFinding]:
    if target_paths and "wiki/log.md" not in target_paths:
        return [_partial_result(ValidatorName.APPEND_ONLY_LOG, tuple(target_paths))]

    log_path = repo_root / "wiki" / "log.md"
    if not log_path.exists():
        return [_prereq_missing(ValidatorName.APPEND_ONLY_LOG, "wiki/log.md", "wiki/log.md is required")]
    if log_path.is_symlink() or not log_path.is_file():
        return [
            ValidationFinding(
                validator=ValidatorName.APPEND_ONLY_LOG.value,
                target="wiki/log.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message="wiki/log.md must be a regular non-symlink file",
            )
        ]

    contract = contracts.governed_artifact_contract("wiki/log.md")
    if contract is None:
        return [_prereq_missing(ValidatorName.APPEND_ONLY_LOG, "wiki/log.md", "governed artifact contract missing")]
    if contract.mutability != contracts.ArtifactMutability.APPEND_ONLY.value:
        return [
            ValidationFinding(
                validator=ValidatorName.APPEND_ONLY_LOG.value,
                target="wiki/log.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message="wiki/log.md must remain append-only",
            )
        ]
    if contract.write_strategy != contracts.ArtifactWriteStrategy.APPEND_UNDER_LOCK.value:
        return [
            ValidationFinding(
                validator=ValidatorName.APPEND_ONLY_LOG.value,
                target="wiki/log.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message="wiki/log.md must use append-under-lock semantics",
            )
        ]
    return [_ok(ValidatorName.APPEND_ONLY_LOG, "wiki/log.md", "append-only log contract passed")]


def _validate_topology_hygiene(repo_root: Path, target_paths: Sequence[str]) -> list[ValidationFinding]:
    if target_paths and not any(path == "wiki/index.md" or path.startswith("wiki/") for path in target_paths):
        return [_partial_result(ValidatorName.TOPOLOGY_HYGIENE, tuple(target_paths))]

    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        return [_prereq_missing(ValidatorName.TOPOLOGY_HYGIENE, "wiki", "wiki root is required")]

    index_path = wiki_root / "index.md"
    if not index_path.exists():
        return [_prereq_missing(ValidatorName.TOPOLOGY_HYGIENE, "wiki/index.md", "wiki/index.md is required")]
    if index_path.is_symlink() or not index_path.is_file():
        return [
            ValidationFinding(
                validator=ValidatorName.TOPOLOGY_HYGIENE.value,
                target="wiki/index.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message="wiki/index.md must be a regular non-symlink file",
            )
        ]

    try:
        generated = update_index.generate_index_content(wiki_root)
    except update_index.IndexGenerationError as exc:
        return [
            ValidationFinding(
                validator=ValidatorName.TOPOLOGY_HYGIENE.value,
                target="wiki/index.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message=f"topology hygiene failed: {exc}",
            )
        ]

    current = index_path.read_text(encoding="utf-8")
    if current != generated:
        return [
            ValidationFinding(
                validator=ValidatorName.TOPOLOGY_HYGIENE.value,
                target="wiki/index.md",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.VALIDATION_FAILED,
                message="wiki/index.md is out of sync with topology. FIX: run python3 scripts/kb/update_index.py --wiki-root wiki --write",
            )
        ]
    return [_ok(ValidatorName.TOPOLOGY_HYGIENE, "wiki/index.md", "topology hygiene passed")]


def _validate_freshness_threshold(repo_root: Path, target_paths: Sequence[str]) -> list[ValidationFinding]:
    freshness_script = repo_root / "scripts" / "validation" / "check_doc_freshness.py"
    if not freshness_script.is_file():
        return [_prereq_missing(
            ValidatorName.FRESHNESS_THRESHOLD,
            str(freshness_script.relative_to(repo_root)),
            "check_doc_freshness.py is required",
        )]

    as_of = date.today().isoformat()
    cmd = [
        sys.executable,
        str(freshness_script),
        "--scope",
        "wiki",
        "--as-of",
        as_of,
        "--max-age-days",
        "90",
    ]
    if target_paths:
        for path in target_paths:
            if path.startswith("wiki/") and path.endswith(".md"):
                cmd.extend(["--path", path])
        # If target_paths contains no wiki-scoped .md paths, the --path filter is
        # omitted and check_doc_freshness.py scans the full wiki scope. This is
        # intentional: the freshness validator is wiki-only; non-wiki paths are ignored.

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    except OSError as exc:
        return [
            ValidationFinding(
                validator=ValidatorName.FRESHNESS_THRESHOLD.value,
                target="wiki",
                status=FindingStatus.FAIL,
                reason_code=ReasonCode.PREREQ_MISSING,
                message=f"freshness check subprocess failed to start: {exc}",
            )
        ]

    if result.returncode == 0:
        return [_ok(ValidatorName.FRESHNESS_THRESHOLD, "wiki", "freshness-threshold checks passed")]

    try:
        data = json.loads(result.stdout)
        message = data.get("message", result.stdout.strip() or "freshness check failed")
    except (json.JSONDecodeError, AttributeError):
        message = result.stdout.strip() or result.stderr.strip() or "freshness check failed"

    return [
        ValidationFinding(
            validator=ValidatorName.FRESHNESS_THRESHOLD.value,
            target="wiki",
            status=FindingStatus.FAIL,
            reason_code=ReasonCode.VALIDATION_FAILED,
            message=message,
        )
    ]


def _select_sourceref_targets(repo_root: Path, target_paths: Sequence[str]) -> list[str] | None:
    if target_paths:
        selected = [path for path in target_paths if path.startswith("wiki/") and path.endswith(".md")]
        return selected or None
    return _all_wiki_markdown_paths(repo_root)


def _select_template_targets(repo_root: Path, target_paths: Sequence[str]) -> list[str] | None:
    if target_paths:
        selected = [path for path in target_paths if _is_topical_page_path(path)]
        return selected or None
    return _all_topical_page_paths(repo_root)


def _all_wiki_markdown_paths(repo_root: Path) -> list[str]:
    wiki_root = repo_root / "wiki"
    if not wiki_root.is_dir():
        return []
    return sorted(path.relative_to(repo_root).as_posix() for path in wiki_root.rglob("*.md") if path.is_file())


def _all_topical_page_paths(repo_root: Path) -> list[str]:
    wiki_root = repo_root / "wiki"
    pages: list[str] = []
    for namespace in page_template_utils.TOPICAL_NAMESPACES:
        namespace_root = wiki_root / namespace
        if not namespace_root.exists():
            continue
        for path in sorted(namespace_root.rglob("*.md")):
            if path.is_file():
                pages.append(path.relative_to(repo_root).as_posix())
    return pages


def _is_topical_page_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return len(parts) >= 3 and parts[0] == "wiki" and parts[1] in page_template_utils.TOPICAL_NAMESPACES and path.endswith(".md")


def _ok(validator: ValidatorName, target: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        validator=validator.value,
        target=target,
        status=FindingStatus.PASS,
        reason_code=ReasonCode.OK,
        message=message,
    )


def _partial_result(validator: ValidatorName, target_paths: Iterable[str]) -> ValidationFinding:
    target = ",".join(target_paths) if target_paths else "*"
    return ValidationFinding(
        validator=validator.value,
        target=target,
        status=FindingStatus.SKIP,
        reason_code=ReasonCode.PARTIAL_RESULTS,
        message="requested scope does not include an applicable target for this validator",
    )


def _prereq_missing(validator: ValidatorName, target: str, message: str) -> ValidationFinding:
    return ValidationFinding(
        validator=validator.value,
        target=target,
        status=FindingStatus.FAIL,
        reason_code=ReasonCode.PREREQ_MISSING,
        message=message,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = run_validation(
            requested_mode=None if args.mode is None else ValidationMode(args.mode),
            validator_names=args.validators,
            target_paths=args.paths,
        )
    except InvalidPathError as exc:
        print(
            json.dumps(
                {
                    "reason_code": ReasonCode.INVALID_INPUT.value,
                    "message": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    if args.quiet:
        failures = [f for f in report.findings if f.status != FindingStatus.PASS.value]
        if not failures:
            print(json.dumps({"findings_count": 0, "status": "pass", "validators_passed": len(report.validators)}, sort_keys=True))
        else:
            report_dict = report.to_dict()
            report_dict["findings"] = [f.to_dict() for f in failures]
            print(json.dumps(report_dict, sort_keys=True))
    else:
        print(json.dumps(report.to_dict(), sort_keys=True))
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
