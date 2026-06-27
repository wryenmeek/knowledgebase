"""Runtime for the wiki-processing checkpoint registry.

Supports three explicit modes:

* ``--bootstrap`` classifies existing generated wiki artifacts and optionally
  seeds ``raw/wiki-processing/wiki-processing-checkpoint-registry.json``.
* ``--mutate`` applies a lock-protected batch of item state transitions.
* ``--verify`` validates the registry and emits retention/parse/schema signals.

All write-capable paths are approval-gated and acquire only the lock declared
for the target artifact. Bootstrap and mutation writes hold
``CHECKPOINT_REGISTRY_LOCK_PATH``; verify remains read-only unless approved
warning telemetry is appended to ``wiki/log.md`` under ``WRITE_LOCK_PATH``.

Governance: ADR-026 (decision), ADR-027 (amendment),
schema/wiki-processing-checkpoint-registry-contract.md (schema), issue #187 (PR3).
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence, TextIO

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts._optional_surface_common import (  # noqa: E402
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    REASON_CODE_APPROVAL_REQUIRED,
    REASON_CODE_INVALID_INPUT,
    STATUS_FAIL,
    STATUS_PASS,
    JsonArgumentParser,
    SurfaceResult,
    base_path_rules,
    looks_like_repo_root,
    repo_relative,
    sha256_file,
)
from scripts.kb import contracts, page_template_utils, path_utils, write_utils  # noqa: E402

SURFACE = "scripts/kb/checkpoint_registry.py"
REGISTRY_PATH = "raw/wiki-processing/wiki-processing-checkpoint-registry.json"
SCHEMA_OWNER = "schema/wiki-processing-checkpoint-registry-contract.md"
SCHEMA_VERSION = "1"
STALE_TIMEOUT = timedelta(hours=1)
ITEM_COUNT_WARN_THRESHOLD = 5_000
MAX_INPUT_BYTES = 1_000_000
DRY_RUN_REDUNDANT_WARNING = (
    "--dry-run is redundant with --bootstrap; bootstrap is dry-run unless --apply is supplied"
)

ITEM_STATUSES = frozenset(
    {"pending", "in_progress", "completed", "stale", "failed", "skipped"}
)
BATCH_STATUSES = frozenset({"running", "completed", "failed", "partial"})
TERMINAL_BATCH_STATUSES = frozenset({"completed", "failed", "partial"})
ARTIFACT_TYPE_VALUES = frozenset(artifact.value for artifact in contracts.ArtifactType)
TRIGGER_VALUES = frozenset(trigger.value for trigger in contracts.TriggerType)
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
FP16_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-[0-9a-f]{16}$")
SLUG_RE = re.compile(r"[^a-z0-9]+")
IDENTITY_SUFFIX_RE = re.compile(r"^[a-z0-9](?:[a-z0-9:-]*[a-z0-9])?$")

ARTIFACT_PATH_ROOTS = {
    contracts.ArtifactType.WIKI_ENTITY_PAGE.value: "wiki/entities",
    contracts.ArtifactType.WIKI_CONCEPT_PAGE.value: "wiki/concepts",
    contracts.ArtifactType.WIKI_ANALYSIS_PAGE.value: "wiki/analyses",
}
ARTIFACT_TYPE_BY_NAMESPACE = {
    "entities": contracts.ArtifactType.WIKI_ENTITY_PAGE.value,
    "concepts": contracts.ArtifactType.WIKI_CONCEPT_PAGE.value,
    "analyses": contracts.ArtifactType.WIKI_ANALYSIS_PAGE.value,
}
ALLOWED_TRANSITIONS = frozenset(
    {
        ("pending", "in_progress"),
        ("in_progress", "completed"),
        ("in_progress", "stale"),
        ("in_progress", "failed"),
        ("completed", "stale"),
        ("stale", "in_progress"),
        ("failed", "in_progress"),
        ("pending", "skipped"),
        ("stale", "skipped"),
        ("skipped", "pending"),
    }
)

__all__ = [
    "REGISTRY_PATH",
    "STALE_TIMEOUT",
    "SURFACE",
    "bootstrap_registry",
    "main",
    "mutate_registry",
    "render_checkpoint_status",
    "run_checkpoint_registry",
    "verify_registry",
]


def _path_rules() -> dict[str, Any]:
    return base_path_rules(
        allowed_roots=("raw/wiki-processing", "wiki", "schema"),
        allowed_suffixes=(".json", ".md"),
    )


def _result(
    *,
    mode: str,
    status: str,
    reason_code: str,
    message: str,
    approval: str = APPROVAL_NONE,
    lock_required: bool = False,
    lock_path: str | None = None,
    items: Iterable[dict[str, Any]] = (),
    summary: dict[str, Any] | None = None,
) -> SurfaceResult:
    return SurfaceResult(
        surface=SURFACE,
        mode=mode,
        status=status,
        reason_code=reason_code,
        message=message,
        approval=approval,
        lock_path=(lock_path or contracts.CHECKPOINT_REGISTRY_LOCK_PATH) if lock_required else None,
        lock_required=lock_required,
        path_rules=_path_rules(),
        items=tuple(items),
        summary=dict(summary or {}),
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be an ISO 8601 string or null")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _is_single_line_text(value: Any, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    if not allow_empty and not value:
        return False
    return "\n" not in value and "\r" not in value and all(ord(char) >= 32 for char in value)


def _markdown_safe(value: Any) -> str:
    return (
        str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("`", "'")
    )


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64_RE.fullmatch(value))


def _validate_item_key_for_artifact(item_key: Any, artifact_type: Any) -> str:
    if not _is_single_line_text(item_key) or not isinstance(artifact_type, str):
        raise ValueError("item_key must be a non-empty string")
    if artifact_type not in ARTIFACT_TYPE_VALUES:
        raise ValueError("artifact_type is unsupported")
    prefix = f"{artifact_type}:"
    if not item_key.startswith(prefix):
        raise ValueError(f"item_key must start with {prefix}")
    suffix = item_key[len(prefix):]
    if not IDENTITY_SUFFIX_RE.fullmatch(suffix):
        raise ValueError("item_key identity suffix must be a canonical slug")
    return item_key


def _slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.casefold()).strip("-")
    return slug or "item"


def _resolve_registry_path(repo_root: Path, raw_path: str) -> Path:
    normalized = path_utils.normalize_repo_relative_path(raw_path)
    if normalized != REGISTRY_PATH:
        raise ValueError(f"registry path must be exactly {REGISTRY_PATH}")
    write_utils.check_no_symlink_path(repo_root / normalized)
    resolved = (repo_root / normalized).resolve(strict=False)
    if not resolved.is_relative_to(repo_root.resolve()):
        raise ValueError("registry path escapes repository root")
    return resolved


def _validate_output_path(repo_root: Path, output_path: str, artifact_type: str) -> str:
    normalized = path_utils.normalize_repo_relative_path(output_path)
    root = ARTIFACT_PATH_ROOTS.get(artifact_type)
    if root is None:
        raise ValueError(f"unsupported artifact_type: {artifact_type}")
    if not normalized.startswith(f"{root}/") or not normalized.endswith(".md"):
        raise ValueError(f"{artifact_type} output_path must be under {root}/ and end in .md")
    if len(normalized.removeprefix(f"{root}/").split("/")) != 1:
        raise ValueError(f"{artifact_type} output_path must be a direct child of {root}/")
    write_utils.check_no_symlink_path(repo_root / normalized)
    resolved = (repo_root / normalized).resolve(strict=False)
    root_path = (repo_root / root).resolve(strict=False)
    if not resolved.is_relative_to(root_path):
        raise ValueError(f"output_path escapes {root}: {output_path}")
    write_utils.check_no_symlink_path(resolved)
    return normalized


def _artifact_type_for_path(path: Path, repo_root: Path) -> str | None:
    try:
        rel = path.relative_to(repo_root / "wiki")
    except ValueError:
        return None
    if len(rel.parts) != 2 or path.suffix != ".md":
        return None
    return ARTIFACT_TYPE_BY_NAMESPACE.get(rel.parts[0])


def _item_key_for_page(path: Path, repo_root: Path, artifact_type: str) -> str:
    rel = repo_relative(repo_root, path)
    text = path.read_text(encoding="utf-8")
    metadata = page_template_utils.parse_page_frontmatter(text)
    if artifact_type == contracts.ArtifactType.WIKI_ENTITY_PAGE.value:
        identity = page_template_utils.strip_quotes(metadata.get("entity_id", "")) or path.stem
    elif artifact_type == contracts.ArtifactType.WIKI_CONCEPT_PAGE.value:
        identity = path.stem
    else:
        if not FP16_SUFFIX_RE.fullmatch(path.stem):
            raise ValueError("analysis page filename must end with a 16-character fingerprint")
        identity = path.stem
    _validate_output_path(repo_root, rel, artifact_type)
    return f"{artifact_type}:{_slugify(identity)}"


def _scan_source_fingerprints(repo_root: Path) -> dict[str, str]:
    source_root = repo_root / "wiki" / "sources"
    if not source_root.exists():
        return {}
    fingerprints: dict[str, str] = {}
    for path in sorted(source_root.rglob("*.md")):
        if not path.is_file():
            continue
        write_utils.check_no_symlink_path(path)
        fingerprints[repo_relative(repo_root, path)] = sha256_file(path)
    return fingerprints


def _compute_dependency_fingerprint(repo_root: Path) -> str:
    paths: set[Path] = set()
    for patterns in contracts.DEPENDENCY_FINGERPRINT_SOURCES.values():
        for pattern in patterns:
            if any(char in pattern for char in "*?["):
                # `Path.glob("**")` behavior changed in Python 3.13: prior to
                # 3.13 the trailing `**` only matched directories, but in
                # 3.13+ it matches files and directories. To keep dependency
                # fingerprints deterministic across the supported interpreter
                # range (CI runs 3.12; local dev may run 3.13/3.14), normalize
                # trailing `**` to `**/*` so files are enumerated explicitly.
                normalized_pattern = pattern[:-2] + "**/*" if pattern.endswith("/**") else pattern
                paths.update(
                    path for path in repo_root.glob(normalized_pattern) if path.is_file()
                )
            else:
                candidate = repo_root / pattern
                if candidate.is_file():
                    paths.add(candidate)
    # Filter out Python bytecode caches — they are environment-dependent
    # transients (created/refreshed by every interpreter run) and must not
    # affect the deterministic dependency fingerprint. Without this filter,
    # the seed value diverges between a clean checkout and any environment
    # that has imported the skill modules (e.g., a pytest run). See PR #376
    # cross-functional review P1/P2 findings.
    paths = {
        path
        for path in paths
        if "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    }
    for path in paths:
        write_utils.check_no_symlink_path(path)
    payload = [
        f"{repo_relative(repo_root, path)}\0{sha256_file(path)}"
        for path in sorted(paths)
    ]
    return _sha256_text("\n".join(payload))


def _source_fingerprint_for_page(
    path: Path,
    source_fingerprints: dict[str, str],
) -> str:
    frontmatter, _ = page_template_utils.extract_frontmatter(path.read_text(encoding="utf-8"))
    sources = page_template_utils.extract_sources_from_frontmatter(frontmatter or "")
    payload = {
        "sources": sorted(sources),
        "matched_source_fingerprints": {
            source: source_fingerprints[source]
            for source in sorted(sources)
            if source in source_fingerprints
        },
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))


def _candidate_item(path: Path, repo_root: Path, dependency_fingerprint: str, source_fingerprints: dict[str, str]) -> dict[str, Any]:
    write_utils.check_no_symlink_path(path)
    artifact_type = _artifact_type_for_path(path, repo_root)
    if artifact_type is None:
        raise ValueError("unsupported wiki artifact path")
    relative = repo_relative(repo_root, path)
    key = _item_key_for_page(path, repo_root, artifact_type)
    _, violations = page_template_utils.validate_page_template_path(
        relative,
        repo_root=repo_root,
        required_frontmatter_keys=page_template_utils.REQUIRED_FRONTMATTER_KEYS,
    )
    if violations:
        messages = "; ".join(f"{code}: {msg}" for code, msg in violations)
        raise ValueError(f"page template validation failed: {messages}")
    return {
        "item_key": key,
        "output_path": relative,
        "path_aliases": [],
        "artifact_type": artifact_type,
        "source_fingerprint": _source_fingerprint_for_page(path, source_fingerprints),
        "dependency_fingerprint": dependency_fingerprint,
        "status": "completed",
        "last_attempted_at": None,
        "last_succeeded_at": _bootstrap_success_timestamp(path),
        "last_error": None,
        "last_successful_batch_id": None,
    }


def _bootstrap_success_timestamp(path: Path) -> str:
    metadata = page_template_utils.parse_page_frontmatter(path.read_text(encoding="utf-8"))
    timestamp = page_template_utils.strip_quotes(metadata.get("updated_at", ""))
    try:
        _parse_timestamp(timestamp)
    except (TypeError, ValueError):
        return "1970-01-01T00:00:00Z"
    return timestamp


def _empty_registry(source_fingerprints: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "source_fingerprints": dict(sorted(source_fingerprints.items())),
        "batches": [],
        "items": sorted(items, key=lambda item: item["item_key"]),
    }


def _build_bootstrap_registry(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_fingerprints = _scan_source_fingerprints(repo_root)
    dependency_fingerprint = _compute_dependency_fingerprint(repo_root)
    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    wiki_root = repo_root / "wiki"
    for namespace in ("entities", "concepts", "analyses"):
        for path in sorted((wiki_root / namespace).glob("*.md")):
            try:
                candidates.append(
                    _candidate_item(path, repo_root, dependency_fingerprint, source_fingerprints)
                )
            except (OSError, ValueError) as exc:
                excluded.append(
                    {
                        "path": repo_relative(repo_root, path),
                        "status": "excluded",
                        "reason_code": "classification_failed",
                        "message": str(exc),
                    }
                )

    collisions: set[str] = set()
    for key, values in _group_by(candidates, "item_key").items():
        if len(values) > 1:
            collisions.update(item["item_key"] for item in values)
    for output_path, values in _group_by(candidates, "output_path").items():
        if len(values) > 1:
            collisions.update(item["item_key"] for item in values)
            excluded.append(
                {
                    "path": output_path,
                    "status": "excluded",
                    "reason_code": "collision_detected",
                    "message": "duplicate output_path",
                }
            )
    items = [item for item in candidates if item["item_key"] not in collisions]
    for item in candidates:
        if item["item_key"] in collisions:
            excluded.append(
                {
                    "path": item["output_path"],
                    "status": "excluded",
                    "reason_code": "collision_detected",
                    "message": f"duplicate item_key: {item['item_key']}",
                }
            )
    return _empty_registry(source_fingerprints, items), _dedupe_exclusions(excluded)


def _dedupe_exclusions(excluded: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in excluded:
        key = (
            str(item.get("path", "")),
            str(item.get("reason_code", "")),
            str(item.get("message", "")),
        )
        deduped.setdefault(key, item)
    return sorted(deduped.values(), key=lambda item: (item["reason_code"], item["path"]))


def _group_by(items: Sequence[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item[field])].append(item)
    return grouped


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_registry(path: Path) -> dict[str, Any]:
    raw = _load_json_file(path)
    if not isinstance(raw, dict):
        raise ValueError("registry JSON must be an object")
    return raw


def _validate_registry(data: dict[str, Any], repo_root: Path) -> list[str]:
    errors: list[str] = []
    if data.get("version") != SCHEMA_VERSION:
        errors.append("version must be exactly '1'")
    source_fingerprints = data.get("source_fingerprints")
    if not isinstance(source_fingerprints, dict):
        errors.append("source_fingerprints must be an object")
    else:
        for key, value in source_fingerprints.items():
            try:
                path_utils.normalize_repo_relative_path(str(key))
            except path_utils.RepoRelativePathError as exc:
                errors.append(f"source_fingerprints key invalid: {key}: {exc}")
            if not _is_hex64(value):
                errors.append(f"source_fingerprints value for {key} must be 64-hex")
    errors.extend(_validate_batches(data.get("batches")))
    errors.extend(_validate_items(data.get("items"), repo_root))
    return errors


def _validate_batches(raw_batches: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw_batches, list):
        return ["batches must be an array"]
    seen: set[str] = set()
    required_fields = {
        "batch_id",
        "trigger",
        "triggered_by",
        "started_at",
        "finished_at",
        "status",
        "input_fingerprint",
        "error_summary",
    }
    for index, batch in enumerate(raw_batches):
        if not isinstance(batch, dict):
            errors.append(f"batches[{index}] must be an object")
            continue
        missing = required_fields.difference(batch)
        for field in sorted(missing):
            errors.append(f"batches[{index}].{field} is required")
        batch_id = batch.get("batch_id")
        if not _is_single_line_text(batch_id):
            errors.append(f"batches[{index}].batch_id must be a non-empty string")
        elif batch_id in seen:
            errors.append(f"duplicate batch_id: {batch_id}")
        else:
            seen.add(batch_id)
        if batch.get("trigger") not in TRIGGER_VALUES:
            errors.append(f"batches[{index}].trigger is unsupported")
        if not _is_single_line_text(batch.get("triggered_by")):
            errors.append(f"batches[{index}].triggered_by must be a non-empty string")
        if batch.get("status") not in BATCH_STATUSES:
            errors.append(f"batches[{index}].status is unsupported")
        if not _is_hex64(batch.get("input_fingerprint")):
            errors.append(f"batches[{index}].input_fingerprint must be 64-hex")
        for field in ("started_at", "finished_at"):
            try:
                _parse_timestamp(batch.get(field))
            except (TypeError, ValueError):
                errors.append(f"batches[{index}].{field} must be ISO 8601 or null")
        error_summary = batch.get("error_summary")
        if error_summary is not None and not _is_single_line_text(error_summary, allow_empty=False):
            errors.append(f"batches[{index}].error_summary must be a single-line string or null")
        if batch.get("status") in {"failed", "partial"} and not error_summary:
            errors.append(f"batches[{index}].error_summary is required for failed/partial")
        if batch.get("status") in {"running", "completed"} and error_summary is not None:
            errors.append(f"batches[{index}].error_summary must be null for running/completed")
        if batch.get("status") == "running" and batch.get("finished_at") is not None:
            errors.append(f"batches[{index}].finished_at must be null while running")
        if batch.get("status") in TERMINAL_BATCH_STATUSES and batch.get("finished_at") is None:
            errors.append(f"batches[{index}].finished_at is required for terminal batches")
    return errors


def _validate_items(raw_items: Any, repo_root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw_items, list):
        return ["items must be an array"]
    seen_keys: set[str] = set()
    seen_outputs: dict[str, int] = {}
    alias_owners: dict[str, int] = {}
    required_fields = {
        "item_key",
        "output_path",
        "path_aliases",
        "artifact_type",
        "source_fingerprint",
        "dependency_fingerprint",
        "status",
        "last_attempted_at",
        "last_succeeded_at",
        "last_error",
        "last_successful_batch_id",
    }
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object")
            continue
        missing = required_fields.difference(item)
        for field in sorted(missing):
            errors.append(f"items[{index}].{field} is required")
        key = item.get("item_key")
        artifact_type = item.get("artifact_type")
        if artifact_type not in ARTIFACT_TYPE_VALUES:
            errors.append(f"items[{index}].artifact_type is unsupported")
        else:
            try:
                _validate_item_key_for_artifact(key, artifact_type)
            except ValueError as exc:
                errors.append(f"items[{index}].item_key invalid: {exc}")
            if key in seen_keys:
                errors.append(f"duplicate item_key: {key}")
            elif isinstance(key, str):
                seen_keys.add(key)
            try:
                output = _validate_output_path(repo_root, str(item.get("output_path", "")), artifact_type)
                if output in seen_outputs:
                    errors.append(f"duplicate output_path: {output}")
                seen_outputs[output] = index
            except (OSError, ValueError) as exc:
                errors.append(f"items[{index}].output_path invalid: {exc}")
        path_aliases = item.get("path_aliases")
        if not isinstance(path_aliases, list) or not all(isinstance(path, str) for path in path_aliases):
            errors.append(f"items[{index}].path_aliases must be an array of strings")
        elif artifact_type in ARTIFACT_TYPE_VALUES:
            for alias in path_aliases:
                try:
                    normalized_alias = _validate_output_path(repo_root, alias, str(artifact_type))
                except (OSError, ValueError) as exc:
                    errors.append(f"items[{index}].path_aliases entry invalid: {exc}")
                    continue
                if normalized_alias in alias_owners:
                    errors.append(f"contradictory path_aliases entry: {normalized_alias}")
                alias_owners[normalized_alias] = index
        for field in ("source_fingerprint", "dependency_fingerprint"):
            if not _is_hex64(item.get(field)):
                errors.append(f"items[{index}].{field} must be 64-hex")
        if item.get("status") not in ITEM_STATUSES:
            errors.append(f"items[{index}].status is unsupported")
        for field in ("last_attempted_at", "last_succeeded_at"):
            try:
                _parse_timestamp(item.get(field))
            except (TypeError, ValueError):
                errors.append(f"items[{index}].{field} must be ISO 8601 or null")
        if item.get("last_error") is not None and not _is_single_line_text(item.get("last_error")):
            errors.append(f"items[{index}].last_error must be a single-line string or null")
        if item.get("last_successful_batch_id") is not None and not _is_single_line_text(item.get("last_successful_batch_id")):
            errors.append(f"items[{index}].last_successful_batch_id must be a single-line string or null")
    for alias, owner_index in alias_owners.items():
        if alias in seen_outputs:
            errors.append(
                f"contradictory path_aliases entry: {alias} collides with items[{seen_outputs[alias]}].output_path"
            )
    return errors


def bootstrap_registry(
    *,
    repo_root: str | Path = ".",
    registry_path: str = REGISTRY_PATH,
    apply: bool = False,
    dry_run: bool = False,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    """Classify existing wiki artifacts and optionally seed the registry.

    The default path is a read-only reconciliation report. The ``dry_run`` flag
    exists for CLI compatibility and only records a warning because bootstrap is
    already dry-run unless ``apply=True``. Approved apply mode requires
    ``--approval approved``, acquires ``CHECKPOINT_REGISTRY_LOCK_PATH``, and
    writes only the initial registry JSON. Primary failures include
    ``approval_required``, ``invalid_input``, ``schema_validation_failed``,
    ``registry_exists``, and ``lock_unavailable``.
    """
    mode = "bootstrap"
    root = Path(repo_root).resolve()
    if not looks_like_repo_root(root):
        return _result(mode=mode, status=STATUS_FAIL, reason_code="prereq_missing:repo_root", message="repository root must contain AGENTS.md")
    try:
        target = _resolve_registry_path(root, registry_path)
        registry, excluded = _build_bootstrap_registry(root)
    except (OSError, ValueError) as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=REASON_CODE_INVALID_INPUT, message=str(exc))
    errors = _validate_registry(registry, root)
    if errors:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="schema_validation_failed", message="bootstrap registry failed schema validation", items=_error_items(errors))
    content = _canonical_json(registry)
    summary = _bootstrap_summary(registry, excluded, target, would_write=apply)
    if dry_run and not apply:
        summary["warnings"] = [DRY_RUN_REDUNDANT_WARNING]
    if not apply:
        return _result(mode=mode, status=STATUS_PASS, reason_code="ok", message="bootstrap dry-run completed", items=(*registry["items"], *excluded), summary=summary)
    if approval != APPROVAL_APPROVED:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=REASON_CODE_APPROVAL_REQUIRED, message="bootstrap apply requires --approval approved", approval=approval, lock_required=True, summary=summary)
    try:
        with write_utils.exclusive_write_lock(root, lock_path=contracts.CHECKPOINT_REGISTRY_LOCK_PATH):
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if existing == content:
                    summary["changed"] = False
                    return _result(mode=mode, status=STATUS_PASS, reason_code="ok", message="bootstrap registry already up to date", approval=approval, lock_required=True, items=(*registry["items"], *excluded), summary=summary)
                return _result(mode=mode, status=STATUS_FAIL, reason_code="registry_exists", message="registry already exists with different content", approval=approval, lock_required=True, summary=summary)
            write_utils.atomic_replace_governed_artifact(root, REGISTRY_PATH, content)
    except write_utils.LockUnavailableError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="lock_unavailable", message=str(exc), approval=approval, lock_required=True, summary=summary)
    except OSError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="write_failed", message=str(exc), approval=approval, lock_required=True, summary=summary)
    summary["changed"] = True
    return _result(mode=mode, status=STATUS_PASS, reason_code="ok", message="bootstrap registry written", approval=approval, lock_required=True, items=(*registry["items"], *excluded), summary=summary)


def _bootstrap_summary(
    registry: dict[str, Any],
    excluded: Sequence[dict[str, Any]],
    target: Path,
    *,
    would_write: bool,
) -> dict[str, Any]:
    counts = Counter(item["artifact_type"] for item in registry["items"])
    return {
        "registry_path": REGISTRY_PATH,
        "absolute_registry_path": target.as_posix(),
        "would_write": would_write,
        "classified_count": len(registry["items"]),
        "excluded_count": len(excluded),
        "source_fingerprint_count": len(registry["source_fingerprints"]),
        "artifact_type_counts": dict(sorted(counts.items())),
    }


def _error_items(errors: Sequence[str]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "path": REGISTRY_PATH,
            "status": STATUS_FAIL,
            "reason_code": "schema_validation_failed",
            "message": error,
        }
        for error in errors
    )


def _load_mutation_input(repo_root: Path, input_path: str) -> dict[str, Any]:
    if input_path == "-":
        raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
        if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError(f"stdin mutation input exceeds {MAX_INPUT_BYTES} byte limit")
    else:
        normalized = path_utils.normalize_repo_relative_path(input_path)
        if not normalized.startswith("docs/staged/") or not normalized.endswith(".json"):
            raise ValueError("--input must be '-' or a repo-relative JSON file under docs/staged/**")
        resolved = path_utils.resolve_within_repo(repo_root, normalized)
        write_utils.check_no_symlink_path(repo_root / normalized)
        if not resolved.is_file() or not resolved.resolve().is_relative_to(repo_root):
            raise ValueError("--input must be a file inside the repository")
        if resolved.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError(f"mutation input exceeds {MAX_INPUT_BYTES} byte limit")
        raw = resolved.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("mutation input must be a JSON object")
    return data


def mutate_registry(
    *,
    repo_root: str | Path = ".",
    registry_path: str = REGISTRY_PATH,
    input_path: str,
    approval: str = APPROVAL_NONE,
    now: str | None = None,
    trigger: str | None = None,
) -> SurfaceResult:
    """Apply one approved batch of checkpoint item transitions.

    Requires ``--approval approved`` and ``--input`` from ``docs/staged/**`` or
    stdin. Inputs are capped by ``MAX_INPUT_BYTES`` before JSON parsing. Holds
    ``CHECKPOINT_REGISTRY_LOCK_PATH`` while loading, validating, mutating, and
    atomically replacing the registry. Primary failures include
    ``approval_required``, ``invalid_input``, ``json_parse_failed``,
    ``schema_validation_failed``, ``lock_unavailable``, ``illegal_transition``,
    ``fingerprint_mismatch``, and ``stale_timeout``.
    """
    mode = "mutate"
    root = Path(repo_root).resolve()
    if approval != APPROVAL_APPROVED:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=REASON_CODE_APPROVAL_REQUIRED, message="mutate requires --approval approved", approval=approval, lock_required=True)
    try:
        target = _resolve_registry_path(root, registry_path)
        payload = _load_mutation_input(root, input_path)
        if trigger is not None:
            if not isinstance(payload.get("batch"), dict):
                raise ValueError("--trigger requires mutation input with a batch object")
            payload["batch"]["trigger"] = trigger
        now_iso = now or payload.get("now") or _now_iso()
        now_dt = _parse_timestamp(now_iso)
        if now_dt is None:
            raise ValueError("now must be non-null")
    except json.JSONDecodeError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="json_parse_failed", message=str(exc), approval=approval, lock_required=True)
    except (OSError, ValueError) as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=REASON_CODE_INVALID_INPUT, message=str(exc), approval=approval, lock_required=True)
    try:
        with write_utils.exclusive_write_lock(root, lock_path=contracts.CHECKPOINT_REGISTRY_LOCK_PATH):
            registry = _load_registry(target)
            errors = _validate_registry(registry, root)
            if errors:
                return _result(mode=mode, status=STATUS_FAIL, reason_code="schema_validation_failed", message="registry failed schema validation", approval=approval, lock_required=True, items=_error_items(errors))
            mutated, transition_items = _apply_mutation(registry, payload, root, now_iso, now_dt)
            post_errors = _validate_registry(mutated, root)
            if post_errors:
                return _result(mode=mode, status=STATUS_FAIL, reason_code="schema_validation_failed", message="mutated registry failed schema validation", approval=approval, lock_required=True, items=_error_items(post_errors))
            write_utils.atomic_replace_governed_artifact(root, REGISTRY_PATH, _canonical_json(mutated))
    except write_utils.LockUnavailableError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="lock_unavailable", message=str(exc), approval=approval, lock_required=True)
    except OSError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="write_failed", message=str(exc), approval=approval, lock_required=True)
    except json.JSONDecodeError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code="json_parse_failed", message=str(exc), approval=approval, lock_required=True)
    except ValueError as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=getattr(exc, "reason_code", "invalid_transition"), message=str(exc), approval=approval, lock_required=True)
    summary = {
        "registry_path": REGISTRY_PATH,
        "batch_id": payload.get("batch", {}).get("batch_id"),
        "transition_count": len(transition_items),
    }
    return _result(mode=mode, status=STATUS_PASS, reason_code="ok", message="registry mutation applied", approval=approval, lock_required=True, items=transition_items, summary=summary)


class TransitionError(ValueError):
    """Mutation-specific validation error carrying a stable reason code."""

    reason_code: str

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _apply_mutation(
    registry: dict[str, Any],
    payload: dict[str, Any],
    repo_root: Path,
    now_iso: str,
    now_dt: datetime,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    mutated = deepcopy(registry)
    batch = _normalized_batch(payload.get("batch"), now_iso)
    batch = _upsert_batch(mutated, batch)
    trigger = batch["trigger"]
    operations = payload.get("items")
    if not isinstance(operations, list) or not operations:
        raise TransitionError("invalid_input", "mutation input requires a non-empty items array")
    seen_ops: set[str] = set()
    items_by_key = {item["item_key"]: item for item in mutated["items"]}
    transition_items: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise TransitionError("invalid_input", "each mutation item must be an object")
        key = _required_string(operation, "item_key")
        if key in seen_ops:
            raise TransitionError("invalid_input", f"duplicate mutation item_key: {key}")
        seen_ops.add(key)
        target_status = _required_string(operation, "target_status")
        if target_status not in ITEM_STATUSES:
            raise TransitionError("illegal_transition", f"unsupported target_status: {target_status}")
        item = items_by_key.get(key)
        if item is None:
            item = _new_pending_item(operation, repo_root)
            mutated["items"].append(item)
            items_by_key[key] = item
        before_status = item["status"]
        operation_with_batch = {**operation, "batch_id": batch["batch_id"]}
        _transition_item(item, operation_with_batch, trigger, repo_root, now_iso, now_dt)
        transition_items.append(
            {
                "path": item["output_path"],
                "item_key": key,
                "status": item["status"],
                "reason_code": "ok",
                "message": f"{before_status} -> {item['status']}",
            }
        )
    _enforce_batch_item_outcomes(batch, transition_items, mutated["items"])
    mutated["items"].sort(key=lambda item: item["item_key"])
    return mutated, tuple(transition_items)


def _enforce_batch_item_outcomes(
    batch: dict[str, Any],
    transition_items: Sequence[dict[str, Any]],
    all_items: Sequence[dict[str, Any]],
) -> None:
    statuses = [str(item["status"]) for item in transition_items]
    if batch["status"] == "running":
        return
    successful = {"completed", "skipped"}
    if batch["status"] == "completed":
        if any(status not in successful for status in statuses):
            raise TransitionError(
                "illegal_transition",
                "completed batch requires every planned item to be completed or skipped",
            )
        if any(item.get("status") == "in_progress" for item in all_items):
            raise TransitionError(
                "illegal_transition",
                "completed batch cannot leave any claimed registry item in_progress",
            )
        return
    if batch["status"] == "partial":
        if not any(status in successful for status in statuses) or not any(
            status not in successful for status in statuses
        ):
            raise TransitionError(
                "illegal_transition",
                "partial batch requires at least one successful item and at least one unfinished or failed item",
            )
        return
    if batch["status"] == "failed" and not any(status not in successful for status in statuses):
        raise TransitionError(
            "illegal_transition",
            "failed batch requires a failed or unfinished planned item",
        )


def _normalized_batch(raw_batch: Any, now_iso: str) -> dict[str, Any]:
    if not isinstance(raw_batch, dict):
        raise TransitionError("invalid_input", "mutation input requires a batch object")
    trigger = _required_string(raw_batch, "trigger")
    if trigger not in {trigger_type.value for trigger_type in contracts.TriggerType}:
        raise TransitionError("invalid_input", f"unsupported trigger: {trigger}")
    status = raw_batch.get("status", "running")
    if status not in BATCH_STATUSES:
        raise TransitionError("invalid_input", f"unsupported batch status: {status}")
    error_summary = raw_batch.get("error_summary")
    if error_summary is not None and not _is_single_line_text(error_summary):
        raise TransitionError("invalid_input", "error_summary must be a single-line string or null")
    if status in {"failed", "partial"} and not error_summary:
        raise TransitionError("invalid_input", "failed/partial batch requires error_summary")
    if status in {"running", "completed"} and error_summary is not None:
        raise TransitionError("invalid_input", "running/completed batch requires null error_summary")
    finished_at = raw_batch.get(
        "finished_at",
        now_iso if status in TERMINAL_BATCH_STATUSES else None,
    )
    if status == "running" and finished_at is not None:
        raise TransitionError("invalid_input", "running batch requires null finished_at")
    if status in TERMINAL_BATCH_STATUSES and finished_at is None:
        raise TransitionError("invalid_input", "terminal batch requires finished_at")
    batch = {
        "batch_id": _required_string(raw_batch, "batch_id"),
        "trigger": trigger,
        "triggered_by": _single_line_or_default(raw_batch.get("triggered_by"), "unknown"),
        "started_at": str(raw_batch.get("started_at") or now_iso),
        "finished_at": finished_at,
        "status": status,
        "input_fingerprint": _required_hash(raw_batch, "input_fingerprint"),
        "error_summary": error_summary,
    }
    _parse_timestamp(batch["started_at"])
    _parse_timestamp(batch["finished_at"])
    return batch


def _upsert_batch(registry: dict[str, Any], batch: dict[str, Any]) -> dict[str, Any]:
    for existing in registry["batches"]:
        if existing["batch_id"] != batch["batch_id"]:
            continue
        if existing["status"] in TERMINAL_BATCH_STATUSES:
            raise TransitionError("illegal_transition", f"terminal batch cannot be rewritten: {batch['batch_id']}")
        for field in ("trigger", "triggered_by", "started_at", "input_fingerprint"):
            if existing.get(field) != batch.get(field):
                raise TransitionError("invalid_input", f"running batch metadata mismatch: {field}")
        if batch["status"] == "running":
            return existing
        existing.update(batch)
        return existing
    registry["batches"].append(batch)
    return batch


def _required_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not _is_single_line_text(value):
        raise TransitionError("invalid_input", f"{field} must be a non-empty string")
    return value


def _single_line_or_default(value: Any, default: str) -> str:
    if value is None or value == "":
        return default
    if not _is_single_line_text(value):
        raise TransitionError("invalid_input", "string fields must be single-line strings")
    return str(value)


def _required_hash(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not _is_hex64(value):
        raise TransitionError("invalid_input", f"{field} must be a 64-hex string")
    return str(value)


def _new_pending_item(operation: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    artifact_type = _required_string(operation, "artifact_type")
    try:
        output_path = _validate_output_path(repo_root, _required_string(operation, "output_path"), artifact_type)
    except (OSError, ValueError) as exc:
        raise TransitionError("invalid_input", str(exc)) from exc
    try:
        item_key = _validate_item_key_for_artifact(_required_string(operation, "item_key"), artifact_type)
    except (OSError, ValueError) as exc:
        raise TransitionError("invalid_input", str(exc)) from exc
    raw_aliases = operation.get("path_aliases") or []
    if not isinstance(raw_aliases, list) or not all(isinstance(path, str) for path in raw_aliases):
        raise TransitionError("invalid_input", "path_aliases must be an array of strings")
    try:
        path_aliases = [_validate_output_path(repo_root, alias, artifact_type) for alias in raw_aliases]
    except (OSError, ValueError) as exc:
        raise TransitionError("invalid_input", str(exc)) from exc
    return {
        "item_key": item_key,
        "output_path": output_path,
        "path_aliases": path_aliases,
        "artifact_type": artifact_type,
        "source_fingerprint": _required_hash(operation, "source_fingerprint"),
        "dependency_fingerprint": _required_hash(operation, "dependency_fingerprint"),
        "status": "pending",
        "last_attempted_at": None,
        "last_succeeded_at": None,
        "last_error": None,
        "last_successful_batch_id": None,
    }


def _transition_item(
    item: dict[str, Any],
    operation: dict[str, Any],
    trigger: str,
    repo_root: Path,
    now_iso: str,
    now_dt: datetime,
) -> None:
    current_status = item["status"]
    target_status = operation["target_status"]
    _enforce_stale_timeout(item, target_status, now_dt)
    _enforce_transition_matrix(item, operation, trigger)
    _apply_path_continuity(item, operation, repo_root)
    if target_status == "completed":
        _validate_completion(item, operation, repo_root)
    item["status"] = target_status
    if target_status in {"in_progress", "failed", "stale", "completed", "skipped"}:
        item["last_attempted_at"] = now_iso
    if target_status == "completed":
        item["last_succeeded_at"] = now_iso
        item["last_successful_batch_id"] = operation.get("batch_id") or operation.get("last_successful_batch_id") or None
        item["last_error"] = None
    elif target_status == "failed":
        item["last_error"] = _required_string(operation, "last_error")
    elif target_status == "skipped":
        item["last_error"] = _single_line_or_default(
            operation.get("last_error"),
            "retired or out of scope",
        )
    elif target_status == "in_progress":
        item["last_error"] = (
            None
            if operation.get("last_error") is None
            else _required_string(operation, "last_error")
        )
    for field in ("source_fingerprint", "dependency_fingerprint"):
        if field in operation:
            item[field] = _required_hash(operation, field)


def _enforce_stale_timeout(item: dict[str, Any], target_status: str, now_dt: datetime) -> None:
    if item["status"] != "in_progress" or target_status == "stale":
        return
    attempted_at = _parse_timestamp(item.get("last_attempted_at"))
    if attempted_at is not None and now_dt - attempted_at >= STALE_TIMEOUT:
        raise TransitionError("stale_timeout", "in_progress item exceeded the 1-hour stale timeout; transition to stale before advancing")


def _enforce_transition_matrix(item: dict[str, Any], operation: dict[str, Any], trigger: str) -> None:
    current = item["status"]
    target = operation["target_status"]
    if current == target:
        return
    if (current, target) not in ALLOWED_TRANSITIONS:
        raise TransitionError("illegal_transition", f"illegal item transition: {current} -> {target}")
    if target == "skipped" and trigger != contracts.TriggerType.MANUAL_RESCAN.value:
        raise TransitionError("illegal_transition", "only manual_rescan may retire items to skipped")
    if current == "skipped" and target == "pending" and trigger != contracts.TriggerType.MANUAL_RESCAN.value:
        raise TransitionError("illegal_transition", "only manual_rescan may move skipped -> pending")
    if current == "completed" and target == "stale":
        source_changed = operation.get("source_fingerprint") not in {None, item["source_fingerprint"]}
        dependency_changed = operation.get("dependency_fingerprint") not in {None, item["dependency_fingerprint"]}
        if trigger == contracts.TriggerType.INTAKE_DRIVEN.value and not source_changed:
            raise TransitionError("fingerprint_mismatch", "intake_driven completed -> stale requires source_fingerprint change")
        if trigger == contracts.TriggerType.INFRASTRUCTURE_REVALIDATION.value and (source_changed or not dependency_changed):
            raise TransitionError("fingerprint_mismatch", "infrastructure_revalidation completed -> stale requires dependency-only change")
        if trigger == contracts.TriggerType.MANUAL_RESCAN.value and not (source_changed or dependency_changed):
            raise TransitionError("fingerprint_mismatch", "manual_rescan completed -> stale requires a fingerprint change")


def _apply_path_continuity(item: dict[str, Any], operation: dict[str, Any], repo_root: Path) -> None:
    if "output_path" not in operation:
        return
    try:
        new_output = _validate_output_path(repo_root, _required_string(operation, "output_path"), item["artifact_type"])
    except (OSError, ValueError) as exc:
        raise TransitionError("invalid_input", str(exc)) from exc
    old_output = item["output_path"]
    if new_output == old_output:
        return
    if item["artifact_type"] == contracts.ArtifactType.WIKI_ANALYSIS_PAGE.value:
        raise TransitionError("illegal_transition", "analysis output_path changes alter identity and are not allowed")
    aliases = list(item.get("path_aliases") or [])
    if old_output not in aliases:
        aliases.append(old_output)
    item["output_path"] = new_output
    item["path_aliases"] = aliases


def _validate_completion(item: dict[str, Any], operation: dict[str, Any], repo_root: Path) -> None:
    output_path = repo_root / item["output_path"]
    if not output_path.is_file():
        raise TransitionError("output_missing", f"completed transition requires existing output: {item['output_path']}")
    relative = item["output_path"]
    _, violations = page_template_utils.validate_page_template_path(
        relative,
        repo_root=repo_root,
        required_frontmatter_keys=page_template_utils.REQUIRED_FRONTMATTER_KEYS,
    )
    if violations:
        raise TransitionError("schema_validation_failed", f"completed output failed page validation: {violations[0][0]}")
    for field in ("source_fingerprint", "dependency_fingerprint"):
        if field not in operation:
            raise TransitionError("fingerprint_mismatch", f"completed transition requires {field}")
        if operation[field] != item[field]:
            raise TransitionError("fingerprint_mismatch", f"{field} does not match the claimed in-progress item")


def _build_verify_summary(root: Path, target: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "registry_path": REGISTRY_PATH,
        "file_size_bytes": 0,
        "item_count": None,
        "json_parse_pass": False,
        "schema_check_pass": False,
        "warnings": [],
        "errors": [],
        "log_appended": False,
    }
    data: dict[str, Any] | None = None
    if not target.exists():
        summary["errors"].append("registry file is missing")
    else:
        try:
            summary["file_size_bytes"] = target.stat().st_size
            data = _load_registry(target)
            summary["json_parse_pass"] = True
        except json.JSONDecodeError as exc:
            summary["errors"].append(f"json_parse_failed: {exc.msg}")
        except OSError as exc:
            summary["errors"].append(f"registry_read_failed: {exc}")
        except ValueError as exc:
            summary["errors"].append(str(exc))
    if data is not None:
        summary["item_count"] = len(data.get("items", [])) if isinstance(data.get("items"), list) else None
        validation_errors = _validate_registry(data, root)
        summary["schema_check_pass"] = not validation_errors
        summary["errors"].extend(validation_errors)
        if (summary["item_count"] or 0) > ITEM_COUNT_WARN_THRESHOLD:
            summary["warnings"].append("item_count exceeds 5000")
    if summary["file_size_bytes"] > contracts.CHECKPOINT_REGISTRY_SIZE_WARN_BYTES:
        summary["warnings"].append("file_size_bytes exceeds CHECKPOINT_REGISTRY_SIZE_WARN_BYTES")
    if summary["file_size_bytes"] > contracts.CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES:
        summary["errors"].append("file_size_bytes exceeds CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES")
    return summary


def _emit_warning_log_entries(repo_root: Path, summary: dict[str, Any]) -> bool:
    return _append_verify_warning(repo_root, summary)


def verify_registry(
    *,
    repo_root: str | Path = ".",
    registry_path: str = REGISTRY_PATH,
    warn_only: bool = False,
    log_warnings: bool = False,
    approval: str = APPROVAL_NONE,
) -> SurfaceResult:
    """Validate registry parse, schema, size, and item-count telemetry.

    Default verify is read-only and acquires no checkpoint lock; ``warn_only``
    controls strict exit semantics. ``--log-warnings`` requires approval and
    appends only warning telemetry to ``wiki/log.md`` under ``wiki/.kb_write.lock``.
    Primary failures include ``invalid_input``, ``json_parse_failed``,
    ``schema_validation_failed``, ``approval_required``, ``lock_unavailable``,
    and ``write_failed``.
    """
    mode = "verify"
    root = Path(repo_root).resolve()
    try:
        target = _resolve_registry_path(root, registry_path)
    except (OSError, ValueError) as exc:
        return _result(mode=mode, status=STATUS_FAIL, reason_code=REASON_CODE_INVALID_INPUT, message=str(exc))
    summary = _build_verify_summary(root, target)
    if log_warnings and (summary["warnings"] or summary["errors"]):
        if approval != APPROVAL_APPROVED:
            return _result(
                mode=mode,
                status=STATUS_FAIL,
                reason_code=REASON_CODE_APPROVAL_REQUIRED,
                message="--log-warnings requires --approval approved",
                approval=approval,
                lock_required=True,
                lock_path=contracts.WRITE_LOCK_PATH,
                summary=summary,
            )
        try:
            summary["log_appended"] = _emit_warning_log_entries(root, summary)
        except write_utils.LockUnavailableError as exc:
            return _result(
                mode=mode,
                status=STATUS_FAIL,
                reason_code="lock_unavailable",
                message=str(exc),
                approval=approval,
                lock_required=True,
                lock_path=contracts.WRITE_LOCK_PATH,
                summary=summary,
            )
        except (OSError, ValueError) as exc:
            return _result(
                mode=mode,
                status=STATUS_FAIL,
                reason_code="write_failed",
                message=str(exc),
                approval=approval,
                lock_required=True,
                lock_path=contracts.WRITE_LOCK_PATH,
                summary=summary,
            )
    has_errors = bool(summary["errors"])
    if has_errors and not warn_only:
        reason = "json_parse_failed" if not summary["json_parse_pass"] and target.exists() else "schema_validation_failed"
        return _result(
            mode=mode,
            status=STATUS_FAIL,
            reason_code=reason,
            message="checkpoint registry verification failed",
            approval=approval,
            lock_required=bool(log_warnings and summary["log_appended"]),
            lock_path=contracts.WRITE_LOCK_PATH,
            summary=summary,
        )
    reason = "verify_warning" if summary["warnings"] or summary["errors"] else "ok"
    message = "checkpoint registry verification emitted warnings" if reason != "ok" else "checkpoint registry verification passed"
    return _result(
        mode=mode,
        status=STATUS_PASS,
        reason_code=reason,
        message=message,
        approval=approval,
        lock_required=bool(log_warnings and summary["log_appended"]),
        lock_path=contracts.WRITE_LOCK_PATH,
        summary=summary,
    )


def _append_verify_warning(repo_root: Path, summary: dict[str, Any]) -> bool:
    entry = (
        "- checkpoint_registry.verify_warning: "
        f"errors={len(summary['errors'])}; warnings={len(summary['warnings'])}; "
        f"file_size_bytes={summary['file_size_bytes']}; item_count={summary['item_count']}"
    )
    normalized = write_utils.validate_log_entry(entry)
    with write_utils.exclusive_write_lock(repo_root):
        return write_utils.append_log_only_state_changes(repo_root, normalized, state_changed=True)


def render_checkpoint_status(repo_root: str | Path = ".") -> str:
    """Render a compact checkpoint registry section for ``wiki/status.md``."""
    root = Path(repo_root).resolve()
    try:
        target = _resolve_registry_path(root, REGISTRY_PATH)
        if not target.exists():
            return "## Checkpoint Registry\n\n- Registry: not initialized\n"
        data = _load_registry(target)
        errors = _validate_registry(data, root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return f"## Checkpoint Registry\n\n- Registry: invalid ({exc})\n"
    if errors:
        return f"## Checkpoint Registry\n\n- Registry: schema invalid ({len(errors)} errors)\n"
    batches = data.get("batches", [])
    latest = batches[-1] if batches else None
    counts = Counter(item["status"] for item in data.get("items", []))
    lines = ["## Checkpoint Registry", ""]
    if latest:
        lines.extend(
            [
                f"- Latest batch: `{_markdown_safe(latest['batch_id'])}`",
                f"- Trigger: `{_markdown_safe(latest['trigger'])}`",
                f"- Batch status: `{_markdown_safe(latest['status'])}`",
                f"- Error summary: `{_markdown_safe(latest['error_summary'] or 'none')}`",
            ]
        )
    else:
        lines.append("- Latest batch: none")
    lines.append(
        "- Item statuses: "
        + ", ".join(f"{status}={counts.get(status, 0)}" for status in sorted(ITEM_STATUSES))
    )
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Manage the wiki-processing checkpoint registry.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--bootstrap",
        action="store_true",
        help="Classify existing wiki artifacts and emit reconciliation report; with --apply --approval approved, seed the initial registry.",
    )
    mode.add_argument(
        "--mutate",
        action="store_true",
        help="Apply a per-batch state transition from --input JSON; requires --approval approved.",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Read-only schema validation of the registry; --warn-only returns exit 0 even on warnings.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root path (must satisfy looks_like_repo_root).")
    parser.add_argument("--registry", default=REGISTRY_PATH, choices=(REGISTRY_PATH,), help="Registry JSON path (fixed to raw/wiki-processing/wiki-processing-checkpoint-registry.json).")
    parser.add_argument("--apply", action="store_true", help="Write bootstrap output after approval.")
    parser.add_argument("--dry-run", action="store_true", help="Compatibility flag; bootstrap defaults to dry-run unless --apply is set.")
    parser.add_argument("--input", help="Repo-local mutation input JSON path, or '-' for stdin.")
    parser.add_argument("--trigger", choices=tuple(trigger.value for trigger in contracts.TriggerType), help="Override the mutation input batch trigger.")
    parser.add_argument("--approval", choices=(APPROVAL_NONE, APPROVAL_APPROVED), default=APPROVAL_NONE, help="Approval gate: 'approved' required for any write-capable mode.")
    parser.add_argument("--warn-only", action="store_true", help="Return exit 0 for verify warnings/failures.")
    parser.add_argument("--log-warnings", action="store_true", help="Append verify warning telemetry to wiki/log.md; requires --approval approved.")
    parser.add_argument("--now", help="Deterministic ISO timestamp for mutation tests.")
    parser.add_argument("--result-json", action="store_true", help="Compatibility flag; JSON is always emitted.")
    return parser


def run_checkpoint_registry(args: argparse.Namespace) -> SurfaceResult:
    """Dispatch parsed CLI arguments to bootstrap, mutate, or verify mode.

    Each mode enforces its own approval and lock contract: bootstrap/mutate write
    the registry under ``CHECKPOINT_REGISTRY_LOCK_PATH``; verify is read-only
    unless approved warning logging appends to ``wiki/log.md``. Dispatch-level
    failures include cross-mode argument misuse and ``--mutate`` without
    ``--input``; mode functions return their own failure reason codes.
    """
    invalid = _validate_cli_mode_arguments(args)
    if invalid is not None:
        return invalid
    if args.bootstrap:
        return bootstrap_registry(
            repo_root=args.repo_root,
            registry_path=args.registry,
            apply=bool(args.apply),
            dry_run=bool(args.dry_run),
            approval=args.approval,
        )
    if args.mutate:
        if not args.input:
            return _result(mode="mutate", status=STATUS_FAIL, reason_code=REASON_CODE_INVALID_INPUT, message="--mutate requires --input", approval=args.approval, lock_required=True)
        return mutate_registry(
            repo_root=args.repo_root,
            registry_path=args.registry,
            input_path=args.input,
            approval=args.approval,
            now=args.now,
            trigger=args.trigger,
        )
    return verify_registry(
        repo_root=args.repo_root,
        registry_path=args.registry,
        warn_only=bool(args.warn_only),
        log_warnings=bool(args.log_warnings),
        approval=args.approval,
    )


def _validate_cli_mode_arguments(args: argparse.Namespace) -> SurfaceResult | None:
    if args.bootstrap:
        mode = "bootstrap"
        invalid_message = _first_present_argument(
            args,
            {
                "input": "--input is only valid with --mutate",
                "trigger": "--trigger is only valid with --mutate",
                "warn_only": "--warn-only is only valid with --verify",
                "log_warnings": "--log-warnings is only valid with --verify",
                "now": "--now is only valid with --mutate",
            },
        )
        if invalid_message is None and args.apply and args.dry_run:
            invalid_message = "--dry-run cannot be combined with --apply"
    elif args.mutate:
        mode = "mutate"
        invalid_message = _first_present_argument(
            args,
            {
                "apply": "--apply is only valid with --bootstrap",
                "dry_run": "--dry-run is only valid with --bootstrap",
                "warn_only": "--warn-only is only valid with --verify",
                "log_warnings": "--log-warnings is only valid with --verify",
            },
        )
    else:
        mode = "verify"
        invalid_message = _first_present_argument(
            args,
            {
                "apply": "--apply is only valid with --bootstrap",
                "dry_run": "--dry-run is only valid with --bootstrap",
                "input": "--input is only valid with --mutate",
                "trigger": "--trigger is only valid with --mutate",
                "now": "--now is only valid with --mutate",
            },
        )
    if invalid_message is None:
        return None
    return _result(
        mode=mode,
        status=STATUS_FAIL,
        reason_code=REASON_CODE_INVALID_INPUT,
        message=invalid_message,
        approval=args.approval,
    )


def _first_present_argument(args: argparse.Namespace, messages_by_attr: dict[str, str]) -> str | None:
    for attr, message in messages_by_attr.items():
        if bool(getattr(args, attr)):
            return message
    return None


def main(argv: Sequence[str] | None = None, *, output_stream: TextIO = sys.stdout) -> int:
    """Parse CLI arguments, emit one ``SurfaceResult`` JSON line, and return an exit code."""

    try:
        args = _build_parser().parse_args(list(argv) if argv is not None else None)
    except ValueError as exc:
        result = _result(mode="unknown", status=STATUS_FAIL, reason_code=REASON_CODE_INVALID_INPUT, message=str(exc))
        output_stream.write(result.to_json() + "\n")
        return 1
    result = run_checkpoint_registry(args)
    output_stream.write(result.to_json() + "\n")
    return 0 if result.status == STATUS_PASS else 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
