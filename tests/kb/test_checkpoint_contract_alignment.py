"""Checkpoint registry schema and contract alignment tests."""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.kb import contracts


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "schema" / "wiki-processing-checkpoint-registry-contract.md"


class CheckpointRegistryContractAlignmentTests(unittest.TestCase):
    def test_governed_contract_entry_and_lock_registration_are_declared(self) -> None:
        contract = contracts.governed_artifact_contract(
            "raw/wiki-processing/wiki-processing-checkpoint-registry.json"
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.artifact_id, "wiki-processing-checkpoint-registry")
        self.assertEqual(contract.lock_path, contracts.CHECKPOINT_REGISTRY_LOCK_PATH)
        self.assertIn(".wiki-processing-checkpoint.lock", contracts.GOVERNANCE_LOCK_FILES)

    def test_trigger_and_artifact_type_enums_match_checkpoint_scope(self) -> None:
        self.assertEqual(
            tuple(trigger.value for trigger in contracts.TriggerType),
            (
                "intake_driven",
                "infrastructure_revalidation",
                "manual_rescan",
            ),
        )
        self.assertEqual(
            tuple(artifact.value for artifact in contracts.ArtifactType),
            (
                "wiki_entity_page",
                "wiki_concept_page",
                "wiki_analysis_page",
            ),
        )

    def test_dependency_fingerprint_sources_match_ci3_push_allowlist(self) -> None:
        self.assertEqual(
            contracts.DEPENDENCY_FINGERPRINT_SOURCES["infrastructure_revalidation"],
            (
                ".github/workflows/ci-3-pr-producer.yml",
                ".github/skills/extract-entities-and-claims/**",
                ".github/skills/validate-wiki-governance/**",
                ".github/skills/synthesize-entity-page/**",
                ".github/skills/synthesize-concept-page/**",
            ),
        )

    def test_schema_contract_mentions_public_constants_and_state_machines(self) -> None:
        contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
        for required_text in (
            "raw/wiki-processing/wiki-processing-checkpoint-registry.json",
            "raw/.wiki-processing-checkpoint.lock",
            "source_fingerprints",
            "CHECKPOINT_REGISTRY_SIZE_WARN_BYTES = 5 MB",
            "CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES = 10 MB",
            "Trigger x transition matrix",
            "Bootstrap classification rules",
            "Fail-closed behavior",
            "wiki_entity_page",
            "wiki_concept_page",
            "wiki_analysis_page",
        ):
            self.assertIn(required_text, contract_text)


if __name__ == "__main__":
    unittest.main()
