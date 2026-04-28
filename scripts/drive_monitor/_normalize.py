"""Canonical Markdown export normalization for Drive API content hashing.

Google's ``files.export`` endpoint is NOT byte-idempotent for native Google
Docs formats (e.g. ``application/vnd.google-apps.document``).  Repeated
exports of unchanged content may produce different raw bytes due to invisible
formatting metadata, zero-width characters, or whitespace variation.

To enable stable SHA-256 comparison across CI runs, all Markdown exports
**must** be normalized before hashing.  The normalized bytes are also what
gets vendored to ``raw/assets/gdrive/`` — raw export bytes are discarded.

Non-native formats (PDF, DOCX, text/plain, text/markdown) are downloaded
directly and use the Drive API ``md5Checksum`` field as the content-change
signal, so this module does NOT apply to them.

Usage::

    from scripts.drive_monitor._normalize import normalize_markdown_export
    import hashlib

    raw_export: bytes = drive_client.export_file(file_id, "text/markdown")
    normalized: bytes = normalize_markdown_export(raw_export)
    sha256 = hashlib.sha256(normalized).hexdigest()
"""

from __future__ import annotations


def normalize_markdown_export(raw_bytes: bytes) -> bytes:
    """Canonical normalization for SHA-256 computation of Markdown exports.

    Steps (applied in order):

    1. Decode the export bytes as UTF-8 (``errors='replace'``).
    2. Normalize all line endings to ``\\n`` (handles ``\\r\\n`` and ``\\r``).
    3. Strip trailing whitespace (spaces and tabs) from every line.
    4. Strip leading and trailing blank lines from the document body.
    5. Ensure exactly one trailing newline character.
    6. Re-encode as UTF-8.

    The resulting bytes are the canonical form for SHA-256 comparison and
    asset vendoring.  The function is **idempotent**: calling it twice on
    already-normalized bytes produces identical output.

    Parameters
    ----------
    raw_bytes:
        Raw bytes as returned by the Drive ``files.export`` API.

    Returns
    -------
    bytes
        Normalized UTF-8 bytes.  Never empty — a document that is entirely
        blank normalizes to a single ``\\n``.

    Examples
    --------
    >>> normalize_markdown_export(b"hello  \\r\\nworld\\n")
    b'hello\\nworld\\n'
    >>> normalize_markdown_export(b"")
    b'\\n'
    >>> normalize_markdown_export(b"\\n\\n\\n")
    b'\\n'
    """
    text = raw_bytes.decode("utf-8", errors="replace")

    # Normalize line endings to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into lines (trailing \n produces an empty string at end of split)
    lines = text.split("\n")

    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in lines]

    # Join back and strip leading/trailing blank lines from the whole document
    rejoined = "\n".join(lines)
    rejoined = rejoined.strip("\n")

    # Ensure exactly one trailing newline
    if not rejoined:
        return b"\n"
    return (rejoined + "\n").encode("utf-8")
