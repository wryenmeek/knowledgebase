"""Persona contract and reference checks for framework personas."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from tests.kb.harnesses import parse_frontmatter_fields, section_body


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = REPO_ROOT / ".github" / "agents"
INGEST_SAFE_PERSONAS: tuple[str, ...] = (
    "knowledgebase-orchestrator",
    "source-intake-steward",
    "evidence-verifier",
    "policy-arbiter",
)
CONTROLLED_POST_GOVERNANCE_PERSONAS: tuple[str, ...] = (
    "synthesis-curator",
    "query-synthesist",
    "topology-librarian",
)
OPERATIONS_PERSONAS: tuple[str, ...] = (
    "maintenance-auditor",
    "change-patrol",
    "quality-analyst",
)
ALL_PERSONAS: tuple[str, ...] = (
    *INGEST_SAFE_PERSONAS,
    *CONTROLLED_POST_GOVERNANCE_PERSONAS,
    *OPERATIONS_PERSONAS,
)
PERSONA_FILES: dict[str, Path] = {
    persona: AGENTS_ROOT / f"{persona}.md" for persona in ALL_PERSONAS
}
REQUIRED_SECTIONS: tuple[str, ...] = (
    "## Mission / role",
    "## Inputs",
    "## Outputs",
    "## Required skills / upstream references",
    "## Stop conditions / fail-closed behavior",
    "## Escalate to the Human Steward when",
    "## Downstream handoff",
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
BACKTICK_PATH_RE = re.compile(
    r"`((?:\.github|docs|schema|scripts|tests|wiki|raw)/[^`<>]*|AGENTS\.md|README\.md)`"
)
DEV_TOOL_PERSONAS: tuple[str, ...] = (
    "code-reviewer",
    "security-auditor",
    "test-engineer",
)
DEV_TOOL_PERSONA_FILES: dict[str, Path] = {
    persona: AGENTS_ROOT / f"{persona}.md" for persona in DEV_TOOL_PERSONAS
}


class FrameworkPersonaTests(unittest.TestCase):
    def test_expected_persona_files_exist(self) -> None:
        for persona, path in PERSONA_FILES.items():
            with self.subTest(persona=persona):
                self.assertTrue(path.is_file())

    def test_persona_frontmatter_matches_filename_and_discovery_requirements(self) -> None:
        for persona, path in PERSONA_FILES.items():
            frontmatter = self._parse_frontmatter(path.read_text(encoding="utf-8"))
            description = frontmatter.get("description", "")
            with self.subTest(persona=persona):
                self.assertEqual(frontmatter.get("name"), persona)
                self.assertIn("Use when", description)
                self.assertGreater(len(description.strip()), len("Use when"))

    def test_persona_docs_cover_required_contract_sections(self) -> None:
        for persona, path in PERSONA_FILES.items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(persona=persona):
                for heading in REQUIRED_SECTIONS:
                    body = self._section_body(text, heading)
                    self.assertTrue(body.strip(), f"Missing body for {heading}")
                self.assertRegex(self._section_body(text, "## Inputs"), r"(?m)^- ")
                self.assertRegex(self._section_body(text, "## Outputs"), r"(?m)^- ")
                self.assertRegex(
                    self._section_body(text, "## Outputs"),
                    r"(?m)^- Handoff artifact:",
                )
                self.assertRegex(
                    self._section_body(text, "## Outputs"),
                    r"(?m)^- Escalation artifact:",
                )
                self.assertRegex(
                    self._section_body(text, "## Required skills / upstream references"),
                    r"(?m)^- ",
                )
                self.assertRegex(
                    self._section_body(text, "## Stop conditions / fail-closed behavior"),
                    r"(?m)^- Stop",
                )
                self.assertRegex(
                    self._section_body(text, "## Escalate to the Human Steward when"),
                    r"(?m)^- ",
                )
                self.assertRegex(
                    self._section_body(text, "## Downstream handoff"),
                    r"(?m)^- ",
                )
                self.assertRegex(
                    self._section_body(text, "## Downstream handoff"),
                    r"(?m)^- Downstream artifact:",
                )
                self.assertRegex(
                    self._section_body(text, "## Downstream handoff"),
                    r"(?m)(`[a-z0-9-]+`|Human Steward)",
                )

    def test_orchestrator_declares_explicit_safe_lane_order(self) -> None:
        text = PERSONA_FILES["knowledgebase-orchestrator"].read_text(encoding="utf-8")
        expected_steps = (
            "1. `knowledgebase-orchestrator`",
            "2. `source-intake-steward`",
            "3. `evidence-verifier`",
            "4. `policy-arbiter`",
        )
        position = -1
        for step in expected_steps:
            current = text.find(step)
            with self.subTest(step=step):
                self.assertGreater(current, position)
            position = current
        self.assertIn("`synthesis-curator`", text)
        self.assertIn("`query-synthesist`", text)
        self.assertIn("`topology-librarian`", text)

    def test_orchestrator_afk_lane_declared_per_adr014(self) -> None:
        """ADR-014 §9: The orchestrator must declare an AFK lane and its constraints.

        This test enforces that the AFK lane is explicitly documented in the
        orchestrator persona so future persona additions cannot silently fall into
        the bypass scope.  Three properties are required:
        1. The AFK lane is named and references ADR-014.
        2. The lane requires a lock and audit log entry.
        3. The lane is post-publication subject to change-patrol review.
        """
        text = PERSONA_FILES["knowledgebase-orchestrator"].read_text(encoding="utf-8")
        with self.subTest("afk_lane_references_adr014"):
            self.assertIn("ADR-014", text)
        with self.subTest("afk_lane_requires_lock_and_log"):
            self.assertIn("lock", text.lower())
            self.assertIn("classification: afk", text)
        with self.subTest("afk_lane_requires_change_patrol"):
            self.assertIn("change-patrol", text)

    def test_persona_handoffs_follow_ingest_and_controlled_downstream_lanes(self) -> None:
        self.assertIn(
            "- Normal ingest-safe handoff: `source-intake-steward`",
            PERSONA_FILES["knowledgebase-orchestrator"].read_text(encoding="utf-8"),
        )
        self.assertIn(
            "- Success: `evidence-verifier` receives the intake package and provenance record",
            PERSONA_FILES["source-intake-steward"].read_text(encoding="utf-8"),
        )
        self.assertIn(
            "- Success: `policy-arbiter`",
            PERSONA_FILES["evidence-verifier"].read_text(encoding="utf-8"),
        )
        policy_text = PERSONA_FILES["policy-arbiter"].read_text(encoding="utf-8")
        self.assertIn(
            "- On rejection or ambiguity: return to `knowledgebase-orchestrator`",
            policy_text,
        )
        self.assertIn("- On approval for source-backed drafting: `synthesis-curator`", policy_text)
        self.assertIn(
            "- On approval for query or discovery follow-up: `query-synthesist` or `topology-librarian`",
            policy_text,
        )

    def test_governance_and_policy_checks_block_write_capable_steps(self) -> None:
        orchestrator_text = PERSONA_FILES["knowledgebase-orchestrator"].read_text(
            encoding="utf-8"
        )
        intake_text = PERSONA_FILES["source-intake-steward"].read_text(encoding="utf-8")
        verifier_text = PERSONA_FILES["evidence-verifier"].read_text(encoding="utf-8")
        arbiter_text = PERSONA_FILES["policy-arbiter"].read_text(encoding="utf-8")
        synthesis_text = PERSONA_FILES["synthesis-curator"].read_text(encoding="utf-8")
        query_text = PERSONA_FILES["query-synthesist"].read_text(encoding="utf-8")
        topology_text = PERSONA_FILES["topology-librarian"].read_text(encoding="utf-8")

        self.assertIn(
            "does not authorize synthesis or topology writes under `wiki/` before evidence and policy review succeed",
            orchestrator_text,
        )
        self.assertIn(
            "No handoff to any synthesis or topology persona is allowed from this role",
            intake_text,
        )
        self.assertIn(
            "does not approve writes under `wiki/` on its own",
            verifier_text,
        )
        self.assertIn(
            "This role never hands off directly to synthesis, topology, or wiki-writing automation",
            verifier_text,
        )
        self.assertIn(
            "explicitly marked provisional SourceRefs may pass intake evidence review",
            verifier_text,
        )
        self.assertIn("authoritative review mode", verifier_text)
        self.assertIn(
            "Governance must pass here before any downstream `synthesis-curator`, `query-synthesist`, or `topology-librarian` work can begin",
            arbiter_text,
        )
        self.assertIn(
            "Approval never authorizes direct wiki writes",
            arbiter_text,
        )
        self.assertIn(
            "passed `source-intake-steward`, `evidence-verifier`, and `policy-arbiter`",
            synthesis_text,
        )
        self.assertIn(
            "No direct write, redirect, or out-of-band persistence is permitted from this persona",
            synthesis_text,
        )
        self.assertIn("read `wiki/index.md` and the relevant pages under `wiki/` first", query_text)
        self.assertIn("scripts/kb/persist_query.py", query_text)
        self.assertIn(
            "No direct wiki write or persistence-side effect is permitted from this persona",
            query_text,
        )
        self.assertIn("treating taxonomy and information architecture as explicit policy", topology_text)
        self.assertIn("does not invent a second runtime", topology_text)
        self.assertIn(
            "No direct bulk rewrite, ungated redirect creation, or out-of-band write is permitted from this persona",
            topology_text,
        )

    def test_synthesis_curator_consumes_explicit_knowledge_structure_skills(self) -> None:
        text = PERSONA_FILES["synthesis-curator"].read_text(encoding="utf-8")
        for skill in (
            ".github/skills/extract-entities-and-claims/SKILL.md",
            ".github/skills/information-architecture-and-taxonomy/SKILL.md",
            ".github/skills/ontology-and-entity-modeling/SKILL.md",
            ".github/skills/knowledge-schema-and-metadata-governance/SKILL.md",
            ".github/skills/entity-resolution-and-canonicalization/SKILL.md",
        ):
            with self.subTest(skill=skill):
                self.assertIn(skill, text)

    def test_query_and_synthesis_personas_reference_governed_workflow_skills(self) -> None:
        query_text = PERSONA_FILES["query-synthesist"].read_text(encoding="utf-8")
        synthesis_text = PERSONA_FILES["synthesis-curator"].read_text(encoding="utf-8")

        for skill in (
            ".github/skills/retrieve-from-index/SKILL.md",
            ".github/skills/synthesize-cited-answer/SKILL.md",
            ".github/skills/prepare-high-value-synthesis-handoff/SKILL.md",
            ".github/skills/handoff-query-derived-page/SKILL.md",
        ):
            with self.subTest(query_skill=skill):
                self.assertIn(skill, query_text)

        for skill in (
            ".github/skills/record-open-questions/SKILL.md",
            ".github/skills/enforce-npov/SKILL.md",
        ):
            with self.subTest(synthesis_skill=skill):
                self.assertIn(skill, synthesis_text)

        self.assertIn(
            "pass through `prepare-high-value-synthesis-handoff` and `handoff-query-derived-page`, then return to `knowledgebase-orchestrator`",
            query_text,
        )
        self.assertIn(
            "any durable publication or persistence candidate returns to governed review rather than bypassing the control plane",
            synthesis_text,
        )

    def test_operations_personas_preserve_governed_mvp_boundary(self) -> None:
        maintenance_text = PERSONA_FILES["maintenance-auditor"].read_text(encoding="utf-8")
        change_text = PERSONA_FILES["change-patrol"].read_text(encoding="utf-8")
        quality_text = PERSONA_FILES["quality-analyst"].read_text(encoding="utf-8")

        self.assertIn("semantic discipline, not a formatting-only cleanup pass", maintenance_text)
        self.assertIn("Heavyweight maintenance automation remains deferred outside MVP", maintenance_text)
        self.assertIn("No direct bulk rewrite, archive action, or out-of-band write is permitted", maintenance_text)
        self.assertIn(
            "return to `knowledgebase-orchestrator`, which may reopen `topology-librarian`",
            maintenance_text,
        )
        self.assertNotIn(
            "- Discoverability or index-safe structural follow-up within cleared scope: `topology-librarian`",
            maintenance_text,
        )

        self.assertIn("does not invent a broad repo crawler, daemon, webhook mesh", change_text)
        self.assertIn("policy/citation-risk review is recommendation-first", change_text.lower())
        self.assertIn(".github/skills/policy-diff-review/SKILL.md", change_text)
        self.assertIn(".github/skills/log-patrol-incident/SKILL.md", change_text)
        self.assertIn("Policy-diff review bundle", change_text)
        self.assertIn("`knowledgebase-orchestrator`", change_text)
        self.assertIn("No direct revert, silent suppression, or out-of-band write is permitted", change_text)
        self.assertIn("no direct remediation, revert, or cleanup path opens from this persona", change_text)
        self.assertIn(
            "`knowledgebase-orchestrator` to reopen `topology-librarian` only within the approved scope",
            change_text,
        )
        self.assertNotIn(
            "- Cleared structural/discovery follow-up only: `topology-librarian` within the approved scope",
            change_text,
        )

        self.assertIn("existing repository evidence", quality_text)
        self.assertIn("defer rather than invent dashboards, daemons, crawlers, or external reporting systems", quality_text)
        self.assertIn("No direct telemetry rollout, quality-score writeback, or out-of-band write is permitted", quality_text)
        self.assertIn("Recommendation-only review may use repo-local prioritization evidence", quality_text)
        self.assertIn("score-updating or reporting-backed modes stay disabled until an explicit reporting/egress approval and contract exist", quality_text)
        self.assertIn(
            "`knowledgebase-orchestrator`, which may route to `topology-librarian`",
            quality_text,
        )
        self.assertNotIn(
            "- Discovery/structure recommendation within existing policy: `topology-librarian`",
            quality_text,
        )

    def test_persona_repo_references_resolve(self) -> None:
        for persona, path in PERSONA_FILES.items():
            text = path.read_text(encoding="utf-8")
            targets = {
                *BACKTICK_PATH_RE.findall(text),
                *(
                    target.split("#", 1)[0]
                    for target in MARKDOWN_LINK_RE.findall(text)
                    if target and "://" not in target
                ),
            }
            for target in sorted(targets):
                with self.subTest(persona=persona, target=target):
                    self.assertTrue(self._resolve_doc_target(path, target).exists())

    def _parse_frontmatter(self, text: str) -> dict[str, str]:
        return parse_frontmatter_fields(text, subject="Persona file")

    def _section_body(self, text: str, heading: str) -> str:
        return section_body(text, heading)

    def _resolve_doc_target(self, source_path: Path, target: str) -> Path:
        return _resolve_doc_target(source_path, target)


def _resolve_doc_target(source_path: Path, target: str) -> Path:
    if target.startswith("/"):
        return Path(target)
    if target in {"AGENTS.md", "README.md"} or target.startswith(
        (".github/", "docs/", "schema/", "scripts/", "tests/", "wiki/", "raw/")
    ):
        return (REPO_ROOT / target).resolve()
    return (source_path.parent / target).resolve()


class DevToolPersonaTests(unittest.TestCase):
    """Contract checks for dev-tool personas (code-reviewer, security-auditor, test-engineer).

    These personas have a different structure from knowledgebase-workflow personas:
    they use ``## Related skill`` (not ``## Required skills / upstream references``)
    and omit the full knowledgebase contract sections.
    """

    def test_dev_tool_persona_files_exist(self) -> None:
        for persona, path in DEV_TOOL_PERSONA_FILES.items():
            with self.subTest(persona=persona):
                self.assertTrue(path.is_file(), f"Missing: {path}")

    def test_dev_tool_persona_frontmatter(self) -> None:
        for persona, path in DEV_TOOL_PERSONA_FILES.items():
            text = path.read_text(encoding="utf-8")
            frontmatter = parse_frontmatter_fields(text, subject="Dev-tool persona")
            with self.subTest(persona=persona, field="name"):
                self.assertEqual(frontmatter.get("name"), persona)
            with self.subTest(persona=persona, field="description"):
                description = frontmatter.get("description", "")
                self.assertTrue(
                    "Use when" in description or "Use for" in description,
                    f"Description must contain 'Use when' or 'Use for': {description!r}",
                )
            with self.subTest(persona=persona, field="updated_at"):
                raw_value = str(frontmatter.get("updated_at", ""))
                value = raw_value.strip('"').strip("'")
                self.assertRegex(
                    value,
                    r"^\d{4}-\d{2}-\d{2}$",
                    f"Dev-tool persona 'updated_at' must be ISO 8601 date (YYYY-MM-DD), got: {raw_value!r}",
                )

    def test_dev_tool_persona_related_skill_section_exists(self) -> None:
        for persona, path in DEV_TOOL_PERSONA_FILES.items():
            text = path.read_text(encoding="utf-8")
            body = section_body(text, "## Related skill")
            with self.subTest(persona=persona):
                self.assertTrue(body.strip(), "## Related skill section must be non-empty")
                self.assertRegex(body, r"SKILL\.md", "Section must reference a SKILL.md path")

    def test_dev_tool_persona_skill_links_resolve(self) -> None:
        for persona, path in DEV_TOOL_PERSONA_FILES.items():
            text = path.read_text(encoding="utf-8")
            body = section_body(text, "## Related skill")
            targets = {
                *BACKTICK_PATH_RE.findall(body),
                *(
                    t.split("#", 1)[0]
                    for t in MARKDOWN_LINK_RE.findall(body)
                    if t and "://" not in t
                ),
            }
            for target in sorted(targets):
                with self.subTest(persona=persona, target=target):
                    self.assertTrue(
                        _resolve_doc_target(path, target).exists(),
                        f"Broken reference in ## Related skill: {target}",
                    )


if __name__ == "__main__":
    unittest.main()
