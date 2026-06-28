"""Shared stderr/markdown redaction helpers for scripts that surface external content.

Consolidates :func:`redact_stderr` and :func:`sanitize_gh_md` so the
``github_monitor`` and ``drive_monitor`` (and any future) surfaces share a
single source of truth for credential redaction and GitHub-flavored
markdown sanitization. Prior to consolidation the two surfaces carried
divergent copies (different Authorization-header regexes, asymmetric
token-prefix coverage), which violated ADR-011's "import, don't duplicate"
rule and meant any future GitHub token format change had to be remembered
twice.

This module has no I/O and no side effects. Safe to import from read-only
analyzer surfaces.

**Token redaction coverage** (canonical GitHub token prefixes, see
<https://docs.github.com/authentication/keeping-your-account-and-data-secure/about-authentication-to-github#githubs-token-formats>):

* ``ghp_`` — Classic personal access tokens
* ``github_pat_`` — Fine-grained personal access tokens
* ``gho_`` — OAuth user access tokens
* ``ghs_`` — **GitHub App installation tokens** (the format of
  ``GITHUB_TOKEN`` inside Actions runners — the most common one)
* ``ghu_`` — GitHub App user-to-server tokens
* ``ghr_`` — GitHub App refresh tokens

**Truncation order:** redaction runs *before* truncation, so a token that
straddles the ``max_len`` boundary cannot leak its body fragment past
the cut. Pre-consolidation code truncated first, which leaked short
suffixes (< 30 chars after the cut) past the catch-all regex.

**Base64 catch-all:** kept as a defense-in-depth fallback, but tightened
to require either ``=`` padding OR at least one ``+/`` char so a
30-char alphanumeric *path segment* (e.g.,
``repos/owner/repo/path/segments/...``) is no longer over-redacted.
"""

from __future__ import annotations

import re

# Order matters: GitHub token-prefix patterns run FIRST (most specific),
# THEN the SHA-or-hex catch-all (which would otherwise consume token bodies
# that happen to be 40+ hex characters and leave the prefix marker behind).
# Then the Authorization-header sweep, then the tightened base64/JWT fallback.
#
# `\b` anchor is NOT used on the GitHub token regex because real stderr can
# embed tokens adjacent to non-whitespace context (e.g., `token=ghs_…` is
# fine, but log noise like `prefix-ghs_…` would skip the match with `\b`).
# Removing `\b` is safe because the prefix list (`ghp_`, `ghs_`, etc.) is
# unique enough to not false-match natural text.
_GITHUB_TOKEN_RE = re.compile(
    r"(?:ghp|ghs|ghu|ghr|gho)_[A-Za-z0-9_]+"
)
_GITHUB_PAT_RE = re.compile(r"github_pat_[A-Za-z0-9_]+")
_SHA_OR_TOKEN_HEX_RE = re.compile(r"[0-9a-fA-F]{40,}")
_AUTHORIZATION_RE = re.compile(
    r"Authorization:[ \t]*\S+(?:[ \t]+\S+)?",
    flags=re.IGNORECASE,
)
# Tightened catch-all: require padding (=) OR a non-alphanumeric base64
# char (+/), to avoid clobbering alphanumeric paths. The trailing optional
# `=` group accepts the 0/1/2-pad cases.
_BASE64_BLOB_RE = re.compile(
    r"(?:[A-Za-z0-9+/]{20,}={1,2})"          # padded base64
    r"|(?:[A-Za-z0-9]{20,}[+/][A-Za-z0-9+/]{10,}={0,2})"  # mixed-char base64
)
# JWT (header.payload.signature) — base64url alphabet uses `-_`, distinct
# from `+/`. Caught here because the base64 catch-all above doesn't see
# `-_` chars.
_JWT_RE = re.compile(
    r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"
)


def redact_stderr(stderr: str, max_len: int = 200) -> str:
    """Redact then truncate stderr before logging.

    Order matters: redaction runs first so a token that straddles the
    ``max_len`` boundary is consumed by its pattern before the cut. Returns
    a stripped string capped at ``max_len`` characters.

    Pattern application order is also load-bearing: token-prefix patterns
    run before the SHA-hex catch-all so a hex-only token body (e.g., a
    PAT body of 40 ``B`` chars) is replaced as ``[REDACTED]`` rather than
    leaving the ``github_pat_`` prefix marker in front of a ``<redacted>``
    SHA replacement.

    All patterns are linear-time (no nested quantifiers); no ReDoS risk
    on plausible stderr sizes from the ``gh`` CLI or Google APIs.
    """
    redacted = stderr
    redacted = _GITHUB_TOKEN_RE.sub("[REDACTED]", redacted)
    redacted = _GITHUB_PAT_RE.sub("[REDACTED]", redacted)
    redacted = _SHA_OR_TOKEN_HEX_RE.sub("<redacted>", redacted)
    redacted = _AUTHORIZATION_RE.sub("[REDACTED]", redacted)
    redacted = _JWT_RE.sub("[REDACTED]", redacted)
    redacted = _BASE64_BLOB_RE.sub("[REDACTED]", redacted)
    return redacted[:max_len].strip()


def sanitize_gh_md(value: str, max_len: int = 200) -> str:
    """Strip characters that trigger side effects in GitHub-flavored markdown.

    Defense-in-depth: even when ``value`` is operator-controlled metadata
    (dedupe keys, registry slugs, paths), neutralize HTML tags,
    ``@mentions``, image embeds, auto-close keywords (``fixes #N``), and
    GitHub Actions expression-injection markers (``${{`` / ``}}``).

    The ``${{`` / ``}}`` neutralization is a two-step process:

    1. **Paired expression pass** — a balanced regex replaces every
       ``${{ … }}`` expression with ``[expr]``.  The inner alternation
       ``(?:[^}]|\\}(?!\\}))`` allows a single ``}`` inside the body
       (i.e., ``${{ foo } bar }}``) while still correctly terminating at
       the first ``}}``.  Orphan ``}}`` (e.g., from JSON content like
       ``{"a": {"b": "c"}}``) are left untouched — no false-positive
       corruption.

    2. **Bare-opener defense pass** — after the regex has consumed all
       balanced pairs, any remaining ``${{`` (orphan opener with no
       matching ``}}``) is replaced with ``[expr]`` as defense-in-depth.
       This restores the prior ``str.replace`` behavior for bare openers
       without re-introducing JSON corruption (paired ``}}`` are already
       gone, so only genuinely orphan openers remain).
    """
    s = value.replace("`", "").replace("\n", " ").replace("\r", "")
    s = re.sub(r"[<>]", "", s)                                     # HTML tags
    s = re.sub(r"@[\w/-]+", "", s)                                  # @mention / @org/team
    s = re.sub(r"!\[", "[", s)                                      # image embeds
    s = re.sub(
        r"\b(fix(es)?|close[sd]?|resolve[sd]?)\s+#\d+",
        "",
        s,
        flags=re.IGNORECASE,
    )
    # Step 1: neutralize paired ${{ … }} — allows single } inside expression body.
    s = re.sub(r"\$\{\{(?:[^}]|\}(?!\}))*\}\}", "[expr]", s)
    # Step 2: neutralize any remaining bare ${{ (orphan opener, no matching }}).
    s = s.replace("${{", "[expr]")
    return s[:max_len].strip()
