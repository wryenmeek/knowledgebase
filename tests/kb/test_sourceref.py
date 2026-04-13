"""Unit tests for SourceRef parsing and validation."""

from __future__ import annotations

import unittest

from scripts.kb.sourceref import SourceRefValidationError, parse_sourceref, _validate_source_path, SourceRefReasonCode


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
                SourceRefReasonCode.PATH_NOT_ALLOWLISTED,
            ),
            (
                "repo://owner/repo/raw/inbox/../secrets.md@abc1234"
                f"#L1-L2?sha256={self.checksum}",
                SourceRefReasonCode.PATH_TRAVERSAL,
            ),
        )

        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    parse_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)



    def test_validate_source_path_invalid(self) -> None:
        cases = (
            ("/", SourceRefReasonCode.INVALID_PATH),
            ("/raw/inbox/file.md", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/file.md/", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/file\\md", SourceRefReasonCode.INVALID_PATH),
            ("raw//inbox/file.md", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/.", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/./file.md", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/..", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/../file.md", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/other/file.md", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
            ("something/else", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
            ("raw", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
        )
        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    _validate_source_path(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)



    def test_validate_source_path_valid(self) -> None:
        valid_paths = (
            "raw/inbox/file.md",
            "raw/processed/some/dir/file.md",
            "raw/assets/image.png",
        )
        for path in valid_paths:
            with self.subTest(path=path):
                # Should not raise any exception
                _validate_source_path(path)



    def test_validate_source_path_empty(self) -> None:
        with self.assertRaises(SourceRefValidationError) as ctx:
            _validate_source_path("")
        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_FORMAT)


if __name__ == "__main__":
    unittest.main()
