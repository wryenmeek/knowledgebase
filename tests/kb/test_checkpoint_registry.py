"""Runtime tests for scripts/kb/checkpoint_registry.py."""

from __future__ import annotations

import io
import inspect
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
from contextlib import contextmanager
from typing import Any

import pytest

from scripts.kb import checkpoint_registry, contracts, write_utils


RUNTIME_ROOT = Path("tests/kb/.runtime/checkpoint_registry")
SYNC_LOGIC_PATH = Path(".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
NOW = "2026-06-13T04:00:00Z"
RECENT = "2026-06-13T03:30:00Z"
OLD = "2026-06-13T02:30:00Z"


@pytest.fixture()
def repo_root(request: pytest.FixtureRequest) -> Path:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.name)
    root = RUNTIME_ROOT / name
    if root.exists():
        shutil.rmtree(root)
    (root / "wiki" / "entities").mkdir(parents=True)
    (root / "wiki" / "concepts").mkdir(parents=True)
    (root / "wiki" / "analyses").mkdir(parents=True)
    (root / "wiki" / "sources").mkdir(parents=True)
    (root / "raw" / "wiki-processing").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    (root / "docs" / "staged").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n\n## Write-surface matrix\n", encoding="utf-8")
    (root / "schema" / "wiki-processing-checkpoint-registry-contract.md").write_text(
        "# contract\n",
        encoding="utf-8",
    )
    yield root
    if root.exists():
        shutil.rmtree(root)


