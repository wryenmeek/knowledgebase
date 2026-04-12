"""Contract tests for shared knowledgebase constants and result envelopes."""

from __future__ import annotations

import json
import unittest

from scripts.kb import contracts


class SharedContractsTests(unittest.TestCase):
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
            ),
        )
        self.assertEqual(
            contracts.WRITE_ALLOWLIST_PATHS,
            (
                "wiki/**",
                "wiki/index.md",
                "wiki/log.md",
                "raw/processed/**",
            ),
        )
        self.assertEqual(contracts.WRITE_LOCK_PATH, "wiki/.kb_write.lock")

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


if __name__ == "__main__":
    unittest.main()
