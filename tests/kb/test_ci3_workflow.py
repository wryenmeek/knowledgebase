"""Workflow contract checks for CI-3 PR-producing write path."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
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


def _find_top_level_block_start(lines: list[str], key: str) -> int:
    target = f"{key}:"
    block_indices = [
        index
        for index, line in enumerate(lines)
        if line.strip() == target and not line.startswith(" ")
    ]

    if not block_indices:
        raise AssertionError(f"Top-level '{key}' block is missing from {WORKFLOW_PATH}")
    if len(block_indices) > 1:
        raise AssertionError(
            f"Top-level '{key}' block is duplicated in {WORKFLOW_PATH}; found {len(block_indices)} copies"
        )

    return block_indices[0]


def _find_child_block_start(
    lines: list[str],
    *,
    parent_start: int,
    parent_indent: int,
    key: str,
    context: str,
) -> int:
    target = f"{key}:"
    child_indent = parent_indent + 2
    block_indices: list[int] = []

    for index in range(parent_start + 1, len(lines)):
        candidate = lines[index]
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue

        candidate_indent = len(candidate) - len(candidate.lstrip(" "))
        if candidate_indent <= parent_indent:
            break
        if candidate_indent != child_indent:
            continue
        if stripped == target:
            block_indices.append(index)

    if not block_indices:
        raise AssertionError(f"{context} is missing '{key}' block in {WORKFLOW_PATH}")
    if len(block_indices) > 1:
        raise AssertionError(
            f"{context} has duplicated '{key}' blocks in {WORKFLOW_PATH}; found {len(block_indices)} copies"
        )

    return block_indices[0]


def _parse_workflow_dispatch_input_mapping_block(text: str, input_name: str) -> dict[str, str]:
    lines = text.splitlines()
    on_block_index = _find_top_level_block_start(lines, "on")
    workflow_dispatch_index = _find_child_block_start(
        lines,
        parent_start=on_block_index,
        parent_indent=0,
        key="workflow_dispatch",
        context="top-level 'on' block",
    )
    inputs_index = _find_child_block_start(
        lines,
        parent_start=workflow_dispatch_index,
        parent_indent=2,
        key="inputs",
        context="'workflow_dispatch' block",
    )
    input_index = _find_child_block_start(
        lines,
        parent_start=inputs_index,
        parent_indent=4,
        key=input_name,
        context="'workflow_dispatch.inputs' block",
    )

    return _parse_mapping_block(
        lines,
        input_index,
        indent=8,
        context=f"workflow_dispatch input '{input_name}' block",
    )


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


def _leading_spaces(value: str) -> int:
    return len(value) - len(value.lstrip(" "))


def _extract_step_run_script(workflow_text: str, *, step_name: str) -> str:
    lines = workflow_text.splitlines()
    step_start = next(
        (index for index, line in enumerate(lines) if line.strip() == f"- name: {step_name}"),
        None,
    )
    if step_start is None:
        raise AssertionError(f"Unable to locate CI-3 step: {step_name}")
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
        raise AssertionError(f"Unable to locate run block for CI-3 step: {step_name}")
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
        raise AssertionError(f"CI-3 run block is empty for step: {step_name}")

    script_indent = min(_leading_spaces(line) for line in non_empty_lines)
    script_lines = [line[script_indent:] if line.strip() else "" for line in raw_script_lines]
    return "\n".join(script_lines)


def _extract_ci3_preflight_script(workflow_text: str) -> str:
    return _extract_step_run_script(
        workflow_text,
        step_name="Assert CI-3 preflight prerequisites",
    )


def _extract_ci3_source_resolution_script(workflow_text: str) -> str:
    return _extract_step_run_script(
        workflow_text,
        step_name="Resolve CI-3 source inputs",
    )


def _extract_ci3_write_path_script(workflow_text: str) -> str:
    return _extract_step_run_script(
        workflow_text,
        step_name="Run CI-3 required checks and write path",
    )


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

            while IFS= read -r line || [[ -n "${line}" ]]; do
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


def _run_ci3_preflight_script(
    workflow_text: str,
    *,
    dispatch_changed_paths: tuple[str, ...],
    manual_approved: str = "true",
    event_name: str = "workflow_dispatch",
    dispatch_sha: str = "1111111111111111111111111111111111111111",
    dispatch_merge_base: str = "0000000000000000000000000000000000000000",
    dispatch_merge_base_exit: int = 0,
    dispatch_diff_exit: int = 0,
    workflow_run_name: str = "",
    workflow_run_event: str = "",
    workflow_run_conclusion: str = "",
) -> subprocess.CompletedProcess[str]:
    script = _with_mapfile_compat(_extract_ci3_preflight_script(workflow_text))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        workflow_file = temp_root / ".github/workflows/ci-3-pr-producer.yml"
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(workflow_text, encoding="utf-8")

        scripts_dir = temp_root / "scripts/kb"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for script_name in ("ingest.py", "update_index.py", "lint_wiki.py", "persist_query.py"):
            (scripts_dir / script_name).write_text("# stub\n", encoding="utf-8")

        fake_bin = temp_root / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)

        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"merge-base\" ]]; then\n"
            "  if [[ \"${MOCK_DISPATCH_MERGE_BASE_EXIT:-0}\" != \"0\" ]]; then\n"
            "    exit \"${MOCK_DISPATCH_MERGE_BASE_EXIT}\"\n"
            "  fi\n"
            "  printf '%s\\n' \"${MOCK_DISPATCH_MERGE_BASE:-}\"\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"diff\" ]]; then\n"
            "  if [[ \"${MOCK_DISPATCH_DIFF_EXIT:-0}\" != \"0\" ]]; then\n"
            "    exit \"${MOCK_DISPATCH_DIFF_EXIT}\"\n"
            "  fi\n"
            "  if [[ -n \"${MOCK_DISPATCH_CHANGED_PATHS:-}\" ]]; then\n"
            "    while IFS= read -r changed_path; do\n"
            "      [[ -z \"${changed_path}\" ]] && continue\n"
            "      printf '%s\\0' \"${changed_path}\"\n"
            "    done <<< \"${MOCK_DISPATCH_CHANGED_PATHS}\"\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

        fake_gh = fake_bin / "gh"
        fake_gh.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

        github_output_path = temp_root / "github-output.txt"
        github_output_path.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "CI_ID": "CI-3",
                "TOKEN_PROFILE": "tp-pr-producer",
                "WRITE_ALLOWLIST": "wiki/**,wiki/index.md,wiki/log.md,raw/processed/**,raw/rejected/**",
                "FALLBACK_MANUAL_INSTRUCTIONS": "manual fallback",
                "EVENT_NAME": event_name,
                "MANUAL_APPROVED": manual_approved,
                "DISPATCH_SHA": dispatch_sha,
                "DEFAULT_BRANCH": "main",
                "WORKFLOW_RUN_NAME": workflow_run_name,
                "WORKFLOW_RUN_EVENT": workflow_run_event,
                "WORKFLOW_RUN_CONCLUSION": workflow_run_conclusion,
                "WORKFLOW_FILE": ".github/workflows/ci-3-pr-producer.yml",
                "GITHUB_OUTPUT": str(github_output_path),
                "MOCK_DISPATCH_CHANGED_PATHS": "\n".join(dispatch_changed_paths),
                "MOCK_DISPATCH_MERGE_BASE": dispatch_merge_base,
                "MOCK_DISPATCH_MERGE_BASE_EXIT": str(dispatch_merge_base_exit),
                "MOCK_DISPATCH_DIFF_EXIT": str(dispatch_diff_exit),
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


def _run_ci3_source_resolution_script(
    workflow_text: str,
    *,
    manual_source_path: str = "",
    inbox_files: tuple[str, ...] = ("raw/inbox/example-source.md",),
    extra_files: tuple[str, ...] = (),
    symlinks: tuple[tuple[str, str], ...] = (),
) -> subprocess.CompletedProcess[str]:
    script = _with_mapfile_compat(_extract_ci3_source_resolution_script(workflow_text))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for rel_path in inbox_files + extra_files:
            target = temp_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("stub\n", encoding="utf-8")

        for link_path, link_target in symlinks:
            link = temp_root / link_path
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(link_target)

        github_output_path = temp_root / "github-output.txt"
        github_output_path.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "MANUAL_SOURCE_PATH": manual_source_path,
                "GITHUB_OUTPUT": str(github_output_path),
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


def _run_ci3_write_path_script(
    workflow_text: str,
    *,
    tracked_changed_path: str = "wiki/index.md",
) -> tuple[subprocess.CompletedProcess[str], str, dict[str, object]]:
    script = _with_mapfile_compat(_extract_ci3_write_path_script(workflow_text))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        (temp_root / "raw/inbox").mkdir(parents=True, exist_ok=True)
        (temp_root / "raw/inbox/.ci3-ingest-manifest").write_text(
            "raw/inbox/example-source.md\n",
            encoding="utf-8",
        )
        (temp_root / "wiki/sources").mkdir(parents=True, exist_ok=True)
        (temp_root / "wiki/sources/example.md").write_text("# Source: Example\n", encoding="utf-8")

        fake_bin = temp_root / "bin"
        fake_bin.mkdir(parents=True, exist_ok=True)

        real_python = subprocess.run(
            ["python3", "-c", "import sys; print(sys.executable)"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ \"${1:-}\" == \"-m\" && \"${2:-}\" == \"scripts.kb.ingest\" ]]; then\n"
            "  cat <<'JSON'\n"
            '{"status":"ok","per_source":[{"status":"written","source_page":"wiki/sources/example.md"}]}\n'
            "JSON\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \".github/skills/extract-entities-and-claims/logic/extract_entities.py\" ]]; then\n"
            "  output_path=\"\"\n"
            "  while [[ \"$#\" -gt 0 ]]; do\n"
            "    if [[ \"$1\" == \"--output\" ]]; then\n"
            "      output_path=\"$2\"\n"
            "      shift 2\n"
            "      continue\n"
            "    fi\n"
            "    shift\n"
            "  done\n"
            "  if [[ -n \"${output_path}\" ]]; then\n"
            "    cat <<'JSON' > \"${output_path}\"\n"
            '{"entities":[],"concepts":[],"claims":[]}\n'
            "JSON\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \".github/skills/synthesize-entity-page/logic/synthesize_combined.py\" ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"-c\" && \"${2:-}\" == *\"from scripts.kb import update_index\"* ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"scripts/kb/lint_wiki.py\" ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"-m\" && \"${2:-}\" == \"scripts.kb.persist_query\" ]]; then\n"
            "  cat <<'JSON'\n"
            '{"status":"no_write_policy","reason_code":"policy_enforced"}\n'
            "JSON\n"
            "  exit 0\n"
            "fi\n"
            "exec \"${REAL_PYTHON}\" \"$@\"\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)

        fake_git = fake_bin / "git"
        fake_git.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "while [[ \"${1:-}\" == \"-c\" ]]; do\n"
            "  shift 2\n"
            "done\n"
            "if [[ \"${1:-}\" == \"diff\" ]]; then\n"
            "  printf 'M\\t%s\\0' \"${MOCK_TRACKED_CHANGED_PATH:-wiki/index.md}\"\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"ls-files\" ]]; then\n"
            "  exit 0\n"
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_git.chmod(0o755)

        github_output_path = temp_root / "github-output.txt"
        github_output_path.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "GITHUB_OUTPUT": str(github_output_path),
                "SYNTHESIS_GITHUB_TOKEN": "stub-token",
                "WRITE_ALLOWLIST": "wiki/**,wiki/index.md,wiki/log.md,raw/processed/**,raw/rejected/**",
                "REAL_PYTHON": real_python,
                "MOCK_TRACKED_CHANGED_PATH": tracked_changed_path,
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            }
        )

        result = subprocess.run(
            ["bash", "-c", script],
            cwd=temp_root,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        runtime_metrics_path = temp_root / "ci3-metrics/runtime-metrics.json"
        runtime_metrics = (
            json.loads(runtime_metrics_path.read_text(encoding="utf-8"))
            if runtime_metrics_path.exists()
            else {}
        )
        return result, github_output_path.read_text(encoding="utf-8"), runtime_metrics


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
        self.assertEqual(
            _parse_workflow_dispatch_input_mapping_block(
                self.workflow_text,
                "maintainer_approved",
            )["description"],
            (
                "Manual attestation flag for write-capable CI-3 dispatch; "
                "protected-environment reviewers enforce authoritative approval."
            ),
        )
        self.assertIn("source_path:", self.workflow_text)
        self.assertIn("manual-approval:", self.workflow_text)
        self.assertIn("name: ci3-manual-approval", self.workflow_text)
        self.assertIn(".github/skills/extract-entities-and-claims/**", self.workflow_text)

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
            _parse_job_mapping_block(self.workflow_text, "synthesis-curator", "permissions"),
            {
                "actions": "read",
                "checks": "read",
                "contents": "read",
                "models": "read",
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
            "WRITE_ALLOWLIST: wiki/**,wiki/index.md,wiki/log.md,raw/processed/**,raw/rejected/**",
            "DISPATCH_SHA: ${{ github.sha }}",
            "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}",
            "fetch-depth: 0",
            "persist-credentials: false",
            "Set up Node.js",
            "uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444",
            "Install pinned qmd runtime",
            'QMD_NPM_PACKAGE="@tobilu/qmd"',
            'QMD_VERSION="2.5.1"',
            'QMD_EXPECTED_INTEGRITY="sha512-Ep9ccOj1bNRinfTIszp5UZP8xfi5AJNtmzwWDD4ZVm2YdWVS+rFobWJQovj0HD2uIAFrryvbSpZYeGa3flEO7g=="',
            'npm view "${QMD_NPM_PACKAGE}@${QMD_VERSION}" dist.integrity --registry=https://registry.npmjs.org',
            'if [ "${QMD_DIST_INTEGRITY}" != "${QMD_EXPECTED_INTEGRITY}" ]; then',
            "::error::qmd dist.integrity mismatch",
            'npm install --global "${QMD_NPM_PACKAGE}@${QMD_VERSION}" --registry=https://registry.npmjs.org',
            "qmd init",
            "cp .qmd/index.sqlite .qmd/index/index.sqlite",
            "cp .qmd/index.yml .qmd/index/index.yml",
            "python3 scripts/kb/qmd_preflight.py --repo-root .",
            "Run framework governance wrapper",
            "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "reject:trusted_trigger_model:manual_approval_required",
            "prereq_missing:ghaw_readiness:missing_dispatch_sha",
            "prereq_missing:ghaw_readiness:dispatch_merge_base_unavailable",
            "prereq_missing:ghaw_readiness:dispatch_changed_paths_unavailable",
            "reject:trusted_trigger_model:unexpected_handoff_workflow",
            "reject:trusted_trigger_model:workflow_run_event_not_push",
            "reject:trusted_trigger_model:upstream_ci1_not_success",
            "reject:path_filter:no_changed_paths_detected",
            "reject:path_filter:sensitive_control_plane_path:",
            "reject:trusted_trigger_model:manual_dispatch_sensitive_paths_present",
            'dispatch_merge_base="$(git merge-base "origin/${DEFAULT_BRANCH}" "${DISPATCH_SHA}" 2>/dev/null)"',
            'git diff --name-only -z "${dispatch_merge_base}" "${DISPATCH_SHA}" > "${dispatch_diff_file}" 2>/dev/null',
            "while IFS= read -r -d '' changed_path || [[ -n \"${changed_path:-}\" ]]; do",
            ".github/workflows/*|.github/skills/*|.github/agents/*|.github/extensions/*|scripts/*|schema/*|AGENTS.md|pyproject.toml)",
            "reject:permissions_scope:minimum_permissions_mismatch",
            "reject:permissions_scope:permissions_block_missing:top_level",
            "reject:permissions_scope:permissions_block_duplicated:top_level",
            "reject:permissions_scope:{scope}_job_missing",
            "reject:permissions_scope:{scope}_job_duplicated",
            "reject:permissions_scope:permissions_block_missing:{scope}",
            "reject:permissions_scope:permissions_block_duplicated:{scope}",
            "reject:permissions_scope:permissions_key_duplicated:{scope}:{duplicate_key}",
            "reject:permissions_scope:permissions_key_missing:{scope}:{missing_key}",
            "reject:permissions_scope:permissions_key_unexpected:{scope}:{unexpected_key}",
            "reject:permissions_scope:permissions_value_mismatch:",
            'scope="top_level"',
            'scope="synthesis_curator"',
            'scope="pr_producer"',
            "prereq_missing:concurrency_guard:missing_kb_write_group",
            "prereq_missing:concurrency_guard:cancel_in_progress_mismatch",
            "reject:permissions_scope:out_of_allowlist_write:",
            "manual workflow_dispatch cannot run when commit includes sensitive control-plane paths",
            "split sensitive control-plane changes from manual CI-3 dispatch commits",
            "Download CI-3 extraction bundles",
            "ci3-extraction-bundles-${{ github.run_id }}",
            "ci3-synthesis/extraction-bundles.tsv",
            "git -c core.quotepath=false diff --name-status -z --no-renames -- .",
            "git -c core.quotepath=false ls-files --others --exclude-standard -z -- .",
            "reason_code=lock_unavailable",
            "gh auth setup-git",
            'if [[ "${changed_path}" == ci3-metrics/* ]]; then',
            "No allowlisted repository changes detected after CI-3 write path.",
            "exit 1",
            'repo_root="$(realpath .)"',
            'inbox_root="$(realpath raw/inbox)"',
            'if [[ -L "${MANUAL_SOURCE_PATH}" ]]; then',
            "reject:path_filter:manual_source_symlink:",
            'manual_resolved="$(realpath "${MANUAL_SOURCE_PATH}")"',
            'manual_relative="${manual_resolved#"${repo_root}/"}"',
            'source_resolved="$(realpath "${source_path}")"',
        )
        for expected in required_controls:
            self.assertIn(expected, self.workflow_text)
        self.assertNotIn(".ci-bin", self.workflow_text)
        self.assertNotIn("cat > .ci-bin/qmd", self.workflow_text)

    def test_preflight_checkout_step_uses_fetch_depth_zero(self) -> None:
        self.assertRegex(
            self.workflow_text,
            r"(?ms)- name: Checkout workflow context\s+uses: actions/checkout@[^\n]+\n\s+with:\n\s+fetch-depth:\s*0\b",
        )

    def test_preflight_behavior_rejects_manual_dispatch_sensitive_control_plane_paths(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=("scripts/kb/ingest.py",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:sensitive_control_plane_path:scripts/kb/ingest.py",
            combined_output,
        )
        self.assertIn(
            "reject:trusted_trigger_model:manual_dispatch_sensitive_paths_present",
            combined_output,
        )

    def test_preflight_behavior_rejects_manual_dispatch_github_skills_paths(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=(".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:sensitive_control_plane_path:.github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            combined_output,
        )
        self.assertIn(
            "reject:trusted_trigger_model:manual_dispatch_sensitive_paths_present",
            combined_output,
        )

    def test_preflight_behavior_rejects_when_dispatch_paths_unavailable(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=(),
            manual_approved="true",
            dispatch_diff_exit=1,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "prereq_missing:ghaw_readiness:dispatch_changed_paths_unavailable",
            combined_output,
        )

    def test_preflight_behavior_rejects_when_dispatch_merge_base_unavailable(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            manual_approved="true",
            dispatch_merge_base_exit=1,
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "prereq_missing:ghaw_readiness:dispatch_merge_base_unavailable",
            combined_output,
        )

    def test_preflight_behavior_rejects_when_dispatch_merge_base_is_empty(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            dispatch_merge_base="",
            dispatch_merge_base_exit=0,
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "prereq_missing:ghaw_readiness:dispatch_merge_base_unavailable",
            combined_output,
        )

    def test_preflight_behavior_rejects_when_dispatch_sha_missing(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_sha="",
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "prereq_missing:ghaw_readiness:missing_dispatch_sha",
            combined_output,
        )

    def test_preflight_behavior_rejects_when_no_changed_paths_detected(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=(),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn("reject:path_filter:no_changed_paths_detected", combined_output)

    def test_preflight_behavior_accepts_manual_dispatch_source_only_commit(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("CI-3 preflight PASS", combined_output)

    def test_preflight_behavior_accepts_push_extract_entities_skill_change(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            event_name="push",
            dispatch_changed_paths=(
                ".github/skills/extract-entities-and-claims/logic/extract_entities.py",
            ),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("CI-3 preflight PASS", combined_output)

    def test_preflight_behavior_rejects_push_non_allowlisted_skill_change(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            event_name="push",
            dispatch_changed_paths=(".github/skills/some-unrelated-skill/logic/x.py",),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:disallowed_push_path:.github/skills/some-unrelated-skill/logic/x.py",
            combined_output,
        )

    def test_preflight_behavior_rejects_missing_synthesis_curator_job(self) -> None:
        mutated_workflow = self.workflow_text.replace(
            "  synthesis-curator:\n",
            "  synthesis-curator-disabled:\n",
            1,
        )
        result = _run_ci3_preflight_script(
            mutated_workflow,
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:permissions_scope:synthesis_curator_job_missing",
            combined_output,
        )

    def test_preflight_behavior_rejects_pr_producer_models_scope_drift(self) -> None:
        mutated_workflow = self.workflow_text.replace(
            "      pull-requests: write\n",
            "      models: read\n      pull-requests: write\n",
            1,
        )
        result = _run_ci3_preflight_script(
            mutated_workflow,
            dispatch_changed_paths=("raw/inbox/example-source.md",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:permissions_scope:permissions_key_unexpected:pr_producer:models",
            combined_output,
        )

    def test_preflight_behavior_rejects_sensitive_paths_with_spaces(self) -> None:
        result = _run_ci3_preflight_script(
            self.workflow_text,
            dispatch_changed_paths=("scripts/kb/path with spaces.py",),
            manual_approved="true",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:sensitive_control_plane_path:scripts/kb/path with spaces.py",
            combined_output,
        )

    def test_source_resolution_rejects_manual_source_symlink(self) -> None:
        result = _run_ci3_source_resolution_script(
            self.workflow_text,
            manual_source_path="raw/inbox/manual-link.md",
            inbox_files=("raw/inbox/example-source.md",),
            extra_files=("raw/processed/outside.md",),
            symlinks=(("raw/inbox/manual-link.md", "../processed/outside.md"),),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:manual_source_symlink:raw/inbox/manual-link.md",
            combined_output,
        )

    def test_source_resolution_rejects_manual_source_path_traversal(self) -> None:
        result = _run_ci3_source_resolution_script(
            self.workflow_text,
            manual_source_path="raw/inbox/../../raw/processed/outside.md",
            inbox_files=("raw/inbox/example-source.md",),
            extra_files=("raw/processed/outside.md",),
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0, combined_output)
        self.assertIn(
            "reject:path_filter:outside_raw_inbox:raw/inbox/../../raw/processed/outside.md",
            combined_output,
        )

    def test_write_path_behavior_emits_runtime_metrics_and_allowlisted_changed_paths(self) -> None:
        result, github_output, runtime_metrics = _run_ci3_write_path_script(self.workflow_text)
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("has_changes=true", github_output)
        self.assertIn("wiki/index.md", github_output)
        self.assertEqual(runtime_metrics.get("workflow_id"), "ci-3-pr-producer")
        stage_durations = runtime_metrics.get("stage_durations_seconds")
        self.assertIsInstance(stage_durations, dict)
        self.assertIn("ingest_write_path", stage_durations)
        self.assertIn("persist_query_gate", stage_durations)

    def test_write_path_behavior_handles_allowlisted_paths_with_spaces(self) -> None:
        result, github_output, _runtime_metrics = _run_ci3_write_path_script(
            self.workflow_text,
            tracked_changed_path="wiki/pages/page with spaces.md",
        )
        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertEqual(result.returncode, 0, combined_output)
        self.assertIn("has_changes=true", github_output)
        self.assertIn("wiki/pages/page with spaces.md", github_output)

    def test_pr_updates_are_gated_by_preflight_and_required_checks(self) -> None:
        self.assertIn("needs:", self.workflow_text)
        self.assertIn("- preflight", self.workflow_text)
        self.assertIn("- manual-approval", self.workflow_text)
        self.assertIn("- synthesis-curator", self.workflow_text)
        self.assertIn(
            "needs.manual-approval.result == 'success'",
            self.workflow_text,
        )
        self.assertIn(
            "needs.synthesis-curator.result == 'success'",
            self.workflow_text,
        )
        self.assertIn("if: steps.write-path.outputs.has_changes == 'true'", self.workflow_text)
        self.assertIn(
            "persist_query returned disallowed status",
            self.workflow_text,
        )
        self.assertIn(
            "find raw/inbox -type f ! -name '.gitkeep' ! -name '.ci3-ingest-manifest' | sort",
            self.workflow_text,
        )
        self.assertIn("python3 -m scripts.kb.ingest", self.workflow_text)
        self.assertIn("python3 -m scripts.kb.persist_query", self.workflow_text)
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
            1,
            "Expected at least one embedded python snippet in CI-3 workflow",
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
        # sources list is now passed via workspace file (.ci3-ingest-manifest), not GITHUB_OUTPUT
        # (#14, #15 — batch ingest + file-based handoff to avoid GITHUB_OUTPUT size limits).
        self.assertNotIn('echo "sources<<EOF"', self.workflow_text)
        # changed_paths uses a random delimiter (openssl rand -hex 16) to prevent premature
        # block termination if a path exactly equals the delimiter string (#SEC-P2-1).
        self.assertNotIn('echo "changed_paths<<EOF"', self.workflow_text)
        self.assertIn('openssl rand -hex 16', self.workflow_text)
        self.assertIn('changed_paths<<${_delim}', self.workflow_text)
        self.assertNotIn("changed_paths<<'EOF'", self.workflow_text)

    def test_source_list_uses_file_based_handoff(self) -> None:
        # #15: source list must be written to a workspace manifest file instead of
        # GITHUB_OUTPUT multiline output to avoid size limits for large inboxes.
        self.assertIn(".ci3-ingest-manifest", self.workflow_text)
        self.assertIn("--sources-manifest raw/inbox/.ci3-ingest-manifest", self.workflow_text)
        # The SOURCE_LIST env var (piped via GITHUB_OUTPUT) must no longer be used.
        self.assertNotIn("SOURCE_LIST", self.workflow_text)

    def test_ingest_runs_in_batch_mode(self) -> None:
        # #14: single batch ingest invocation via --sources-manifest instead of
        # per-source loop to avoid repeated process startup and index rebuild costs.
        self.assertIn("--sources-manifest raw/inbox/.ci3-ingest-manifest", self.workflow_text)
        # Per-source --source flag should no longer appear in the ingest invocation.
        self.assertNotIn("--source \"${source_path}\"", self.workflow_text)
        # Manifest is cleaned up after use.
        self.assertIn("rm -f raw/inbox/.ci3-ingest-manifest", self.workflow_text)

    def test_synthesis_token_env_var_is_wired(self) -> None:
        self.assertIn("SYNTHESIS_GITHUB_TOKEN", self.workflow_text)
        # Token must come from secrets, not as a CLI argument
        self.assertNotIn("--github-token", self.workflow_text)

    def test_write_path_uses_artifact_handoff_not_model_calls(self) -> None:
        write_path_script = _extract_ci3_write_path_script(self.workflow_text)
        self.assertIn("ci3-synthesis/extraction-bundles.tsv", write_path_script)
        self.assertNotIn("extract_entities.py", write_path_script)
        self.assertIn("synthesize_combined.py", write_path_script)

    def test_base_branch_validated_before_gh_cli_use(self) -> None:
        # SEC-P2-2: base_branch must be validated as a safe format before being passed
        # to gh CLI to prevent flag injection via a maliciously-renamed default branch.
        self.assertIn(
            '[[ ! "${base_branch}" =~ ^[A-Za-z0-9._/-]+$ ]]',
            self.workflow_text,
        )
        self.assertIn("Unexpected default_branch format", self.workflow_text)

    def test_synthesis_stage_precedes_update_index(self) -> None:
        synthesis_marker = "Synthesis Curator stage"
        update_index_marker = "update_index --write"
        self.assertIn(synthesis_marker, self.workflow_text)
        self.assertIn(update_index_marker, self.workflow_text)
        self.assertLess(
            self.workflow_text.index(synthesis_marker),
            self.workflow_text.index(update_index_marker),
            "Synthesis Curator stage must appear before update_index in the workflow",
        )


if __name__ == "__main__":
    unittest.main()
