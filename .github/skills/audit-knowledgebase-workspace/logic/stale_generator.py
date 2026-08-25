"""Deterministic stale deletion-candidate generator for the audit improve flow.

Implements `docs/ideas/audit-workspace-improve-flow.md` § Phase 4 (issue #205;
the GitHub issue title names slice 8d): the Hybrid deletion-candidate
generator's "Stale (deterministic)" bullet. Four deterministic detection paths
— missing repo-relative paths
(`git ls-files`), missing Python symbols (`rg --type python` over
`git ls-files -- "*.py"`, with a tracked-file text fallback when `rg` is
unavailable), closed GitHub issues (`gh issue view --json state`), and
superseded ADRs (parsed from `docs/decisions/ADR-*.md` H2/H3 `Status`
headings). LLM is NOT used on any path. Findings conform to
`.github/skills/audit-knowledgebase-workspace/schema/finding.schema.json`
(`proposed_destination: "Delete"`; `compliance_risk: "deterministic"`;
`cache_strategy` propagated by the caller, defaulting to mtime_first_para per
Q11 with hybrid_signature reserved per K15). Decision Q8 (lazy creation only)
is honored trivially — this module never writes. ADR-028 owns the
locality-ladder context this generator feeds. Repository reads are limited to
`scripts/kb/contracts.py` lock-path constants, ADR status files, tracked Python
fallback/AST validation, and the bounded `git`/`gh`/`rg` subprocess probes
above; repository writes are never performed.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable, Sequence


def _prepend_sys_path_once(path: Path) -> None:
    path_text = str(path)
    sys.path[:] = [entry for entry in sys.path if entry != path_text]
    sys.path.insert(0, path_text)


if __package__ in (None, ""):
    _prepend_sys_path_once(Path(__file__).resolve().parents[4])
    _prepend_sys_path_once(Path(__file__).resolve().parent)

from scripts._redaction import redact_stderr
from scripts.kb.contracts import (
    CHECKPOINT_REGISTRY_LOCK_PATH,
    CUSTOMIZATIONS_LOCK_PATH,
    DRIVE_SOURCES_LOCK_PATH,
    GITHUB_SOURCES_LOCK_PATH,
    REJECTION_REGISTRY_LOCK_PATH,
    WRITE_LOCK_PATH,
)
from skill_corpus_cache import CACHE_STRATEGY
try:
    from _paths import SAFE_REPO_RELATIVE_PATH_PATTERN, SAFE_REPO_RELATIVE_PATH_RE
except ImportError:  # pragma: no cover - exercised when imported as a package
    from ._paths import SAFE_REPO_RELATIVE_PATH_PATTERN, SAFE_REPO_RELATIVE_PATH_RE


COMMAND_TIMEOUT_SECONDS = 10
ISSUE_COMMAND_TIMEOUT_SECONDS = 5
MAX_INSTRUCTION_CHARS = 50_000
MAX_REFERENCES_PER_KIND = 100
MAX_TOTAL_PROBES = 200
MAX_ISSUE_REFERENCE_DIGITS = 10
VALID_CACHE_STRATEGIES = (CACHE_STRATEGY, "hybrid_signature")
GOVERNANCE_LOCK_PATHS = frozenset(
    {
        CHECKPOINT_REGISTRY_LOCK_PATH,
        CUSTOMIZATIONS_LOCK_PATH,
        DRIVE_SOURCES_LOCK_PATH,
        GITHUB_SOURCES_LOCK_PATH,
        REJECTION_REGISTRY_LOCK_PATH,
        WRITE_LOCK_PATH,
    }
)
PATH_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_/.-])"
    r"([A-Za-z0-9_/.-]+\."
    r"(?:py|md|json|ya?ml|sh|js|ts|toml|txt|lock|cfg|ini|example|baseline|gitkeep)"
    r"|\.gitkeep)\b",
    re.IGNORECASE,
)
ISSUE_REFERENCE_RE = re.compile(
    rf"(?<![A-Za-z0-9])#([0-9]{{1,{MAX_ISSUE_REFERENCE_DIGITS}}})\b"
)
ADR_REFERENCE_RE = re.compile(r"\bADR-([0-9]{1,4})\b", re.IGNORECASE)
STATUS_HEADING_RE = re.compile(r"^#{2,3}\s+status\b", re.IGNORECASE)
SCHEMELESS_URL_PATH_RE = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+/")
SYMBOL_BACKTICK_REFERENCE_RE = re.compile(
    r"\b(?:function|func|method|class|symbol|helper)\s+`([A-Za-z_][A-Za-z0-9_]*)`(?:\(\))?",
    re.IGNORECASE,
)
SYMBOL_PLAIN_REFERENCE_RE = re.compile(
    r"\b(?:function|func|method|class|symbol|helper)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\(\))?",
    re.IGNORECASE,
)
BACKTICK_CALL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)\(\)`")
BACKTICK_IDENTIFIER_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
CommandRunner = Callable[
    [Sequence[str], Path, int],
    subprocess.CompletedProcess[str],
]
StaleFinding = dict[str, str | int | None]


def generate_stale_findings(
    instruction_text: str,
    *,
    source_file: str,
    source_section: str,
    repo_root: str | Path = ".",
    cache_strategy: str = CACHE_STRATEGY,
    command_runner: CommandRunner | None = None,
) -> tuple[StaleFinding, ...]:
    """Return deterministic Delete findings for stale instruction references."""

    normalized_source_file = _validate_repo_relative_path(source_file, "source_file")
    normalized_source_section = source_section.strip()
    if not normalized_source_section:
        raise ValueError("source_section must be non-empty")
    if cache_strategy not in VALID_CACHE_STRATEGIES:
        raise ValueError(f"unsupported cache_strategy: {cache_strategy}")

    repo_root_path = Path(repo_root).resolve()
    runner = command_runner or _run_command
    findings: list[StaleFinding] = []

    if len(instruction_text) > MAX_INSTRUCTION_CHARS:
        raise ValueError("instruction_text exceeds deterministic stale-generator input limit")

    path_references = _bounded_references(extract_path_references(instruction_text), "path")
    symbol_references = _bounded_references(extract_symbol_references(instruction_text), "symbol")
    issue_references = _bounded_references(extract_issue_references(instruction_text), "issue")
    adr_references = _bounded_references(extract_adr_references(instruction_text), "ADR")
    _check_total_probe_budget(
        path_references,
        symbol_references,
        issue_references,
        extra_probe_count=1 if symbol_references else 0,
    )

    for referenced_path in path_references:
        if not _git_path_exists(referenced_path, repo_root=repo_root_path, runner=runner):
            findings.append(
                _finding(
                    source_file=normalized_source_file,
                    source_section=normalized_source_section,
                    rationale=(
                        f"References file {referenced_path} which does not exist in git ls-files."
                    ),
                    deletion_candidate=f"missing file reference: {referenced_path}",
                    cache_strategy=cache_strategy,
                )
            )

    tracked_python_files = (
        _tracked_python_files(repo_root=repo_root_path, runner=runner) if symbol_references else ()
    )
    existing_python_symbols = (
        _existing_python_symbols(
            symbol_references,
            repo_root=repo_root_path,
            runner=runner,
            python_files=tracked_python_files,
        )
        if symbol_references
        else frozenset()
    )
    for symbol in symbol_references:
        if symbol not in existing_python_symbols:
            findings.append(
                _finding(
                    source_file=normalized_source_file,
                    source_section=normalized_source_section,
                    rationale=(
                        f"References Python symbol {symbol} which was not found by rg --type python."
                    ),
                    deletion_candidate=f"missing Python symbol reference: {symbol}",
                    cache_strategy=cache_strategy,
                )
            )

    for issue_number in issue_references:
        if _issue_is_closed(issue_number, repo_root=repo_root_path, runner=runner):
            findings.append(
                _finding(
                    source_file=normalized_source_file,
                    source_section=normalized_source_section,
                    rationale=f"References closed GitHub issue #{issue_number}.",
                    deletion_candidate=f"closed issue reference: #{issue_number}",
                    cache_strategy=cache_strategy,
                )
            )

    if adr_references:
        adr_statuses = build_adr_supersession_map(repo_root_path)
        for adr_id in adr_references:
            status = adr_statuses.get(adr_id)
            if status is None:
                continue
            findings.append(
                _finding(
                    source_file=normalized_source_file,
                    source_section=normalized_source_section,
                    rationale=(
                        f"References {adr_id}, whose ## Status indicates it was superseded: "
                        f"{status}."
                    ),
                    deletion_candidate=f"superseded ADR reference: {adr_id}",
                    cache_strategy=cache_strategy,
                )
            )

    return tuple(findings)


def extract_path_references(instruction_text: str) -> tuple[str, ...]:
    """Extract unique, validated repo-relative file references from instruction text."""

    paths: set[str] = set()
    for match in PATH_REFERENCE_RE.finditer(instruction_text):
        try:
            normalized_path = _validate_repo_relative_path(match.group(1), "instruction path reference")
        except ValueError:
            continue
        if SCHEMELESS_URL_PATH_RE.match(normalized_path):
            continue
        if normalized_path in GOVERNANCE_LOCK_PATHS:
            continue
        paths.add(normalized_path)
    return tuple(sorted(paths))


def extract_symbol_references(instruction_text: str) -> tuple[str, ...]:
    """Extract explicit Python symbol references from instruction text."""

    symbols = {match.group(1) for match in SYMBOL_BACKTICK_REFERENCE_RE.finditer(instruction_text)}
    symbols.update(
        match.group(1)
        for match in SYMBOL_PLAIN_REFERENCE_RE.finditer(instruction_text)
        if _looks_like_code_symbol(match.group(1))
    )
    symbols.update(match.group(1) for match in BACKTICK_CALL_RE.finditer(instruction_text))
    symbols.update(
        match.group(1)
        for match in BACKTICK_IDENTIFIER_RE.finditer(instruction_text)
        if _looks_like_code_symbol(match.group(1))
    )
    return tuple(sorted(_validate_symbol(symbol) for symbol in symbols))


def extract_issue_references(instruction_text: str) -> tuple[str, ...]:
    """Extract unique GitHub issue numbers from instruction text."""

    issue_numbers = {
        normalized
        for match in ISSUE_REFERENCE_RE.finditer(instruction_text)
        if (normalized := match.group(1).lstrip("0")) != ""
        and int(normalized) > 0
    }
    return tuple(str(number) for number in sorted(int(issue_number) for issue_number in issue_numbers))


def extract_adr_references(instruction_text: str) -> tuple[str, ...]:
    """Extract unique normalized ADR identifiers from instruction text."""

    adr_ids = {
        f"ADR-{int(match.group(1)):03d}"
        for match in ADR_REFERENCE_RE.finditer(instruction_text)
    }
    return tuple(sorted(adr_ids))


def build_adr_supersession_map(repo_root: str | Path = ".") -> dict[str, str]:
    """Return ``ADR-NNN`` statuses whose Status section says the ADR is superseded."""

    repo_root_path = Path(repo_root).resolve()
    decisions_dir = repo_root_path / "docs" / "decisions"
    if not decisions_dir.is_dir():
        return {}

    statuses: dict[str, str] = {}
    for adr_path in sorted(decisions_dir.glob("ADR-*.md")):
        resolved = adr_path.resolve()
        if not resolved.is_relative_to(decisions_dir):
            raise ValueError(f"ADR path escapes docs/decisions: {adr_path}")
        adr_id = _adr_id_for_path(resolved)
        if adr_id is None:
            continue
        status = _extract_status_line(resolved.read_text(encoding="utf-8"))
        if status is not None and _status_indicates_supersession(status):
            statuses[adr_id] = status
    return statuses


def _bounded_references(references: tuple[str, ...], kind: str) -> tuple[str, ...]:
    if len(references) > MAX_REFERENCES_PER_KIND:
        raise ValueError(f"too many {kind} references for deterministic stale scan")
    return references


def _check_total_probe_budget(
    *reference_groups: tuple[str, ...],
    extra_probe_count: int = 0,
) -> None:
    total_probes = sum(len(group) for group in reference_groups) + extra_probe_count
    if total_probes > MAX_TOTAL_PROBES:
        raise ValueError("too many subprocess probes for deterministic stale scan")


def _git_path_exists(
    referenced_path: str,
    *,
    repo_root: Path,
    runner: CommandRunner,
) -> bool:
    result = runner(
        ["git", "ls-files", "--", referenced_path],
        repo_root,
        COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(_command_error_message("git ls-files", result))
    return bool(result.stdout.strip())


def _existing_python_symbols(
    symbols: tuple[str, ...],
    *,
    repo_root: Path,
    runner: CommandRunner,
    python_files: tuple[str, ...],
) -> frozenset[str]:
    if not symbols or not python_files:
        return frozenset()

    existing_symbols: set[str] = set()
    for symbol in symbols:
        try:
            if _python_symbol_exists_with_rg(
                symbol,
                repo_root=repo_root,
                runner=runner,
                python_files=python_files,
            ):
                existing_symbols.add(symbol)
        except RuntimeError as exc:
            if "rg CLI is required" not in str(exc):
                raise
            return _python_fallback_defined_symbols(
                symbols,
                repo_root=repo_root,
                python_files=python_files,
            )
    return frozenset(existing_symbols)


def _python_symbol_exists_with_rg(
    symbol: str,
    *,
    repo_root: Path,
    runner: CommandRunner,
    python_files: tuple[str, ...],
) -> bool:
    if not python_files:
        return False
    result = runner(
        ["rg", "-l", "--fixed-strings", "--type", "python", "--", symbol, *python_files],
        repo_root,
        COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode == 1:
        return False
    if result.returncode != 0:
        raise RuntimeError(_command_error_message("rg", result))
    candidate_paths = tuple(
        _validate_repo_relative_path(line.strip(), "rg match path")
        for line in result.stdout.splitlines()
        if line.strip()
    )
    return _python_symbol_defined(symbol, repo_root=repo_root, candidate_paths=candidate_paths)


def _tracked_python_files(
    *,
    repo_root: Path,
    runner: CommandRunner,
) -> tuple[str, ...]:
    result = runner(
        ["git", "ls-files", "--", "*.py"],
        repo_root,
        COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(_command_error_message("git ls-files python", result))
    return tuple(
        _validate_repo_relative_path(line.strip(), "tracked Python path")
        for line in result.stdout.splitlines()
        if line.strip()
    )


def _python_symbol_defined(
    symbol: str,
    *,
    repo_root: Path,
    candidate_paths: tuple[str, ...],
) -> bool:
    for candidate_path in candidate_paths:
        path = (repo_root / candidate_path).resolve()
        if not path.is_relative_to(repo_root):
            raise ValueError(f"rg match path escapes repository root: {candidate_path}")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=candidate_path)
        except OSError as exc:
            raise RuntimeError(f"unable to read rg match path: {candidate_path}") from exc
        except SyntaxError as exc:
            raise RuntimeError(f"unable to parse rg match path: {candidate_path}") from exc
        if symbol in _defined_symbol_names(tree):
            return True
    return False


def _python_fallback_defined_symbols(
    symbols: tuple[str, ...],
    *,
    repo_root: Path,
    python_files: tuple[str, ...],
) -> frozenset[str]:
    sought_symbols = set(symbols)
    defined_symbols: set[str] = set()
    for python_file in python_files:
        path = (repo_root / python_file).resolve()
        if not path.is_relative_to(repo_root):
            raise ValueError(f"tracked Python path escapes repository root: {python_file}")
        try:
            file_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"unable to read tracked Python path: {python_file}") from exc
        if not any(symbol in file_text for symbol in sought_symbols):
            continue
        try:
            tree = ast.parse(file_text, filename=python_file)
        except SyntaxError as exc:
            raise RuntimeError(f"unable to parse tracked Python path: {python_file}") from exc
        defined_symbols.update(_defined_symbol_names(tree) & sought_symbols)
        if sought_symbols.issubset(defined_symbols):
            break
    return frozenset(defined_symbols)


def _defined_symbol_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            names.update(_assignment_target_names(node))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(_imported_names(node))
    return names


def _assignment_target_names(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> set[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    else:
        targets = [node.target]
    names: set[str] = set()
    for target in targets:
        names.update(_target_names(target))
    return names


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_target_names(element))
        return names
    return set()


def _imported_names(node: ast.Import | ast.ImportFrom) -> set[str]:
    names: set[str] = set()
    for alias in node.names:
        if alias.asname:
            names.add(alias.asname)
        elif isinstance(node, ast.Import):
            names.add(alias.name.split(".", 1)[0])
        else:
            names.add(alias.name)
    return names


def _issue_is_closed(
    issue_number: str,
    *,
    repo_root: Path,
    runner: CommandRunner,
) -> bool:
    if not issue_number.isdigit() or len(issue_number) > MAX_ISSUE_REFERENCE_DIGITS:
        raise ValueError(f"invalid issue number: {issue_number}")
    result = runner(
        ["gh", "issue", "view", issue_number, "--json", "state", "--jq", ".state"],
        repo_root,
        ISSUE_COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(_command_error_message("gh issue view", result))
    state = result.stdout.strip().lower()
    if state not in {"open", "closed"}:
        raise RuntimeError(
            f"gh issue view returned unsupported state for #{issue_number}: {state!r}"
        )
    return state == "closed"


def _run_command(
    command: Sequence[str],
    repo_root: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{command[0]} CLI is required but not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{command[0]} command timed out after {timeout_seconds} seconds") from exc


def _finding(
    *,
    source_file: str,
    source_section: str,
    rationale: str,
    deletion_candidate: str,
    cache_strategy: str,
) -> StaleFinding:
    return {
        "source_file": source_file,
        "source_section": source_section,
        "proposed_destination": "Delete",
        "rationale": rationale,
        "compliance_risk": "deterministic",
        "expected_token_efficiency_rank": 0,
        "cache_strategy": cache_strategy,
        "suggested_artifact_path": source_file,
        "deletion_candidate": deletion_candidate,
        "citation": None,
    }


def _validate_repo_relative_path(raw_path: str, label: str) -> str:
    candidate = raw_path.strip()
    while candidate.startswith("./"):
        candidate = candidate[2:]
    if not SAFE_REPO_RELATIVE_PATH_RE.fullmatch(candidate):
        raise ValueError(f"unsafe {label}: {raw_path}")
    return candidate


def _validate_symbol(symbol: str) -> str:
    if len(symbol) > 128 or not symbol.isidentifier():
        raise ValueError(f"unsafe symbol reference: {symbol}")
    return symbol


def _looks_like_code_symbol(symbol: str) -> bool:
    return "_" in symbol or symbol[:1].isupper()


def _adr_id_for_path(adr_path: Path) -> str | None:
    match = re.match(r"ADR-([0-9]{1,4})-", adr_path.name, re.IGNORECASE)
    if match is None:
        return None
    return f"ADR-{int(match.group(1)):03d}"


def _extract_status_line(markdown_text: str) -> str | None:
    lines = markdown_text.splitlines()
    for index, line in enumerate(lines):
        # Historical ADRs use H2/H3 Status headings and some include a trailing colon.
        if not STATUS_HEADING_RE.match(line.strip().rstrip(":")):
            continue
        for status_line in lines[index + 1 :]:
            stripped = status_line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                return None
            return stripped
    return None


def _status_indicates_supersession(status: str) -> bool:
    return status.lower().lstrip("-• ").startswith("superseded")


def _command_error_message(command_name: str, result: subprocess.CompletedProcess[str]) -> str:
    stderr = redact_stderr(result.stderr).splitlines()
    detail = stderr[0] if stderr else f"exit {result.returncode}"
    return f"{command_name} failed: {detail}"


__all__ = [
    "COMMAND_TIMEOUT_SECONDS",
    "ISSUE_COMMAND_TIMEOUT_SECONDS",
    "MAX_INSTRUCTION_CHARS",
    "MAX_ISSUE_REFERENCE_DIGITS",
    "MAX_REFERENCES_PER_KIND",
    "MAX_TOTAL_PROBES",
    "SAFE_REPO_RELATIVE_PATH_PATTERN",
    "VALID_CACHE_STRATEGIES",
    "StaleFinding",
    "build_adr_supersession_map",
    "extract_adr_references",
    "extract_issue_references",
    "extract_path_references",
    "extract_symbol_references",
    "generate_stale_findings",
]
