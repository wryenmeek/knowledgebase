"""Framework contract checks for the AGENTS.md write-surface matrix."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


AGENTS_PATH = Path("AGENTS.md")
WRITE_SURFACE_MATRIX_HEADING = "## Write-surface matrix"
EXPECTED_WRITE_SURFACE_MATRIX_ROWS: dict[str, dict[str, tuple[str, ...]]] = {
    ".github/skills/append-log-entry/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/log.md", "append-only"),
        "Lock requirements": ("wiki/.kb_write.lock", "ADR-005"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "schema/page-template.md"),
        "Hard-fail behavior": ("lock_unavailable", "non-log write", "fail closed"),
    },
    ".github/skills/check-link-topology/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/taxonomy-contract.md", "schema/page-template.md"),
        "Hard-fail behavior": ("topology_invalid", "path_not_allowlisted", "fail closed"),
    },
    ".github/skills/manage-redirects-and-anchors/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/redirects.md", "append-only"),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("ADR-009", "schema/governed-artifact-contract.md"),
        "Hard-fail behavior": ("lock_unavailable", "duplicate redirect", "fail closed"),
    },
    ".github/skills/compute-kpis/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/report-artifact-contract.md", ".github/agents/quality-analyst.md"),
        "Hard-fail behavior": ("missing artifact", "write attempt", "fail closed"),
    },
    ".github/skills/analyze-missed-queries/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/page-template.md", ".github/agents/quality-analyst.md"),
        "Hard-fail behavior": ("path escape", "invalid wiki path", "fail closed"),
    },
    ".github/skills/audit-knowledgebase-workspace/logic/**": {
        "Runtime mode": ("Mixed surface", "read-only only", "blocking-only", "transient skill-local"),
        "Writable paths": ("None for the wildcard scope", "narrower rows below", "transient skill-local cache"),
        "Read-only / prerequisite paths": (".github/copilot-instructions.md", "AGENTS.md", ".github/skills/**", ".github/agents/**", ".github/hooks/**", "tests/kb/**"),
        "Lock requirements": ("None", "transient cache", ".github/.customizations.lock"),
        "Artifact / schema owners": (".github/skills/audit-knowledgebase-workspace/SKILL.md", "scripts/_optional_surface_common.py", "ADR-028"),
        "Hard-fail behavior": ("unsupported mode", "unsupported approval", "missing repo root", "undeclared", "protected-path", "fail closed"),
    },
    ".github/skills/audit-knowledgebase-workspace/logic/skill_corpus_cache.py": {
        "Runtime mode": ("blocking-only", "transient skill-local cache"),
        "Writable paths": (".github/skills/audit-knowledgebase-workspace/.cache/skill-corpus.json", "transient runtime cache", "not governed"),
        "Read-only / prerequisite paths": (".github/skills/*/SKILL.md", "in full", "caches only", "frontmatter", "first prose paragraph", "staleness", "mtime_ns"),
        "Lock requirements": ("None", "transient skill-local cache"),
        "Artifact / schema owners": ("docs/ideas/audit-workspace-improve-flow.md", "scripts/kb/page_template_utils.py", "scripts/kb/write_utils.py"),
        "Hard-fail behavior": ("path escape", "missing skill root", "outside the skill-local", "governed-path", "fail closed"),
    },
    ".github/skills/context-engineering/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("docs/architecture.md", ".github/skills/context-engineering/SKILL.md"),
        "Hard-fail behavior": ("invalid manifest", "path_not_allowlisted", "fail closed"),
    },
    ".github/skills/documentation-and-adrs/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/page-template.md", "docs/decisions/ADR-007-control-plane-layering-and-packaging.md"),
        "Hard-fail behavior": ("missing_link", "needs_repair", "fail closed"),
    },
    ".github/skills/enforce-page-template/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/page-template.md", "schema/metadata-schema-contract.md"),
        "Hard-fail behavior": ("missing frontmatter", "missing heading", "fail closed"),
    },
    ".github/skills/enforce-repository-boundaries/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None direct", "delegate"),
        "Lock requirements": ("Delegated writer", "ADR-005"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "AGENTS.md"),
        "Hard-fail behavior": ("path_not_allowlisted", "undeclared direct write", "fail closed"),
    },
    ".github/skills/run-deterministic-validators/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/**", "scripts/kb/contracts.py"),
        "Hard-fail behavior": ("unknown_validator", "validator_failed", "fail closed"),
    },
    ".github/skills/sync-knowledgebase-state/logic/**": {
        "Runtime mode": ("read-only only", "blocking-only"),
        "Writable paths": ("wiki/index.md", "wiki/log.md", "wiki/open-questions.md", "wiki/backlog.md", "wiki/status.md"),
        "Lock requirements": ("wiki/.kb_write.lock", "ADR-005", "stale unlocked lock files"),
        "Artifact / schema owners": ("scripts/kb/update_index.py", "scripts/kb/write_utils.py", "schema/taxonomy-contract.md", "schema/governed-artifact-contract.md", "schema/wiki-processing-checkpoint-registry-contract.md"),
        "Hard-fail behavior": ("lock contention", "unsupported artifact", "postcheck", "fail closed"),
    },
    ".github/skills/validate-inbox-source/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/ingest-checklist.md", "raw/processed/SPEC.md"),
        "Hard-fail behavior": ("invalid_registry", "path_not_allowlisted", "fail closed"),
    },
    ".github/skills/validate-wiki-governance/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "schema/page-template.md"),
        "Hard-fail behavior": ("unsupported", "partial validator result", "fail closed"),
    },
    ".github/skills/write-sourceref-citations/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/metadata-schema-contract.md", "schema/ingest-checklist.md"),
        "Hard-fail behavior": ("path_not_allowlisted", "authoritative byte mismatch", "fail closed"),
    },
    ".github/skills/suggest-backlinks/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/taxonomy-contract.md", ".github/skills/suggest-backlinks/SKILL.md"),
        "Hard-fail behavior": ("path escape", "invalid wiki path", "write attempt", "fail closed"),
    },
    "scripts/kb/**": {
        "Runtime mode": ("Mixed", "blocking-only"),
        "Writable paths": ("wiki/**", "raw/processed/**"),
        "Lock requirements": ("wiki/.kb_write.lock", "append-only"),
        "Artifact / schema owners": ("raw/processed/SPEC.md", "schema/**"),
        "Hard-fail behavior": ("permission mismatch", "partial validator result", "undeclared writes"),
    },
    "scripts/kb/checkpoint_registry.py": {
        "Runtime mode": ("--verify", "read-only only", "--verify --log-warnings", "--bootstrap --apply", "--mutate", "blocking-only"),
        "Writable paths": ("raw/wiki-processing/wiki-processing-checkpoint-registry.json", "wiki/log.md", "append-only", "--log-warnings"),
        "Read-only / prerequisite paths": ("wiki/entities/**", "wiki/concepts/**", "wiki/analyses/**", "wiki/sources/**", "docs/staged/**", "schema/wiki-processing-checkpoint-registry-contract.md"),
        "Lock requirements": ("raw/.wiki-processing-checkpoint.lock", "CHECKPOINT_REGISTRY_LOCK_PATH", "wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "scripts/kb/write_utils.py", "scripts/kb/page_template_utils.py", "scripts/_optional_surface_common.py", "schema/wiki-processing-checkpoint-registry-contract.md"),
        "Hard-fail behavior": ("lock unavailable", "schema-invalid", "docs/staged/**", "illegal transition", "stale timeout", "atomic-replace failure", "fail closed"),
    },
    "scripts/kb/batch_persist_query.py` — `apply` mode": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/analyses/**", "wiki/index.md", "wiki/log.md"),
        "Lock requirements": ("wiki/.kb_write.lock", "ADR-005"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "scripts/kb/persist_query.py", "scripts/kb/write_utils.py"),
        "Hard-fail behavior": (
            "Malformed batch JSON",
            "lock unavailable",
            "path outside repo boundary",
            "MAX_BATCH_SIZE (100)",
            "fail closed",
        ),
    },
    "scripts/validation/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "narrower contract"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/**", "scripts/kb/contracts.py"),
        "Hard-fail behavior": ("unsupported checks", "partial validator results", "write attempt"),
    },
    "scripts/validation/validate_afk_output.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/page-template.md", "ADR-014"),
        "Hard-fail behavior": ("path outside", "missing input file", "write attempt", "fail closed"),
    },
    "scripts/validation/snapshot_knowledgebase.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("scripts/_optional_surface_common.py", "scripts/kb/contracts.py"),
        "Hard-fail behavior": ("ALLOWED_SNAPSHOT_ROOTS", "fail closed"),
    },
    "scripts/validation/classify_stale.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("ADR-014",),
        "Hard-fail behavior": ("freshness report json", "fail closed"),
    },
    "scripts/validation/check_doc_freshness.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("scripts/kb/page_template_utils.py", "scripts/_optional_surface_common.py"),
        "Hard-fail behavior": ("SCOPE_ROOTS", "fail closed"),
    },
    "scripts/validation/check_issue_closure_evidence.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("docs/mvp-runbook.md", "scripts/_optional_surface_common.py"),
        "Hard-fail behavior": ("closedat", "cli failure", "fail closed"),
    },
    "scripts/reporting/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "narrower contract"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("schema/**",),
        "Hard-fail behavior": ("unsupported report checks", "undeclared artifacts", "fail closed"),
    },
    "scripts/reporting/content_quality_report.py` — `persist` mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/reports/content-quality-*.json",),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("schema/report-artifact-contract.md", "scripts/_optional_surface_common.py"),
        "Hard-fail behavior": ("schema validation failure", "lock contention", "fail closed"),
    },
    "scripts/reporting/quality_runtime.py` — `score-update` and `report` modes": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/reports/quality-scores-*.json", "wiki/reports/quality-report-*.json"),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("schema/report-artifact-contract.md", "scripts/_optional_surface_common.py"),
        "Hard-fail behavior": ("schema validation failure", "lock contention", "fail closed"),
    },
    "scripts/reporting/coverage_report.py` — `summary` and `persist` modes": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/reports/coverage-report-*.json",),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("schema/report-artifact-contract.md", "scripts/_optional_surface_common.py"),
        "Hard-fail behavior": ("Missing approval", "lock contention", "wiki path escapes boundary", "fail closed"),
    },
    "scripts/context/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None direct", "delegate"),
        "Lock requirements": ("Delegated writer", "ADR-005"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "delegated artifact schema owner"),
        "Hard-fail behavior": ("unsupported check", "undeclared direct write", "fail closed"),
    },
    "scripts/context/manage_context_pages.py` — `publish-status` mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None direct", "wiki/status.md"),
        "Lock requirements": ("wiki/.kb_write.lock", "ADR-005"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "sync-knowledgebase-state"),
        "Hard-fail behavior": ("staged-status-path", "undeclared direct write", "fail closed"),
    },
    "scripts/context/fill_context_pages.py` — `apply` mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": (".github/skills/**", "docs/**"),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/_optional_surface_common.py", "scripts/kb/write_utils.py"),
        "Hard-fail behavior": ("path outside write roots", "SHA drift", "placeholder markers", "fail closed"),
    },
    "scripts/maintenance/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None direct", "narrower row"),
        "Lock requirements": ("ADR-005",),
        "Artifact / schema owners": ("schema/**", "delegated artifact schema owner"),
        "Hard-fail behavior": ("partial audit/validator results", "undeclared writes", "fail closed"),
    },
    "scripts/maintenance/generate_docs.py` — `apply` mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("docs/**",),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/_optional_surface_common.py", "scripts/kb/write_utils.py"),
        "Hard-fail behavior": ("path outside docs/**", "SHA drift", "lock unavailable", "fail closed"),
    },
    ".github/skills/log-intake-rejection/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("raw/rejected/", "write-once", "wiki/log.md"),
        "Lock requirements": ("raw/.rejection-registry.lock", "wiki/.kb_write.lock"),
        "Artifact / schema owners": ("schema/rejection-registry-contract.md", "docs/decisions/ADR-013-rejected-source-registry.md"),
        "Hard-fail behavior": ("duplicate sha256", "path outside", "lock unavailable", "fail closed", "append failure"),
    },
    ".github/skills/extract-entities-and-claims/logic/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "writes are forbidden"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("scripts/kb/page_template_utils.py", "schema/page-template.md"),
        "Hard-fail behavior": ("soft_skipped", "hard exit 1", "missing source file"),
    },
    ".github/skills/synthesize-entity-page/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/entities/",),
        "Lock requirements": ("wiki/.kb_write.lock",),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "schema/page-template.md"),
        "Hard-fail behavior": ("lock_unavailable", "ambiguous dedup", "slug collision", "fail closed"),
    },
    ".github/skills/synthesize-concept-page/logic/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/concepts/",),
        "Lock requirements": ("wiki/.kb_write.lock",),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "schema/page-template.md"),
        "Hard-fail behavior": ("lock_unavailable", "ambiguous dedup", "slug collision", "fail closed"),
    },
    "scripts/ingest/**": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None by default", "raw/processed/**", "wiki/**"),
        "Lock requirements": ("ADR-005", "wiki/log.md"),
        "Artifact / schema owners": ("ADR-006", "schema/**", "scripts/kb/contracts.py"),
        "Hard-fail behavior": ("missing provenance", "partial validator result", "fail closed"),
    },
    "scripts/ingest/convert_sources_to_md.py` — `apply` mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("raw/processed/**", "write-once", "immutable post-write"),
        "Lock requirements": ("wiki/.kb_write.lock", "--approval approved"),
        "Artifact / schema owners": ("ADR-006", "ADR-010"),
        "Hard-fail behavior": ("raw/inbox", "output already exists", "lock unavailable", "fail closed"),
    },
    "scripts/github_monitor/**": {
        "Runtime mode": ("read-only only", "blocking-only"),
        "Writable paths": ("raw/assets/**", "raw/github-sources/**", "wiki/**"),
        "Lock requirements": ("raw/.github-sources.lock", "wiki/.kb_write.lock", "ADR-012"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "schema/github-source-registry-contract.md", "ADR-012"),
        "Hard-fail behavior": ("missing provenance", "partial validator result", "fail closed"),
    },
    "scripts/github_monitor/check_drift.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/github-source-registry-contract.md", "schema/drift-report-contract.md", "ADR-012"),
        "Hard-fail behavior": ("invalid registry json", "api shape violation", "path traversal", "fail closed"),
    },
    "scripts/github_monitor/classify_drift.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/drift-report-contract.md", "ADR-014"),
        "Hard-fail behavior": ("invalid drift report json", "governed-path write attempt", "fail closed"),
    },
    "scripts/github_monitor/fetch_content.py` — write mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("raw/assets/", "raw/github-sources/", "last_fetched_"),
        "Lock requirements": ("raw/.github-sources.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "scripts/kb/contracts.py", "schema/github-source-registry-contract.md"),
        "Hard-fail behavior": ("sha-256 mismatch", "path traversal", "lock unavailable", "last_applied_", "fail closed"),
    },
    "scripts/github_monitor/synthesize_diff.py` — write mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/**", "raw/github-sources/", "last_applied_"),
        "Lock requirements": ("wiki/.kb_write.lock", "raw/.github-sources.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "scripts/kb/contracts.py", "schema/github-source-registry-contract.md"),
        "Hard-fail behavior": ("diff injection", "lock unavailable", "last_applied_", "fail closed"),
    },
    "scripts/github_monitor/create_issues.py": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/github-source-registry-contract.md", "ADR-014"),
        "Hard-fail behavior": ("malformed json", "fail closed"),
    },
    "scripts/github_monitor/relay_http.py": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None", "repository_dispatch"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": (
            "scripts/github_monitor/_relay.py",
            "dispatch_client.py",
            "ADR-012",
        ),
        "Hard-fail behavior": (
            "missing required env",
            "relay validation failure",
            "dispatch failure",
            "fail closed",
        ),
    },
    "scripts/hooks/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "scripts/kb/page_template_utils.py", "scripts/kb/agents_matrix_utils.py", "scripts/kb/github_customizations_graph.py"),
        "Hard-fail behavior": ("staged governance lock file", "missing required frontmatter field", "invalid hooks.json", "fail closed"),
    },
    "scripts/hooks/check_instructions_applyto_present.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": (".github/instructions", "ADR-016"),
        "Hard-fail behavior": (
            "missing frontmatter",
            "missing applyTo",
            "empty applyTo",
            "unreadable staged content",
            "invalid instruction path",
            "fail closed",
        ),
    },
    "scripts/hooks/check_adr_cross_ref.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("docs/decisions/README.md",),
        "Hard-fail behavior": ("ADR status line changed", "amended", "README.md", "fail closed"),
    },
    "scripts/hooks/check_stub_archive_path.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("docs/ideas",),
        "Hard-fail behavior": ("stub", "raw/inbox", "wiki/sources", "fail closed"),
    },
    "scripts/hooks/locality_postuse_advisory.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Read-only / prerequisite paths": (
            "PostToolUse",
            "tool_result",
            ".github/copilot-instructions.md",
            "AGENTS.md",
        ),
        "Lock requirements": ("None", "forbidden"),
        "Artifact / schema owners": ("ADR-028", ".github/hooks/hooks.json"),
        "Hard-fail behavior": ("exit 0", "no warning", "stdout advisory", "never block"),
    },
    "scripts/drive_monitor/**": {
        "Runtime mode": ("read-only only", "blocking-only"),
        "Writable paths": ("raw/assets/gdrive/**", "raw/drive-sources/**", "wiki/**"),
        "Lock requirements": ("raw/.drive-sources.lock", "wiki/.kb_write.lock", "ADR-021"),
        "Artifact / schema owners": ("scripts/kb/contracts.py", "schema/drive-source-registry-contract.md", "ADR-021"),
        "Hard-fail behavior": ("missing provenance", "partial validator result", "fail closed"),
    },
    "scripts/drive_monitor/check_drift.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/drive-source-registry-contract.md", "schema/drift-report-contract.md", "ADR-021"),
        "Hard-fail behavior": ("invalid registry json", "Drive API error", "path traversal", "fail closed"),
    },
    "scripts/drive_monitor/classify_drift.py": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "forbidden"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/drive-source-registry-contract.md", "ADR-014"),
        "Hard-fail behavior": ("invalid drift report json", "governed-path write attempt", "fail closed"),
    },
    "scripts/drive_monitor/fetch_content.py` — write mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("raw/assets/gdrive/", "raw/drive-sources/", "last_fetched_"),
        "Lock requirements": ("raw/.drive-sources.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "scripts/kb/contracts.py", "schema/drive-source-registry-contract.md"),
        "Hard-fail behavior": ("sha-256 mismatch", "path traversal", "lock unavailable", "last_applied_", "fail closed"),
    },
    "scripts/drive_monitor/synthesize_diff.py` — write mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("wiki/**", "raw/drive-sources/", "last_applied_"),
        "Lock requirements": ("wiki/.kb_write.lock", "raw/.drive-sources.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "scripts/kb/contracts.py", "schema/drive-source-registry-contract.md"),
        "Hard-fail behavior": ("lock unavailable", "path traversal", "last_applied_", "fail closed"),
    },
    "scripts/drive_monitor/create_issues.py": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None",),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/drive-source-registry-contract.md", "ADR-014"),
        "Hard-fail behavior": ("malformed json", "fail closed"),
    },
    "scripts/drive_monitor/advance_cursor.py` — write mode only": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("raw/drive-sources/", "changes_page_token"),
        "Lock requirements": ("raw/.drive-sources.lock", "--approval approved"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py", "scripts/kb/contracts.py", "schema/drive-source-registry-contract.md"),
        "Hard-fail behavior": ("lock unavailable", "alias with pipeline errors", "fail closed"),
    },
    "scripts/drive_monitor/relay_http.py": {
        "Runtime mode": ("blocking-only",),
        "Writable paths": ("None", "repository_dispatch"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("scripts/drive_monitor/_relay.py", "dispatch_client.py", "ADR-021"),
        "Hard-fail behavior": ("missing required env", "relay validation failure", "dispatch failure", "fail closed"),
    },
    "scripts/init.py` — `--fresh` mode only": {
        "Runtime mode": ("blocking-only", "destructive"),
        "Writable paths": ("wiki/log.md", "wiki/index.md", "raw/processed/SPEC.md"),
        "Lock requirements": ("wiki/.kb_write.lock", "INIT_ALLOW_WIPE", "--fresh"),
        "Artifact / schema owners": ("scripts/kb/write_utils.py",),
        "Hard-fail behavior": ("symlink", "sentinel", "fail closed"),
    },
}


def _extract_markdown_section(text: str, heading: str) -> str:
    pattern = rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, text)
    if match is None:
        raise AssertionError(f"AGENTS.md is missing section: {heading}")
    return match.group(1)


def _parse_markdown_table(section_text: str) -> list[dict[str, str]]:
    table_lines = [line for line in section_text.splitlines() if line.startswith("|")]
    if len(table_lines) < 3:
        raise AssertionError("Expected markdown table with header, separator, and rows")

    def normalize_cell(cell: str) -> str:
        return cell.strip().strip("`")

    headers = [normalize_cell(cell) for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for row_line in table_lines[2:]:
        cells = [normalize_cell(cell) for cell in row_line.strip("|").split("|")]
        if len(cells) != len(headers):
            raise AssertionError(f"Malformed markdown table row: {row_line}")
        rows.append(dict(zip(headers, cells, strict=True)))
    return rows


class FrameworkWriteSurfaceMatrixTests(unittest.TestCase):
    def test_agents_write_surface_matrix_declares_current_and_future_surfaces(self) -> None:
        agents_text = AGENTS_PATH.read_text(encoding="utf-8")
        matrix_rows = _parse_markdown_table(
            _extract_markdown_section(agents_text, WRITE_SURFACE_MATRIX_HEADING)
        )
        surfaces = [row["Surface"] for row in matrix_rows]
        self.assertEqual(
            len(surfaces),
            len(set(surfaces)),
            "AGENTS.md write-surface matrix must not contain duplicate Surface rows",
        )
        self.assertEqual(
            surfaces.count("scripts/kb/checkpoint_registry.py"),
            1,
            "AGENTS.md must declare exactly one row for scripts/kb/checkpoint_registry.py",
        )
        rows_by_surface = {row["Surface"]: row for row in matrix_rows}

        self.assertEqual(
            set(rows_by_surface),
            set(EXPECTED_WRITE_SURFACE_MATRIX_ROWS),
            "AGENTS.md write-surface matrix must cover every declared skill-local and scripts/** surface",
        )

        for surface, expectations in EXPECTED_WRITE_SURFACE_MATRIX_ROWS.items():
            row = rows_by_surface[surface]
            for column, required_snippets in expectations.items():
                with self.subTest(surface=surface, column=column):
                    normalized_column = row[column].lower()
                    for snippet in required_snippets:
                        self.assertIn(
                            snippet.lower(),
                            normalized_column,
                            f"{surface} row must mention '{snippet}' in column '{column}'",
                        )

    def test_existing_skill_logic_directories_are_declared_in_agents_matrix(self) -> None:
        agents_text = AGENTS_PATH.read_text(encoding="utf-8")
        matrix_rows = _parse_markdown_table(
            _extract_markdown_section(agents_text, WRITE_SURFACE_MATRIX_HEADING)
        )
        declared_surfaces = {row["Surface"] for row in matrix_rows}
        expected_skill_surfaces = {
            f".github/skills/{logic_dir.parent.name}/logic/**"
            for logic_dir in Path(".github/skills").glob("*/logic")
            if logic_dir.is_dir()
        }

        self.assertTrue(expected_skill_surfaces, "Expected at least one skill logic directory")
        self.assertTrue(
            expected_skill_surfaces.issubset(declared_surfaces),
            "Every current .github/skills/*/logic directory must have a matrix row in AGENTS.md",
        )

    def test_agents_matrix_preserves_fail_closed_policy_for_protected_paths(self) -> None:
        agents_text = AGENTS_PATH.read_text(encoding="utf-8")
        required_controls = (
            "New surfaces without a row are undeclared and must hard-fail",
            "Unsupported checks, missing prerequisites, or partial validator results are hard failures",
            "protected/write path",
            "deny-by-default",
        )
        for control in required_controls:
            self.assertIn(
                control,
                agents_text,
                f"AGENTS.md must preserve fail-closed policy language: {control}",
            )


if __name__ == "__main__":
    unittest.main()
