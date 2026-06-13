"""Checkpoint registry schema and contract alignment tests."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml

from scripts.kb import contracts


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "schema" / "wiki-processing-checkpoint-registry-contract.md"
CI3_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-3-pr-producer.yml"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"


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
        contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
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
        for enum_value in (
            *(trigger.value for trigger in contracts.TriggerType),
            *(artifact.value for artifact in contracts.ArtifactType),
        ):
            with self.subTest(enum_value=enum_value):
                self.assertIn(enum_value, contract_text)

    def test_dependency_fingerprint_sources_match_ci3_push_allowlist(self) -> None:
        """DEPENDENCY_FINGERPRINT_SOURCES must equal the CI-3 push.paths allowlist.

        The schema contract names ``.github/workflows/ci-3-pr-producer.yml``
        ``on.push.paths`` as the authoritative dependency set for the
        ``infrastructure_revalidation`` trigger. Parse the workflow YAML and
        compare against ``contracts.DEPENDENCY_FINGERPRINT_SOURCES`` so that
        future drift in either side fails this test instead of silently
        producing inconsistent infrastructure fingerprints.

        This test also pins the key-set of ``DEPENDENCY_FINGERPRINT_SOURCES``
        to exactly ``{"infrastructure_revalidation"}``. The schema contract
        explicitly states that ``intake_driven`` is driven by
        ``source_fingerprint`` and ``manual_rescan`` by an operator-selected
        set — neither belongs in ``DEPENDENCY_FINGERPRINT_SOURCES``. Without
        this key-set pin, a future addition like
        ``intake_driven: (...)`` would pass silently and contradict the
        schema. The lookup is performed through the ``TriggerType`` enum so
        a rename of the enum value without updating the dict key also fails.
        """
        with CI3_WORKFLOW_PATH.open("r", encoding="utf-8") as handle:
            workflow = yaml.safe_load(handle)

        # The PyYAML reader parses the YAML key ``on:`` as the Python
        # boolean ``True`` (YAML 1.1 implicit typing). Fall back to that
        # key if the literal string ``"on"`` is not present.
        on_section = workflow.get("on", workflow.get(True))
        self.assertIsNotNone(on_section, "CI-3 workflow has no on: section")
        push_paths = tuple(on_section["push"]["paths"])
        # Look up through the TriggerType enum so a future rename of the
        # enum value without a matching dict-key update fails this test.
        self.assertEqual(
            contracts.DEPENDENCY_FINGERPRINT_SOURCES[
                contracts.TriggerType.INFRASTRUCTURE_REVALIDATION
            ],
            push_paths,
        )
        # Pin the key-set so an accidental addition of another trigger
        # (which the schema forbids — intake_driven is source-driven and
        # manual_rescan is operator-driven) fails this test rather than
        # silently widening the dict.
        self.assertEqual(
            set(contracts.DEPENDENCY_FINGERPRINT_SOURCES.keys()),
            {contracts.TriggerType.INFRASTRUCTURE_REVALIDATION.value},
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

    def test_agents_matrix_declares_checkpoint_runtime_surface(self) -> None:
        agents_text = AGENTS_PATH.read_text(encoding="utf-8")
        self.assertIn("| `scripts/kb/checkpoint_registry.py` |", agents_text)
        self.assertIn("`--bootstrap --apply`", agents_text)
        self.assertIn("`--mutate`", agents_text)
        self.assertIn("`--verify`", agents_text)
        self.assertIn("raw/wiki-processing/wiki-processing-checkpoint-registry.json", agents_text)
        self.assertIn("schema/wiki-processing-checkpoint-registry-contract.md", agents_text)
        self.assertIn("CHECKPOINT_REGISTRY_LOCK_PATH", agents_text)

    def test_schema_contract_pins_batch_state_machine_rewrite(self) -> None:
        """Guard the wording introduced by the PR #213 review fix.

        The batch state machine was rewritten to mark ``completed``,
        ``partial``, and ``failed`` as terminal and remove the three
        ``*->running`` back-edges. Retries/resumes now create a new
        running batch record. Without this guard, a future editorial
        pass could silently reintroduce the contradictory transitions.
        """
        contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
        for required_text in (
            "terminal for the batch record",
            "appending a new batch record",
            "Only the most recent error is retained",
            "the original ADR-026 Decision text listing `automatic` is superseded",
        ):
            with self.subTest(required=required_text):
                self.assertIn(required_text, contract_text)

        # The three removed batch-state transition rows must stay absent.
        for forbidden_row in (
            "| `partial` | `running` |",
            "| `failed` | `running` |",
            "| `completed` | `running` |",
        ):
            with self.subTest(forbidden=forbidden_row):
                self.assertNotIn(forbidden_row, contract_text)

    def test_retention_constants_have_expected_byte_values(self) -> None:
        """Pin the numeric byte values for the registry retention thresholds.

        The schema contract specifies these as ``5 * 1024 * 1024`` and
        ``10 * 1024 * 1024`` respectively. The name-only assertion above
        would not catch a value drift like ``5 * 1000 * 1000`` or an
        accidental order-of-magnitude change.
        """
        self.assertEqual(
            contracts.CHECKPOINT_REGISTRY_SIZE_WARN_BYTES,
            5 * 1024 * 1024,
        )
        self.assertEqual(
            contracts.CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES,
            10 * 1024 * 1024,
        )

    def test_retention_constants_match_schema_contract_values(self) -> None:
        contract_text = CONTRACT_PATH.read_text(encoding="utf-8")
        expected = {
            "CHECKPOINT_REGISTRY_SIZE_WARN_BYTES": contracts.CHECKPOINT_REGISTRY_SIZE_WARN_BYTES,
            "CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES": contracts.CHECKPOINT_REGISTRY_SIZE_FAIL_BYTES,
        }
        for name, actual_value in expected.items():
            match = re.search(rf"`{name} = (?P<mb>\d+) MB`", contract_text)
            self.assertIsNotNone(match, f"{name} row missing from schema contract")
            assert match is not None
            self.assertEqual(actual_value, int(match.group("mb")) * 1024 * 1024)

    def test_schema_contract_declares_in_governed_artifact_contract(self) -> None:
        """The new artifact must be declared in schema/governed-artifact-contract.md.

        ``schema/governed-artifact-contract.md`` is the authoritative index of
        governed state artifacts. Every governed artifact must have a row or
        section there before any durable write can land. This guards against
        the artifact being added to ``scripts/kb/contracts.py`` without the
        documentation cascade.
        """
        governed_text = (REPO_ROOT / "schema" / "governed-artifact-contract.md").read_text(
            encoding="utf-8"
        )
        for required_text in (
            "raw/wiki-processing/wiki-processing-checkpoint-registry.json",
            "schema/wiki-processing-checkpoint-registry-contract.md",
            "raw/.wiki-processing-checkpoint.lock",
            "wiki-processing-checkpoint-registry",
        ):
            self.assertIn(required_text, governed_text)


if __name__ == "__main__":
    unittest.main()
