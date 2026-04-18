"""Early framework contract-alignment checks for docs and skills."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
FOCUSED_FRAMEWORK_COMMAND = (
    "python3 -m unittest "
    "tests.kb.test_framework_contracts "
    "tests.kb.test_framework_skills "
    "tests.kb.test_framework_agents "
    "tests.kb.test_framework_references "
    "tests.kb.test_framework_write_surface_matrix "
    "tests.kb.test_skill_wrappers"
)

FRAMEWORK_BOUNDARY_DOCS: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "decisions" / "ADR-007-control-plane-layering-and-packaging.md",
    REPO_ROOT / "docs" / "ideas" / "wiki-curation-agent-framework.md",
)
EXECUTION_SURFACE = (
    "scripts/kb/ingest.py",
    "scripts/kb/update_index.py",
    "scripts/kb/lint_wiki.py",
    "scripts/kb/qmd_preflight.py",
    "scripts/kb/persist_query.py",
)
SKILL_REFERENCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "context-engineering": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
    ),
    "documentation-and-adrs": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "schema/page-template.md",
    ),
    "information-architecture-and-taxonomy": (
        "schema/taxonomy-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "docs/architecture.md",
        "AGENTS.md",
    ),
    "ontology-and-entity-modeling": (
        "schema/ontology-entity-contract.md",
        "schema/taxonomy-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "AGENTS.md",
    ),
    "knowledge-schema-and-metadata-governance": (
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "docs/architecture.md",
        "AGENTS.md",
    ),
    "entity-resolution-and-canonicalization": (
        "schema/ontology-entity-contract.md",
        "schema/taxonomy-contract.md",
        "schema/metadata-schema-contract.md",
        "docs/architecture.md",
        "AGENTS.md",
    ),
    "search-and-discovery-optimization": (
        "schema/taxonomy-contract.md",
        "schema/metadata-schema-contract.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "AGENTS.md",
    ),
    "update-index": (
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "wiki/index.md",
        "AGENTS.md",
    ),
    "suggest-backlinks": (
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "wiki/index.md",
        "AGENTS.md",
    ),
    "validate-taxonomy-placement": (
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "wiki/index.md",
        "AGENTS.md",
    ),
    "check-link-topology": (
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "wiki/index.md",
        "AGENTS.md",
    ),
    "validate-inbox-source": (
        "AGENTS.md",
        "docs/architecture.md",
        "raw/processed/SPEC.md",
        "schema/ingest-checklist.md",
        "schema/metadata-schema-contract.md",
    ),
    "verify-citations": (
        "AGENTS.md",
        "docs/architecture.md",
        "raw/processed/SPEC.md",
        "schema/ingest-checklist.md",
        "schema/metadata-schema-contract.md",
    ),
    "enforce-npov": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "raw/processed/SPEC.md",
        "schema/page-template.md",
    ),
    "record-open-questions": (
        "AGENTS.md",
        "docs/architecture.md",
        "schema/metadata-schema-contract.md",
        "schema/page-template.md",
        "raw/processed/SPEC.md",
    ),
    "log-policy-conflict": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "raw/processed/SPEC.md",
        "wiki/log.md",
    ),
    "policy-diff-review": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "schema/ingest-checklist.md",
        "schema/page-template.md",
        "schema/metadata-schema-contract.md",
    ),
    "log-patrol-incident": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "raw/processed/SPEC.md",
        "wiki/log.md",
    ),
    "enforce-repository-boundaries": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "schema/page-template.md",
    ),
    "enforce-page-template": (
        "schema/page-template.md",
        "schema/metadata-schema-contract.md",
        "schema/taxonomy-contract.md",
        "schema/ontology-entity-contract.md",
        "AGENTS.md",
    ),
    "write-sourceref-citations": (
        "AGENTS.md",
        "docs/architecture.md",
        "schema/metadata-schema-contract.md",
        "schema/ingest-checklist.md",
    ),
    "append-log-entry": (
        "AGENTS.md",
        "docs/architecture.md",
        "raw/processed/SPEC.md",
        "schema/page-template.md",
    ),
    "run-deterministic-validators": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "schema/page-template.md",
        "schema/ingest-checklist.md",
    ),
    "validate-wiki-governance": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "schema/page-template.md",
        "schema/ingest-checklist.md",
    ),
    "sync-knowledgebase-state": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "docs/mvp-runbook.md",
    ),
    "review-wiki-plan": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "schema/page-template.md",
        "schema/ingest-checklist.md",
    ),
    "audit-knowledgebase-workspace": (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
        "docs/ideas/wiki-curation-agent-framework.md",
        "tests/kb/test_framework_references.py",
        "tests/kb/test_skill_wrappers.py",
    ),
}


class FrameworkContractAlignmentTests(unittest.TestCase):
    def test_boundary_docs_list_same_execution_surface(self) -> None:
        for path in FRAMEWORK_BOUNDARY_DOCS:
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                for entrypoint in EXECUTION_SURFACE:
                    self.assertIn(entrypoint, text)

    def test_framework_skill_docs_link_back_to_authoritative_contracts(self) -> None:
        skills_root = REPO_ROOT / ".github" / "skills"
        for skill_name, required_refs in SKILL_REFERENCE_REQUIREMENTS.items():
            skill_path = skills_root / skill_name / "SKILL.md"
            text = skill_path.read_text(encoding="utf-8")
            with self.subTest(skill=skill_name):
                for required_ref in required_refs:
                    self.assertIn(required_ref, text)

    def test_runbook_documents_narrow_high_risk_baseline_gate(self) -> None:
        text = (REPO_ROOT / "docs" / "mvp-runbook.md").read_text(encoding="utf-8")
        self.assertIn("## Phase 0 bootstrap: runtime prerequisites", text)
        self.assertIn("Local wrapper validation", text)
        self.assertIn("CI-2 / CI-3 wrapper validation", text)
        self.assertIn("mkdir -p .ci-bin .qmd/index", text)
        self.assertIn("authoritative qmd packaging/version pinning stays in the post-MVP verification story", text)
        self.assertIn("## High-risk schema/topology baseline gate", text)
        self.assertIn(
            "python3 .github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            text,
        )
        self.assertIn(
            "git --no-pager status --short --untracked-files=all -- schema wiki .github/skills .github/agents docs/architecture.md docs/decisions/ADR-007-control-plane-layering-and-packaging.md",
            text,
        )
        self.assertIn(
            FOCUSED_FRAMEWORK_COMMAND,
            text,
        )
        self.assertIn("tests/kb/test_skill_wrappers.py", text)
        self.assertIn("tests/kb/test_framework_write_surface_matrix.py", text)
        self.assertNotIn("python3 scripts/validation/", text)
        self.assertNotIn("snapshot_knowledgebase.py", text)

    def test_runbook_separates_framework_wrapper_helper_script_and_workflow_entrypoints(self) -> None:
        text = (REPO_ROOT / "docs" / "mvp-runbook.md").read_text(encoding="utf-8")
        self.assertIn("## Authoritative verification and approval entrypoints", text)
        self.assertIn("Framework contract suites", text)
        self.assertIn("Wrapper behavior suite", text)
        self.assertIn("Helper surface suites", text)
        self.assertIn("Repo script suites", text)
        self.assertIn("Workflow governance suites", text)
        self.assertIn("Verification matrix suites", text)
        self.assertIn("Broad regression suite", text)
        self.assertIn("tests/kb/test_framework_write_surface_matrix.py", text)
        self.assertIn("tests.kb.test_context_import_helpers", text)
        self.assertIn("tests.kb.test_documentation_helpers", text)
        self.assertIn("tests.kb.test_ci_permission_asserts", text)
        self.assertIn("tests.kb.test_unit_verification_matrix", text)
        self.assertIn("CI-1 no-write trusted handoff", text)
        self.assertIn("CI-2 read-only diagnostics", text)
        self.assertIn("CI-3 allowlisted writes", text)

    def test_runbook_and_spec_define_verification_matrix_migration_rules(self) -> None:
        runbook_text = (REPO_ROOT / "docs" / "mvp-runbook.md").read_text(encoding="utf-8")
        spec_text = (REPO_ROOT / "docs" / "ideas" / "spec.md").read_text(encoding="utf-8")

        self.assertIn("## Verification planning baseline", runbook_text)
        self.assertIn("verification-matrix-and-ci-migration-rules", runbook_text)
        self.assertIn("tests/kb/test_ci1_workflow.py", runbook_text)
        self.assertIn("tests/kb/test_unit_verification_matrix.py", runbook_text)
        self.assertIn('python3 -m unittest discover -s tests -p "test_*.py"', runbook_text)

        self.assertIn("## Verification matrix and CI migration rules", spec_text)
        self.assertIn("### Current MVP suites that stay green in every phase", spec_text)
        self.assertIn("Skill-local helpers", spec_text)
        self.assertIn("Wrapper modes", spec_text)
        self.assertIn("Repo-level scripts", spec_text)
        self.assertIn("Workflow lanes", spec_text)
        self.assertIn("| Pre-script |", spec_text)
        self.assertIn("| Script-expansion |", spec_text)
        self.assertIn("| Final consolidation |", spec_text)

    def test_schema_contracts_document_authoritative_sourceref_hardening(self) -> None:
        metadata_contract = (
            REPO_ROOT / "schema" / "metadata-schema-contract.md"
        ).read_text(encoding="utf-8")
        ingest_checklist = (
            REPO_ROOT / "schema" / "ingest-checklist.md"
        ).read_text(encoding="utf-8")
        self.assertIn("placeholder/sentinel", metadata_contract)
        self.assertIn("authoritative mode", metadata_contract)
        self.assertIn("provisional ingest-time SourceRefs", metadata_contract)
        self.assertIn("provenance.status", metadata_contract)
        self.assertIn("authoritative: false", metadata_contract)
        self.assertIn("real git revision", metadata_contract)
        self.assertIn("that revision", metadata_contract)
        self.assertIn("placeholder/sentinel", ingest_checklist)
        self.assertIn("recomputed", ingest_checklist)
        self.assertIn("commit-bound reconciliation step", ingest_checklist)
        self.assertIn("real git revision", ingest_checklist)
        self.assertIn("structured provisional provenance marker", ingest_checklist)

    def test_framework_docs_preserve_governance_before_durable_follow_up(self) -> None:
        framework_idea = (
            REPO_ROOT / "docs" / "ideas" / "wiki-curation-agent-framework.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "intake -> verification -> policy -> synthesis/query/topology",
            framework_idea,
        )
        self.assertIn(
            "No durable save, topology mutation, or publication path should open before that governance sequence succeeds",
            framework_idea,
        )
        self.assertIn(
            "Knowledgebase Orchestrator for any durable follow-up",
            framework_idea,
        )
        self.assertNotIn("save synthesis?", framework_idea)
        self.assertNotIn(
            "Synthesis Curator** or **Query Synthesist** saves it as a durable synthesis page",
            framework_idea,
        )

    def test_status_docs_reflect_active_doc_only_framework_expansion(self) -> None:
        architecture_text = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        framework_idea = (
            REPO_ROOT / "docs" / "ideas" / "wiki-curation-agent-framework.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "`entity-resolution-and-canonicalization`, `search-and-discovery-optimization`",
            architecture_text,
        )
        self.assertIn(
            "`validate-inbox-source`, `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan`, `audit-knowledgebase-workspace`",
            architecture_text,
        )
        self.assertNotIn("Deferred scaffolding", architecture_text)
        self.assertIn(
            "| **Active doc-only skills** | `information-architecture-and-taxonomy`, `ontology-and-entity-modeling`, `knowledge-schema-and-metadata-governance`, `entity-resolution-and-canonicalization`, `search-and-discovery-optimization` |",
            framework_idea,
        )
        self.assertIn(
            "| **Active doc-only workflow skills** | `validate-inbox-source`, `verify-citations`, `enforce-npov`, `record-open-questions`, `log-policy-conflict`, `review-wiki-plan`, `audit-knowledgebase-workspace` |",
            framework_idea,
        )
        self.assertNotIn("| **Deferred scaffolding** |", framework_idea)

    def test_taxonomy_contract_separates_blocking_flat_namespace_from_advisory_quality(self) -> None:
        taxonomy_contract = (
            REPO_ROOT / "schema" / "taxonomy-contract.md"
        ).read_text(encoding="utf-8")
        self.assertIn("### Deterministic MVP blocking", taxonomy_contract)
        self.assertIn("Topical namespaces are flat in MVP", taxonomy_contract)
        self.assertIn("Nested topical paths under `wiki/sources/`, `wiki/entities/`", taxonomy_contract)
        self.assertIn("are rejected.", taxonomy_contract)
        self.assertIn("### Advisory in MVP", taxonomy_contract)
        self.assertIn("they are not enforced by the", taxonomy_contract)
        self.assertIn("deterministic lint/index gates in MVP", taxonomy_contract)
        self.assertIn("A page could be moved to a more specific category.", taxonomy_contract)
        self.assertIn("`browse_path` is omitted where discoverability would materially benefit.", taxonomy_contract)


if __name__ == "__main__":
    unittest.main()
