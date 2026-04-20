"""Framework skill scaffolding checks."""

from __future__ import annotations

from pathlib import Path
import unittest

from tests.kb.harnesses import parse_frontmatter_fields


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / ".github" / "skills"
FRAMEWORK_SKILLS: dict[str, dict[str, object]] = {
    "information-architecture-and-taxonomy": {"logic": False, "classification": "Doc-only contract consumer"},
    "ontology-and-entity-modeling": {"logic": False, "classification": "Doc-only contract consumer"},
    "knowledge-schema-and-metadata-governance": {"logic": False, "classification": "Doc-only contract consumer"},
    "entity-resolution-and-canonicalization": {
        "logic": False,
        "classification": "Doc-only contract consumer",
    },
    "search-and-discovery-optimization": {
        "logic": False,
        "classification": "Doc-only contract consumer",
    },
    "update-index": {"logic": False, "classification": "Doc-only workflow"},
    "suggest-backlinks": {
        "logic": True,
    },
    "validate-taxonomy-placement": {
        "logic": False,
        "classification": "Doc-only contract consumer",
    },
    "check-link-topology": {"logic": True},
    "validate-inbox-source": {"logic": True},
    "verify-citations": {"logic": False, "classification": "Doc-only workflow"},
    "enforce-npov": {"logic": False, "classification": "Doc-only workflow"},
    "record-open-questions": {"logic": False, "classification": "Doc-only workflow"},
    "log-policy-conflict": {"logic": False, "classification": "Doc-only workflow"},
    "policy-diff-review": {"logic": False, "classification": "Doc-only workflow"},
    "log-patrol-incident": {"logic": False, "classification": "Doc-only workflow"},
    "enforce-repository-boundaries": {"logic": True},
    "enforce-page-template": {"logic": True},
    "write-sourceref-citations": {"logic": True},
    "append-log-entry": {"logic": True},
    "run-deterministic-validators": {"logic": True},
    "validate-wiki-governance": {"logic": True},
    "sync-knowledgebase-state": {"logic": True},
    "review-wiki-plan": {"logic": False, "classification": "Doc-only workflow"},
    "audit-knowledgebase-workspace": {"logic": False, "classification": "Doc-only workflow"},
    "extract-entities-and-claims": {"logic": False, "classification": "Doc-only workflow"},
    "retrieve-from-index": {"logic": False, "classification": "Doc-only workflow"},
    "synthesize-cited-answer": {"logic": False, "classification": "Doc-only workflow"},
    "prepare-high-value-synthesis-handoff": {"logic": False, "classification": "Doc-only workflow"},
    "handoff-query-derived-page": {"logic": False, "classification": "Doc-only workflow"},
    # G3b — thin wrapper skills
    "run-ingest": {"logic": False, "classification": "Doc-only workflow"},
    "persist-query-result": {"logic": False, "classification": "Doc-only workflow"},
    # G3a Wave 1 — intake provenance (source-intake-steward)
    "register-source-provenance": {"logic": False, "classification": "Doc-only workflow"},
    "checksum-asset": {"logic": False, "classification": "Doc-only workflow"},
    "create-intake-manifest": {"logic": False, "classification": "Doc-only workflow"},
    "log-ingest-event": {"logic": False, "classification": "Doc-only workflow"},
    # G3a Wave 2 — synthesis (synthesis-curator, evidence-verifier)
    "synthesize-entity-page": {"logic": False, "classification": "Doc-only workflow"},
    "synthesize-concept-page": {"logic": False, "classification": "Doc-only workflow"},
    "claim-inventory": {"logic": False, "classification": "Doc-only workflow"},
    # G4b — post-draft claim verification (evidence-verifier)
    "semi-formal-reasoning": {"logic": False, "classification": "Doc-only workflow"},
    "detect-ai-tells": {"logic": False, "classification": "Doc-only workflow"},
    # G3a Wave 3 — maintenance arm (maintenance-auditor, change-patrol, policy-arbiter, topology-librarian)
    "semantic-wiki-lint": {"logic": False, "classification": "Doc-only workflow"},
    "freshness-audit": {"logic": False, "classification": "Doc-only workflow"},
    "cross-reference-symmetry-check": {"logic": False, "classification": "Doc-only workflow"},
    "propose-supersede-or-archive": {"logic": False, "classification": "Doc-only workflow"},
    "append-maintenance-log": {"logic": False, "classification": "Doc-only workflow"},
    "patrol-human-edits": {"logic": False, "classification": "Doc-only workflow"},
    "route-noncompliant-edit-for-review": {"logic": False, "classification": "Doc-only workflow"},
    "manage-redirects-and-anchors": {"logic": True},
    "detect-original-research": {"logic": False, "classification": "Doc-only workflow"},
    "compare-against-existing-pages": {"logic": False, "classification": "Doc-only workflow"},
    "escalate-contradictions": {"logic": False, "classification": "Doc-only workflow"},
    # G3a Wave 4 — quality and orchestration (quality-analyst, knowledgebase-orchestrator)
    "score-page-quality": {"logic": False, "classification": "Doc-only workflow"},
    "compute-kpis": {"logic": True},
    "analyze-missed-queries": {"logic": True},
    "prioritize-curation-backlog": {"logic": False, "classification": "Doc-only workflow"},
    "route-wiki-task": {"logic": False, "classification": "Doc-only workflow"},
    "plan-wiki-job": {"logic": False, "classification": "Doc-only workflow"},
    "fail-closed-on-errors": {"logic": False, "classification": "Doc-only workflow"},
}
HELPER_OWNING_SKILLS: dict[str, tuple[str, ...]] = {
    "context-engineering": (
        "context_import_contract.py",
        "normalize_context_imports.py",
        "validate_context_imports.py",
    ),
    "documentation-and-adrs": (
        "repair_markdown_structure.py",
        "validate_doc_batch.py",
    ),
}