def _write_page(
    root: Path,
    relative: str,
    *,
    page_type: str,
    title: str,
    sources: list[str] | None = None,
    extra_frontmatter: str = "",
) -> None:
    source_lines = "\n".join(f"  - {source}" for source in (sources or []))
    if not source_lines:
        source_block = "sources: []"
    else:
        source_block = f"sources:\n{source_lines}"
    text = f"""---
type: {page_type}
title: {title}
status: draft
{source_block}
open_questions: []
confidence: medium
sensitivity: internal
updated_at: 2026-06-13T00:00:00Z
tags: []
{extra_frontmatter}---
# {title}

## Summary

Summary.

## Evidence

Evidence.

## Open Questions

None.
"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _registry_path(root: Path) -> Path:
    return root / checkpoint_registry.REGISTRY_PATH


def _write_registry(root: Path, data: dict[str, Any]) -> None:
    _registry_path(root).parent.mkdir(parents=True, exist_ok=True)
    _registry_path(root).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_registry(root: Path) -> dict[str, Any]:
    return json.loads(_registry_path(root).read_text(encoding="utf-8"))


def _item(
    *,
    key: str = "wiki_entity_page:alpha",
    output_path: str = "wiki/entities/alpha.md",
    artifact_type: str = "wiki_entity_page",
    status: str = "pending",
    source_fingerprint: str = HASH_A,
    dependency_fingerprint: str = HASH_B,
    last_attempted_at: str | None = None,
    last_succeeded_at: str | None = None,
    last_error: str | None = None,
    last_successful_batch_id: str | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_key": key,
        "output_path": output_path,
        "path_aliases": aliases or [],
        "artifact_type": artifact_type,
        "source_fingerprint": source_fingerprint,
        "dependency_fingerprint": dependency_fingerprint,
        "status": status,
        "last_attempted_at": last_attempted_at,
        "last_succeeded_at": last_succeeded_at,
        "last_error": last_error,
        "last_successful_batch_id": last_successful_batch_id,
    }


def _batch(
    *,
    batch_id: str = "batch-1",
    trigger: str = "intake_driven",
    status: str = "running",
    error_summary: str | None = None,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "trigger": trigger,
        "triggered_by": "test",
        "started_at": NOW,
        "finished_at": None if status == "running" else NOW,
        "status": status,
        "input_fingerprint": HASH_C,
        "error_summary": error_summary,
    }


def _base_registry(*, items: list[dict[str, Any]], batches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "version": "1",
        "source_fingerprints": {"wiki/sources/source.md": HASH_A},
        "batches": batches or [],
        "items": items,
    }


def _write_mutation(root: Path, payload: dict[str, Any], name: str = "mutation.json") -> str:
    path = root / "docs" / "staged" / name
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path.relative_to(root).as_posix()


def _track_lock_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    original_lock = checkpoint_registry.write_utils.exclusive_write_lock
    calls: list[str] = []

    @contextmanager
    def tracking_lock(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs.get("lock_path", contracts.WRITE_LOCK_PATH))
        with original_lock(*args, **kwargs) as lock_path:
            yield lock_path

    monkeypatch.setattr(checkpoint_registry.write_utils, "exclusive_write_lock", tracking_lock)
    return calls


def _mutation_payload(
    *,
    trigger: str = "intake_driven",
    batch_id: str = "batch-1",
    status: str = "running",
    error_summary: str | None = None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "now": NOW,
        "batch": _batch(batch_id=batch_id, trigger=trigger, status=status, error_summary=error_summary),
        "items": items,
    }


def test_bootstrap_classifies_each_artifact_type_and_reports_shape(repo_root: Path) -> None:
    (repo_root / "wiki" / "sources" / "source.md").write_text("source\n", encoding="utf-8")
    _write_page(
        repo_root,
        "wiki/entities/alpha.md",
        page_type="entity",
        title="Alpha",
        sources=["wiki/sources/source.md"],
        extra_frontmatter="entity_id: entity-alpha\n",
    )
    _write_page(repo_root, "wiki/concepts/beta.md", page_type="concept", title="Beta")
    _write_page(
        repo_root,
        "wiki/analyses/query-1234567890abcdef.md",
        page_type="analysis",
        title="Query 1234567890abcdef",
    )

    result = checkpoint_registry.bootstrap_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["classified_count"] == 3
    assert result.summary["excluded_count"] == 0
    assert result.summary["artifact_type_counts"] == {
        "wiki_analysis_page": 1,
        "wiki_concept_page": 1,
        "wiki_entity_page": 1,
    }
    assert {item["artifact_type"] for item in result.items} == {
        "wiki_analysis_page",
        "wiki_concept_page",
        "wiki_entity_page",
    }
    assert all(item["status"] == "completed" for item in result.items)
    assert not _registry_path(repo_root).exists()


def test_main_bootstrap_and_mutate_argument_errors(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    bootstrap_stream = io.StringIO()
    mutate_stream = io.StringIO()
    parse_stream = io.StringIO()

    bootstrap_exit = checkpoint_registry.main(
        ["--bootstrap", "--repo-root", str(repo_root), "--result-json"],
        output_stream=bootstrap_stream,
    )
    mutate_exit = checkpoint_registry.main(
        ["--mutate", "--repo-root", str(repo_root), "--approval", "approved"],
        output_stream=mutate_stream,
    )
    parse_exit = checkpoint_registry.main([], output_stream=parse_stream)

    assert bootstrap_exit == 0
    assert json.loads(bootstrap_stream.getvalue())["mode"] == "bootstrap"
    assert mutate_exit == 1
    assert json.loads(mutate_stream.getvalue())["message"] == "--mutate requires --input"
    assert parse_exit == 1
    assert json.loads(parse_stream.getvalue())["mode"] == "unknown"


def test_bootstrap_apply_requires_approval_then_replays_idempotently(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")

    denied = checkpoint_registry.bootstrap_registry(repo_root=repo_root, apply=True)
    assert denied.status == "fail"
    assert denied.reason_code == "approval_required"
    assert not _registry_path(repo_root).exists()

    written = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )
    assert written.status == "pass"
    assert written.summary["changed"] is True
    first_text = _registry_path(repo_root).read_text(encoding="utf-8")
    assert first_text == json.dumps(json.loads(first_text), indent=2, sort_keys=True) + "\n"

    monkeypatch.setattr(checkpoint_registry, "_now_iso", lambda: "2030-01-01T00:00:00Z")
    replay = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )
    assert replay.status == "pass"
    assert replay.summary["changed"] is False
    assert _registry_path(repo_root).read_text(encoding="utf-8") == first_text


def test_bootstrap_apply_uses_checkpoint_lock_path(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    calls = _track_lock_calls(monkeypatch)

    result = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )

    assert result.status == "pass"
    assert calls == [contracts.CHECKPOINT_REGISTRY_LOCK_PATH]


def test_bootstrap_apply_fails_closed_on_lock_contention(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")

    def locked(*args: Any, **kwargs: Any) -> Any:
        raise write_utils.LockUnavailableError(contracts.CHECKPOINT_REGISTRY_LOCK_PATH)

    monkeypatch.setattr(checkpoint_registry.write_utils, "exclusive_write_lock", locked)
    result = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )

    assert result.status == "fail"
    assert result.reason_code == "lock_unavailable"
    assert not _registry_path(repo_root).exists()


def test_bootstrap_apply_refuses_to_clobber_different_existing_registry(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    _write_registry(repo_root, _base_registry(items=[]))
    before = _registry_path(repo_root).read_text(encoding="utf-8")

    result = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )

    assert result.status == "fail"
    assert result.reason_code == "registry_exists"
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_bootstrap_detects_identity_collisions_without_writing(repo_root: Path) -> None:
    _write_page(
        repo_root,
        "wiki/entities/alpha.md",
        page_type="entity",
        title="Alpha",
        extra_frontmatter="entity_id: shared-id\n",
    )
    _write_page(
        repo_root,
        "wiki/entities/bravo.md",
        page_type="entity",
        title="Bravo",
        extra_frontmatter="entity_id: shared-id\n",
    )

    result = checkpoint_registry.bootstrap_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.summary["classified_count"] == 0
    assert result.summary["excluded_count"] == 2
    assert {item["reason_code"] for item in result.items} == {"collision_detected"}
    assert not _registry_path(repo_root).exists()


def test_bootstrap_excludes_unclassifiable_outputs(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/analyses/missing-fingerprint.md", page_type="analysis", title="Bad Analysis")
    (repo_root / "wiki" / "entities" / "broken.md").write_text("not frontmatter\n", encoding="utf-8")

    result = checkpoint_registry.bootstrap_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.summary["classified_count"] == 0
    assert result.summary["excluded_count"] == 2
    assert {item["reason_code"] for item in result.items} == {"classification_failed"}


def test_bootstrap_fails_for_non_repo_root_and_bad_registry_path(repo_root: Path) -> None:
    missing_agent = repo_root / "nested"
    missing_agent.mkdir()

    no_root = checkpoint_registry.bootstrap_registry(repo_root=missing_agent)
    bad_registry = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        registry_path="raw/wiki-processing/other.json",
    )

    assert no_root.status == "fail"
    assert no_root.reason_code == "prereq_missing:repo_root"
    assert bad_registry.status == "fail"
    assert bad_registry.reason_code == "invalid_input"


def test_registry_path_rejects_symlinked_parent(repo_root: Path) -> None:
    shutil.rmtree(repo_root / "raw" / "wiki-processing")
    try:
        os.symlink(repo_root / "wiki", repo_root / "raw" / "wiki-processing")
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = checkpoint_registry.bootstrap_registry(
        repo_root=repo_root,
        apply=True,
        approval="approved",
    )

    assert result.status == "fail"
    assert result.reason_code == "invalid_input"
    assert "symlinked path component" in result.message


def test_bootstrap_excludes_symlinked_candidate_before_reading(repo_root: Path) -> None:
    target = repo_root / "outside-entity.md"
    target.write_text("not a valid page\n", encoding="utf-8")
    link = repo_root / "wiki" / "entities" / "linked.md"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = checkpoint_registry.bootstrap_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.summary["classified_count"] == 0
    assert result.summary["excluded_count"] == 1
    assert "symlinked path component" in result.items[0]["message"]


def test_mutate_resumes_interrupted_running_batch_to_completion(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    _write_registry(
        repo_root,
        _base_registry(
            batches=[_batch(batch_id="batch-1", status="running")],
            items=[_item(status="in_progress", last_attempted_at=RECENT)],
        ),
    )
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            status="completed",
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "completed",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                }
            ],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    registry = _read_registry(repo_root)
    assert result.status == "pass"
    assert len(registry["batches"]) == 1
    assert registry["batches"][0]["status"] == "completed"
    assert registry["items"][0]["status"] == "completed"
    assert registry["items"][0]["last_error"] is None


def test_mutate_revalidates_stale_item_by_claiming_it(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="stale")]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "in_progress",
                }
            ],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "pass"
    assert _read_registry(repo_root)["items"][0]["status"] == "in_progress"


def test_mutate_requires_approval_and_can_add_new_pending_item(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {
                    "item_key": "wiki_concept_page:new",
                    "artifact_type": "wiki_concept_page",
                    "output_path": "wiki/concepts/new.md",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                    "target_status": "pending",
                }
            ],
        ),
    )

    denied = checkpoint_registry.mutate_registry(repo_root=repo_root, input_path=mutation)
    applied = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert denied.status == "fail"
    assert denied.reason_code == "approval_required"
    assert applied.status == "pass"
    assert _read_registry(repo_root)["items"][0]["item_key"] == "wiki_concept_page:new"


def test_mutate_cli_trigger_override_updates_batch_trigger(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="stale")]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            trigger="intake_driven",
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "in_progress",
                }
            ],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
        trigger="manual_rescan",
    )

    assert result.status == "pass"
    assert _read_registry(repo_root)["batches"][0]["trigger"] == "manual_rescan"


def test_mutate_fails_closed_on_lock_contention(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]),
    )

    def locked(*args: Any, **kwargs: Any) -> Any:
        raise write_utils.LockUnavailableError(contracts.CHECKPOINT_REGISTRY_LOCK_PATH)

    monkeypatch.setattr(checkpoint_registry.write_utils, "exclusive_write_lock", locked)
    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "lock_unavailable"
    assert _read_registry(repo_root)["items"][0]["status"] == "pending"


def test_mutate_uses_checkpoint_lock_path(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]),
    )
    calls = _track_lock_calls(monkeypatch)

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "pass"
    assert calls == [contracts.CHECKPOINT_REGISTRY_LOCK_PATH]


def test_mutate_preserves_identity_across_rename_with_path_alias(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha-renamed.md", page_type="entity", title="Alpha Renamed")
    _write_registry(repo_root, _base_registry(items=[_item(status="completed", last_succeeded_at=RECENT)]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "completed",
                    "output_path": "wiki/entities/alpha-renamed.md",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                }
            ],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    item = _read_registry(repo_root)["items"][0]
    assert result.status == "pass"
    assert item["item_key"] == "wiki_entity_page:alpha"
    assert item["output_path"] == "wiki/entities/alpha-renamed.md"
    assert item["path_aliases"] == ["wiki/entities/alpha.md"]


def test_mutate_enforces_one_hour_stale_timeout_and_rolls_back(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    original = _base_registry(items=[_item(status="in_progress", last_attempted_at=OLD)])
    _write_registry(repo_root, original)
    before = _registry_path(repo_root).read_text(encoding="utf-8")
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "completed"}]),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "stale_timeout"
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rolls_back_when_atomic_replace_fails(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    before = _registry_path(repo_root).read_text(encoding="utf-8")
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]),
    )

    def fail_replace(*args: Any, **kwargs: Any) -> Any:
        raise OSError("simulated write failure")

    monkeypatch.setattr(checkpoint_registry.write_utils, "atomic_replace_governed_artifact", fail_replace)
    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "write_failed"
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rolls_back_entire_batch_when_later_item_fails(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            items=[
                _item(status="pending"),
                _item(
                    key="wiki_concept_page:beta",
                    output_path="wiki/concepts/beta.md",
                    artifact_type="wiki_concept_page",
                    status="in_progress",
                    last_attempted_at=RECENT,
                ),
            ]
        ),
    )
    before = _registry_path(repo_root).read_text(encoding="utf-8")
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"},
                {
                    "item_key": "wiki_concept_page:beta",
                    "target_status": "completed",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                },
            ]
        ),
        "partial-failure.json",
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "output_missing"
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_records_failed_transition_and_missing_output_fail_closed(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="in_progress", last_attempted_at=RECENT)]))
    fail_mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "failed",
                    "last_error": "validator failed",
                }
            ],
        ),
        "fail.json",
    )
    failed = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=fail_mutation,
        approval="approved",
        now=NOW,
    )
    assert failed.status == "pass"
    assert _read_registry(repo_root)["items"][0]["last_error"] == "validator failed"

    _write_registry(repo_root, _base_registry(items=[_item(status="in_progress", last_attempted_at=RECENT)]))
    missing_output_mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "completed"}]),
        "missing-output.json",
    )
    missing = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=missing_output_mutation,
        approval="approved",
        now=NOW,
    )
    assert missing.status == "fail"
    assert missing.reason_code == "output_missing"


def test_mutate_completion_requires_valid_page_and_matching_fingerprints(repo_root: Path) -> None:
    (repo_root / "wiki" / "entities" / "alpha.md").write_text("not frontmatter\n", encoding="utf-8")
    _write_registry(repo_root, _base_registry(items=[_item(status="in_progress", last_attempted_at=RECENT)]))
    invalid_page_mutation = _write_mutation(
        repo_root,
        _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "completed"}]),
        "invalid-page.json",
    )
    invalid_page = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=invalid_page_mutation,
        approval="approved",
        now=NOW,
    )
    assert invalid_page.status == "fail"
    assert invalid_page.reason_code == "schema_validation_failed"

    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    mismatch_mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "completed",
                    "source_fingerprint": HASH_C,
                }
            ]
        ),
        "fingerprint-mismatch.json",
    )
    mismatch = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mismatch_mutation,
        approval="approved",
        now=NOW,
    )
    assert mismatch.status == "fail"
    assert mismatch.reason_code == "fingerprint_mismatch"


def test_mutate_rejects_invalid_batch_and_item_inputs(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")], batches=[_batch(status="completed")]))
    cases = [
        ({}, "mutation input requires a batch object"),
        ({"batch": _batch(batch_id="other"), "items": []}, "non-empty items array"),
        ({"batch": _batch(batch_id="other"), "items": [None]}, "each mutation item must be an object"),
        (
            {
                "batch": _batch(batch_id="other"),
                "items": [
                    {"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"},
                    {"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"},
                ],
            },
            "duplicate mutation item_key",
        ),
        (
            {
                "batch": _batch(batch_id="other"),
                "items": [{"item_key": "wiki_entity_page:alpha", "target_status": "bogus"}],
            },
            "unsupported target_status",
        ),
        (
            {"batch": _batch(batch_id="other", status="failed", error_summary=None), "items": [{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]},
            "failed/partial batch requires error_summary",
        ),
        (
            {"batch": _batch(batch_id="other", status="completed", error_summary="not allowed"), "items": [{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]},
            "running/completed batch requires null error_summary",
        ),
        (
            {"batch": _batch(batch_id="other", status="bogus"), "items": [{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]},
            "unsupported batch status",
        ),
        (
            {"batch": _batch(batch_id="batch-1"), "items": [{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}]},
            "terminal batch cannot be rewritten",
        ),
    ]
    for index, (payload, message) in enumerate(cases):
        mutation = _write_mutation(repo_root, payload, f"invalid-{index}.json")
        result = checkpoint_registry.mutate_registry(
            repo_root=repo_root,
            input_path=mutation,
            approval="approved",
            now=NOW,
        )
        assert result.status == "fail"
        assert message in result.message


def test_mutate_rejects_input_paths_outside_staged_json_boundary(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    payload = _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}])
    outside = repo_root / "mutation.json"
    outside.write_text(json.dumps(payload), encoding="utf-8")
    text_file = repo_root / "docs" / "staged" / "mutation.txt"
    text_file.write_text(json.dumps(payload), encoding="utf-8")

    for input_path in ("../outside.json", "mutation.json", "docs/staged/mutation.txt"):
        before = _registry_path(repo_root).read_text(encoding="utf-8")
        result = checkpoint_registry.mutate_registry(
            repo_root=repo_root,
            input_path=input_path,
            approval="approved",
            now=NOW,
        )
        assert result.status == "fail"
        assert result.reason_code == "invalid_input"
        assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rejects_symlinked_input_file(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    payload = _mutation_payload(items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}])
    target = repo_root / "docs" / "staged" / "real.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    link = repo_root / "docs" / "staged" / "linked.json"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    before = _registry_path(repo_root).read_text(encoding="utf-8")

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path="docs/staged/linked.json",
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "invalid_input"
    assert "symlinked path component" in result.message
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rejects_new_item_output_path_traversal_and_wrong_namespace(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[]))
    cases = [
        ("wiki/entities/../concepts/bad.md", "wiki_entity_page"),
        ("wiki/concepts/bad.md", "wiki_entity_page"),
        ("wiki/entities/nested/bad.md", "wiki_entity_page"),
    ]
    for index, (output_path, artifact_type) in enumerate(cases):
        before = _registry_path(repo_root).read_text(encoding="utf-8")
        mutation = _write_mutation(
            repo_root,
            _mutation_payload(
                items=[
                    {
                        "item_key": f"{artifact_type}:bad-{index}",
                        "artifact_type": artifact_type,
                        "output_path": output_path,
                        "source_fingerprint": HASH_A,
                        "dependency_fingerprint": HASH_B,
                        "target_status": "pending",
                    }
                ]
            ),
            f"bad-output-{index}.json",
        )

        result = checkpoint_registry.mutate_registry(
            repo_root=repo_root,
            input_path=mutation,
            approval="approved",
            now=NOW,
        )

        assert result.status == "fail"
        assert result.reason_code == "invalid_input"
        assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rejects_running_batch_metadata_mismatch(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            batches=[_batch(batch_id="batch-1", trigger="intake_driven", status="running")],
            items=[_item(status="pending")],
        ),
    )
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            trigger="manual_rescan",
            batch_id="batch-1",
            items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "invalid_input"
    assert "running batch metadata mismatch: trigger" in result.message


def test_mutate_enforces_terminal_batch_item_outcome_invariants(repo_root: Path) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            status="completed",
            items=[{"item_key": "wiki_entity_page:alpha", "target_status": "in_progress"}],
        ),
        "completed-with-in-progress.json",
    )
    before = _registry_path(repo_root).read_text(encoding="utf-8")

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "illegal_transition"
    assert "completed batch requires every planned item" in result.message
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_rejects_completed_batch_when_omitted_claimed_item_remains_in_progress(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    _write_registry(
        repo_root,
        _base_registry(
            items=[
                _item(status="in_progress", last_attempted_at=RECENT),
                _item(
                    key="wiki_concept_page:beta",
                    output_path="wiki/concepts/beta.md",
                    artifact_type="wiki_concept_page",
                    status="in_progress",
                    last_attempted_at=RECENT,
                ),
            ]
        ),
    )
    before = _registry_path(repo_root).read_text(encoding="utf-8")
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            status="completed",
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "completed",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                }
            ],
        ),
        "completed-omits-in-progress.json",
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "fail"
    assert result.reason_code == "illegal_transition"
    assert "cannot leave any claimed registry item in_progress" in result.message
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_mutate_allows_partial_batch_only_with_mixed_item_outcomes(repo_root: Path) -> None:
    _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    _write_registry(
        repo_root,
        _base_registry(
            items=[
                _item(status="in_progress", last_attempted_at=RECENT),
                _item(
                    key="wiki_concept_page:beta",
                    output_path="wiki/concepts/beta.md",
                    artifact_type="wiki_concept_page",
                    status="in_progress",
                    last_attempted_at=RECENT,
                ),
            ]
        ),
    )
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            status="partial",
            error_summary="one item failed",
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": "completed",
                    "source_fingerprint": HASH_A,
                    "dependency_fingerprint": HASH_B,
                },
                {
                    "item_key": "wiki_concept_page:beta",
                    "target_status": "failed",
                    "last_error": "validator failed",
                },
            ],
        ),
        "partial-mixed.json",
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == "pass"
    registry = _read_registry(repo_root)
    assert registry["batches"][0]["status"] == "partial"
    statuses = {item["item_key"]: item["status"] for item in registry["items"]}
    assert statuses == {
        "wiki_entity_page:alpha": "completed",
        "wiki_concept_page:beta": "failed",
    }


@pytest.mark.parametrize(
    ("trigger", "start_status", "target_status", "operation_extra", "expected_status", "expected_reason"),
    [
        ("intake_driven", "pending", "in_progress", {}, "pass", "ok"),
        ("infrastructure_revalidation", "pending", "in_progress", {}, "pass", "ok"),
        ("manual_rescan", "pending", "in_progress", {}, "pass", "ok"),
        ("intake_driven", "in_progress", "completed", {"source_fingerprint": HASH_A, "dependency_fingerprint": HASH_B}, "pass", "ok"),
        ("intake_driven", "in_progress", "stale", {}, "pass", "ok"),
        ("manual_rescan", "in_progress", "failed", {"last_error": "validator failed"}, "pass", "ok"),
        ("intake_driven", "stale", "in_progress", {}, "pass", "ok"),
        ("infrastructure_revalidation", "stale", "in_progress", {}, "pass", "ok"),
        ("manual_rescan", "stale", "in_progress", {}, "pass", "ok"),
        ("intake_driven", "failed", "in_progress", {}, "pass", "ok"),
        ("infrastructure_revalidation", "failed", "in_progress", {}, "pass", "ok"),
        ("manual_rescan", "failed", "in_progress", {}, "pass", "ok"),
        ("manual_rescan", "skipped", "pending", {}, "pass", "ok"),
        ("intake_driven", "skipped", "pending", {}, "fail", "illegal_transition"),
        ("infrastructure_revalidation", "skipped", "pending", {}, "fail", "illegal_transition"),
        ("intake_driven", "completed", "stale", {"source_fingerprint": HASH_C}, "pass", "ok"),
        ("intake_driven", "completed", "stale", {}, "fail", "fingerprint_mismatch"),
        ("infrastructure_revalidation", "completed", "stale", {"dependency_fingerprint": HASH_C}, "pass", "ok"),
        ("infrastructure_revalidation", "completed", "stale", {"source_fingerprint": HASH_C}, "fail", "fingerprint_mismatch"),
        ("manual_rescan", "completed", "stale", {"source_fingerprint": HASH_C}, "pass", "ok"),
        ("manual_rescan", "completed", "stale", {}, "fail", "fingerprint_mismatch"),
        ("intake_driven", "pending", "skipped", {}, "fail", "illegal_transition"),
        ("infrastructure_revalidation", "pending", "skipped", {}, "fail", "illegal_transition"),
        ("manual_rescan", "pending", "skipped", {"last_error": "operator retired"}, "pass", "ok"),
        ("intake_driven", "stale", "skipped", {"last_error": "operator retired"}, "fail", "illegal_transition"),
        ("manual_rescan", "stale", "skipped", {"last_error": "operator retired"}, "pass", "ok"),
        ("infrastructure_revalidation", "stale", "skipped", {"last_error": "operator retired"}, "fail", "illegal_transition"),
    ],
)
def test_mutate_enforces_trigger_transition_matrix(
    repo_root: Path,
    trigger: str,
    start_status: str,
    target_status: str,
    operation_extra: dict[str, Any],
    expected_status: str,
    expected_reason: str,
) -> None:
    if target_status == "completed":
        _write_page(repo_root, "wiki/entities/alpha.md", page_type="entity", title="Alpha")
    _write_registry(
        repo_root,
        _base_registry(
            items=[
                _item(
                    status=start_status,
                    last_attempted_at=RECENT if start_status in {"in_progress", "failed"} else None,
                    last_error="previous failure" if start_status == "failed" else None,
                    last_succeeded_at=RECENT if start_status == "completed" else None,
                )
            ]
        ),
    )
    mutation = _write_mutation(
        repo_root,
        _mutation_payload(
            trigger=trigger,
            items=[
                {
                    "item_key": "wiki_entity_page:alpha",
                    "target_status": target_status,
                    **operation_extra,
                }
            ],
        ),
    )

    result = checkpoint_registry.mutate_registry(
        repo_root=repo_root,
        input_path=mutation,
        approval="approved",
        now=NOW,
    )

    assert result.status == expected_status
    assert result.reason_code == expected_reason


def test_verify_reports_file_size_item_count_and_preserves_registry(repo_root: Path) -> None:
    registry = _base_registry(items=[_item(status="pending"), _item(key="wiki_concept_page:beta", output_path="wiki/concepts/beta.md", artifact_type="wiki_concept_page")])
    _write_registry(repo_root, registry)
    before = _registry_path(repo_root).read_text(encoding="utf-8")

    result = checkpoint_registry.verify_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.reason_code == "ok"
    assert result.summary["file_size_bytes"] == len(before.encode("utf-8"))
    assert result.summary["item_count"] == 2
    assert result.summary["json_parse_pass"] is True
    assert result.summary["schema_check_pass"] is True
    assert _registry_path(repo_root).read_text(encoding="utf-8") == before


def test_verify_detects_schema_failure_and_warn_only_exit_semantics(repo_root: Path) -> None:
    broken = _base_registry(items=[_item(status="not-a-state")])
    _write_registry(repo_root, broken)
    strict_stream = io.StringIO()
    warn_stream = io.StringIO()

    strict_exit = checkpoint_registry.main(
        ["--verify", "--repo-root", str(repo_root)],
        output_stream=strict_stream,
    )
    warn_exit = checkpoint_registry.main(
        ["--verify", "--warn-only", "--repo-root", str(repo_root)],
        output_stream=warn_stream,
    )

    strict = json.loads(strict_stream.getvalue())
    warn = json.loads(warn_stream.getvalue())
    assert strict_exit == 1
    assert strict["reason_code"] == "schema_validation_failed"
    assert warn_exit == 0
    assert warn["reason_code"] == "verify_warning"
    assert not (repo_root / "wiki" / "log.md").exists()


def test_verify_log_warnings_requires_approval_and_uses_lock(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _base_registry(items=[_item(status="not-a-state")])
    _write_registry(repo_root, broken)
    calls = _track_lock_calls(monkeypatch)

    denied = checkpoint_registry.verify_registry(
        repo_root=repo_root,
        warn_only=True,
        log_warnings=True,
    )
    approved = checkpoint_registry.verify_registry(
        repo_root=repo_root,
        warn_only=True,
        log_warnings=True,
        approval="approved",
    )

    assert denied.status == "fail"
    assert denied.reason_code == "approval_required"
    assert approved.status == "pass"
    assert approved.summary["log_appended"] is True
    assert approved.lock_path == contracts.WRITE_LOCK_PATH
    assert approved.lock_required is True
    assert calls == [contracts.WRITE_LOCK_PATH]
    assert not write_utils.is_write_lock_held(repo_root)
    assert "checkpoint_registry.verify_warning" in (repo_root / "wiki" / "log.md").read_text(encoding="utf-8")


def test_verify_log_warnings_logs_json_parse_failures(repo_root: Path) -> None:
    _registry_path(repo_root).write_text("{not json", encoding="utf-8")

    result = checkpoint_registry.verify_registry(
        repo_root=repo_root,
        warn_only=True,
        log_warnings=True,
        approval="approved",
    )

    assert result.status == "pass"
    assert result.reason_code == "verify_warning"
    assert result.summary["log_appended"] is True
    log_text = (repo_root / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "checkpoint_registry.verify_warning" in log_text


def test_verify_log_warnings_fails_closed_on_wiki_lock_contention(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _base_registry(items=[_item(status="not-a-state")])
    _write_registry(repo_root, broken)

    def locked(*args: Any, **kwargs: Any) -> Any:
        raise write_utils.LockUnavailableError(contracts.WRITE_LOCK_PATH)

    monkeypatch.setattr(checkpoint_registry.write_utils, "exclusive_write_lock", locked)
    result = checkpoint_registry.verify_registry(
        repo_root=repo_root,
        warn_only=True,
        log_warnings=True,
        approval="approved",
    )

    assert result.status == "fail"
    assert result.reason_code == "lock_unavailable"
    assert not (repo_root / "wiki" / "log.md").exists()


def test_verify_rejects_symlinked_registry_path(repo_root: Path) -> None:
    _registry_path(repo_root).unlink(missing_ok=True)
    target = repo_root / "redirect-registry.json"
    target.write_text(json.dumps(_base_registry(items=[])), encoding="utf-8")
    try:
        os.symlink(target, _registry_path(repo_root))
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)

    assert result.status == "fail"
    assert result.reason_code == "invalid_input"
    assert "symlinked path component" in result.message


def test_verify_reports_registry_read_oserror(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_registry(repo_root, _base_registry(items=[]))

    def unreadable(*args: Any, **kwargs: Any) -> Any:
        raise OSError("permission denied")

    monkeypatch.setattr(checkpoint_registry, "_load_registry", unreadable)
    result = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)

    assert result.status == "pass"
    assert result.reason_code == "verify_warning"
    assert "registry_read_failed" in "\n".join(result.summary["errors"])


def test_verify_reports_schema_errors_for_malformed_registry_fields(repo_root: Path) -> None:
    malformed = {
        "version": "2",
        "source_fingerprints": {"../bad": "not-a-hash"},
        "batches": [
            [],
            {
                "batch_id": "dup",
                "trigger": "bogus",
                "triggered_by": "",
                "started_at": "not-a-date",
                "finished_at": "not-a-date",
                "status": "bogus",
                "input_fingerprint": "bad",
                "error_summary": "not allowed",
            },
            {
                "batch_id": "dup",
                "trigger": "intake_driven",
                "triggered_by": "test",
                "started_at": NOW,
                "finished_at": NOW,
                "status": "failed",
                "input_fingerprint": HASH_A,
                "error_summary": None,
            },
        ],
        "items": [
            [],
            {
                **_item(status="pending"),
                "path_aliases": "not-list",
                "source_fingerprint": "bad",
                "last_attempted_at": "not-a-date",
                "last_error": 123,
                "last_successful_batch_id": 456,
            },
            _item(status="pending"),
            {
                **_item(
                    key="bad key",
                    output_path="wiki/concepts/wrong.md",
                    status="bogus",
                ),
                "artifact_type": "wiki_entity_page",
            },
            {
                **_item(
                    key="wiki_entity_page:alias",
                    output_path="wiki/entities/alias.md",
                    status="pending",
                    aliases=["wiki/entities/alpha.md"],
                )
            },
            {
                **_item(
                    key="wiki_unknown_page:item",
                    output_path="wiki/unknown/item.md",
                    artifact_type="wiki_unknown_page",
                )
            },
        ],
    }
    _write_registry(repo_root, malformed)

    result = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)

    errors = "\n".join(result.summary["errors"])
    assert result.status == "pass"
    assert "version must be exactly" in errors
    assert "source_fingerprints key invalid" in errors
    assert "batches[0] must be an object" in errors
    assert "duplicate batch_id" in errors
    assert "items[0] must be an object" in errors
    assert "duplicate item_key" in errors
    assert "item_key invalid" in errors
    assert "contradictory path_aliases" in errors
    assert "artifact_type is unsupported" in errors


def test_verify_detects_alias_collision_with_later_output_path(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            items=[
                _item(
                    key="wiki_entity_page:first",
                    output_path="wiki/entities/first.md",
                    aliases=["wiki/entities/second.md"],
                ),
                _item(
                    key="wiki_entity_page:second",
                    output_path="wiki/entities/second.md",
                ),
            ]
        ),
    )

    result = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)

    assert result.status == "pass"
    assert any("collides with items" in error for error in result.summary["errors"])


def test_verify_detects_json_parse_failure(repo_root: Path) -> None:
    _registry_path(repo_root).write_text("{not json", encoding="utf-8")

    result = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)

    assert result.status == "pass"
    assert result.reason_code == "verify_warning"
    assert result.summary["json_parse_pass"] is False
    assert result.summary["schema_check_pass"] is False
    assert any("json_parse_failed" in error for error in result.summary["errors"])


def test_verify_missing_registry_and_bad_registry_path(repo_root: Path) -> None:
    missing = checkpoint_registry.verify_registry(repo_root=repo_root, warn_only=True)
    bad_path = checkpoint_registry.verify_registry(
        repo_root=repo_root,
        registry_path="raw/wiki-processing/not-the-registry.json",
    )

    assert missing.status == "pass"
    assert missing.reason_code == "verify_warning"
    assert missing.summary["errors"] == ["registry file is missing"]
    assert bad_path.status == "fail"
    assert bad_path.reason_code == "invalid_input"


def test_verify_warns_on_retention_thresholds(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    monkeypatch.setattr(checkpoint_registry.contracts, "CHECKPOINT_REGISTRY_SIZE_WARN_BYTES", 1)
    monkeypatch.setattr(checkpoint_registry.contracts, "CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES", 10_000_000)

    result = checkpoint_registry.verify_registry(repo_root=repo_root)

    assert result.status == "pass"
    assert result.reason_code == "verify_warning"
    assert "file_size_bytes exceeds CHECKPOINT_REGISTRY_SIZE_WARN_BYTES" in result.summary["warnings"]


def test_verify_strict_fails_on_size_fail_threshold(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_registry(repo_root, _base_registry(items=[_item(status="pending")]))
    monkeypatch.setattr(checkpoint_registry.contracts, "CHECKPOINT_REGISTRY_SIZE_WARN_BYTES", 1)
    monkeypatch.setattr(checkpoint_registry.contracts, "CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES", 2)

    result = checkpoint_registry.verify_registry(repo_root=repo_root)

    assert result.status == "fail"
    assert "file_size_bytes exceeds CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES" in result.summary["errors"]


def test_render_checkpoint_status_includes_latest_batch_and_item_counts(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            batches=[_batch(batch_id="batch-7", trigger="manual_rescan", status="partial", error_summary="one failed")],
            items=[_item(status="completed", last_succeeded_at=NOW), _item(key="wiki_concept_page:beta", output_path="wiki/concepts/beta.md", artifact_type="wiki_concept_page", status="failed", last_error="boom")],
        ),
    )

    rendered = checkpoint_registry.render_checkpoint_status(repo_root)

    assert "## Checkpoint Registry" in rendered
    assert "batch-7" in rendered
    assert "manual_rescan" in rendered
    assert "completed=1" in rendered
    assert "failed=1" in rendered


def test_render_checkpoint_status_wraps_untrusted_error_summary_in_code_span(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            batches=[
                _batch(
                    batch_id="batch-9",
                    trigger="manual_rescan",
                    status="partial",
                    error_summary="![x](https://example.invalid/a)|`bad`",
                )
            ],
            items=[_item(status="failed", last_error="boom")],
        ),
    )

    rendered = checkpoint_registry.render_checkpoint_status(repo_root)

    assert "- Error summary: `" in rendered
    assert "\\|" in rendered
    assert "`bad`" not in rendered
    assert "![x](https://example.invalid/a)" in rendered


def test_render_checkpoint_status_rejects_symlinked_registry_path(repo_root: Path) -> None:
    _registry_path(repo_root).unlink(missing_ok=True)
    target = repo_root / "redirect-registry.json"
    target.write_text(json.dumps(_base_registry(items=[])), encoding="utf-8")
    try:
        os.symlink(target, _registry_path(repo_root))
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    rendered = checkpoint_registry.render_checkpoint_status(repo_root)

    assert "Registry: invalid" in rendered
    assert "symlinked path component" in rendered


def test_sync_skill_inline_checkpoint_status_render_uses_registry(repo_root: Path) -> None:
    _write_registry(
        repo_root,
        _base_registry(
            batches=[_batch(batch_id="batch-8", trigger="manual_rescan", status="completed")],
            items=[_item(status="completed", last_succeeded_at=NOW)],
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "sync_knowledgebase_state_checkpoint_test",
        SYNC_LOGIC_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.REPO_ROOT = repo_root

    rendered = module.render_checkpoint_status()
    updated = module._with_checkpoint_status(
        "# Status\n\n## Checkpoint Registry\n\n- old\n\n## Later Section\n\nkeep\n"
    )

    assert "batch-8" in rendered
    assert "manual_rescan" in rendered
    assert "completed=1" in rendered
    assert "\n\n## Later Section" in updated
    assert "## Later Section" in updated
    assert "keep" in updated
    assert "- old" not in updated
    source_lines, _ = inspect.getsourcelines(module.render_checkpoint_status)
    assert len(source_lines) < 50
