"""Tests for synthesis-curator logic scripts.

Covers:
- validate_extraction_bundle (extract_entities.py)
- title_to_slug, find_duplicate, render_draft_page, validate_draft_frontmatter,
  append_to_existing_page (_synthesis_utils.py)
- run() for synthesize_entity_page.py: create, update, soft-skip, ambiguous match
- run() for synthesize_concept_page.py: create, soft-skip
- run() for extract_entities.py: mocked HTTP, self-correction, soft-skip
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTITY_LOGIC = REPO_ROOT / ".github/skills/synthesize-entity-page/logic"
CONCEPT_LOGIC = REPO_ROOT / ".github/skills/synthesize-concept-page/logic"
EXTRACT_LOGIC = REPO_ROOT / ".github/skills/extract-entities-and-claims/logic"

# Ensure paths are importable before loading any module-under-test
for _p in [str(REPO_ROOT), str(ENTITY_LOGIC)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_module(spec_file: Path, module_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, spec_file)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Load modules once for this test session
import _synthesis_utils as _su
_extract_mod = _load_module(EXTRACT_LOGIC / "extract_entities.py", "extract_entities")
_entity_mod = _load_module(ENTITY_LOGIC / "synthesize_entity_page.py", "synthesize_entity_page")
_concept_mod = _load_module(CONCEPT_LOGIC / "synthesize_concept_page.py", "synthesize_concept_page")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MINIMAL_SOURCE_PAGE = """\
---
type: source
title: "Test Source"
sources: []
open_questions: []
confidence: 3
sensitivity: internal
updated_at: "2024-01-01T00:00:00Z"
tags:
  - test
---

# Test Source

