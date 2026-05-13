"""Test TOKEN_PROFILE registry completeness: every TOKEN_PROFILE value used in
workflows must be declared in contracts.TokenProfileId, and every workflow that
declares a TOKEN_PROFILE must be registered in test_ci_permission_asserts.WORKFLOW_POLICY_MATRIX.

These tests catch the class of drift where a new CI workflow is added with a new
token profile but the profile is not registered in the canonical enum or the
policy matrix.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from scripts.kb import contracts
from tests.kb.test_ci_permission_asserts import WORKFLOW_POLICY_MATRIX

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def _extract_token_profiles_from_workflow(path: Path) -> list[str]:
    """Extract TOKEN_PROFILE values from top-level and job-level env blocks.

    Ignores TOKEN_PROFILE references inside ``run:`` bash script blocks to
    avoid false positives from variable references like ``${TOKEN_PROFILE}``.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []

    profiles: list[str] = []

    # Top-level env block
    top_env = data.get("env") or {}
    if isinstance(top_env, dict) and "TOKEN_PROFILE" in top_env:
        profiles.append(str(top_env["TOKEN_PROFILE"]))

    # Job-level env blocks
    jobs = data.get("jobs") or {}
    if isinstance(jobs, dict):
        for job_data in jobs.values():
            if not isinstance(job_data, dict):
                continue
            job_env = job_data.get("env") or {}
            if isinstance(job_env, dict) and "TOKEN_PROFILE" in job_env:
                profiles.append(str(job_env["TOKEN_PROFILE"]))

    return profiles


class TestTokenProfileRegistryCompleteness(unittest.TestCase):
    """All TOKEN_PROFILE values in workflow YAMLs must be in TokenProfileId enum."""

    def test_all_workflow_token_profiles_are_registered_in_enum(self) -> None:
        if not WORKFLOWS_DIR.is_dir():
            self.skipTest(".github/workflows/ directory does not exist")

        registered = set(contracts.TOKEN_PROFILE_IDS)

        for workflow_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            profiles = _extract_token_profiles_from_workflow(workflow_path)
            for profile in profiles:
                with self.subTest(workflow=workflow_path.name, profile=profile):
                    self.assertIn(
                        profile,
                        registered,
                        f"{workflow_path.name} declares TOKEN_PROFILE '{profile}' which is "
                        f"not in contracts.TokenProfileId. Add it to scripts/kb/contracts.py "
                        f"and update tests/kb/test_contracts.py expected tuple.",
                    )

    def test_all_token_profile_workflows_registered_in_policy_matrix(self) -> None:
        """Every workflow that declares TOKEN_PROFILE must appear in WORKFLOW_POLICY_MATRIX."""
        if not WORKFLOWS_DIR.is_dir():
            self.skipTest(".github/workflows/ directory does not exist")

        matrix_paths = {
            str(policy.workflow_path) for policy in WORKFLOW_POLICY_MATRIX
        }

        for workflow_path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            profiles = _extract_token_profiles_from_workflow(workflow_path)
            if not profiles:
                continue  # No TOKEN_PROFILE declared — not a governed CI workflow

            rel_path = str(workflow_path.relative_to(REPO_ROOT))
            with self.subTest(workflow=workflow_path.name):
                self.assertIn(
                    rel_path,
                    matrix_paths,
                    f"{workflow_path.name} declares TOKEN_PROFILE but is not registered in "
                    f"WORKFLOW_POLICY_MATRIX in tests/kb/test_ci_permission_asserts.py. "
                    f"Add a WorkflowPolicyExpectation entry for this workflow.",
                )


if __name__ == "__main__":
    unittest.main()
