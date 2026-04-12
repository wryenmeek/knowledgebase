"""Workflow contract checks for CI-3 PR-producing write path."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import textwrap
import unittest


WORKFLOW_PATH = Path(".github/workflows/ci-3-pr-producer.yml")


def _parse_mapping_block(
    lines: list[str],
    block_start: int,
    *,
    indent: int,
    context: str,
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
            raise AssertionError(f"Malformed entry in {context} for {WORKFLOW_PATH}: {candidate}")
        map_key, map_value = stripped.split(":", 1)
        normalized_key = map_key.strip()
        if normalized_key in mapping:
            duplicate_keys.add(normalized_key)
        mapping[normalized_key] = map_value.strip()

    if duplicate_keys:
        duplicates = ", ".join(sorted(duplicate_keys))
        raise AssertionError(f"Duplicate keys in {context} for {WORKFLOW_PATH}: {duplicates}")

    return mapping


def _parse_top_level_mapping_block(text: str, key: str) -> dict[str, str]:
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
        )

    raise AssertionError(f"Top-level '{key}' block is missing from {WORKFLOW_PATH}")


def _parse_job_mapping_block(text: str, job_name: str, key: str) -> dict[str, str]:
    lines = text.splitlines()
    job_target = f"{job_name}:"
    key_target = f"{key}:"
    job_indices = [
        index
        for index, line in enumerate(lines)
        if line.strip() == job_target and line.startswith("  ") and not line.startswith("    ")
    ]
    if not job_indices:
        raise AssertionError(f"Job '{job_name}' block is missing from {WORKFLOW_PATH}")
    if len(job_indices) > 1:
        raise AssertionError(
            f"Job '{job_name}' block is duplicated in {WORKFLOW_PATH}; found {len(job_indices)} copies"
        )

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
        raise AssertionError(f"Job '{job_name}' is missing '{key}' block in {WORKFLOW_PATH}")
    if len(key_indices) > 1:
        raise AssertionError(
            f"Job '{job_name}' has duplicated '{key}' blocks in {WORKFLOW_PATH}; found {len(key_indices)} copies"
        )

    return _parse_mapping_block(
        lines,
        key_indices[0],
        indent=6,
        context=f"job '{job_name}' '{key}' block",
    )


class Ci3WorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_ci3_metadata_and_triggers_are_spec_aligned(self) -> None:
        self.assertIn("name: CI-3 PR Producer Write Path", self.workflow_text)
        self.assertIn("CI_ID: CI-3", self.workflow_text)
        self.assertIn("TOKEN_PROFILE: tp-pr-producer", self.workflow_text)
        self.assertIn("workflow_run:", self.workflow_text)
        self.assertIn("- CI-1 Gatekeeper Trusted Handoff", self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)
        self.assertIn("maintainer_approved:", self.workflow_text)
        self.assertIn("source_path:", self.workflow_text)

    def test_permissions_and_concurrency_match_ci3_requirements(self) -> None:
        self.assertEqual(
            _parse_top_level_mapping_block(self.workflow_text, "permissions"),
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
            },
        )
        self.assertEqual(
            _parse_job_mapping_block(self.workflow_text, "pr-producer", "permissions"),
            {
                "actions": "read",
                "checks": "read",
                "contents": "write",
                "pull-requests": "write",
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
                r"(?im)^\s*(issues|packages|id-token|security-events|attestations|deployments)\s*:\s*write\s*$",
                self.workflow_text,
            ),
            "CI-3 workflow must not request forbidden write scopes",
        )

    def test_preflight_and_allowlist_fail_closed_controls_are_explicit(self) -> None:
        required_controls = (
            "WRITE_ALLOWLIST: wiki/**,wiki/index.md,wiki/log.md,raw/processed/**",
            "reject:trusted_trigger_model:manual_approval_required",
            "reject:trusted_trigger_model:unexpected_handoff_workflow",
            "reject:trusted_trigger_model:workflow_run_event_not_push",
            "reject:trusted_trigger_model:upstream_ci1_not_success",
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
            "prereq_missing:concurrency_guard:missing_kb_write_group",
            "prereq_missing:concurrency_guard:cancel_in_progress_mismatch",
            "reject:permissions_scope:out_of_allowlist_write:",
            "reason_code=lock_unavailable",
            "exit 1",
        )
        for expected in required_controls:
            self.assertIn(expected, self.workflow_text)

    def test_pr_updates_are_gated_by_preflight_and_required_checks(self) -> None:
        self.assertIn("needs: preflight", self.workflow_text)
        self.assertIn("if: steps.write-path.outputs.has_changes == 'true'", self.workflow_text)
        self.assertIn(
            "persist_query returned disallowed status",
            self.workflow_text,
        )
        self.assertNotIn("gh pr merge", self.workflow_text)

    def test_embedded_python_snippets_compile(self) -> None:
        snippets: list[str] = []
        current_snippet_lines: list[str] = []
        collecting = False

        for workflow_line in self.workflow_text.splitlines():
            if not collecting and "<<'PY'" in workflow_line:
                collecting = True
                current_snippet_lines = []
                continue
            if not collecting:
                continue
            if workflow_line.strip() == "PY":
                snippet = textwrap.dedent("\n".join(current_snippet_lines)).strip()
                snippets.append(snippet)
                collecting = False
                current_snippet_lines = []
                continue
            current_snippet_lines.append(workflow_line)

        self.assertFalse(
            collecting,
            "Unterminated embedded python heredoc block found in CI-3 workflow",
        )
        self.assertGreaterEqual(
            len(snippets),
            2,
            "Expected at least two embedded python snippets in CI-3 workflow",
        )
        for index, snippet in enumerate(snippets, start=1):
            with self.subTest(snippet=index):
                self.assertNotEqual(snippet, "", "Embedded python snippet must not be empty")
                try:
                    compile(snippet, f"<ci3-workflow-python-{index}>", "exec")
                except SyntaxError as error:
                    self.fail(f"Embedded python snippet {index} is invalid: {error}")

    def test_extract_json_field_handles_piped_json_payloads(self) -> None:
        function_match = re.search(
            r"(?ms)^\s*extract_json_field\(\)\s*\{\n.*?^\s*\}",
            self.workflow_text,
        )
        self.assertIsNotNone(function_match, "CI-3 workflow missing extract_json_field helper")

        extract_function = textwrap.dedent(function_match.group(0))
        payload = '{"status":"written","reason_code":"lock_unavailable"}'
        script = "\n".join(
            [
                "set -euo pipefail",
                extract_function,
                f"printf '%s' '{payload}' | extract_json_field status",
                f"printf '%s' '{payload}' | extract_json_field reason_code",
            ]
        )
        result = subprocess.run(
            ["bash", "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"extract_json_field helper failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertEqual(
            result.stdout.splitlines(),
            ["written", "lock_unavailable"],
            "extract_json_field must read piped JSON and return requested fields",
        )

    def test_github_output_multiline_delimiters_are_unquoted(self) -> None:
        self.assertIn('echo "sources<<EOF"', self.workflow_text)
        self.assertIn('echo "changed_paths<<EOF"', self.workflow_text)
        self.assertNotIn('sources<<\'EOF\'', self.workflow_text)
        self.assertNotIn('changed_paths<<\'EOF\'', self.workflow_text)


if __name__ == "__main__":
    unittest.main()
