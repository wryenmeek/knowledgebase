"""Unit tests for suggest-backlinks logic/ scanner.

Tests are written red-first: the logic module doesn't exist yet when this
file is first committed. The scanner must be read-only, neighborhood-scoped,
and exit cleanly on an empty or sparse corpus.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Add logic/ dir to path so the module can be imported without install
SKILL_LOGIC_DIR = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "skills"
    / "suggest-backlinks"
    / "logic"
)
sys.path.insert(0, str(SKILL_LOGIC_DIR))

import suggest_backlinks as sb  # noqa: E402  (must be after sys.path insert)


class SuggestBacklinksEmptyCorpusTests(unittest.TestCase):
    """Scanner must exit cleanly when the wiki corpus is empty or sparse."""

    def test_empty_wiki_root_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            wiki_root.mkdir()
            candidate = wiki_root / "concepts" / "test-page.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text("---\ntitle: Test Page\n---\n\n# Test Page\n\nSome content.\n")
            proposals = sb.scan(candidate, wiki_root)
            self.assertEqual(proposals, [])

    def test_nonexistent_candidate_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            wiki_root.mkdir()
            proposals = sb.scan(wiki_root / "concepts" / "missing.md", wiki_root)
            self.assertEqual(proposals, [])

    def test_single_page_corpus_no_self_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            (wiki_root / "entities").mkdir(parents=True)
            candidate = wiki_root / "entities" / "part-a.md"
            candidate.write_text(
                "---\ntitle: Part A\n---\n\n# Part A\n\nPart A covers inpatient hospital.\n"
            )
            proposals = sb.scan(candidate, wiki_root)
            self.assertEqual(proposals, [])


class SuggestBacklinksNamespaceScopeTests(unittest.TestCase):
    """Scanner finds unlinked mentions within the same namespace only."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.wiki_root = Path(self._tmpdir.name) / "wiki"
        (self.wiki_root / "entities").mkdir(parents=True)
        (self.wiki_root / "concepts").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _write(self, rel_path: str, content: str) -> Path:
        p = self.wiki_root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_unlinked_mention_in_same_namespace_produces_proposal(self) -> None:
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\nPart B covers outpatient services.\n",
        )
        self._write(
            "entities/medicare-overview.md",
            "---\ntitle: Medicare Overview\n---\n\n# Medicare Overview\n\n"
            "Medicare has four parts: Part A, Part B, Part C, and Part D.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        self.assertTrue(len(proposals) >= 1)
        first = proposals[0]
        self.assertEqual(first.surface_text, "Part B")
        self.assertEqual(first.source_file, "entities/medicare-overview.md")
        self.assertIn("namespace", first.rationale)

    def test_already_linked_mention_is_skipped(self) -> None:
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\nOutpatient services.\n",
        )
        self._write(
            "entities/overview.md",
            "---\ntitle: Overview\n---\n\n# Overview\n\n"
            "See [[Part B]] for outpatient coverage.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        self.assertEqual(proposals, [])

    def test_markdown_linked_mention_is_skipped(self) -> None:
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\nOutpatient services.\n",
        )
        self._write(
            "entities/overview.md",
            "---\ntitle: Overview\n---\n\n# Overview\n\n"
            "[Part B](entities/part-b.md) covers outpatient services.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        self.assertEqual(proposals, [])

    def test_cross_namespace_page_not_scanned(self) -> None:
        """Pages in a different namespace are outside the neighborhood."""
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\nOutpatient services.\n",
        )
        self._write(
            "concepts/outpatient-care.md",
            "---\ntitle: Outpatient Care\n---\n\n# Outpatient Care\n\nPart B covers this.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        # concepts/ is a different namespace — not in scope for entities/ candidate
        self.assertEqual(proposals, [])

    def test_mention_in_code_block_is_skipped(self) -> None:
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\nContent.\n",
        )
        self._write(
            "entities/examples.md",
            "---\ntitle: Examples\n---\n\n# Examples\n\n"
            "```\nPart B example\n```\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        self.assertEqual(proposals, [])

    def test_linked_neighbor_md_link_expansion(self) -> None:
        """Linked-neighbor expansion must follow md link URL paths, not display text."""
        # Candidate in entities/ links via md link to a page in concepts/
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\n"
            "See [Outpatient Care](concepts/outpatient-care.md) for details.\n",
        )
        # The linked page mentions Part B (unlinked)
        self._write(
            "concepts/outpatient-care.md",
            "---\ntitle: Outpatient Care\n---\n\n# Outpatient Care\n\n"
            "Part B covers outpatient services through Medicare.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        sources = {p.source_file for p in proposals}
        self.assertIn("concepts/outpatient-care.md", sources,
                      "Linked-neighbor via md link URL should be scanned")
        neighbor_props = [p for p in proposals if p.source_file == "concepts/outpatient-care.md"]
        self.assertEqual(len(neighbor_props), 1)
        self.assertEqual(neighbor_props[0].rationale, "linked-neighbor")

    def test_linked_neighbor_wikilink_expansion(self) -> None:
        """Linked-neighbor expansion follows [[wikilink]] via kebab-case resolution."""
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\n"
            "See [[outpatient-care]] for details.\n",
        )
        self._write(
            "concepts/outpatient-care.md",
            "---\ntitle: Outpatient Care\n---\n\n# Outpatient Care\n\n"
            "Part B covers outpatient services.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        sources = {p.source_file for p in proposals}
        self.assertIn("concepts/outpatient-care.md", sources,
                      "Linked-neighbor via [[wikilink]] should resolve via kebab")

    def test_candidate_without_frontmatter_derives_title_from_filename(self) -> None:
        """Title falls back to stem-derived name when frontmatter is absent."""
        candidate = self._write(
            "entities/part-b.md",
            "# Part B\n\nOutpatient services.\n",  # no frontmatter block
        )
        self._write(
            "entities/overview.md",
            "---\ntitle: Overview\n---\n\n# Overview\n\nPart B covers outpatient care.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        self.assertTrue(len(proposals) >= 1)
        self.assertEqual(proposals[0].surface_text, "Part B")

    def test_anchored_md_link_still_resolves_neighbor(self) -> None:
        """Anchored md links (#section) are stripped so the page is still found."""
        candidate = self._write(
            "entities/part-b.md",
            "---\ntitle: Part B\n---\n\n# Part B\n\n"
            "See [details](concepts/outpatient-care.md#coverage) here.\n",
        )
        self._write(
            "concepts/outpatient-care.md",
            "---\ntitle: Outpatient Care\n---\n\n# Outpatient Care\n\n"
            "Part B covers this.\n",
        )
        proposals = sb.scan(candidate, self.wiki_root)
        sources = {p.source_file for p in proposals}
        self.assertIn("concepts/outpatient-care.md", sources,
                      "Anchor in md link URL should be stripped during resolution")


class SuggestBacklinksResolveLinkTargetTests(unittest.TestCase):
    """Unit tests for the _resolve_link_target helper."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.wiki_root = Path(self._tmpdir.name) / "wiki"
        (self.wiki_root / "entities").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_http_url_returns_none(self) -> None:
        self.assertIsNone(sb._resolve_link_target("http://cms.gov/page", self.wiki_root))

    def test_https_url_returns_none(self) -> None:
        self.assertIsNone(sb._resolve_link_target("https://example.com/page", self.wiki_root))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(sb._resolve_link_target("", self.wiki_root))

    def test_nonexistent_path_returns_none(self) -> None:
        self.assertIsNone(sb._resolve_link_target("entities/missing.md", self.wiki_root))

    def test_existing_md_path_resolves(self) -> None:
        page = self.wiki_root / "entities" / "part-b.md"
        page.write_text("# Part B\n")
        result = sb._resolve_link_target("entities/part-b.md", self.wiki_root)
        self.assertEqual(result, page.resolve())

    def test_anchored_path_strips_anchor(self) -> None:
        page = self.wiki_root / "entities" / "part-b.md"
        page.write_text("# Part B\n")
        result = sb._resolve_link_target("entities/part-b.md#section", self.wiki_root)
        self.assertEqual(result, page.resolve())

    def test_query_string_stripped(self) -> None:
        page = self.wiki_root / "entities" / "part-b.md"
        page.write_text("# Part B\n")
        result = sb._resolve_link_target("entities/part-b.md?foo=bar", self.wiki_root)
        self.assertEqual(result, page.resolve())

    def test_kebab_wikilink_resolves_across_namespaces(self) -> None:
        (self.wiki_root / "concepts").mkdir(parents=True)
        page = self.wiki_root / "concepts" / "outpatient-care.md"
        page.write_text("# Outpatient Care\n")
        result = sb._resolve_link_target("outpatient-care", self.wiki_root)
        self.assertEqual(result, page.resolve())

    def test_mailto_scheme_returns_none(self) -> None:
        self.assertIsNone(sb._resolve_link_target("mailto:contact@cms.gov", self.wiki_root))

    def test_path_traversal_outside_wiki_root_returns_none(self) -> None:
        """A link like '../scripts/kb/foo.py' must not escape wiki_root."""
        # Create a real file one level above wiki_root to confirm it exists but is rejected
        outside = self.wiki_root.parent / "secret.md"
        outside.write_text("# Secret\n")
        result = sb._resolve_link_target("../secret.md", self.wiki_root)
        self.assertIsNone(result, "Path traversal outside wiki_root must return None")


class SuggestBacklinksProposalStructureTests(unittest.TestCase):
    """BacklinkProposal and scan() return value structure."""

    def test_proposal_to_dict_has_required_keys(self) -> None:
        proposal = sb.BacklinkProposal(
            source_file="entities/overview.md",
            source_line=7,
            surface_text="Part B",
            suggested_link="entities/part-b.md",
            rationale="namespace:entities",
        )
        d = proposal.to_dict()
        for key in ("source_file", "source_line", "surface_text", "suggested_link", "rationale"):
            with self.subTest(key=key):
                self.assertIn(key, d)

    def test_scan_returns_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            wiki_root.mkdir()
            result = sb.scan(wiki_root / "nonexistent.md", wiki_root)
            self.assertIsInstance(result, list)


class SuggestBacklinksMainTests(unittest.TestCase):
    """Smoke tests for the main() CLI entry point."""

    def test_main_emits_json_array_for_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            (wiki_root / "entities").mkdir(parents=True)
            candidate = wiki_root / "entities" / "part-b.md"
            candidate.write_text("---\ntitle: Part B\n---\n\n# Part B\n\nOutpatient coverage.\n")
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sb.main([str(candidate), "--wiki-root", str(wiki_root)])
            self.assertEqual(rc, 0)
            import json
            parsed = json.loads(buf.getvalue())
            self.assertIsInstance(parsed, list)

    def test_main_emits_empty_array_for_nonexistent_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_root = Path(tmpdir) / "wiki"
            wiki_root.mkdir()
            import io, contextlib, json
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sb.main([str(wiki_root / "missing.md"), "--wiki-root", str(wiki_root)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()), [])


if __name__ == "__main__":
    unittest.main()
