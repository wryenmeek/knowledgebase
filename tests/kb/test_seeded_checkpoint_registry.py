"""Validity tests for the seeded `wiki-processing-checkpoint-registry.json`.

PR4 (#376) seeded the initial registry by running
`python3 scripts/kb/checkpoint_registry.py --bootstrap --apply --approval approved`
on a clean tree. These tests pin the seeded fixture's structural invariants
so a manual hand-edit, accidental partial commit, or environment-polluted
re-bootstrap can be caught at PR time rather than via the post-merge job
summary surface.

Specifically:
- The seeded JSON must satisfy `_validate_registry` against the live REPO_ROOT.
- All declared `output_path` values must exist on disk.
- All `artifact_type` values must be in the contract enum.
- Top-level shape: version "1", non-empty items, empty batches (post-bootstrap),
  non-empty source_fingerprints map.
- Per-item shape: `status: completed`, source/dependency fingerprints are 64-hex,
  `last_succeeded_at` is set, `last_attempted_at`/`last_successful_batch_id` are
  null (the post-bootstrap-pre-first-batch invariant).
- The shared `dependency_fingerprint` value must equal what
  `_compute_dependency_fingerprint(REPO_ROOT)` produces, defending against the
  "polluted __pycache__" footgun observed during PR #376 cross-functional review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.kb import checkpoint_registry, contracts

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "raw" / "wiki-processing" / "wiki-processing-checkpoint-registry.json"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@pytest.fixture(scope="module")
def registry() -> dict:
    if not REGISTRY_PATH.exists():
        pytest.skip(
            "raw/wiki-processing/wiki-processing-checkpoint-registry.json "
            "not on disk — expected after PR #376 bootstrap."
        )
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_validate_registry_against_live_repo(registry: dict) -> None:
    errors = checkpoint_registry._validate_registry(registry, REPO_ROOT)
    assert errors == [], f"seeded registry failed schema validation: {errors}"


def test_top_level_shape(registry: dict) -> None:
    assert registry.get("version") == "1"
    assert isinstance(registry.get("batches"), list)
    assert registry["batches"] == [], (
        "post-bootstrap registry must have empty batches[] (no batch lineage yet)"
    )
    assert isinstance(registry.get("items"), list)
    assert len(registry["items"]) > 0, "seeded registry must classify at least one item"
    assert isinstance(registry.get("source_fingerprints"), dict)
    assert len(registry["source_fingerprints"]) > 0, (
        "seeded registry must include at least one source fingerprint entry"
    )


def test_all_items_completed_with_post_bootstrap_field_state(
    registry: dict, subtests
) -> None:
    for index, item in enumerate(registry["items"]):
        with subtests.test(index=index, item_key=item.get("item_key")):
            assert item.get("status") == "completed"
            assert item.get("last_succeeded_at") is not None
            assert item.get("last_attempted_at") is None, (
                "bootstrap items have no prior batch attempt — last_attempted_at must be null"
            )
            assert item.get("last_successful_batch_id") is None, (
                "bootstrap items have no batch lineage — last_successful_batch_id must be null"
            )
            assert item.get("last_error") is None
            assert item.get("path_aliases") == []


def test_all_artifact_types_in_contract_enum(registry: dict, subtests) -> None:
    allowed = {value.value for value in contracts.ArtifactType}
    for index, item in enumerate(registry["items"]):
        with subtests.test(index=index, item_key=item.get("item_key")):
            assert item.get("artifact_type") in allowed


def test_all_output_paths_exist_on_disk(registry: dict, subtests) -> None:
    for index, item in enumerate(registry["items"]):
        with subtests.test(index=index, item_key=item.get("item_key")):
            output_path = item.get("output_path", "")
            resolved = (REPO_ROOT / output_path).resolve()
            assert resolved.exists(), (
                f"output_path {output_path} does not exist on disk — "
                "registry references a stale or deleted page"
            )


def test_all_source_fingerprints_are_hex64(registry: dict, subtests) -> None:
    for source_path, fingerprint in registry["source_fingerprints"].items():
        with subtests.test(source_path=source_path):
            assert _HEX64_RE.match(fingerprint), (
                f"source fingerprint for {source_path} is not 64-hex: {fingerprint!r}"
            )


def test_per_item_fingerprints_are_hex64(registry: dict, subtests) -> None:
    for index, item in enumerate(registry["items"]):
        with subtests.test(index=index, item_key=item.get("item_key")):
            sf = item.get("source_fingerprint", "")
            df = item.get("dependency_fingerprint", "")
            assert _HEX64_RE.match(sf), f"source_fingerprint not 64-hex: {sf!r}"
            assert _HEX64_RE.match(df), f"dependency_fingerprint not 64-hex: {df!r}"


def test_dependency_fingerprint_matches_clean_tree_computation(registry: dict) -> None:
    """Defends against polluted __pycache__ during seed.

    Discovered during PR #376 cross-functional review: a stale `__pycache__`
    in `.github/skills/*/logic/` caused the seeded dependency_fingerprint to
    diverge from what `_compute_dependency_fingerprint` produces on a clean
    tree. The fix landed in PR #376 by filtering `__pycache__` and `.pyc`/`.pyo`
    files in `_compute_dependency_fingerprint`. This test pins the invariant.
    """
    expected = checkpoint_registry._compute_dependency_fingerprint(REPO_ROOT)
    actual_values = {item.get("dependency_fingerprint") for item in registry["items"]}
    assert actual_values == {expected}, (
        f"seeded dependency_fingerprint values {sorted(actual_values)!r} "
        f"must equal the clean-tree _compute_dependency_fingerprint output {expected!r}. "
        "If this fails, the registry was seeded against a polluted cache or the "
        "DEPENDENCY_FINGERPRINT_SOURCES changed without re-bootstrapping. "
        "See PR #376 code-reviewer P1 finding."
    )
