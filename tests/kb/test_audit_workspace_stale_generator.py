"""Tests for deterministic audit-workspace stale deletion candidates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from tests.kb import test_audit_workspace_finding_schema as _finding_schema
from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
STALE_GENERATOR_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "stale_generator.py"
)
SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "schema"
    / "finding.schema.json"
)


class AuditWorkspaceStaleGeneratorTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.module = load_module("audit_workspace_stale_generator", STALE_GENERATOR_PATH)
        self.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_instruction_mentions_missing_file_emits_stale_finding(self) -> None:
        instruction = "When debugging, read docs/missing-runbook.md before proceeding."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assert_schema_valid(finding)
        self.assertEqual(finding["proposed_destination"], "Delete")
        self.assertEqual(finding["compliance_risk"], "deterministic")
        self.assertIn("docs/missing-runbook.md", finding["deletion_candidate"])
        run.assert_called_once()

    def test_instruction_mentions_present_file_does_not_emit_finding(self) -> None:
        instruction = "When debugging, read docs/present-runbook.md before proceeding."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="docs/present-runbook.md\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(
            run.call_args.args[0],
            ["git", "ls-files", "--", "docs/present-runbook.md"],
        )

    def test_instruction_mentions_missing_non_markdown_file_emits_stale_finding(self) -> None:
        instruction = "Check requirements-pages.txt before adding page dependencies."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Build, test, and verify commands",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assert_schema_valid(finding)
        self.assertIn("requirements-pages.txt", finding["deletion_candidate"])

    def test_instruction_mentions_present_toml_file_does_not_emit_finding(self) -> None:
        instruction = "Respect pyproject.toml before changing Python packaging."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="pyproject.toml\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Build, test, and verify commands",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "--", "pyproject.toml"])

    def test_instruction_mentions_hidden_dotted_files_emits_stale_findings(self) -> None:
        instruction = "Seed .env.example, .secrets.baseline, and .gitkeep when bootstrapping."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Guardrails",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 3)
        deletion_candidates = {finding["deletion_candidate"] for finding in findings}
        self.assertIn("missing file reference: .env.example", deletion_candidates)
        self.assertIn("missing file reference: .secrets.baseline", deletion_candidates)
        self.assertIn("missing file reference: .gitkeep", deletion_candidates)

    def test_instruction_references_missing_symbol_emits_stale_finding(self) -> None:
        instruction = "Use symbol `missing_symbol` before changing the runtime."

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                self._completed(["rg"], stdout="", returncode=1),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assert_schema_valid(finding)
        self.assertIn("missing_symbol", finding["deletion_candidate"])
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["git", "ls-files", "--", "*.py"],
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    "--type",
                    "python",
                    "--",
                    "missing_symbol",
                    "scripts/kb/present.py",
                ],
            ],
        )

    def test_instruction_references_present_symbol_does_not_emit_finding(self) -> None:
        instruction = "Use function present_symbol before changing the runtime."
        self.write_file("scripts/kb/present.py", "def present_symbol():\n    return None\n")

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                self._completed(["rg"], stdout="scripts/kb/present.py\n"),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["git", "ls-files", "--", "*.py"],
                [
                    "rg",
                    "-l",
                    "--fixed-strings",
                    "--type",
                    "python",
                    "--",
                    "present_symbol",
                    "scripts/kb/present.py",
                ],
            ],
        )

    def test_instruction_references_lowercase_backticked_symbol_emits_stale_finding(self) -> None:
        instruction = "Use function `render` before changing the runtime."

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                self._completed(["rg"], stdout="", returncode=1),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        self.assert_schema_valid(findings[0])
        self.assertIn("render", findings[0]["deletion_candidate"])

    def test_comment_or_string_rg_hit_does_not_suppress_missing_symbol_finding(self) -> None:
        instruction = "Use function `missing_symbol` before changing the runtime."
        self.write_file(
            "scripts/kb/comment_only.py",
            "# missing_symbol appears only in a comment\nTEXT = 'missing_symbol'\n",
        )

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/comment_only.py\n"),
                self._completed(["rg"], stdout="scripts/kb/comment_only.py\n"),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        self.assert_schema_valid(findings[0])
        self.assertIn("missing_symbol", findings[0]["deletion_candidate"])

    def test_present_constant_symbol_does_not_emit_finding(self) -> None:
        instruction = "Reuse `CACHE_STRATEGY` when emitting stale findings."
        self.write_file("scripts/kb/constants.py", 'CACHE_STRATEGY = "mtime_first_para"\n')

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/constants.py\n"),
                self._completed(["rg"], stdout="scripts/kb/constants.py\n"),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())

    def test_present_import_alias_symbol_does_not_emit_finding(self) -> None:
        instruction = "Reuse symbol `json_lib` when parsing reports."
        self.write_file("scripts/kb/imports.py", "import json as json_lib\n")

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/imports.py\n"),
                self._completed(["rg"], stdout="scripts/kb/imports.py\n"),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())

    def test_missing_rg_binary_uses_tracked_file_fallback(self) -> None:
        instruction = "Use function present_symbol before changing the runtime."
        self.write_file("scripts/kb/present.py", "def present_symbol():\n    return None\n")

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                FileNotFoundError(),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())

    def test_missing_rg_binary_fallback_still_emits_missing_symbol_finding(self) -> None:
        instruction = "Use function missing_symbol before changing the runtime."
        self.write_file("scripts/kb/present.py", "def other_symbol():\n    return None\n")

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                FileNotFoundError(),
            )
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        self.assert_schema_valid(findings[0])
        self.assertIn("missing_symbol", findings[0]["deletion_candidate"])

    def test_backticked_tool_name_does_not_emit_symbol_finding(self) -> None:
        instruction = "Run `pytest` before merging."

        with patch.object(self.module.subprocess, "run") as run:
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Build, test, and verify commands",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        run.assert_not_called()

    def test_invalid_cache_strategy_fails_before_subprocess_probe(self) -> None:
        instruction = "Read docs/missing-runbook.md."

        with patch.object(self.module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "unsupported cache_strategy"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                    cache_strategy="mtime_first_paragraph",
                )

        run.assert_not_called()

    def test_hybrid_signature_cache_strategy_is_propagated_to_finding(self) -> None:
        instruction = "Read docs/missing-runbook.md."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
                cache_strategy="hybrid_signature",
            )

        self.assertEqual(len(findings), 1)
        self.assert_schema_valid(findings[0])
        self.assertEqual(findings[0]["cache_strategy"], "hybrid_signature")

    def test_plain_prose_after_symbol_keywords_does_not_emit_symbol_finding(self) -> None:
        instruction = "Review private helper that duplicates the function signature guidance."

        with patch.object(self.module.subprocess, "run") as run:
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Codebase-specific patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        run.assert_not_called()

    def test_instruction_references_closed_issue_emits_stale_finding(self) -> None:
        instruction = "Keep this workaround until #205 is resolved."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["gh"], stdout="closed\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assert_schema_valid(finding)
        self.assertIn("#205", finding["deletion_candidate"])
        self.assertEqual(
            run.call_args.args[0],
            ["gh", "issue", "view", "205", "--json", "state", "--jq", ".state"],
        )

    def test_instruction_references_open_issue_does_not_emit_finding(self) -> None:
        instruction = "Keep this workaround until #206 is resolved."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["gh"], stdout="open\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(
            run.call_args.args[0],
            ["gh", "issue", "view", "206", "--json", "state", "--jq", ".state"],
        )

    def test_instruction_cites_superseded_adr_emits_stale_finding(self) -> None:
        self.write_file(
            "docs/decisions/ADR-007-example.md",
            "# ADR-007: Old decision\n\n## Status\nSuperseded by ADR-009\n\n## Decision\nOld.\n",
        )
        instruction = "Follow ADR-007 for write-surface decisions."

        findings = self.module.generate_stale_findings(
            instruction,
            source_file="AGENTS.md",
            source_section="## Guardrails",
            repo_root=self.workspace_root,
        )

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assert_schema_valid(finding)
        self.assertIn("ADR-007", finding["deletion_candidate"])
        self.assertIn("superseded", finding["rationale"].lower())

    def test_instruction_cites_extended_adr_does_not_emit_stale_finding(self) -> None:
        self.write_file(
            "docs/decisions/ADR-015-example.md",
            "# ADR-015: Old decision\n\n## Status\nAccepted — extended by ADR-021\n\n",
        )
        instruction = "Follow ADR-015 for write-surface decisions."

        findings = self.module.generate_stale_findings(
            instruction,
            source_file="AGENTS.md",
            source_section="## Guardrails",
            repo_root=self.workspace_root,
        )

        self.assertEqual(findings, ())

    def test_too_many_references_fail_closed_before_subprocess_probe(self) -> None:
        instruction = " ".join(
            f"docs/missing-{index}.md"
            for index in range(self.module.MAX_REFERENCES_PER_KIND + 1)
        )

        with patch.object(self.module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "too many path references"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

        run.assert_not_called()

    def test_total_probe_budget_fails_closed_before_subprocess_probe(self) -> None:
        path_refs = " ".join(f"docs/missing-{index}.md" for index in range(90))
        symbol_refs = " ".join(f"symbol `missing_symbol_{index}`" for index in range(90))
        issue_refs = " ".join(f"#{index + 1}" for index in range(30))
        instruction = f"{path_refs} {symbol_refs} {issue_refs}"

        with patch.object(self.module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "too many subprocess probes"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

        run.assert_not_called()

    def test_total_probe_budget_includes_symbol_tracking_probe(self) -> None:
        path_refs = " ".join(f"docs/missing-{index}.md" for index in range(100))
        symbol_refs = " ".join(f"symbol `missing_symbol_{index}`" for index in range(100))
        instruction = f"{path_refs} {symbol_refs}"

        with patch.object(self.module.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "too many subprocess probes"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

        run.assert_not_called()

    def test_git_path_probe_failure_fails_closed(self) -> None:
        instruction = "Read docs/missing-runbook.md."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="", stderr="fatal: bad repo", returncode=128)
            with self.assertRaisesRegex(RuntimeError, "git ls-files failed"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

    def test_rg_unexpected_error_fails_closed(self) -> None:
        instruction = "Use symbol `missing_symbol` before changing runtime."

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                self._completed(["rg"], stdout="", stderr="regex error", returncode=2),
            )
            with self.assertRaisesRegex(RuntimeError, "rg failed"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

    def test_gh_nonzero_result_fails_closed(self) -> None:
        instruction = "Keep this workaround until #205 is resolved."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["gh"], stdout="", stderr="not found", returncode=1)
            with self.assertRaisesRegex(RuntimeError, "gh issue view failed"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

    def test_unsupported_issue_state_fails_closed(self) -> None:
        instruction = "Keep this workaround until #205 is resolved."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["gh"], stdout="merged\n")
            with self.assertRaisesRegex(RuntimeError, "unsupported state"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

    def test_subprocess_timeout_fails_closed(self) -> None:
        instruction = "Read docs/missing-runbook.md."

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = subprocess.TimeoutExpired(["git"], timeout=10)
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

    def assert_schema_valid(self, finding: dict[str, object]) -> None:
        _finding_schema.AuditWorkspaceFindingSchemaTests._validate_with_schema(
            finding,
            self.schema,
        )

    @staticmethod
    def _completed(
        args: list[str],
        *,
        stdout: str,
        stderr: str = "",
        returncode: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
