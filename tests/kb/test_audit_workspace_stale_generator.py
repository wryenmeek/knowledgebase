"""Tests for deterministic audit-workspace stale deletion candidates."""

from __future__ import annotations

import json
import subprocess
import sys
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

    def test_runtime_safe_path_pattern_matches_finding_schema(self) -> None:
        schema_patterns = {
            self.schema["properties"]["source_file"]["pattern"],
            self.schema["properties"]["suggested_artifact_path"]["pattern"],
        }

        self.assertEqual(schema_patterns, {self.module.SAFE_REPO_RELATIVE_PATH_PATTERN})

    def test_import_setup_does_not_duplicate_sys_path_entries(self) -> None:
        repo_root = str(STALE_GENERATOR_PATH.resolve().parents[4])
        logic_dir = str(STALE_GENERATOR_PATH.resolve().parent)
        expected_paths = {repo_root, logic_dir}
        original_path = list(sys.path)

        try:
            sys.path[:] = ["sentinel-before", repo_root, "sentinel-between", logic_dir]
            load_module("audit_workspace_stale_generator_sys_path_a", STALE_GENERATOR_PATH)
            load_module("audit_workspace_stale_generator_sys_path_b", STALE_GENERATOR_PATH)

            self.assertEqual(sys.path[:2], [logic_dir, repo_root])
            for expected_path in expected_paths:
                self.assertEqual(sys.path.count(expected_path), 1)
        finally:
            sys.path[:] = original_path

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

    def test_url_in_instruction_text_is_skipped_not_fail_closed(self) -> None:
        instruction = (
            "See https://github.com/wryenmeek/knowledgebase/blob/main/README.md "
            "or github.com/wryenmeek/knowledgebase/blob/main/docs/README.md "
            "for details. Also note missing-file.py here."
        )

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="some/file.md",
                source_section="## References",
                repo_root=self.workspace_root,
            )

        self.assertGreater(len(findings), 0)
        self.assertFalse(any("github.com" in finding["rationale"] for finding in findings))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "--", "missing-file.py"])

    def test_path_reference_extension_matching_is_case_insensitive(self) -> None:
        instruction = "When changing docs, check README.MD first."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="README.MD\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Guardrails",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "--", "README.MD"])

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

    def test_numeric_dotted_toml_filename_remains_accepted(self) -> None:
        instruction = "Respect 1.2.3.toml before changing version fixtures."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="1.2.3.toml\n")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Build, test, and verify commands",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "--", "1.2.3.toml"])

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

    def test_governance_lock_paths_are_skipped_not_reported_stale(self) -> None:
        instruction = (
            "Respect wiki/.kb_write.lock, raw/.rejection-registry.lock, "
            "raw/.github-sources.lock, raw/.drive-sources.lock, "
            "raw/.wiki-processing-checkpoint.lock, and .github/.customizations.lock."
        )

        with patch.object(self.module.subprocess, "run") as run:
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Guardrails",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        run.assert_not_called()

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

    def test_missing_rg_binary_fallback_reads_each_tracked_file_once(self) -> None:
        instruction = "Use function present_symbol and function missing_symbol before changing runtime."
        self.write_file(
            "scripts/kb/present.py",
            "def present_symbol():\n    return None\n",
        )
        read_count = 0
        original_read_text = Path.read_text

        def counting_read_text(path: Path, *args: object, **kwargs: object) -> str:
            nonlocal read_count
            if path.name == "present.py":
                read_count += 1
            return original_read_text(path, *args, **kwargs)

        with (
            patch.object(self.module.subprocess, "run") as run,
            patch.object(self.module.Path, "read_text", counting_read_text),
        ):
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

        self.assertEqual(read_count, 1)
        self.assertEqual(len(findings), 1)
        self.assertIn("missing_symbol", findings[0]["deletion_candidate"])
        self.assertEqual(run.call_count, 2)

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

    def test_six_digit_issue_reference_uses_gh_probe(self) -> None:
        instruction = "Keep this workaround until #100000 is resolved."

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
            ["gh", "issue", "view", "100000", "--json", "state", "--jq", ".state"],
        )

    def test_issue_reference_above_digit_cap_is_ignored_before_gh_probe(self) -> None:
        instruction = "Do not treat #12345678901 as a bounded GitHub issue reference."

        with patch.object(self.module.subprocess, "run") as run:
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        run.assert_not_called()

    def test_issue_zero_reference_is_ignored_before_gh_probe(self) -> None:
        instruction = "Do not treat #0 as a real GitHub issue reference."

        with patch.object(self.module.subprocess, "run") as run:
            findings = self.module.generate_stale_findings(
                instruction,
                source_file=".github/copilot-instructions.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(findings, ())
        run.assert_not_called()

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

    def test_instruction_cites_superseded_adr_with_h3_status_colon(self) -> None:
        self.write_file(
            "docs/decisions/ADR-008-example.md",
            "# ADR-008: Old decision\n\n### Status:\nSuperseded by ADR-009\n\n## Decision\nOld.\n",
        )
        instruction = "Follow ADR-008 for write-surface decisions."

        findings = self.module.generate_stale_findings(
            instruction,
            source_file="AGENTS.md",
            source_section="## Guardrails",
            repo_root=self.workspace_root,
        )

        self.assertEqual(len(findings), 1)
        self.assert_schema_valid(findings[0])
        self.assertIn("ADR-008", findings[0]["deletion_candidate"])

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

    def test_instruction_cites_reinstated_adr_does_not_emit_stale_finding(self) -> None:
        self.write_file(
            "docs/decisions/ADR-016-example.md",
            "# ADR-016: Current decision\n\n## Status\nReinstated after being superseded in 2024\n\n",
        )
        instruction = "Follow ADR-016 for write-surface decisions."

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

    def test_adversarial_path_in_instruction_fails_closed_on_subprocess(self) -> None:
        instruction = "Ignore ../etc/passwd.md and still check docs/missing-runbook.md."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="")
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 1)
        self.assertIn("docs/missing-runbook.md", findings[0]["deletion_candidate"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["git", "ls-files", "--", "docs/missing-runbook.md"])

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

    def test_tracked_python_path_escape_fails_closed_before_rg_probe(self) -> None:
        instruction = "Use symbol `missing_symbol` before changing runtime."

        with patch.object(self.module.subprocess, "run") as run:
            run.return_value = self._completed(["git"], stdout="../outside.py\n")
            with self.assertRaisesRegex(ValueError, "unsafe tracked Python path"):
                self.module.generate_stale_findings(
                    instruction,
                    source_file="AGENTS.md",
                    source_section="## Operational patterns",
                    repo_root=self.workspace_root,
                )

        self.assertEqual(run.call_count, 1)

    def test_adversarial_rg_stdout_fails_closed(self) -> None:
        instruction = "Use symbol `missing_symbol` before changing runtime."

        with patch.object(self.module.subprocess, "run") as run:
            run.side_effect = (
                self._completed(["git"], stdout="scripts/kb/present.py\n"),
                self._completed(["rg"], stdout="../etc/passwd\n"),
            )
            with self.assertRaisesRegex(ValueError, "unsafe rg match path"):
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

    def test_command_timeout_values_locked_in(self) -> None:
        instruction = "Read docs/missing-runbook.md, use symbol `missing_symbol`, and wait for #205."
        calls: list[tuple[list[str], int]] = []

        def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            timeout = kwargs.get("timeout")
            self.assertIsInstance(timeout, int)
            calls.append((argv, timeout))
            if argv == ["git", "ls-files", "--", "docs/missing-runbook.md"]:
                return self._completed(argv, stdout="")
            if argv == ["git", "ls-files", "--", "*.py"]:
                return self._completed(argv, stdout="scripts/kb/present.py\n")
            if argv[:6] == ["rg", "-l", "--fixed-strings", "--type", "python", "--"]:
                return self._completed(argv, stdout="", returncode=1)
            if argv == ["gh", "issue", "view", "205", "--json", "state", "--jq", ".state"]:
                return self._completed(argv, stdout="open\n")
            raise AssertionError(f"unexpected subprocess call: {argv}")

        with patch.object(self.module.subprocess, "run", side_effect=fake_run):
            findings = self.module.generate_stale_findings(
                instruction,
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

        self.assertEqual(len(findings), 2)
        self.assertEqual(
            calls,
            [
                (["git", "ls-files", "--", "docs/missing-runbook.md"], 10),
                (["git", "ls-files", "--", "*.py"], 10),
                (
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
                    10,
                ),
                (["gh", "issue", "view", "205", "--json", "state", "--jq", ".state"], 5),
            ],
        )

    def test_oversized_instruction_text_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "instruction_text exceeds"):
            self.module.generate_stale_findings(
                "x" * (self.module.MAX_INSTRUCTION_CHARS + 1),
                source_file="AGENTS.md",
                source_section="## Operational patterns",
                repo_root=self.workspace_root,
            )

    def test_command_runner_injection_used_when_provided(self) -> None:
        captured: list[tuple[list[str], Path, int]] = []

        def fake_runner(
            argv: list[str],
            repo_root: Path,
            timeout_seconds: int,
        ) -> subprocess.CompletedProcess[str]:
            captured.append((argv, repo_root, timeout_seconds))
            return self._completed(argv, stdout="")

        findings = self.module.generate_stale_findings(
            "Read docs/missing-runbook.md.",
            source_file="AGENTS.md",
            source_section="## Operational patterns",
            repo_root=self.workspace_root,
            command_runner=fake_runner,
        )

        self.assertEqual(len(findings), 1)
        self.assertTrue(captured, "command_runner not invoked")
        self.assertEqual(captured[0][0], ["git", "ls-files", "--", "docs/missing-runbook.md"])
        self.assertEqual(captured[0][2], 10)

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