class FrameworkSkillTests(unittest.TestCase):
    def test_expected_framework_skills_exist(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            with self.subTest(skill=skill_name):
                self.assertTrue((SKILLS_ROOT / skill_name / "SKILL.md").is_file())

    def test_skill_frontmatter_matches_directory_and_discovery_requirements(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
            frontmatter = parse_frontmatter_fields(
                skill_path.read_text(encoding="utf-8"), subject="Skill file"
            )
            with self.subTest(skill=skill_name):
                self.assertEqual(frontmatter.get("name"), skill_name)
                self.assertIn("Use when", frontmatter.get("description", ""))

    def test_skill_docs_include_overview_and_when_to_use_sections(self) -> None:
        for skill_name in FRAMEWORK_SKILLS:
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Overview", text)
                self.assertIn("## When to Use", text)

    def test_skill_logic_boundary_matches_mvp_scope(self) -> None:
        for skill_name, expectations in FRAMEWORK_SKILLS.items():
            logic_dir = SKILLS_ROOT / skill_name / "logic"
            with self.subTest(skill=skill_name):
                if expectations["logic"]:
                    self.assertTrue(logic_dir.is_dir())
                    self.assertTrue(any(logic_dir.glob("*.py")))
                else:
                    self.assertFalse(logic_dir.exists())

    def test_classified_skills_keep_declared_status_text(self) -> None:
        for skill_name, expectations in FRAMEWORK_SKILLS.items():
            classification = expectations.get("classification")
            if classification is None:
                continue
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn(str(classification), text)

    def test_foundation_logic_skills_document_contract_assertions_and_references(self) -> None:
        for skill_name in (
            "enforce-repository-boundaries",
            "enforce-page-template",
            "write-sourceref-citations",
            "append-log-entry",
            "run-deterministic-validators",
        ):
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Contract", text)
                self.assertIn("## Assertions", text)
                self.assertIn("## References", text)

    def test_operationalized_doc_only_skills_document_contract_assertions_and_references(self) -> None:
        for skill_name in (
            "entity-resolution-and-canonicalization",
            "search-and-discovery-optimization",
            "verify-citations",
            "enforce-npov",
            "record-open-questions",
            "log-policy-conflict",
            "policy-diff-review",
            "log-patrol-incident",
            "review-wiki-plan",
            "audit-knowledgebase-workspace",
            "extract-entities-and-claims",
            "retrieve-from-index",
            "synthesize-cited-answer",
            "prepare-high-value-synthesis-handoff",
            "handoff-query-derived-page",
            "update-index",
            "suggest-backlinks",
            "validate-taxonomy-placement",
        ):
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Contract", text)
                self.assertIn("## Assertions", text)
                self.assertIn("## References", text)

    def test_helper_owning_skills_keep_expected_local_logic_files(self) -> None:
        for skill_name, expected_logic_files in HELPER_OWNING_SKILLS.items():
            logic_dir = SKILLS_ROOT / skill_name / "logic"
            with self.subTest(skill=skill_name):
                self.assertTrue(logic_dir.is_dir())
                self.assertEqual(
                    tuple(path.name for path in sorted(logic_dir.glob("*.py"))),
                    expected_logic_files,
                )

    def test_helper_owning_skills_document_attached_helper_commands(self) -> None:
        expectations = {
            "context-engineering": (
                "validate_context_imports.py",
                "normalize_context_imports.py",
            ),
            "documentation-and-adrs": (
                "repair_markdown_structure.py",
                "validate_doc_batch.py",
            ),
            "validate-inbox-source": ("validate_source_registry.py",),
            "check-link-topology": ("validate_wiki_topology.py",),
        }
        for skill_name, script_names in expectations.items():
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                self.assertIn("## Commands", text)
                for script_name in script_names:
                    self.assertIn(script_name, text)

    def test_topology_skills_keep_graph_follow_up_governed(self) -> None:
        expectations = {
            "update-index": (
                "No direct `wiki/index.md` write occurs here",
                "route the approved refresh to `sync-knowledgebase-state`",
                "Redirect or alias-changing behavior remains explicitly governed rather than silently automated",
            ),
            "suggest-backlinks": (
                "No direct page edit or persistence side effect occurs here",
                "alias- or redirect-changing backlink proposals are escalation items, not automatic fixes",
                "Redirect or alias-changing behavior remains explicitly governed rather than silently automated",
            ),
            "validate-taxonomy-placement": (
                "No direct move, rename, alias rewrite, or redirect creation occurs here",
                "redirect, alias, or canonical-identity pressure routes to `entity-resolution-and-canonicalization` and `review-wiki-plan`",
                "Redirect or alias-changing behavior remains explicitly governed rather than silently automated",
            ),
            "check-link-topology": (
                "No direct topology mutation occurs here",
                "changes that depend on redirect or alias semantics must return to governance first",
                "Do not run a crawler, graph database, or broad runtime scan in MVP",
            ),
        }
        for skill_name, snippets in expectations.items():
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            with self.subTest(skill=skill_name):
                for snippet in snippets:
                    self.assertIn(" ".join(snippet.split()), normalized)

    def test_query_and_synthesis_workflow_skills_route_durable_outputs_back_through_governance(self) -> None:
        expectations = {
            "extract-entities-and-claims": (
                "go to `synthesis-curator` or back to",
                "`knowledgebase-orchestrator`",
                "direct page writes",
            ),
            "retrieve-from-index": (
                "`wiki/index.md`",
                "`synthesize-cited-answer`",
                "never becomes persistence on its own",
            ),
            "synthesize-cited-answer": (
                "route to `prepare-high-value-synthesis-handoff`",
                "Do not persist a query result directly",
                "No direct wiki write or persistence side effect occurs here",
            ),
            "prepare-high-value-synthesis-handoff": (
                "returns to `knowledgebase-orchestrator`",
                "`evidence-verifier` and `policy-arbiter`",
                "No direct page creation, page update, or persistence side effect occurs here",
            ),
            "handoff-query-derived-page": (
                "return to `knowledgebase-orchestrator`",
                "`evidence-verifier`, `policy-arbiter`, and only then `synthesis-curator`",
                "No direct wiki write is permitted from this skill",
            ),
        }
        for skill_name, snippets in expectations.items():
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                for snippet in snippets:
                    self.assertIn(snippet, text)


if __name__ == "__main__":
    unittest.main()
