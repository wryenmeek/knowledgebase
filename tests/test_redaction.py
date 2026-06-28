"""Tests for :mod:`scripts._redaction` — shared stderr/markdown sanitizers."""

from __future__ import annotations

import pytest

from scripts._redaction import redact_stderr, sanitize_gh_md


# ---------- GitHub token prefix coverage ----------


@pytest.mark.parametrize(
    "prefix",
    [
        "ghp",          # classic PAT
        "ghs",          # App installation token — the GITHUB_TOKEN format in Actions
        "ghu",          # App user-to-server
        "ghr",          # App refresh
        "gho",          # OAuth
    ],
)
def test_redact_stderr_strips_all_github_token_prefixes(prefix: str) -> None:
    """All canonical GitHub-issued token prefixes must be fully redacted.

    Pre-consolidation the github_monitor copy only matched ghp_/github_pat_/gho_,
    leaving ghs_/ghu_/ghr_ to fall through to a permissive base64 catch-all
    that only redacted the *body* (the prefix marker survived). ghs_ is the
    actual GITHUB_TOKEN format in Actions runners, so this was the
    runtime-most-common token slipping through.
    """
    token = f"{prefix}_" + "A" * 36
    redacted = redact_stderr(f"Error: token={token} not authorized")
    assert prefix not in redacted, f"prefix {prefix} survived in: {redacted!r}"


def test_redact_stderr_strips_github_pat_separately() -> None:
    """github_pat_ uses underscore in the prefix, distinct regex path."""
    token = "github_pat_" + "B" * 40
    redacted = redact_stderr(f"401 with {token}")
    assert "github_pat" not in redacted


def test_redact_stderr_strips_jwt() -> None:
    """JWT format (header.payload.signature, base64url with -_) must be caught.

    Pre-consolidation the base64 catch-all used [A-Za-z0-9+/=] which doesn't
    include `-_`; a real JWT signature could survive. The dedicated JWT
    pattern in the consolidated module closes this gap.
    """
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        + "."
        + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
        + "."
        + "signature_with-dashes_AND_underscores_only_xyz"
    )
    redacted = redact_stderr(f"401 token={jwt}")
    # Each segment is 40+ chars; the JWT regex should swallow the whole thing.
    assert "eyJ" not in redacted
    assert "signature" not in redacted


# ---------- Truncation order: redact-then-truncate ----------


def test_redact_runs_before_truncate_so_token_at_boundary_does_not_leak() -> None:
    """Pre-consolidation order was truncate-then-redact, leaking the body
    fragment of a token that straddled the 200-char cut. Post: redact first.
    """
    padding = "x" * 195
    token = "ghs_" + "Z" * 40
    leaky = padding + token
    out = redact_stderr(leaky, max_len=200)
    assert "ghs_" not in out
    assert "Z" * 10 not in out  # body fragment also gone


# ---------- Authorization header sweep ----------


def test_redact_strips_authorization_header_case_insensitively() -> None:
    assert "Bearer" not in redact_stderr("Authorization: Bearer secret-value")
    assert "Bearer" not in redact_stderr("authorization: Bearer secret-value")
    assert "Basic" not in redact_stderr("AUTHORIZATION:    Basic dXNlcjpwYXNz")


# ---------- Base64 catch-all tightening (no false-positive path redaction) ----------


def test_redact_does_not_clobber_alphanumeric_paths() -> None:
    """Pre-consolidation the catch-all `[A-Za-z0-9+/=]{30,}` included `/`,
    redacting legit paths that lacked `=`/`+`. The tightened pattern
    requires padding OR a `+/` char so a pure alphanumeric path survives.
    """
    msg = "HTTP 404 on repos/medicarecoverage/wikis/issues/12345endpoint"
    redacted = redact_stderr(msg)
    # Path bits must remain visible — they're the diagnostic value of the log.
    assert "repos" in redacted
    assert "endpoint" in redacted


def test_redact_still_catches_padded_base64_blob() -> None:
    blob = "VGhpc0lzQWxsQmFzZTY0RW5jb2RlZFNlY3JldEJsb2I="  # noqa: S105
    assert "VGhpc0lz" not in redact_stderr(f"payload={blob}")


def test_redact_still_catches_mixed_char_base64_blob() -> None:
    # 32 chars alpha + one + + 16 chars alpha — fits the mixed-char branch.
    blob = "x" * 32 + "+" + "y" * 16
    out = redact_stderr(f"payload={blob}")
    assert "yyy" not in out


# ---------- 40-hex sweep (git SHAs / hex token fragments) ----------


