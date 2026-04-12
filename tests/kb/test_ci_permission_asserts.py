"""Machine-checkable CI permission/profile/concurrency policy assertions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unittest

from scripts.kb import contracts


@dataclass(frozen=True, slots=True)
class WorkflowPolicyExpectation:
    ci_id: str
    workflow_path: Path
    token_profile: str
    permissions: dict[str, str]
    write_capable: bool = False


WORKFLOW_POLICY_MATRIX: tuple[WorkflowPolicyExpectation, ...] = (
    WorkflowPolicyExpectation(
        ci_id="CI-1",
        workflow_path=Path(".github/workflows/ci-1-gatekeeper.yml"),
        token_profile=contracts.TokenProfileId.GATEKEEPER.value,
        permissions={
            "actions": "read",
            "contents": "read",
        },
        write_capable=True,
    ),
    WorkflowPolicyExpectation(
        ci_id="CI-2",
        workflow_path=Path(".github/workflows/ci-2-analyst-diagnostics.yml"),
        token_profile=contracts.TokenProfileId.ANALYST_READONLY.value,
        permissions={
            "actions": "read",
            "checks": "read",
            "contents": "read",
        },
    ),
    WorkflowPolicyExpectation(
        ci_id="CI-3",
        workflow_path=Path(".github/workflows/ci-3-pr-producer.yml"),
        token_profile=contracts.TokenProfileId.PR_PRODUCER.value,
        permissions={
            "actions": "read",
            "checks": "read",
            "contents": "read",
        },
        write_capable=True,
    ),
)

WRITE_CONCURRENCY_GUARD = {
    "group": "kb-write-${{ github.repository }}-${{ github.ref }}",
    "cancel-in-progress": "false",
}
CI3_PR_PRODUCER_JOB_PERMISSIONS = {
    "actions": "read",
    "checks": "read",
    "contents": "write",
    "pull-requests": "write",
}


def _parse_mapping_block(
    lines: list[str],
    block_start: int,
    *,
    indent: int,
    context: str,
    workflow_path: Path,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    duplicate_keys: set[str] = set()
    expected_prefix = " " * indent
    nested_prefix = expected_prefix + "  "

    for candidate in lines[block_start + 1 :]:
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if not candidate.startswith(expected_prefix) or candidate.startswith(nested_prefix):
            break
        if ":" not in stripped:
            raise AssertionError(f"{workflow_path} has malformed entry in {context}: {candidate}")
        map_key, map_value = stripped.split(":", 1)
        normalized_key = map_key.strip()
        if normalized_key in mapping:
            duplicate_keys.add(normalized_key)
        mapping[normalized_key] = map_value.strip()

    if duplicate_keys:
        duplicates = ", ".join(sorted(duplicate_keys))
        raise AssertionError(f"{workflow_path} has duplicate keys in {context}: {duplicates}")

    return mapping


def _parse_top_level_mapping_block(text: str, key: str, workflow_path: Path) -> dict[str, str]:
    lines = text.splitlines()
    target = f"{key}:"

    for index, line in enumerate(lines):
        if line.strip() != target or line.startswith(" "):
            continue

        return _parse_mapping_block(
            lines,
            index,
            indent=2,
            context=f"top-level '{key}' block",
            workflow_path=workflow_path,
        )

    raise AssertionError(f"{workflow_path} is missing top-level '{key}' block")


def _parse_job_mapping_block(text: str, job_name: str, key: str, workflow_path: Path) -> dict[str, str]:
    lines = text.splitlines()
    job_target = f"{job_name}:"
    key_target = f"{key}:"
    job_indices = [
        index
        for index, line in enumerate(lines)
        if line.strip() == job_target and line.startswith("  ") and not line.startswith("    ")
    ]
    if not job_indices:
        raise AssertionError(f"{workflow_path} is missing job '{job_name}'")
    if len(job_indices) > 1:
        raise AssertionError(f"{workflow_path} has duplicate job blocks for '{job_name}'")

    key_indices: list[int] = []
    for index in range(job_indices[0] + 1, len(lines)):
        candidate = lines[index]
        stripped = candidate.strip()
        if not stripped:
            continue
        if not candidate.startswith("    "):
            break
        if stripped == key_target and candidate.startswith("    ") and not candidate.startswith("      "):
            key_indices.append(index)

    if not key_indices:
        raise AssertionError(f"{workflow_path} is missing '{key}' block in job '{job_name}'")
    if len(key_indices) > 1:
        raise AssertionError(f"{workflow_path} has duplicate '{key}' blocks in job '{job_name}'")

    return _parse_mapping_block(
        lines,
        key_indices[0],
        indent=6,
        context=f"job '{job_name}' '{key}' block",
        workflow_path=workflow_path,
    )


class CiPermissionPolicyAssertions(unittest.TestCase):
    def test_ci_profiles_and_permissions_match_spec_matrix(self) -> None:
        for policy in WORKFLOW_POLICY_MATRIX:
            with self.subTest(ci_id=policy.ci_id):
                self.assertTrue(
                    policy.workflow_path.exists(),
                    f"Expected workflow file to exist: {policy.workflow_path}",
                )
                workflow_text = policy.workflow_path.read_text(encoding="utf-8")

                self.assertIn(
                    f"CI_ID: {policy.ci_id}",
                    workflow_text,
                    f"{policy.workflow_path} must declare CI_ID: {policy.ci_id}",
                )
                self.assertIn(
                    f"TOKEN_PROFILE: {policy.token_profile}",
                    workflow_text,
                    (
                        f"{policy.workflow_path} must bind to token profile "
                        f"{policy.token_profile}"
                    ),
                )

                actual_permissions = _parse_top_level_mapping_block(
                    workflow_text,
                    "permissions",
                    policy.workflow_path,
                )
                self.assertEqual(
                    actual_permissions,
                    policy.permissions,
                    (
                        f"{policy.workflow_path} permissions drifted from expected "
                        f"profile matrix for {policy.ci_id}"
                    ),
                )

    def test_ci3_pr_producer_job_permissions_are_explicit_write_scoped(self) -> None:
        ci3_policy = next(policy for policy in WORKFLOW_POLICY_MATRIX if policy.ci_id == "CI-3")
        workflow_text = ci3_policy.workflow_path.read_text(encoding="utf-8")
        actual_permissions = _parse_job_mapping_block(
            workflow_text,
            "pr-producer",
            "permissions",
            ci3_policy.workflow_path,
        )
        self.assertEqual(
            actual_permissions,
            CI3_PR_PRODUCER_JOB_PERMISSIONS,
            (
                f"{ci3_policy.workflow_path} must scope write permissions to the pr-producer job "
                "while keeping workflow-level permissions read-only"
            ),
        )

    def test_write_capable_workflows_use_required_concurrency_guard(self) -> None:
        for policy in WORKFLOW_POLICY_MATRIX:
            if not policy.write_capable:
                continue

            with self.subTest(ci_id=policy.ci_id):
                workflow_text = policy.workflow_path.read_text(encoding="utf-8")
                actual_concurrency = _parse_top_level_mapping_block(
                    workflow_text,
                    "concurrency",
                    policy.workflow_path,
                )
                self.assertEqual(
                    actual_concurrency,
                    WRITE_CONCURRENCY_GUARD,
                    (
                        f"{policy.workflow_path} must keep write-path concurrency guard "
                        f"{WRITE_CONCURRENCY_GUARD}"
                    ),
                )

    def test_ci3_write_allowlist_boundary_checks_are_explicit(self) -> None:
        ci3_policy = next(policy for policy in WORKFLOW_POLICY_MATRIX if policy.ci_id == "CI-3")
        workflow_text = ci3_policy.workflow_path.read_text(encoding="utf-8")
        expected_allowlist = ",".join(contracts.WRITE_ALLOWLIST_PATHS)

        self.assertIn(
            f"WRITE_ALLOWLIST: {expected_allowlist}",
            workflow_text,
            "CI-3 workflow must declare the contract write allowlist in env",
        )

        required_allowlist_controls = (
            'case "${changed_path}" in',
            "wiki/*|raw/processed/*)",
            'allowlist_failures+=("${status_code}:${changed_path}")',
            "reject:permissions_scope:out_of_allowlist_write:",
            "CI-3 write allowlist is restricted to ${WRITE_ALLOWLIST}.",
            "exit 1",
        )
        for control in required_allowlist_controls:
            self.assertIn(
                control,
                workflow_text,
                f"CI-3 write allowlist control missing: {control}",
            )

    def test_ci3_permissions_contract_failure_reasons_are_explicit(self) -> None:
        ci3_policy = next(policy for policy in WORKFLOW_POLICY_MATRIX if policy.ci_id == "CI-3")
        workflow_text = ci3_policy.workflow_path.read_text(encoding="utf-8")

        required_permission_controls = (
            "reject:permissions_scope:minimum_permissions_mismatch",
            "reject:permissions_scope:permissions_block_missing:top_level",
            "reject:permissions_scope:permissions_block_duplicated:top_level",
            "reject:permissions_scope:permissions_block_missing:pr_producer",
            "reject:permissions_scope:permissions_block_duplicated:pr_producer",
            "reject:permissions_scope:permissions_key_duplicated:{scope}:{duplicate_key}",
            "reject:permissions_scope:permissions_key_missing:{scope}:{missing_key}",
            "reject:permissions_scope:permissions_key_unexpected:{scope}:{unexpected_key}",
            "reject:permissions_scope:permissions_value_mismatch:",
            'scope="top_level"',
            'scope="pr_producer"',
        )
        for control in required_permission_controls:
            self.assertIn(
                control,
                workflow_text,
                f"CI-3 permission contract control missing: {control}",
            )


if __name__ == "__main__":
    unittest.main()
