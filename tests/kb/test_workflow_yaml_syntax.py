"""Parser-level syntax checks for GitHub workflow YAML files.

Also covers composite action manifests under ``.github/actions/<name>/action.yml``,
which carry the same YAML parse risk as workflow files. See
audit-knowledgebase-workspace report 2026-06-27 for the gap that
motivated extending the lint surface.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


WORKFLOWS_DIR = Path(".github/workflows")
ACTIONS_DIR = Path(".github/actions")

# Matches a bare GitHub Actions expression referencing `secrets.*` or
# `steps.*` inside a value the composite-action runner treats as prose
# (currently only `description:` fields — `value:`/`if:`/`with:`/`env:`
# fields legitimately use these expressions and must not be flagged).
# See issue #571: the runner's composite-action template validator has
# intermittently mis-parsed such tokens inside description strings as live
# expressions, throwing "Unrecognized named-value: 'secrets'"/"'steps'" and
# failing to load the action.
_EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*(secrets|steps)\.")


def _all_workflow_and_action_files() -> list[str]:
    files: list[Path] = list(WORKFLOWS_DIR.glob("*.yml"))
    if ACTIONS_DIR.is_dir():
        files.extend(ACTIONS_DIR.glob("**/action.yml"))
    return sorted(str(p) for p in files)


@pytest.mark.skipif(
    not shutil.which("ruby"), reason="Ruby is required for YAML syntax validation"
)
def test_all_workflows_are_parseable_yaml() -> None:
    assert WORKFLOWS_DIR.exists(), f"Missing workflows directory: {WORKFLOWS_DIR}"
    workflow_files = _all_workflow_and_action_files()
    assert len(workflow_files) > 0, (
        "Expected at least one workflow or action.yml file"
    )

    ruby_program = """
require "psych"
ARGV.each do |workflow_path|
  Psych.parse_file(workflow_path)
end
"""
    result = subprocess.run(
        ["ruby", "-e", ruby_program, *workflow_files],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Workflow/action YAML parse failed.\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def _collect_description_strings(node: object, path: str = "") -> list[tuple[str, str]]:
    """Recursively collect (path, text) pairs for every ``description`` value."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key == "description" and isinstance(value, str):
                found.append((child_path, value))
            else:
                found.extend(_collect_description_strings(value, child_path))
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            found.extend(_collect_description_strings(item, f"{path}[{idx}]"))
    return found


def test_action_descriptions_do_not_contain_bare_expressions() -> None:
    """Composite action ``description:`` fields must not contain bare
    ``${{ secrets.* }}`` / ``${{ steps.* }}`` expression syntax.

    Regression test for issue #571: the GitHub Actions runner's
    composite-action template validator has intermittently mis-parsed such
    tokens inside description prose as live expressions (which composite
    actions cannot reference directly), throwing
    "Unrecognized named-value: 'secrets'"/"'steps'" and failing to load the
    action entirely. Description fields are documentation for callers and
    must express any illustrative syntax without triggering the runner's
    template parser (e.g. by describing it in prose rather than embedding
    the literal ``${{ }}`` token).
    """
    if not ACTIONS_DIR.is_dir():
        pytest.skip("No .github/actions directory present")

    action_files = sorted(ACTIONS_DIR.glob("**/action.yml"))
    assert len(action_files) > 0, "Expected at least one composite action.yml"

    violations: list[str] = []
    for action_file in action_files:
        data = yaml.safe_load(action_file.read_text(encoding="utf-8"))
        for field_path, text in _collect_description_strings(data):
            if _EXPRESSION_PATTERN.search(text):
                violations.append(f"{action_file}:{field_path} -> {text!r}")

    assert not violations, (
        "Found bare ${{ secrets.* }} / ${{ steps.* }} expressions inside "
        "action.yml description: fields (issue #571). Rewrite the "
        "illustrative syntax as prose so the composite-action template "
        "validator cannot mis-parse it as a live expression:\n"
        + "\n".join(violations)
    )
