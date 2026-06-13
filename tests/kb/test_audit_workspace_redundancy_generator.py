"""Tests for LLM-judged redundant-up-the-ladder citation enforcement."""

from __future__ import annotations

import json
import os
from pathlib import Path

from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
REDUNDANCY_GENERATOR_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "redundancy_generator.py"
)


class AuditWorkspaceRedundancyGeneratorTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.module = load_module(
            f"redundancy_generator_{self._testMethodName}",
            REDUNDANCY_GENERATOR_PATH,
        )
        self.write_file("AGENTS.md", "# AGENTS\n\nGlobal hook-only guidance.\n")
        self.write_file(
            ".github/instructions/hooks.instructions.md",
            "Use the scoped rule for hooks only.\n",
        )
        self.write_file(".github/hooks/hooks.json", '{"hooks": []}\n')
        self.write_file(
            ".github/hooks/check_hooks.py",
            "HOOK_SNIPPET = 'hook-specific rule'\n",
        )
        self.skill_path = self.write_file(
            ".github/skills/context-engineering/SKILL.md",
            "\n".join(
                [
                    "---",
                    "name: context-engineering",
                    "description: Scoped context loading.",
                    "---",
                    "",
                    "Scoped skill covers the same review handoff.",
                    "",
                    "Second paragraph must not be needed by the prompt.",
                ]
            ),
        )

    def test_valid_citation_preserves_schema_shaped_deletion_finding(self) -> None:
        captured_prompts: list[str] = []

        def llm_caller(prompt: str) -> str:
            captured_prompts.append(prompt)
            return json.dumps(
                {
                    "claims": [
                        {
                            "rationale": (
                                "Lower-locality instruction already covers the hook-only "
                                "global guidance."
                            ),
                            "expected_token_efficiency_rank": 0,
                            "deletion_candidate": "Delete the higher-locality hook-only guidance.",
                            "citation": {
                                "artifact_path": ".github/instructions/hooks.instructions.md",
                                "snippet": "Use the scoped rule for hooks only.",
                            },
                        }
                    ]
                }
            )

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(cache_strategy="hybrid_signature"),
            llm_caller=llm_caller,
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(len(result["findings"]), 1)
        finding = result["findings"][0]
        self.assertEqual(finding["source_file"], "AGENTS.md")
        self.assertEqual(finding["source_section"], "Global hook rule")
        self.assertEqual(finding["proposed_destination"], "Delete")
        self.assertEqual(finding["compliance_risk"], "agent-dependent")
        self.assertEqual(finding["expected_token_efficiency_rank"], 0)
        self.assertEqual(finding["cache_strategy"], "hybrid_signature")
        self.assertEqual(finding["suggested_artifact_path"], "AGENTS.md")
        self.assertEqual(
            finding["citation"],
            ".github/instructions/hooks.instructions.md: Use the scoped rule for hooks only.",
        )
        self.assertEqual(
            finding["deletion_candidate"],
            "Delete the higher-locality hook-only guidance.",
        )

        self.assertEqual(len(captured_prompts), 1)
        prompt = captured_prompts[0]
        self.assertIn("Uncited claims will be dropped", prompt)
        self.assertIn("Scoped skill covers the same review handoff.", prompt)
        self.assertIn("Use the scoped rule for hooks only.", prompt)
        self.assertIn("HOOK_SNIPPET = 'hook-specific rule'", prompt)

    def test_loads_precomputed_skill_corpus_cache_without_materializing(self) -> None:
        cache_path = self._cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_payload = self._skill_corpus(cache_strategy="mtime_first_para")
        cache_path.write_text(json.dumps(cache_payload, sort_keys=True), encoding="utf-8")
        before = self.snapshot_workspace()
        captured_prompts: list[str] = []

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            llm_caller=lambda prompt: captured_prompts.append(prompt) or '{"claims": []}',
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("Scoped skill covers the same review handoff.", captured_prompts[0])
        self.assert_workspace_unchanged(before)

    def test_missing_skill_corpus_cache_hard_fails_without_materializing(self) -> None:
        cache_path = self._cache_path()

        with self.assertRaises(FileNotFoundError):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                llm_caller=lambda _prompt: '{"claims": []}',
            )

        self.assertFalse(cache_path.exists())

    def test_cache_entry_outside_skill_docs_hard_fails(self) -> None:
        readme_path = self.write_file("README.md", "Unrelated repo-local snippet.\n")
        cache_path = self._cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    str(readme_path.resolve()): {
                        "frontmatter": {},
                        "first_paragraph": "Unrelated repo-local snippet.",
                        "mtime_ns": 1,
                        "cache_strategy": "mtime_first_para",
                    }
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, r"\.github/skills/\*/SKILL\.md"):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                llm_caller=lambda _prompt: '{"claims": []}',
            )

    def test_injected_corpus_entry_outside_skill_docs_hard_fails(self) -> None:
        readme_path = self.write_file("README.md", "Unrelated repo-local snippet.\n")

        with self.assertRaisesRegex(ValueError, r"\.github/skills/\*/SKILL\.md"):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                skill_corpus={
                    str(readme_path.resolve()): {
                        "frontmatter": {},
                        "first_paragraph": "Unrelated repo-local snippet.",
                        "mtime_ns": 1,
                        "cache_strategy": "mtime_first_para",
                    }
                },
                llm_caller=lambda _prompt: '{"claims": []}',
            )

    def test_symlinked_lower_locality_artifact_hard_fails(self) -> None:
        symlink_path = self.workspace_root / ".github" / "instructions" / "leak.md"
        symlink_path.unlink(missing_ok=True)
        os.symlink(self.workspace_root / "AGENTS.md", symlink_path)

        with self.assertRaisesRegex(ValueError, "symlinked corpus artifact"):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                skill_corpus=self._skill_corpus(),
                llm_caller=lambda _prompt: '{"claims": []}',
            )

    def test_symlinked_skill_cache_path_hard_fails(self) -> None:
        cache_dir = self._cache_path().parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.write_file("cache-target.json", "{}")
        os.symlink(target_path, cache_dir / self.module.CACHE_FILENAME)

        with self.assertRaisesRegex(OSError, "symlinked cache path component"):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                llm_caller=lambda _prompt: '{"claims": []}',
            )

    def test_invalid_source_file_hard_fails_even_with_source_text(self) -> None:
        with self.assertRaises(ValueError):
            self.module.generate_redundancy_findings(
                repo_root=self.workspace_root,
                source_file="../AGENTS.md",
                source_section="Global hook rule",
                source_text="Global hook-only guidance.",
                skill_corpus=self._skill_corpus(),
                llm_caller=lambda _prompt: '{"claims": []}',
            )

    def test_uncited_claim_is_dropped_silently(self) -> None:
        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "A redundant claim with no citation must disappear.",
                        "expected_token_efficiency_rank": 0,
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_claim_with_missing_artifact_path_is_dropped_silently(self) -> None:
        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "The cited path does not exist.",
                        "expected_token_efficiency_rank": 0,
                        "citation": {
                            "artifact_path": ".github/instructions/missing.instructions.md",
                            "snippet": "Use the scoped rule for hooks only.",
                        },
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_claim_with_path_escape_citation_is_dropped_silently(self) -> None:
        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "The cited path escapes the comparison corpus.",
                        "expected_token_efficiency_rank": 0,
                        "citation": {
                            "artifact_path": "../AGENTS.md",
                            "snippet": "Global hook-only guidance.",
                        },
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_self_citation_is_dropped_silently(self) -> None:
        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "The source file cannot cite itself as lower-locality evidence.",
                        "expected_token_efficiency_rank": 0,
                        "citation": {
                            "artifact_path": "AGENTS.md",
                            "snippet": "Global hook-only guidance.",
                        },
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_arbitrary_repo_file_citation_is_dropped_silently(self) -> None:
        self.write_file("README.md", "Unrelated repo-local snippet.\n")

        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "Only loaded lower-locality corpus artifacts may be cited.",
                        "expected_token_efficiency_rank": 0,
                        "citation": {
                            "artifact_path": "README.md",
                            "snippet": "Unrelated repo-local snippet.",
                        },
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_claim_with_non_matching_snippet_is_dropped_silently(self) -> None:
        result = self._generate_with_response(
            {
                "claims": [
                    {
                        "rationale": "The cited snippet is not in the artifact.",
                        "expected_token_efficiency_rank": 0,
                        "citation": {
                            "artifact_path": ".github/instructions/hooks.instructions.md",
                            "snippet": "This exact text is absent.",
                        },
                    }
                ]
            }
        )

        self.assertFalse(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_all_llm_failures_soft_skip_after_bounded_retries(self) -> None:
        attempts = 0

        def failing_llm(_prompt: str) -> str:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("fixture failure")

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(),
            llm_caller=failing_llm,
        )

        self.assertEqual(attempts, 3)
        self.assertTrue(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_malformed_json_root_soft_skips_after_bounded_retries(self) -> None:
        attempts = 0

        def malformed_llm(_prompt: str) -> str:
            nonlocal attempts
            attempts += 1
            return "null"

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(),
            llm_caller=malformed_llm,
        )

        self.assertEqual(attempts, 3)
        self.assertTrue(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_array_json_root_soft_skips_after_bounded_retries(self) -> None:
        attempts = 0

        def array_root_llm(_prompt: str) -> str:
            nonlocal attempts
            attempts += 1
            return "[]"

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(),
            llm_caller=array_root_llm,
        )

        self.assertEqual(attempts, 3)
        self.assertTrue(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def test_syntactically_invalid_json_soft_skips_after_bounded_retries(self) -> None:
        attempts = 0

        def invalid_json_llm(_prompt: str) -> str:
            nonlocal attempts
            attempts += 1
            return "{not valid json"

        result = self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(),
            llm_caller=invalid_json_llm,
        )

        self.assertEqual(attempts, 3)
        self.assertTrue(result["soft_skipped"])
        self.assertEqual(result["findings"], [])

    def _generate_with_response(self, response: dict[str, object]) -> dict[str, object]:
        return self.module.generate_redundancy_findings(
            repo_root=self.workspace_root,
            source_file="AGENTS.md",
            source_section="Global hook rule",
            source_text="Global hook-only guidance.",
            skill_corpus=self._skill_corpus(),
            llm_caller=lambda _prompt: json.dumps(response),
        )

    def _skill_corpus(
        self, *, cache_strategy: str = "mtime_first_para"
    ) -> dict[str, dict[str, object]]:
        return {
            str(self.skill_path.resolve()): {
                "frontmatter": {
                    "name": "context-engineering",
                    "description": "Scoped context loading.",
                },
                "first_paragraph": "Scoped skill covers the same review handoff.",
                "mtime_ns": 1,
                "cache_strategy": cache_strategy,
            }
        }

    def _cache_path(self) -> Path:
        return (
            self.workspace_root
            / ".github"
            / "skills"
            / "audit-knowledgebase-workspace"
            / ".cache"
            / self.module.CACHE_FILENAME
        )
