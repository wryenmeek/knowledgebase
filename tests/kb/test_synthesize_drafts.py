"""Tests for synthesis-curator logic scripts.

Covers:
- validate_extraction_bundle (extract_entities.py)
- title_to_slug, find_duplicate, render_draft_page, validate_draft_frontmatter,
  validate_draft_structure, append_to_existing_page (_synthesis_utils.py)
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

    def test_validates_draft_structure(self) -> None:
        page = self._rendered()
        errors = _su.validate_draft_structure(page)
        self.assertEqual(errors, [], f"Draft page had structural errors: {errors}")

    def test_validate_draft_structure_missing_frontmatter(self) -> None:
        errors = _su.validate_draft_structure("# Missing frontmatter\n")
        self.assertEqual(errors, ["frontmatter missing or undetected"])

    def test_validate_draft_structure_malformed_closing_delimiter(self) -> None:
        draft = '---\ntitle: "Test Entity"\n  ---\n# Test Entity\n'
        errors = _su.validate_draft_structure(draft)
        self.assertEqual(errors, ["frontmatter closing delimiter missing or malformed"])

    def test_validate_draft_structure_detects_extra_frontmatter_delimiter(self) -> None:
        draft = '---\ntitle: "Test Entity"\n---\n---\n# Test Entity\n'
        errors = _su.validate_draft_structure(draft)
        self.assertEqual(errors, ["body starts with an unexpected frontmatter delimiter"])


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
            self.assertEqual(rc, 0)
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

    def test_empty_choices_list_produces_soft_skip(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"
            with self._mock_urlopen({"choices": []}):
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

    def test_schema_self_correction_succeeds_on_second_attempt(self) -> None:
        """Schema validation failure (valid JSON that fails validate_extraction_bundle) triggers correction."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"

            # First response: valid JSON but missing required item keys
            bad_bundle = {"entities": [{"title": "X"}], "concepts": []}
            response_bad = json.dumps(
                {"choices": [{"message": {"content": json.dumps(bad_bundle)}}]}
            ).encode("utf-8")
            response_good = json.dumps(_MOCK_API_RESPONSE).encode("utf-8")

            class _ToggleResponse:
                def __init__(self, data):
                    self._data = data
                def read(self):
                    return self._data
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass

            responses = [response_bad, response_good]
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

    def test_urlerror_on_all_attempts_produces_soft_skip(self) -> None:
        import tempfile
        from urllib import error as urllib_error
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"

            def _raise_urlerror(*a, **kw):
                raise urllib_error.URLError("connection refused")

            with patch.object(_extract_mod.request, "urlopen", side_effect=_raise_urlerror):  # type: ignore[attr-defined]
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

    def test_disallowed_endpoint_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"
            rc = _extract_mod.run(
                source_page_path="wiki/sources/test-source.md",
                wiki_root="wiki",
                github_token="tok",
                output_path=str(out),
                endpoint="https://attacker.example.com",
                repo_root=root,
            )
            self.assertEqual(rc, 1)

    def test_path_traversal_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            self._make_source(root)
            out = root / "bundle.json"
            rc = _extract_mod.run(
                source_page_path="../../etc/passwd",
                wiki_root="wiki",
                github_token="tok",
                output_path=str(out),
                repo_root=root,
            )
            self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# Additional entity/concept tests (slug collision, missing concepts key, etc.)
# ---------------------------------------------------------------------------


