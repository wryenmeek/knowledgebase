"""Unit tests for SourceRef parsing and validation."""

from __future__ import annotations

import unittest

from scripts.kb.sourceref import SourceRefValidationError, parse_sourceref, validate_sourceref, SourceRefReasonCode


class SourceRefValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checksum = "a" * 64

    def test_parse_valid_sourceref(self) -> None:
        source_ref = parse_sourceref(
            "repo://owner/repo/raw/processed/source.md@abc1234"
            f"#L1-L2?sha256={self.checksum}"
        )

        self.assertEqual(source_ref.owner, "owner")
        self.assertEqual(source_ref.repo, "repo")
        self.assertEqual(source_ref.path, "raw/processed/source.md")
        self.assertEqual(source_ref.git_sha, "abc1234")
        self.assertEqual(source_ref.anchor, "L1-L2")
        self.assertEqual(source_ref.sha256, self.checksum)

    def test_missing_or_invalid_anchor(self) -> None:
        cases = (
            (
                "repo://owner/repo/raw/inbox/source.md@abc1234"
                f"?sha256={self.checksum}",
                "missing_anchor",
            ),
            (
                "repo://owner/repo/raw/inbox/source.md@abc1234"
                f"#bad anchor?sha256={self.checksum}",
                "invalid_anchor",
            ),
        )

        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    parse_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)

    def test_invalid_checksum(self) -> None:
        with self.assertRaises(SourceRefValidationError) as ctx:
            parse_sourceref(
                "repo://owner/repo/raw/assets/chart.png@abc1234"
                "#asset?sha256=deadbeef"
            )

        self.assertEqual(ctx.exception.reason_code, "invalid_checksum")

    def test_disallowed_path_or_traversal(self) -> None:
        cases = (
            (
                "repo://owner/repo/raw/other/source.md@abc1234"
                f"#L1-L2?sha256={self.checksum}",
                "path_not_allowlisted",
            ),
            (
                "repo://owner/repo/raw/inbox/../secrets.md@abc1234"
                f"#L1-L2?sha256={self.checksum}",
                "path_traversal",
            ),
        )

        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    parse_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)

    def test_empty_string(self) -> None:
        cases = ("", "   ")
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    validate_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_FORMAT)


    def test_non_string_input(self) -> None:
        cases = (None, 123)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    validate_sourceref(value)  # type: ignore[arg-type]
                self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_STRUCTURE)

if __name__ == "__main__":
    unittest.main()
