"""Contract tests for shared knowledgebase constants and result envelopes."""

from __future__ import annotations

import json

from scripts import init as init_script
from scripts.kb import contracts


class _AssertMixin:
    def assertEqual(self, left, right, msg=None) -> None:
        assert left == right, msg

    def assertIn(self, member, container, msg=None) -> None:
        assert member in container, msg

    def assertIsNotNone(self, value, msg=None) -> None:
        assert value is not None, msg

    def assertIsNone(self, value, msg=None) -> None:
        assert value is None, msg


class TestSharedContracts(_AssertMixin):
    def test_governed_artifact_contracts_cover_declared_state_targets(self) -> None:
        self.assertEqual(
            contracts.GOVERNED_ARTIFACT_IDS,
            (
                "wiki-index",
                "wiki-log",
                "wiki-open-questions",
                "wiki-backlog",
                "wiki-status",
                "github-source-registry",
                "external-asset",
                "rejection-record",
                "wiki-processing-checkpoint-registry",
            ),
        )
        self.assertEqual(
            contracts.GOVERNED_ARTIFACT_PATHS,
            (
                "wiki/index.md",
                "wiki/log.md",
                "wiki/open-questions.md",
                "wiki/backlog.md",
                "wiki/status.md",
                # GitHub source monitoring artifacts use dynamic paths; the ``path``
                # field for these contracts is the directory prefix, not a fixed file.
                "raw/github-sources",
                "raw/assets",
                "raw/rejected",
                "raw/wiki-processing/wiki-processing-checkpoint-registry.json",
            ),
        )

    def test_checkpoint_registry_contract_and_lock_are_declared(self) -> None:
        self.assertEqual(
            contracts.CHECKPOINT_REGISTRY_LOCK_PATH,
            "raw/.wiki-processing-checkpoint.lock",
        )
        self.assertIn(
            ".wiki-processing-checkpoint.lock",
            contracts.GOVERNANCE_LOCK_FILES,
        )

        contract = contracts.governed_artifact_contract(
            "raw/wiki-processing/wiki-processing-checkpoint-registry.json"
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.artifact_id, "wiki-processing-checkpoint-registry")
        self.assertEqual(
            contract.schema_owner,
            "schema/wiki-processing-checkpoint-registry-contract.md",
        )
        self.assertEqual(contract.lock_path, contracts.CHECKPOINT_REGISTRY_LOCK_PATH)
        self.assertEqual(
            contract.mutability,
            contracts.ArtifactMutability.MUTABLE.value,
        )
        self.assertEqual(
            contract.write_strategy,
            contracts.ArtifactWriteStrategy.ATOMIC_REPLACE_UNDER_LOCK.value,
        )

    def test_governed_artifact_contract_by_pattern_matches_registry_files(self) -> None:
        registry_path = "raw/github-sources/cms-gov-regulations.source-registry.json"
        contract = contracts.governed_artifact_contract_by_pattern(registry_path)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.artifact_id, "github-source-registry")
        self.assertEqual(contract.lock_path, "raw/.github-sources.lock")
        self.assertEqual(
            contract.write_strategy,
            contracts.ArtifactWriteStrategy.ATOMIC_REPLACE_UNDER_LOCK.value,
        )

    def test_governed_artifact_contract_by_pattern_matches_assets(self) -> None:
        asset_path = "raw/assets/cms-gov/regulations/abc123def456/docs/guidance.md"
        contract = contracts.governed_artifact_contract_by_pattern(asset_path)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.artifact_id, "external-asset")
        self.assertIsNone(contract.lock_path)
        self.assertEqual(
            contract.write_strategy,
            contracts.ArtifactWriteStrategy.EXCLUSIVE_CREATE_WRITE_ONCE.value,
        )
        # Write-once assets must be declared IMMUTABLE, not MUTABLE.
        self.assertEqual(
            contract.mutability,
            contracts.ArtifactMutability.IMMUTABLE.value,
        )

    def test_governed_artifact_contract_by_pattern_matches_rejection_records(self) -> None:
        rejection_path = "raw/rejected/example-source--a1b2c3d4.rejection.md"
        contract = contracts.governed_artifact_contract_by_pattern(rejection_path)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.artifact_id, "rejection-record")
        self.assertEqual(contract.lock_path, "raw/.rejection-registry.lock")
        self.assertEqual(
            contract.write_strategy,
            contracts.ArtifactWriteStrategy.EXCLUSIVE_CREATE_WRITE_ONCE.value,
        )
        self.assertEqual(
            contract.mutability,
            contracts.ArtifactMutability.IMMUTABLE.value,
        )

    def test_governed_artifact_contract_by_pattern_exact_match_takes_precedence(self) -> None:
        # Exact-path lookup still works via governed_artifact_contract_by_pattern.
        log_contract = contracts.governed_artifact_contract_by_pattern("wiki/log.md")
        self.assertIsNotNone(log_contract)
        assert log_contract is not None
        self.assertEqual(log_contract.artifact_id, "wiki-log")

    def test_governed_artifact_contract_by_pattern_no_match(self) -> None:
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("some/undeclared/path.txt")
        )

    def test_governed_artifact_contract_by_pattern_rejects_traversal(self) -> None:
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("raw/github-sources/../../../etc/passwd")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("../wiki/log.md")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("wiki/../raw/processed/SPEC.md")
        )

    def test_governed_artifact_contract_by_pattern_rejects_platform_specific_paths(
        self,
    ) -> None:
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern(
                r"wiki\..\.github/copilot-instructions.md"
            )
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("\\\\server\\share\\foo")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("C:\\wiki\\index.md")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("C:/wiki/index.md")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("C:wiki/index.md")
        )
        self.assertIsNone(
            contracts.governed_artifact_contract_by_pattern("/wiki/index.md")
        )

    def test_governed_artifact_contract_by_pattern_matches_all_declared_artifacts(
        self,
    ) -> None:
        representative_paths = {
            "github-source-registry": "raw/github-sources/example.source-registry.json",
            "external-asset": "raw/assets/example/repo/abc123/file.md",
            "rejection-record": "raw/rejected/example--a1b2c3d4.rejection.md",
        }
        dynamic_pattern_ids = {
            artifact.artifact_id
            for artifact in contracts.GOVERNED_ARTIFACT_CONTRACTS
            if artifact.path_pattern
        }
        self.assertEqual(set(representative_paths), dynamic_pattern_ids)

        for artifact in contracts.GOVERNED_ARTIFACT_CONTRACTS:
            path = representative_paths.get(artifact.artifact_id, artifact.path)
            matched = contracts.governed_artifact_contract_by_pattern(path)
            assert matched is not None, f"expected match for {artifact.artifact_id}"
            self.assertEqual(matched.artifact_id, artifact.artifact_id)

    def test_governed_artifact_contract_details_are_explicit(self) -> None:
        log_contract = contracts.governed_artifact_contract("wiki/log.md")
        self.assertIsNotNone(log_contract)
        assert log_contract is not None
        self.assertEqual(log_contract.schema_owner, "schema/governed-artifact-contract.md")
        self.assertEqual(
            log_contract.mutability,
            contracts.ArtifactMutability.APPEND_ONLY.value,
        )
        self.assertEqual(
            log_contract.write_strategy,
            contracts.ArtifactWriteStrategy.APPEND_UNDER_LOCK.value,
        )
        self.assertEqual(log_contract.lock_path, contracts.WRITE_LOCK_PATH)

        status_contract = contracts.governed_artifact_contract("wiki/status.md")
        self.assertIsNotNone(status_contract)
        assert status_contract is not None
        self.assertEqual(status_contract.schema_owner, "schema/governed-artifact-contract.md")
        self.assertEqual(
            status_contract.mutability,
            contracts.ArtifactMutability.MUTABLE.value,
        )
        self.assertEqual(
            status_contract.write_strategy,
            contracts.ArtifactWriteStrategy.ATOMIC_REPLACE_UNDER_LOCK.value,
        )

        index_contract = contracts.governed_artifact_contract("wiki/index.md")
        self.assertIsNotNone(index_contract)
        assert index_contract is not None
        self.assertEqual(index_contract.schema_owner, "schema/taxonomy-contract.md")

    def test_spec_aligned_policy_identifiers(self) -> None:
        self.assertIn(
            "continue_and_report_per_source",
            contracts.POLICY_IDENTIFIERS,
        )
        self.assertIn(
            "auto_persist_when_high_value",
            contracts.POLICY_IDENTIFIERS,
        )
        self.assertIn(
            "log_only_state_changes",
            contracts.POLICY_IDENTIFIERS,
        )

    def test_spec_aligned_token_profiles_and_paths(self) -> None:
        self.assertEqual(
            contracts.TOKEN_PROFILE_IDS,
            (
                "tp-gatekeeper",
                "tp-analyst-readonly",
                "tp-pr-producer",
                "tp-framework-writer",
                "tp-github-monitor",
                "tp-freshness-readonly",
                "tp-customizations-readwrite",
                "tp-drive-monitor",
            ),
        )
        self.assertEqual(
            contracts.WRITE_ALLOWLIST_PATHS,
            (
                "wiki/**",
                "wiki/index.md",
                "wiki/log.md",
                "raw/processed/**",
                "raw/rejected/**",
            ),
        )
        self.assertEqual(contracts.WRITE_LOCK_PATH, "wiki/.kb_write.lock")
        self.assertEqual(
            contracts.REJECTION_REGISTRY_LOCK_PATH,
            "raw/.rejection-registry.lock",
        )
        self.assertEqual(
            contracts.CHECKPOINT_REGISTRY_LOCK_PATH,
            "raw/.wiki-processing-checkpoint.lock",
        )

    def test_customizations_lock_path_is_declared_and_exported(self) -> None:
        self.assertEqual(
            contracts.CUSTOMIZATIONS_LOCK_PATH,
            ".github/.customizations.lock",
        )
        self.assertIn("CUSTOMIZATIONS_LOCK_PATH", contracts.__all__)
        self.assertIn(".customizations.lock", contracts.GOVERNANCE_LOCK_FILES)
        self.assertIn(contracts.CUSTOMIZATIONS_LOCK_PATH, init_script.LOCK_FILES)

    def test_governance_meta_lock_and_sibling_set_are_declared_and_exported(self) -> None:
        self.assertEqual(
            contracts.GOVERNANCE_META_LOCK_PATH,
            "raw/.governance-meta.lock",
        )
        self.assertEqual(
            contracts.GOVERNANCE_SIBLING_LOCKS,
            frozenset(
                {
                    contracts.WRITE_LOCK_PATH,
                    contracts.REJECTION_REGISTRY_LOCK_PATH,
                    contracts.CUSTOMIZATIONS_LOCK_PATH,
                    contracts.GITHUB_SOURCES_LOCK_PATH,
                    contracts.DRIVE_SOURCES_LOCK_PATH,
                    contracts.CHECKPOINT_REGISTRY_LOCK_PATH,
                }
            ),
        )
        self.assertIn("GOVERNANCE_META_LOCK_PATH", contracts.__all__)
        self.assertIn("GOVERNANCE_SIBLING_LOCKS", contracts.__all__)
        self.assertIn(".governance-meta.lock", contracts.GOVERNANCE_LOCK_FILES)
        self.assertIn(contracts.GOVERNANCE_META_LOCK_PATH, init_script.LOCK_FILES)

    def test_test_framework_ratchet_baseline_is_declared_and_exported(self) -> None:
        self.assertEqual(contracts.MAX_UNITTEST_FILES, 58)
        self.assertIn("MAX_UNITTEST_FILES", contracts.__all__)

    def test_approval_flag_ratchet_baseline_is_declared_and_exported(self) -> None:
        self.assertEqual(contracts.MAX_APPROVAL_FLAG_SCRIPTS, 8)
        self.assertIn("MAX_APPROVAL_FLAG_SCRIPTS", contracts.__all__)

    def test_reason_codes_include_spec_required_values(self) -> None:
        self.assertIn("lock_unavailable", contracts.REASON_CODES)
        self.assertIn("prereq_missing:ghaw_readiness", contracts.REASON_CODES)
        self.assertIn("prereq_missing:concurrency_guard", contracts.REASON_CODES)

    def test_result_envelope_serialization(self) -> None:
        envelope = contracts.ResultEnvelope(
            status=contracts.ResultStatus.WRITTEN,
            reason_code=contracts.ReasonCode.OK,
            policy=(
                contracts.PolicyId.AUTO_PERSIST_WHEN_HIGH_VALUE,
                contracts.PolicyId.LOG_ONLY_STATE_CHANGES,
            ),
            analysis_path="wiki/analyses/example-query.md",
            index_updated=True,
            log_appended=False,
            sources=(
                "repo://owner/repo/raw/processed/source.md@abc123#L1-L2?sha256="
                + ("f" * 64),
            ),
        )

        envelope_dict = envelope.to_dict()
        self.assertEqual(tuple(envelope_dict.keys()), contracts.RESULT_ENVELOPE_KEYS)
        self.assertEqual(envelope_dict["status"], "written")
        self.assertEqual(envelope_dict["reason_code"], "ok")
        self.assertEqual(
            envelope_dict["policy"],
            [
                "auto_persist_when_high_value",
                "log_only_state_changes",
            ],
        )
        self.assertEqual(
            json.loads(envelope.to_json()),
            envelope_dict,
        )