class TestEntitySlugCollision(unittest.TestCase):
    def test_slug_collision_skips_gracefully(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            slug = _su.title_to_slug("Centers for Medicare & Medicaid Services")
            existing_file = root / "wiki" / "entities" / f"{slug}.md"
            existing_file.write_text("---\ntype: entity\ntitle: \"Other Entity\"\nstatus: active\nsources: []\nopen_questions: []\nconfidence: 2\nsensitivity: internal\nupdated_at: \"2024-01-01T00:00:00Z\"\ntags:\n  - test\n---\n\n# Other Entity\n", encoding="utf-8")
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(_VALID_BUNDLE), encoding="utf-8")
            rc = _entity_mod.run(str(bundle_path), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            # File exists but was not overwritten
            self.assertEqual(existing_file.read_text(encoding="utf-8").count("Other Entity"), 2)


class TestInBatchSlugCollision(unittest.TestCase):
    def test_in_batch_slug_collision_skips_second_entity(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = dict(
                _VALID_BUNDLE,
                entities=[
                    {
                        "title": "CMS",
                        "aliases": [],
                        "summary": "First.",
                        "evidence": "Ev A.",
                        "tags": ["test"],
                        "open_questions": [],
                    },
                    {
                        "title": "C.M.S.",
                        "aliases": [],
                        "summary": "Second (same slug).",
                        "evidence": "Ev B.",
                        "tags": ["test"],
                        "open_questions": [],
                    },
                ],
            )
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            rc = _entity_mod.run(str(bundle_path), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            entity_files = list((root / "wiki" / "entities").glob("*.md"))
            self.assertEqual(len(entity_files), 1)
            self.assertIn("CMS", entity_files[0].read_text(encoding="utf-8"))


class TestConceptSlugCollision(unittest.TestCase):
    def test_slug_collision_skips_gracefully(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            slug = _su.title_to_slug("Medicare Advantage")
            existing_file = root / "wiki" / "concepts" / f"{slug}.md"
            existing_file.write_text("---\ntype: concept\ntitle: \"Other Concept\"\nstatus: active\nsources: []\nopen_questions: []\nconfidence: 2\nsensitivity: internal\nupdated_at: \"2024-01-01T00:00:00Z\"\ntags:\n  - test\n---\n\n# Other Concept\n", encoding="utf-8")
            bundle_path = root / "bundle.json"
            bundle_path.write_text(json.dumps(_VALID_BUNDLE), encoding="utf-8")
            rc = _concept_mod.run(str(bundle_path), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(existing_file.read_text(encoding="utf-8").count("Other Concept"), 2)


class TestSynthesizeConceptPageRunParity(unittest.TestCase):
    """Concept parity tests mirroring entity test coverage."""

    def _bundle_path(self, tmp_path: Path, bundle: dict) -> Path:
        p = tmp_path / "bundle.json"
        p.write_text(json.dumps(bundle), encoding="utf-8")
        return p

    def test_empty_concepts_list_produces_no_writes(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = dict(_VALID_BUNDLE, concepts=[])
            bp = self._bundle_path(root, bundle)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(list((root / "wiki" / "concepts").glob("*.md")), [])

    def test_ambiguous_concept_match_skips(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            for slug, title in [("ma1", "Medicare Advantage"), ("ma2", "MA")]:
                page_content = (
                    f'---\ntype: concept\ntitle: "{title}"\nstatus: active\n'
                    f'sources:\n  - "repo://o/r/old.md@abc"\n'
                    f'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
                    f'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - test\n---\n\n# {title}\n'
                )
                (root / "wiki" / "concepts" / f"{slug}.md").write_text(page_content, encoding="utf-8")
            bp = self._bundle_path(root, _VALID_BUNDLE)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(len(list((root / "wiki" / "concepts").glob("*.md"))), 2)

    def test_concept_missing_bundle_returns_error(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            rc = _concept_mod.run("/nonexistent/bundle.json", "wiki", repo_root=root)
            self.assertEqual(rc, 1)

    def test_missing_concepts_key_treated_as_empty(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            _make_workspace(root)
            bundle = {k: v for k, v in _VALID_BUNDLE.items() if k != "concepts"}
            bp = self._bundle_path(root, bundle)
            rc = _concept_mod.run(str(bp), "wiki", repo_root=root)
            self.assertEqual(rc, 0)
            self.assertEqual(list((root / "wiki" / "concepts").glob("*.md")), [])


class TestSanitizeLlmStr(unittest.TestCase):
    def test_strips_newlines(self) -> None:
        self.assertEqual(_su._sanitize_llm_str("foo\nbar"), "foo bar")

    def test_strips_carriage_return(self) -> None:
        self.assertEqual(_su._sanitize_llm_str("foo\rbar"), "foo bar")

    def test_strips_null_byte(self) -> None:
        self.assertEqual(_su._sanitize_llm_str("foo\x00bar"), "foo bar")

    def test_max_len_truncates(self) -> None:
        self.assertEqual(len(_su._sanitize_llm_str("x" * 600, max_len=500)), 500)

    def test_non_string_returns_empty(self) -> None:
        self.assertEqual(_su._sanitize_llm_str(None), "")


class TestTitleToSlugEdgeCases(unittest.TestCase):
    def test_slug_max_200_chars(self) -> None:
        long_title = "word " * 60  # 300 chars
        slug = _su.title_to_slug(long_title)
        self.assertLessEqual(len(slug), 200)

    def test_unicode_title_produces_slug(self) -> None:
        slug = _su.title_to_slug("Résumé Health Plan")
        self.assertIsInstance(slug, str)
        self.assertGreater(len(slug), 0)


class TestAppendToExistingPageBothNew(unittest.TestCase):
    def test_both_new_source_ref_and_open_question(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            page = Path(td).resolve() / "entity.md"
            page.write_text(
                '---\ntype: entity\ntitle: "X"\nstatus: active\nsources:\n  - "repo://o/r/old.md@abc"\n'
                'open_questions: []\nconfidence: 2\nsensitivity: internal\nupdated_at: "2024-01-01T00:00:00Z"\n'
                'tags:\n  - test\n---\n\n# X\n',
                encoding="utf-8",
            )
            modified = _su.append_to_existing_page(page, "repo://o/r/new.md@xyz", ["What is X?"])
            self.assertTrue(modified)
            content = page.read_text(encoding="utf-8")
            self.assertIn("new.md@xyz", content)
            self.assertIn("What is X?", content)

class TestAppendToExistingPageStructuralValidation(unittest.TestCase):
    """Structural validation added to append_to_existing_page (#116)."""

    def _make_page(self, tmp: str, content: str) -> Path:
        page = Path(tmp).resolve() / "entity.md"
        page.write_text(content, encoding="utf-8")
        return page

    def _valid_page_content(self) -> str:
        return (
            '---\ntype: entity\ntitle: "X"\nstatus: active\n'
            'sources:\n  - "repo://o/r/old.md@abc"\n'
            'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
            'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - test\n---\n\n# X\n'
        )

    def test_valid_append_does_not_raise(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(td, self._valid_page_content())
            # Should not raise
            modified = _su.append_to_existing_page(page, "repo://o/r/new.md@xyz", [])
            self.assertTrue(modified)

    def test_structural_error_raises_runtime_error(self) -> None:
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(td, self._valid_page_content())
            # Patch validate_draft_structure to simulate a structural violation
            with patch.object(
                _su, "validate_draft_structure", return_value=["injected delimiter"]
            ):
                with self.assertRaises(RuntimeError) as cm:
                    _su.append_to_existing_page(page, "repo://o/r/new.md@xyz", [])
                self.assertIn("structural validation failed", str(cm.exception))

    def test_body_starting_with_delimiter_triggers_real_structural_error(self) -> None:
        """A page whose body starts with '---' must trigger RuntimeError without any mocking.

        This validates the #116 guard exercises real validate_draft_structure logic,
        not just the mock path. When YAML surgery reassembles the content, the body
        starting with '---' is caught as a structural violation.
        """
        import tempfile
        # Craft a page where the body (after closing ---) begins with '---'
        content = (
            '---\n'
            'type: entity\ntitle: "X"\nstatus: active\n'
            'sources:\n  - "repo://o/r/old.md@abc"\n'
            'open_questions: []\nconfidence: 2\nsensitivity: internal\n'
            'updated_at: "2024-01-01T00:00:00Z"\ntags:\n  - test\n'
            '---\n'
            '---\n'  # body starts immediately with --- (malformed but extractable)
            '# X\n'
        )
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(td, content)
            with self.assertRaises(RuntimeError) as cm:
                _su.append_to_existing_page(page, "repo://o/r/new.md@xyz", [])
            self.assertIn("structural validation failed", str(cm.exception))

    def test_no_frontmatter_returns_false(self) -> None:
        """append_to_existing_page must return False (not raise) when the page has no frontmatter."""
        import tempfile
        content = "# Just a Heading\n\nNo frontmatter at all.\n"
        with tempfile.TemporaryDirectory() as td:
            page = self._make_page(td, content)
            result = _su.append_to_existing_page(page, "repo://o/r/new.md@xyz", [])
            self.assertFalse(result)


class TestCombinedSynthesisRun(unittest.TestCase):
    """Tests for synthesize_combined.py (#115): single-lock entity+concept synthesis."""

    def setUp(self) -> None:
        self._combined_mod = _load_module(
            ENTITY_LOGIC / "synthesize_combined.py", "synthesize_combined"
        )

    def _make_bundle(self, tmp: Path, *, soft_skipped: bool = False) -> Path:
        bundle: dict = {
            "source_ref": "repo://o/r/src.md@abc123",
            "entities": [
                {
                    "title": "Combined Entity",
                    "type": "organization",
                    "description": "An entity synthesized by the combined script.",
                    "aliases": [],
                    "open_questions": [],
                }
            ],
            "concepts": [
                {
                    "title": "Combined Concept",
                    "description": "A concept synthesized by the combined script.",
                    "aliases": [],
                    "open_questions": [],
                }
            ],
        }
        if soft_skipped:
            bundle = {"soft_skipped": True, "source_ref": ""}
        path = tmp / "bundle.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        return path

    def _make_wiki(self, tmp: Path) -> Path:
        wiki = tmp / "wiki"
        (wiki / "entities").mkdir(parents=True)
        (wiki / "concepts").mkdir(parents=True)
        return wiki

    def test_soft_skipped_bundle_returns_zero(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            bundle = self._make_bundle(tdp, soft_skipped=True)
            rc = self._combined_mod.run(str(bundle), "wiki", repo_root=tdp)
            self.assertEqual(rc, 0)

    def test_missing_bundle_returns_one(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            rc = self._combined_mod.run(str(tdp / "noexist.json"), "wiki", repo_root=tdp)
            self.assertEqual(rc, 1)

    def test_combined_creates_entity_and_concept(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            wiki = self._make_wiki(tdp)
            bundle = self._make_bundle(tdp)
            rc = self._combined_mod.run(str(bundle), str(wiki.relative_to(tdp)), repo_root=tdp)
            self.assertEqual(rc, 0)
            entity_files = list((wiki / "entities").glob("*.md"))
            concept_files = list((wiki / "concepts").glob("*.md"))
            self.assertGreaterEqual(len(entity_files), 1, "Expected entity .md page created")
            self.assertGreaterEqual(len(concept_files), 1, "Expected concept .md page created")
            # Verify the created entity page has correct frontmatter title
            entity_content = entity_files[0].read_text(encoding="utf-8")
            self.assertIn("Combined Entity", entity_content)
            concept_content = concept_files[0].read_text(encoding="utf-8")
            self.assertIn("Combined Concept", concept_content)

    def test_lock_unavailable_returns_one(self) -> None:
        import tempfile
        from unittest.mock import patch
        from scripts.kb.write_utils import LockUnavailableError
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            bundle = self._make_bundle(tdp)
            self._make_wiki(tdp)
            with patch.object(
                self._combined_mod,
                "exclusive_write_lock",
                side_effect=LockUnavailableError("busy"),
            ):
                rc = self._combined_mod.run(str(bundle), "wiki", repo_root=tdp)
            self.assertEqual(rc, 1)

    def test_combined_empty_bundle_returns_zero(self) -> None:
        """An empty bundle (no entities, no concepts, not soft-skipped) returns 0."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            self._make_wiki(tdp)
            empty_bundle = tdp / "empty.json"
            empty_bundle.write_text(
                json.dumps({"source_ref": "repo://o/r/s.md@abc", "entities": [], "concepts": []}),
                encoding="utf-8",
            )
            rc = self._combined_mod.run(str(empty_bundle), "wiki", repo_root=tdp)
            self.assertEqual(rc, 0)

    def test_combined_write_errors_returns_one(self) -> None:
        """When an inner write function returns errors, run() must return 1."""
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            self._make_wiki(tdp)
            bundle = self._make_bundle(tdp)
            error_result = {"created": [], "updated": [], "skipped": [], "errors": ["write failed"]}
            with patch.object(self._combined_mod, "_write_entity_drafts", return_value=error_result):
                with patch.object(
                    self._combined_mod, "_write_concept_drafts",
                    return_value={"created": [], "updated": [], "skipped": [], "errors": []},
                ):
                    rc = self._combined_mod.run(str(bundle), "wiki", repo_root=tdp)
            self.assertEqual(rc, 1)

    def test_combined_lock_acquired_exactly_once(self) -> None:
        """The core #115 invariant: a single lock acquisition covers both entity and concept writes."""
        import tempfile
        from unittest.mock import patch, MagicMock
        import contextlib
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            self._make_wiki(tdp)
            bundle = self._make_bundle(tdp)
            lock_call_count = []

            @contextlib.contextmanager
            def counting_lock(_repo_root):
                lock_call_count.append(1)
                yield

            with patch.object(self._combined_mod, "exclusive_write_lock", counting_lock):
                with patch.object(
                    self._combined_mod, "_write_entity_drafts",
                    return_value={"created": [], "updated": [], "skipped": [], "errors": []},
                ):
                    with patch.object(
                        self._combined_mod, "_write_concept_drafts",
                        return_value={"created": [], "updated": [], "skipped": [], "errors": []},
                    ):
                        self._combined_mod.run(str(bundle), "wiki", repo_root=tdp)

            self.assertEqual(len(lock_call_count), 1, "exclusive_write_lock must be acquired exactly once")

    def test_combined_entity_only_bundle(self) -> None:
        """A bundle with entities but no concepts must succeed and create entity pages."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            wiki = self._make_wiki(tdp)
            entity_only = tdp / "entity_only.json"
            entity_only.write_text(
                json.dumps({
                    "source_ref": "repo://o/r/s.md@abc",
                    "entities": [{"title": "Only Entity", "type": "organization",
                                   "description": "desc", "aliases": [], "open_questions": []}],
                    "concepts": [],
                }),
                encoding="utf-8",
            )
            rc = self._combined_mod.run(str(entity_only), str(wiki.relative_to(tdp)), repo_root=tdp)
            self.assertEqual(rc, 0)
            entity_files = list((wiki / "entities").iterdir())
            self.assertGreaterEqual(len(entity_files), 1, "Expected entity page created")
            self.assertEqual(list((wiki / "concepts").iterdir()), [], "No concept pages expected")

    def test_combined_concept_only_bundle(self) -> None:
        """A bundle with concepts but no entities must succeed and create concept pages."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td).resolve()
            wiki = self._make_wiki(tdp)
            concept_only = tdp / "concept_only.json"
            concept_only.write_text(
                json.dumps({
                    "source_ref": "repo://o/r/s.md@abc",
                    "entities": [],
                    "concepts": [{"title": "Only Concept",
                                   "description": "desc", "aliases": [], "open_questions": []}],
                }),
                encoding="utf-8",
            )
            rc = self._combined_mod.run(str(concept_only), str(wiki.relative_to(tdp)), repo_root=tdp)
            self.assertEqual(rc, 0)
            self.assertEqual(list((wiki / "entities").iterdir()), [], "No entity pages expected")
            concept_files = list((wiki / "concepts").iterdir())
            self.assertGreaterEqual(len(concept_files), 1, "Expected concept page created")


if __name__ == '__main__':
    unittest.main()
