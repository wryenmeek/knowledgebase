"""Workflow contract checks for CI-1 gatekeeper trusted handoff."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW_PATH = Path(".github/workflows/ci-1-gatekeeper.yml")


def _leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


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


def _extract_ci1_preflight_script(workflow_text: str) -> str:
    lines = workflow_text.splitlines()
    step_start = next(
        (index for index, line in enumerate(lines) if line.strip() == "- name: Run CI-1 trusted-trigger preflight checks"),
        None,
    )
    if step_start is None:
        raise AssertionError("Unable to locate CI-1 trusted-trigger preflight step")
    step_indent = _leading_spaces(lines[step_start])

    run_index = next(
        (
            index
            for index in range(step_start + 1, len(lines))
            if lines[index].strip() == "run: |" and _leading_spaces(lines[index]) > step_indent
        ),
        None,
    )
    if run_index is None:
        raise AssertionError("Unable to locate run block for CI-1 trusted-trigger preflight step")
    run_indent = _leading_spaces(lines[run_index])

    raw_script_lines: list[str] = []
    for line in lines[run_index + 1 :]:
        if line.strip() and _leading_spaces(line) <= run_indent:
            break
        if line.strip() == "":
            raw_script_lines.append("")
            continue
        raw_script_lines.append(line)

    non_empty_lines = [line for line in raw_script_lines if line.strip()]
    if not non_empty_lines:
        raise AssertionError("CI-1 trusted-trigger preflight run block is empty")

    script_indent = min(_leading_spaces(line) for line in non_empty_lines)
    script_lines = [line[script_indent:] if line.strip() else "" for line in raw_script_lines]
    return "\n".join(script_lines)


def _with_mapfile_compat(script: str) -> str:
    mapfile_compat = textwrap.dedent(
        """\
        if ! command -v mapfile >/dev/null 2>&1; then
          mapfile() {
            local trim_newline="false"
            if [[ "${1:-}" == "-t" ]]; then
              trim_newline="true"
              shift
            fi

            local target_array="${1:-MAPFILE}"
            if [[ ! "${target_array}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
              echo "mapfile compatibility shim received invalid array name: ${target_array}" >&2
              return 2
            fi

            local index=0
            local line
            eval "${target_array}=()"

            while IFS= read -r line; do
              if [[ "${trim_newline}" != "true" ]]; then
                line="${line}"$'\\n'
              fi
              local quoted_line
              printf -v quoted_line '%q' "${line}"
              eval "${target_array}[${index}]=${quoted_line}"
              index=$((index + 1))
            done
          }
        fi
        """
    ).strip()
    return f"{mapfile_compat}\n{script}"


def _run_ci1_preflight_script(
    workflow_text: str,
    *,
    changed_paths: tuple[str, ...],
    event_name: str = "push",
    ref_name: str = "main",
    default_branch: str = "main",
    ref_protected: str = "true",
) -> subprocess.CompletedProcess[str]:
    script = _extract_ci1_preflight_script(workflow_text).replace(
        '"${changed_paths[@]}"',
        '${changed_paths[@]+"${changed_paths[@]}"}',
    )
    script = _with_mapfile_compat(script)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        workflow_file = temp_root / ".github/workflows/ci-1-gatekeeper.yml"
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(workflow_text, encoding="utf-8")

        scripts_dir = temp_root / "scripts/kb"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for script_name in ("ingest.py", "update_index.py", "lint_wiki.py"):
            (scripts_dir / script_name).write_text("# stub\n", encoding="utf-8")

        fake_bin = temp_root / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ -n \"${MOCK_CHANGED_PATHS:-}\" ]]; then\n"
            "  printf '%s\\n' \"${MOCK_CHANGED_PATHS}\"\n"
            "fi\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

        env = os.environ.copy()
        env.update(
            {
                "CI_ID": "CI-1",
                "TOKEN_PROFILE": "tp-gatekeeper",
                "REQUIRED_EVENT": "push",
                "REQUIRED_PATH_PREFIX": "raw/inbox/",
                "FALLBACK_MANUAL_INSTRUCTIONS": "manual fallback",
                "EVENT_NAME": event_name,
                "REF_NAME": ref_name,
                "REF_PROTECTED": ref_protected,
                "DEFAULT_BRANCH": default_branch,
                "BEFORE_SHA": "1111111111111111111111111111111111111111",
                "CURRENT_SHA": "2222222222222222222222222222222222222222",
                "WORKFLOW_FILE": ".github/workflows/ci-1-gatekeeper.yml",
                "MOCK_CHANGED_PATHS": "\n".join(changed_paths),
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            }
        )

        return subprocess.run(
            ["bash", "-c", script],
            cwd=temp_root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )


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

    def test_preflight_behavior_accepts_default_branch_with_inbox_only_paths(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=("raw/inbox/SPEC.md", "raw/inbox/notes.md"),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("CI-1 gatekeeper preflight PASS", combined_output)

    def test_preflight_script_extraction_handles_alternate_indentation(self) -> None:
        workflow_text = textwrap.dedent(
            """\
            name: CI-1 Gatekeeper Trusted Handoff
            jobs:
              gatekeeper:
                runs-on: ubuntu-latest
                steps:
                    - name: Run CI-1 trusted-trigger preflight checks
                      run: |
                        set -euo pipefail
                        echo "ok"
                    - name: Next step
                      run: echo "done"
            """
        )
        script = _extract_ci1_preflight_script(workflow_text)
        self.assertEqual(
            script,
            textwrap.dedent(
                """\
                set -euo pipefail
                echo "ok"
                """
            ).strip(),
        )

    def test_preflight_behavior_rejects_non_push_events(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=("raw/inbox/SPEC.md",),
            event_name="workflow_dispatch",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:trusted_trigger_model:event_not_push", combined_output)

    def test_preflight_behavior_rejects_non_default_branch(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=("raw/inbox/SPEC.md",),
            ref_name="feature/not-main",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:trusted_trigger_model:not_default_branch", combined_output)

    def test_preflight_behavior_rejects_unprotected_refs(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=("raw/inbox/SPEC.md",),
            ref_protected="false",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:trusted_trigger_model:ref_not_protected", combined_output)
        self.assertIn(
            "action_required:trusted_trigger_model:enable_branch_protection",
            combined_output,
        )

    def test_preflight_behavior_rejects_outside_inbox_paths(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=("raw/inbox/SPEC.md", "README.md"),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:path_filter:outside_raw_inbox:README.md", combined_output)

    def test_preflight_behavior_rejects_missing_changed_paths(self) -> None:
        result = _run_ci1_preflight_script(
            self.workflow_text,
            changed_paths=(),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:path_filter:no_changed_paths_detected", combined_output)

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
