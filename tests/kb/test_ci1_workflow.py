"""Workflow contract checks for CI-1 gatekeeper trusted handoff."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


WORKFLOW_PATH = Path(".github/workflows/ci-1-gatekeeper.yml")


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
    lines = text.splitlines()
    target = f"{key}:"

    for index, line in enumerate(lines):
        if line.strip() != target or line.startswith(" "):
            continue

        mapping: dict[str, str] = {}
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                continue
            if not candidate.startswith("  ") or candidate.startswith("    "):
                break
            if stripped.startswith("#") or ":" not in stripped:
                continue
            map_key, map_value = stripped.split(":", 1)
            mapping[map_key.strip()] = map_value.strip()

        return mapping

    raise AssertionError(f"Top-level '{key}' block is missing from {WORKFLOW_PATH}")


class Ci1WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci1_metadata_and_triggers_are_spec_aligned(self) -> None:
        self.assertIn("name: CI-1 Gatekeeper Trusted Handoff", self.workflow_text)
        self.assertIn("CI_ID: CI-1", self.workflow_text)
        self.assertIn("TOKEN_PROFILE: tp-gatekeeper", self.workflow_text)
        self.assertIn("REQUIRED_EVENT: push", self.workflow_text)
        self.assertIn("REQUIRED_PATH_PREFIX: raw/inbox/", self.workflow_text)
        self.assertRegex(
            self.workflow_text,
            r"(?ms)^on:\n\s+push:\n\s+paths:\n\s+-\s+raw/inbox/\*\*\s*$",
        )
        self.assertNotIn("pull_request:", self.workflow_text)
        self.assertNotIn("workflow_dispatch:", self.workflow_text)

    def test_permissions_and_concurrency_match_ci1_requirements(self) -> None:
        self.assertEqual(
            _parse_top_level_mapping_block(self.workflow_text, "permissions"),
            {
                "actions": "read",
                "contents": "read",
            },
        )
        self.assertEqual(
            _parse_top_level_mapping_block(self.workflow_text, "concurrency"),
            {
                "group": "kb-write-${{ github.repository }}-${{ github.ref }}",
                "cancel-in-progress": "false",
            },
        )
        self.assertIsNone(
            re.search(
                r"(?im)^\s*(contents|actions|checks|pull-requests|issues|packages|id-token)\s*:\s*write\s*$",
                self.workflow_text,
            ),
            "CI-1 workflow must not request forbidden write scopes",
        )

    def test_preflight_rejections_are_explicit_and_fail_closed(self) -> None:
        required_rejections = (
            "reject:trusted_trigger_model:event_not_push",
            "reject:trusted_trigger_model:not_default_branch",
            "reject:trusted_trigger_model:ref_not_protected",
            "action_required:trusted_trigger_model:enable_branch_protection",
            "reject:path_filter:no_changed_paths_detected",
            "reject:path_filter:outside_raw_inbox:",
            "reject:permissions_scope:token_profile_mismatch",
            "reject:permissions_scope:minimum_permissions_mismatch",
            "reject:permissions_scope:forbidden_write_scope_declared",
            "CI-1 gatekeeper rejection reason=",
            "exit 1",
        )
        for expected in required_rejections:
            self.assertIn(expected, self.workflow_text)

    def test_workflow_stays_ci1_gatekeeper_only(self) -> None:
        self.assertIn("CI-3 PR-producing behavior is intentionally out of scope", self.workflow_text)

        forbidden_ci3_actions = (
            "git push",
            "git commit",
            "gh pr",
            "scripts/kb/ingest.py --source",
            "scripts/kb/update_index.py --write",
            "scripts/kb/persist_query.py",
        )
        for forbidden in forbidden_ci3_actions:
            self.assertNotIn(forbidden, self.workflow_text)


if __name__ == "__main__":
    unittest.main()