This is a test source page about Medicare Advantage and CMS.
"""

_VALID_BUNDLE = {
    "entities": [
        {
            "title": "Centers for Medicare & Medicaid Services",
            "aliases": ["CMS"],
            "summary": "Federal agency that administers Medicare.",
            "evidence": "CMS oversees Medicare Advantage plans.",
            "tags": ["government", "medicare"],
            "open_questions": [],
        }
    ],
    "concepts": [
        {
            "title": "Medicare Advantage",
            "aliases": ["MA", "Part C"],
            "summary": "Private health insurance plan option under Medicare.",
            "evidence": "Medicare Advantage is an alternative to original Medicare.",
            "tags": ["medicare", "insurance"],
            "open_questions": ["What are enrollment eligibility requirements?"],
        }
    ],
    "source_ref": "repo://owner/repo/wiki/sources/test-source.md@abc123?sha256=deadbeef" + "0" * 48,
    "source_page": "wiki/sources/test-source.md",
    "soft_skipped": False,
}


def _make_workspace(tmp_path: Path) -> Path:
    """Create a minimal wiki workspace."""
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True)
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "sources").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# _synthesis_utils: pure function tests
# ---------------------------------------------------------------------------


class TestTitleToSlug(unittest.TestCase):
    def test_basic_lowercase_hyphenation(self) -> None:
        self.assertEqual(_su.title_to_slug("Medicare Advantage"), "medicare-advantage")

    def test_strips_special_characters(self) -> None:
        self.assertEqual(_su.title_to_slug("Centers for Medicare & Medicaid"), "centers-for-medicare-medicaid")

    def test_collapses_multiple_spaces(self) -> None:
        self.assertEqual(_su.title_to_slug("foo   bar"), "foo-bar")

    def test_empty_string_returns_untitled(self) -> None:
        self.assertEqual(_su.title_to_slug(""), "untitled")

    def test_numbers_preserved(self) -> None:
        self.assertEqual(_su.title_to_slug("Part D 2024"), "part-d-2024")


class TestFindDuplicate(unittest.TestCase):
    _candidates = [
        {"title": "CMS", "aliases": ["Centers for Medicare & Medicaid Services"]},
        {"title": "Medicare Advantage", "aliases": ["MA", "Part C"]},
    ]

    def test_exact_title_match(self) -> None:
        matches = _su.find_duplicate(self._candidates, "CMS", [])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["title"], "CMS")

    def test_alias_match(self) -> None:
        matches = _su.find_duplicate(self._candidates, "Part C", [])
        self.assertEqual(len(matches), 1)

    def test_case_insensitive_match(self) -> None:
        matches = _su.find_duplicate(self._candidates, "cms", [])
        self.assertEqual(len(matches), 1)

    def test_no_match(self) -> None:
        matches = _su.find_duplicate(self._candidates, "Part A", [])
        self.assertEqual(len(matches), 0)

    def test_alias_in_proposed_aliases(self) -> None:
        matches = _su.find_duplicate(self._candidates, "Original Medicare", ["MA"])
        self.assertEqual(len(matches), 1)

    def test_ambiguous_returns_two(self) -> None:
        # Proposed aliases hit both candidates
        matches = _su.find_duplicate(self._candidates, "CMS", ["Part C"])
        self.assertEqual(len(matches), 2)


class TestRenderDraftPage(unittest.TestCase):
    def _rendered(self, **kwargs) -> str:
        defaults = dict(
            page_type="entity",
            title="Test Entity",
            aliases=[],
            source_ref="repo://o/r/wiki/sources/x.md@abc",
            summary="A test entity.",
            evidence="Found in source.",
            tags=["test"],
            open_questions=[],
        )
        defaults.update(kwargs)
        return _su.render_draft_page(**defaults)

    def test_contains_frontmatter_delimiters(self) -> None:
        page = self._rendered()
        self.assertTrue(page.startswith("---\n"))
        self.assertIn("\n---\n", page)

    def test_type_field_set(self) -> None:
        page = self._rendered(page_type="concept")
        self.assertIn("type: concept", page)

    def test_title_in_frontmatter_and_heading(self) -> None:
        page = self._rendered(title="My Entity")
        self.assertIn('title: "My Entity"', page)
        self.assertIn("# My Entity", page)

    def test_open_questions_list(self) -> None:
        page = self._rendered(open_questions=["What is the eligibility?"])
        self.assertIn("What is the eligibility?", page)

    def test_no_open_questions_produces_empty_list(self) -> None:
        page = self._rendered(open_questions=[])
        self.assertIn("open_questions: []", page)

    def test_aliases_in_frontmatter(self) -> None:
        page = self._rendered(aliases=["Alias1", "Alias2"])
        self.assertIn('"Alias1"', page)

    def test_validates_draft_frontmatter(self) -> None:
        page = self._rendered()
        errors = _su.validate_draft_frontmatter(page)
        self.assertEqual(errors, [], f"Draft page had missing keys: {errors}")


# ---------------------------------------------------------------------------
# validate_extraction_bundle (extract_entities.py)
# ---------------------------------------------------------------------------


class TestValidateExtractionBundle(unittest.TestCase):
    def test_valid_bundle(self) -> None:
        errors = _extract_mod.validate_extraction_bundle(_VALID_BUNDLE)
        self.assertEqual(errors, [])

    def test_missing_entities_key(self) -> None:
        bundle = {"concepts": []}
        errors = _extract_mod.validate_extraction_bundle(bundle)
        self.assertIn("missing required key 'entities'", errors)

    def test_non_list_entities(self) -> None:
        bundle = {"entities": {}, "concepts": []}
        errors = _extract_mod.validate_extraction_bundle(bundle)
        self.assertTrue(any("must be a JSON array" in e for e in errors))

    def test_entity_missing_required_key(self) -> None:
        bundle = {
            "entities": [{"title": "X"}],
            "concepts": [],
        }
        errors = _extract_mod.validate_extraction_bundle(bundle)
        self.assertTrue(len(errors) > 0)

    def test_not_a_dict(self) -> None:
        errors = _extract_mod.validate_extraction_bundle([])
        self.assertTrue(len(errors) > 0)

    def test_empty_arrays_valid(self) -> None:
        bundle = {"entities": [], "concepts": []}
        errors = _extract_mod.validate_extraction_bundle(bundle)
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# append_to_existing_page
# ---------------------------------------------------------------------------


class TestAppendToExistingPage(unittest.TestCase):
    def _make_page(self, tmp_path: Path) -> Path:
        page = tmp_path / "cms.md"
        page.write_text(
            '---\ntype: entity\ntitle: "CMS"\nstatus: active\nsources:\n  - "repo://o/r/x.md@a"\n'
            'open_questions: []\nconfidence: 2\nsensitivity: internal\nupdated_at: "2024-01-01T00:00:00Z"\n'
            'tags:\n  - government\n---\n\n# CMS\n',
            encoding="utf-8",
        )
        return page

    def test_new_source_ref_appended(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(Path(td).resolve())
            modified = _su.append_to_existing_page(page, "repo://o/r/y.md@b", [])
            self.assertTrue(modified)
            content = page.read_text(encoding="utf-8")
            self.assertIn("y.md@b", content)

    def test_duplicate_source_ref_not_appended(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(Path(td).resolve())
            modified = _su.append_to_existing_page(page, "repo://o/r/x.md@a", [])
            self.assertFalse(modified)

    def test_open_question_appended(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(Path(td).resolve())
            modified = _su.append_to_existing_page(page, "", ["What is CMS budget?"])
            self.assertTrue(modified)
            content = page.read_text(encoding="utf-8")
            self.assertIn("What is CMS budget?", content)


# ---------------------------------------------------------------------------
# synthesize_entity_page.run()
# ---------------------------------------------------------------------------


class TestSynthesizeEntityPageRun(unittest.TestCase):
    def _bundle_path(self, tmp_path: Path, bundle: dict) -> Path:
        p = tmp_path / "bundle.json"
        p.write_text(json.dumps(bundle), encoding="utf-8")
        return p

    def test_creates_entity_page_from_valid_bundle(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _entity_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            entity_pages = list((root / "wiki" / "entities").glob("*.md"))
            self.assertEqual(len(entity_pages), 1)
            content = entity_pages[0].read_text(encoding="utf-8")
            self.assertIn("Centers for Medicare", content)

    def test_soft_skipped_bundle_produces_no_writes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = dict(_VALID_BUNDLE, soft_skipped=True)
            bp = self._bundle_path(root, bundle)
            rc = _entity_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(list((root / "wiki" / "entities").glob("*.md")), [])

    def test_empty_entities_list_produces_no_writes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = dict(_VALID_BUNDLE, entities=[])
            bp = self._bundle_path(root, bundle)
            rc = _entity_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(list((root / "wiki" / "entities").glob("*.md")), [])

    def test_duplicate_title_appends_to_existing(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            # Pre-create an entity page with the same title
            existing = (
                '---\ntype: entity\ntitle: "Centers for Medicare & Medicaid Services"\n'
                'status: active\nsources:\n  - "repo://o/r/old.md@abc"\n'
                'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
                'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - government\n---\n\n'
                '# Centers for Medicare & Medicaid Services\n'
            )
            (root / "wiki" / "entities" / "cms.md").write_text(existing, encoding="utf-8")
            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _entity_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            # No new file created
            self.assertEqual(len(list((root / "wiki" / "entities").glob("*.md"))), 1)
            # New source ref appended
            updated = (root / "wiki" / "entities" / "cms.md").read_text(encoding="utf-8")
            self.assertIn(_VALID_BUNDLE["source_ref"][:30], updated)  # type: ignore[arg-type]

    def test_ambiguous_match_skips_without_crash(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            # Create two pages that both match (title and alias)
            for i, slug_title in enumerate([
                ("cms", "Centers for Medicare & Medicaid Services"),
                ("cms-alias", "CMS"),
            ]):
                slug, title = slug_title
                page_content = (
                    f'---\ntype: entity\ntitle: "{title}"\nstatus: active\n'
                    f'sources:\n  - "repo://o/r/old.md@abc"\n'
                    f'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
                    f'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - test\n---\n\n# {title}\n'
                )
                (root / "wiki" / "entities" / f"{slug}.md").write_text(page_content, encoding="utf-8")

            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _entity_mod.run(str(bp), "wiki", repo_root=root)
            # Should succeed (skipped, not errored) — no new pages
            # rc == 0 because skip != error
            self.assertEqual(len(list((root / "wiki" / "entities").glob("*.md"))), 2)

    def test_missing_bundle_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            rc = _entity_mod.run("/nonexistent/bundle.json", "wiki", repo_root=root)
            self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# synthesize_concept_page.run()
# ---------------------------------------------------------------------------


class TestSynthesizeConceptPageRun(unittest.TestCase):
    def _bundle_path(self, tmp_path: Path, bundle: dict) -> Path:
        p = tmp_path / "bundle.json"
        p.write_text(json.dumps(bundle), encoding="utf-8")
        return p

    def test_creates_concept_page_from_valid_bundle(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            concept_pages = list((root / "wiki" / "concepts").glob("*.md"))
            self.assertEqual(len(concept_pages), 1)
            content = concept_pages[0].read_text(encoding="utf-8")
            self.assertIn("Medicare Advantage", content)

    def test_soft_skipped_bundle_produces_no_writes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = dict(_VALID_BUNDLE, soft_skipped=True)
            bp = self._bundle_path(root, bundle)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(list((root / "wiki" / "concepts").glob("*.md")), [])

    def test_duplicate_concept_appends(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            existing = (
                '---\ntype: concept\ntitle: "Medicare Advantage"\nstatus: active\n'
                'sources:\n  - "repo://o/r/old.md@abc"\n'
                'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
                'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - medicare\n---\n\n'
                '# Medicare Advantage\n'
            )
            (root / "wiki" / "concepts" / "medicare-advantage.md").write_text(existing, encoding="utf-8")
            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(len(list((root / "wiki" / "concepts").glob("*.md"))), 1)
            updated = (root / "wiki" / "concepts" / "medicare-advantage.md").read_text(encoding="utf-8")
            self.assertIn(_VALID_BUNDLE["source_ref"][:30], updated)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# extract_entities.run() — mocked HTTP
# ---------------------------------------------------------------------------


_MOCK_API_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "entities": [
                            {
                                "title": "CMS",
                                "aliases": [],
                                "summary": "Federal Medicare agency.",
                                "evidence": "CMS administers Medicare.",
                                "tags": ["government"],
                                "open_questions": [],
                            }
                        ],
                        "concepts": [],
                    }
                )
            }
        }
    ]
}


class TestExtractEntitiesRun(unittest.TestCase):
    def _make_source(self, tmp_path: Path) -> Path:
        sources_dir = tmp_path / "wiki" / "sources"
        sources_dir.mkdir(parents=True)
        (tmp_path / "wiki" / "entities").mkdir(parents=True)
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        sp = sources_dir / "test-source.md"
        sp.write_text(_MINIMAL_SOURCE_PAGE, encoding="utf-8")
        return sp

    def _mock_urlopen(self, api_response: dict):
        """Return a patch context manager that fakes urlopen."""
        import io
        response_bytes = json.dumps(api_response).encode("utf-8")

        class _FakeResponse:
            def read(self):
                return response_bytes
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        return patch.object(
            _extract_mod.request,  # type: ignore[attr-defined]
            "urlopen",
            return_value=_FakeResponse(),
        )

    def test_successful_extraction_writes_bundle(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            sp = self._make_source(root)
            out = root / "bundle.json"
            with self._mock_urlopen(_MOCK_API_RESPONSE):
                rc = _extract_mod.run(
                    source_page_path="wiki/sources/test-source.md",
                    wiki_root="wiki",
                    github_token="tok",
                    output_path=str(out),
                    repo_root=root,
                )
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            bundle = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(bundle["soft_skipped"])
            self.assertEqual(len(bundle["entities"]), 1)
            self.assertEqual(bundle["entities"][0]["title"], "CMS")

    def test_soft_skip_after_three_invalid_responses(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            sp = self._make_source(root)
            out = root / "bundle.json"
            # Return invalid JSON (not a dict) every call
            bad_response = {"choices": [{"message": {"content": "[]"}}]}
            with self._mock_urlopen(bad_response):
                rc = _extract_mod.run(
                    source_page_path="wiki/sources/test-source.md",
                    wiki_root="wiki",
                    github_token="tok",
                    output_path=str(out),
                    repo_root=root,
                )
            self.assertEqual(rc, 0)
            bundle = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(bundle["soft_skipped"])
            self.assertEqual(bundle["entities"], [])
            self.assertEqual(bundle["concepts"], [])

    def test_self_correction_succeeds_on_second_attempt(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"

            call_count = 0
            response_bytes_bad = json.dumps(
                {"choices": [{"message": {"content": "not valid json{"}}]}
            ).encode("utf-8")
            response_bytes_good = json.dumps(_MOCK_API_RESPONSE).encode("utf-8")

            class _ToggleResponse:
                def __init__(self, data):
                    self._data = data
                def read(self):
                    return self._data
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass

            responses = [response_bytes_bad, response_bytes_good]
            call_idx = 0

            def _fake_urlopen(req, timeout=None):
                nonlocal call_idx
                r = _ToggleResponse(responses[min(call_idx, len(responses) - 1)])
                call_idx += 1
                return r

            with patch.object(_extract_mod.request, "urlopen", side_effect=_fake_urlopen):  # type: ignore[attr-defined]
                rc = _extract_mod.run(
                    source_page_path="wiki/sources/test-source.md",
                    wiki_root="wiki",
                    github_token="tok",
                    output_path=str(out),
                    repo_root=root,
                )
            self.assertEqual(rc, 0)
            bundle = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(bundle["soft_skipped"])
            self.assertEqual(call_idx, 2)

    def test_missing_source_page_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            (root / "wiki" / "entities").mkdir(parents=True)
            (root / "wiki" / "concepts").mkdir(parents=True)
            out = root / "bundle.json"
            rc = _extract_mod.run(
                source_page_path="wiki/sources/nonexistent.md",
                wiki_root="wiki",
                github_token="tok",
                output_path=str(out),
                repo_root=root,
            )
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
