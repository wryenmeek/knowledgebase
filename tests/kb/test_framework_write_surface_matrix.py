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
        "Artifact / schema owners": ("scripts/kb/update_index.py", "scripts/kb/write_utils.py", "schema/taxonomy-contract.md", "schema/governed-artifact-contract.md"),
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
    "scripts/kb/**": {
        "Runtime mode": ("Mixed", "blocking-only"),
        "Writable paths": ("wiki/**", "raw/processed/**"),
        "Lock requirements": ("wiki/.kb_write.lock", "append-only"),
        "Artifact / schema owners": ("raw/processed/SPEC.md", "schema/**"),
        "Hard-fail behavior": ("permission mismatch", "partial validator result", "undeclared writes"),
    },
    "scripts/validation/**": {
        "Runtime mode": ("read-only only",),
        "Writable paths": ("None", "narrower contract"),
        "Lock requirements": ("None",),
        "Artifact / schema owners": ("schema/**", "scripts/kb/contracts.py"),
        "Hard-fail behavior": ("unsupported checks", "partial validator results", "write attempt"),
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
