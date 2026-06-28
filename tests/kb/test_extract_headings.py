"""Tests for :func:`scripts.kb.page_template_utils.extract_headings`.

Per ADR-029 this is a new pytest-style file; the existing
``test_page_template_utils.py`` is legacy ``unittest.TestCase`` and is
not eligible for non-docstring edits without a same-commit migration.

The function was rewritten in PR #387 from ``body.splitlines()`` to
``find('\\n')``-streaming for memory efficiency on large bodies. The
algorithm has several edge cases (trailing line without newline,
unclosed fenced block, empty body, CRLF) that the indirect coverage via
``check_page_template`` does not assert by name. This file pins the
behavior so a future refactor can't silently regress it.
"""

from __future__ import annotations

import pytest

from scripts.kb.page_template_utils import extract_headings


def test_empty_body_returns_empty_set() -> None:
    assert extract_headings("") == set()


def test_single_heading_no_trailing_newline() -> None:
    """The streaming branch falls through to the trailing-line handler when
    the body lacks a final ``\\n``. Pre-refactor splitlines() handled this
    transparently; the new code's trailing branch must too.
    """
    assert extract_headings("# Hello") == {"# Hello"}


def test_single_heading_with_trailing_newline() -> None:
    assert extract_headings("# Hello\n") == {"# Hello"}


def test_multiple_headings_collected() -> None:
    body = "# H1\n## H2\n### H3\n"
    assert extract_headings(body) == {"# H1", "## H2", "### H3"}


def test_duplicate_headings_deduplicated() -> None:
    body = "# Same\n# Same\n# Same\n"
    assert extract_headings(body) == {"# Same"}


def test_heading_inside_fenced_block_is_skipped() -> None:
    body = "# Real\n```\n# Fake\n```\n# Other Real\n"
    assert extract_headings(body) == {"# Real", "# Other Real"}


def test_tilde_fence_also_skipped() -> None:
    body = "# Real\n~~~\n# Fake\n~~~\n"
    assert extract_headings(body) == {"# Real"}


def test_unclosed_fence_to_eof_swallows_following_content() -> None:
    """An unclosed ``` to EOF means everything after it is inside the
    fence — including the would-be trailing heading. This matches the
    pre-refactor splitlines() behavior.
    """
    body = "# Before\n```\n# Inside fence to EOF"
    assert extract_headings(body) == {"# Before"}


def test_unclosed_fence_at_eof_then_trailing_heading_via_lf() -> None:
    """When the fence-open line is followed by a heading with no terminating
    fence, the heading stays inside the fence (skipped).
    """
    body = "```\n# Inside\n"
    assert extract_headings(body) == set()


def test_crlf_line_endings_still_extract_headings() -> None:
    """CRLF input: normalized to LF before streaming."""
    body = "# H1\r\n# H2\r\n"
    assert extract_headings(body) == {"# H1", "# H2"}


def test_bare_cr_line_endings_extract_headings() -> None:
    """Bare CR (Classic Mac) input: normalized to LF before streaming."""
    body = "# Title\r## Sub\rbody text\r"
    assert extract_headings(body) == {"# Title", "## Sub"}


def test_non_heading_lines_ignored() -> None:
    body = "Plain text.\n# Real Heading\nMore text.\n"
    assert extract_headings(body) == {"# Real Heading"}


def test_atx_levels_h1_through_h6() -> None:
    body = "\n".join([f"{'#' * n} L{n}" for n in range(1, 7)]) + "\n"
    expected = {f"{'#' * n} L{n}" for n in range(1, 7)}
    assert extract_headings(body) == expected


def test_seven_hashes_not_a_heading() -> None:
    """ATX spec caps headings at 6 levels; ``#######`` is not a heading."""
    assert extract_headings("####### Not A Heading\n") == set()


def test_indented_heading_is_skipped() -> None:
    """Leading whitespace is stripped, so an indented `#` IS treated as a
    heading by this extractor — matches the original splitlines()-based
    implementation.
    """
    # Pre-refactor behavior: stripped().startswith('#') so indentation removed
    assert extract_headings("    # Indented\n") == {"# Indented"}


def test_heading_text_with_internal_hash_preserved() -> None:
    body = "# Title with #hashtag inside\n"
    assert extract_headings(body) == {"# Title with #hashtag inside"}


def test_only_fenced_content_yields_empty_set() -> None:
    body = "```\n# fake1\n## fake2\n```\n"
    assert extract_headings(body) == set()


def test_consecutive_fenced_blocks_alternate_correctly() -> None:
    body = "```\nfake1\n```\n# Real\n```\nfake2\n```\n# Real2\n"
    assert extract_headings(body) == {"# Real", "# Real2"}


@pytest.mark.parametrize("body", ["", "\n", "\n\n", "   \n\t\n"])
def test_whitespace_only_bodies_yield_empty_set(body: str) -> None:
    assert extract_headings(body) == set()


def test_large_body_streaming_does_not_crash() -> None:
    """Sanity check that the streaming branch handles large bodies without
    exploding (the whole point of the splitlines()→find('\\n') refactor).
    """
    body = ("\n".join(f"# H{i}" for i in range(1000))) + "\n"
    result = extract_headings(body)
    assert len(result) == 1000
    assert "# H0" in result
    assert "# H999" in result
