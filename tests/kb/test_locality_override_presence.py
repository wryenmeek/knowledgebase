from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]

OVERRIDE_HEADING = (
    "## ⚠️ Slash-Command Override: /chronicle improve → "
    "audit-knowledgebase-workspace skill"
)
LOCALITY_INVARIANT_BLOCK = """<!-- LOCALITY-0-INVARIANT: This H2 MUST remain the first H2 under the H1. -->
<!-- Position is load-bearing for the /chronicle improve hard-redirect. -->
<!-- Do not move, demote, or insert another H2 above it without ADR-028 (pending) revision. -->"""
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


def _first_h2_after_h1(text: str) -> str:
    seen_h1 = False
    for line in text.splitlines():
        if not seen_h1 and line.startswith("# "):
            seen_h1 = True
            continue
        if seen_h1 and line.startswith("## "):
            return line
    raise AssertionError("No H2 heading found after H1")


class TestLocalityOverridePresence(unittest.TestCase):
    def assert_override_block_first_h2(self, relative_path: str) -> None:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        self.assertIn(LOCALITY_INVARIANT_BLOCK, text)
        self.assertIn(f"{LOCALITY_INVARIANT_BLOCK}\n\n{OVERRIDE_HEADING}", text)
        self.assertEqual(OVERRIDE_HEADING, _first_h2_after_h1(text))

        block = text[
            text.index(LOCALITY_INVARIANT_BLOCK) : text.index(OVERRIDE_HEADING)
            + len(OVERRIDE_HEADING)
            + 1200
        ]
        self.assertIn("ADR-028 (pending)", block)
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
        self.assertIn("ADR-028 (pending)", text)
        self.assertIn("soft budget", text)

    def test_context_terms_present(self) -> None:
        text = (REPO_ROOT / ".github/skills/CONTEXT.md").read_text(encoding="utf-8")
        for term in CONTEXT_TERMS:
            with self.subTest(term=term):
                self.assertIn(f"| {term} |", text)
