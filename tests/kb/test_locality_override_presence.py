from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]

OVERRIDE_HEADING = (
    "## ⚠️ Slash-Command Override: /chronicle improve → "
    "audit-knowledgebase-workspace skill"
)
LOCALITY_INVARIANT_BLOCK = """<!-- LOCALITY-0-INVARIANT: This H2 MUST remain the first H2 under the H1. -->
<!-- Position is load-bearing for the /chronicle improve hard-redirect. -->
<!-- Do not move, demote, or insert another H2 above it without ADR-028 revision. -->"""
OVERRIDE_BLOCK_END = (
    "bypass the locality ladder for this turn (audited)."
)
TRAILER_TEMPLATE = (
    "Locality-4-Justification: <one-line reason explaining why this rule must be "
    "Locality 4>"
)
CONTEXT_TERMS = (
    "instruction ratchet",
    "Locality",
    "trailer soft budget",
    "customizations lock",
)
FALLBACK_REF_PATH = (
    ".github/skills/audit-knowledgebase-workspace/references/locality-ladder.md"
)
OVERRIDE_TWIN_FILES = (
    ".github/copilot-instructions.md",
    "AGENTS.md",
)


def _first_h2_after_h1(text: str) -> str:
    seen_h1 = False
    for line in text.splitlines():
        if not seen_h1 and line.startswith("# "):
            seen_h1 = True
            continue
        if seen_h1 and line.startswith("## "):
            return line
    raise AssertionError("No H2 heading found after H1")


def _extract_override_block(text: str) -> str:
    """Extract the override block as the substring from the invariant comment
    block through the documented OVERRIDE_BLOCK_END marker, inclusive."""
    start_idx = text.index(LOCALITY_INVARIANT_BLOCK)
    end_idx = text.index(OVERRIDE_BLOCK_END, start_idx) + len(OVERRIDE_BLOCK_END)
    return text[start_idx:end_idx]


class TestLocalityOverridePresence(unittest.TestCase):
    def assert_override_block_first_h2(self, relative_path: str) -> None:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        self.assertIn(LOCALITY_INVARIANT_BLOCK, text)
        self.assertIn(f"{LOCALITY_INVARIANT_BLOCK}\n\n{OVERRIDE_HEADING}", text)
        self.assertEqual(OVERRIDE_HEADING, _first_h2_after_h1(text))

        block = _extract_override_block(text)
        self.assertIn("ADR-028", block)
        self.assertIn("Locality-4-Justification:", block)
        self.assertIn("fail closed", block)

    def test_copilot_instructions_override_block_is_first_h2(self) -> None:
        self.assert_override_block_first_h2(".github/copilot-instructions.md")

    def test_agents_override_block_is_first_h2(self) -> None:
        self.assert_override_block_first_h2("AGENTS.md")

    def test_locality_4_justification_trailer_template_documented(self) -> None:
        text = (REPO_ROOT / "docs/templates/locality-4-justification-trailer.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("# Locality 4 Justification Trailer Template", text)
        self.assertIn(TRAILER_TEMPLATE, text)
        self.assertIn("Locality-4-Justification: keep this rule always-on", text)
        self.assertIn("ADR-028", text)
        self.assertIn("soft budget", text)

    def test_context_terms_present(self) -> None:
        text = (REPO_ROOT / ".github/skills/CONTEXT.md").read_text(encoding="utf-8")
        for term in CONTEXT_TERMS:
            with self.subTest(term=term):
                self.assertIn(f"| {term} |", text)

    def test_fallback_reference_path_present_in_both_files(self) -> None:
        """Override block must cite the manual fallback reference path verbatim."""
        for rel in OVERRIDE_TWIN_FILES:
            with self.subTest(file=rel):
                text = (REPO_ROOT / rel).read_text(encoding="utf-8")
                self.assertIn(FALLBACK_REF_PATH, text)

    def test_fallback_reference_file_exists_with_required_sections(self) -> None:
        """Manual fallback reference must be present and operator-actionable."""
        fallback = REPO_ROOT / FALLBACK_REF_PATH
        self.assertTrue(
            fallback.is_file(),
            f"Override block cites {FALLBACK_REF_PATH} which must exist on disk",
        )
        text = fallback.read_text(encoding="utf-8")
        for required in (
            "# Locality Ladder",
            "Locality 0",
            "Locality 4",
            "Paired-deletion",
            "Locality-4-Justification:",
            "audit-knowledgebase-workspace",
        ):
            with self.subTest(section=required):
                self.assertIn(required, text)

    def test_override_block_is_byte_identical_across_both_files(self) -> None:
        """Both override blocks must stay byte-identical to prevent silent drift.

        The block spans from LOCALITY_INVARIANT_BLOCK through OVERRIDE_BLOCK_END.
        Trailing prose between the block end and the next H2 is file-specific
        (each always-on file has its own H1 intro) and is intentionally outside
        the symmetry contract.
        """
        copilot_block = _extract_override_block(
            (REPO_ROOT / ".github/copilot-instructions.md").read_text(encoding="utf-8")
        )
        agents_block = _extract_override_block(
            (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        )
        self.assertEqual(
            copilot_block,
            agents_block,
            "Override block in .github/copilot-instructions.md and AGENTS.md "
            "must stay byte-identical. If you intended to update one, update both.",
        )
