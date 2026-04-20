"""Unit verification-matrix coverage for source refs, log policy, and index determinism."""

from __future__ import annotations

import unittest

from scripts.kb import update_index, write_utils
from scripts.kb.sourceref import SourceRefValidationError, parse_sourceref
from tests.kb.harnesses import KnowledgebaseWorkspaceTestCase


class UnitVerificationMatrixTests(KnowledgebaseWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_verification_unit"
    WIKI_SECTIONS = ("sources", "entities", "concepts", "analyses")  # keep in sync with page_template_utils.TOPICAL_NAMESPACES

    def _write_page(self, relative_path: str, *, title: str, page_type: str, confidence: str) -> None:
        self.write_wiki_page(
            relative_path,
            "\n".join(
                [
                    "---",
                    f"type: {page_type}",
                    f'title: "{title}"',
                    "status: active",
                    "sources: []",
                    "open_questions: []",
                    f"confidence: {confidence}",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags:",
                    "  - test",
                    "---",
                    "",
                    f"# {title}",
                    "",
                    "Fixture page.",
                    "",
                ]
            ),
        )

    def test_sourceref_round_trips_as_canonical_format(self) -> None:
        canonical = (
            "repo://owner/repo/raw/processed/source-a.md@"
            + ("a" * 40)
            + "#L1-L2?sha256="
            + ("b" * 64)
        )

        parsed = parse_sourceref(canonical)

        self.assertEqual(parsed.to_canonical(), canonical)

    def test_sourceref_rejects_path_traversal_segments(self) -> None:
        traversal_ref = (
            "repo://owner/repo/raw/processed/../secrets.md@abc1234"
            + "#L1-L2?sha256="
            + ("f" * 64)
        )

        with self.assertRaises(SourceRefValidationError) as context:
            parse_sourceref(traversal_ref)

        self.assertEqual(context.exception.reason_code, "path_traversal")

    def test_log_only_state_changes_is_noop_when_state_unchanged(self) -> None:
        log_path = self.workspace / "wiki" / "log.md"

        appended = write_utils.append_log_only_state_changes(
            self.workspace,
            "- should not append",
            state_changed=False,
        )

        self.assertFalse(appended)
        self.assertFalse(log_path.exists())

    def test_index_generation_is_deterministic_for_same_inputs(self) -> None:
        self._write_page(
            "sources/zeta-source.md",
            title="Zeta Source",
            page_type="source",
            confidence="2",
        )
        self._write_page(
            "sources/alpha-source.md",
            title="Alpha Source",
            page_type="source",
            confidence="5",
        )

        first_render = update_index.generate_index_content(self.wiki_root)
        second_render = update_index.generate_index_content(self.wiki_root)

        self.assertEqual(first_render, second_render)
        self.assertLess(
            first_render.index("- [Alpha Source](sources/alpha-source.md)"),
            first_render.index("- [Zeta Source](sources/zeta-source.md)"),
        )


if __name__ == "__main__":
    unittest.main()