def test_redact_strips_40_hex_strings() -> None:
    sha = "abc123def456abc123def456abc123def456abcd"  # 40 chars
    redacted = redact_stderr(f"commit {sha} not found")
    assert sha not in redacted


# ---------- Truncation contract ----------


def test_redact_respects_max_len() -> None:
    redacted = redact_stderr("y" * 1000, max_len=50)
    assert len(redacted) <= 50


def test_redact_strips_surrounding_whitespace() -> None:
    assert redact_stderr("   plain msg   ") == "plain msg"


# ---------- sanitize_gh_md regression coverage ----------


def test_sanitize_strips_html_tags() -> None:
    assert "<script>" not in sanitize_gh_md("<script>alert(1)</script>")


def test_sanitize_strips_at_mentions() -> None:
    assert "@evil" not in sanitize_gh_md("hello @evil")


def test_sanitize_strips_image_embeds() -> None:
    assert "![" not in sanitize_gh_md("![img](http://x)")


def test_sanitize_strips_auto_close_keywords() -> None:
    """Auto-close keywords (fixes/closes/resolves #N) must be removed.

    Lost in PR #393's botched merge; the test that used to assert this
    behavior was split off into a misnamed orphan with weaker coverage.
    """
    for kw in ["fixes", "fix", "closes", "close", "closed", "resolves", "resolve", "resolved"]:
        raw = f"{kw} #1"
        assert "#1" not in sanitize_gh_md(raw), f"keyword {kw!r} not stripped"


def test_sanitize_strips_github_actions_expressions() -> None:
    """${{ and }} markers must be neutralized to prevent injection
    when the value is later rendered in an Actions context.
    """
    assert "${{" not in sanitize_gh_md("${{ secrets.GITHUB_TOKEN }}")
    assert "}}" not in sanitize_gh_md("${{ secrets.GITHUB_TOKEN }}")


def test_sanitize_combined_strips_all_dangerous_markup() -> None:
    """The test that PR #393 botched — restored as a single coherent assertion."""
    raw = "fixes #1 <script>@evil `tick` ![img](x)"
    result = sanitize_gh_md(raw)
    assert "<" not in result
    assert ">" not in result
    assert "@evil" not in result
    assert "![" not in result
    assert "`" not in result
    assert "fixes #1" not in result.lower()


def test_sanitize_respects_max_len() -> None:
    assert len(sanitize_gh_md("z" * 1000, max_len=50)) <= 50


def test_sanitize_strips_carriage_returns_and_newlines() -> None:
    assert "\n" not in sanitize_gh_md("a\nb\nc")
    assert "\r" not in sanitize_gh_md("a\r\nb")


def test_sanitize_gh_md_passes_through_unmatched_double_close_brace() -> None:
    """JSON with nested closing braces must not be corrupted.

    The old symmetric str.replace pair rewrote any ``}}`` to ``[expr]``,
    which silently corrupted JSON content.  The balanced-pair regex only
    neutralizes ``${{ ... }}`` expressions and leaves orphan ``}}`` alone.
    """
    assert sanitize_gh_md('{"a": {"b": "c"}}') == '{"a": {"b": "c"}}'


def test_sanitize_gh_md_passes_through_orphan_double_close_brace() -> None:
    """A bare ``}}`` with no preceding ``${{`` must pass through unchanged."""
    assert sanitize_gh_md("orphan }} end") == "orphan }} end"


def test_sanitize_gh_md_neutralizes_expression_with_single_brace_in_body() -> None:
    """A single ``}`` inside the expression body must not prematurely end the match.

    The old ``[^}]*`` regex terminated at the first ``}`` in the body, so
    ``${{ foo } bar }}`` wasn't matched (the class stopped at `` } ``, then
    ``\\}\\}`` required ``}}`` immediately — no match).  The improved
    ``(?:[^}]|\\}(?!\\}))`` alternation allows a single ``}`` not followed
    by another ``}`` and correctly captures the whole expression.
    """
    assert sanitize_gh_md("${{ foo } bar }}") == "[expr]"


def test_sanitize_gh_md_neutralizes_bare_dollar_open_brace() -> None:
    """A bare ``${{`` with no closing ``}}`` must be neutralized as defense-in-depth.

    The balanced-pair regex leaves orphan openers alone (correct — they
    have no matching close).  The post-pass ``str.replace`` then neutralizes
    any remaining ``${{``, restoring the prior behavior for bare openers
    without re-introducing JSON corruption.
    """
    assert sanitize_gh_md("orphan ${{ end") == "orphan [expr] end"
