"""Unit tests for github_monitor validation helpers (_types.py, _validators.py)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.github_monitor._types import (
    GitHubAPIResponseError,
    validate_contents_response,
    validate_commits_response,
)
from scripts.github_monitor._validators import (
    build_asset_path,
    validate_external_path,
)


class ValidateContentsResponseTests(unittest.TestCase):
    def _valid(self) -> dict:
        return {
            "sha": "abc123def456abc123def456abc123def456abc1",
            "content": "aGVsbG8=",
            "encoding": "base64",
            "size": 5,
            "name": "file.md",
            "path": "docs/file.md",
        }

    def test_valid_response_passes(self) -> None:
        result = validate_contents_response(self._valid())
        self.assertEqual(result["sha"], "abc123def456abc123def456abc123def456abc1")

    def test_directory_listing_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response([{"name": "file.md"}])

    def test_missing_sha_raises(self) -> None:
        data = self._valid()
        del data["sha"]
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_missing_content_raises(self) -> None:
        data = self._valid()
        del data["content"]
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_missing_encoding_raises(self) -> None:
        data = self._valid()
        del data["encoding"]
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_missing_size_raises(self) -> None:
        data = self._valid()
        del data["size"]
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_non_base64_encoding_raises(self) -> None:
        data = self._valid()
        data["encoding"] = "utf-8"
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_empty_sha_raises(self) -> None:
        data = self._valid()
        data["sha"] = ""
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)

    def test_integer_size_passes(self) -> None:
        data = self._valid()
        data["size"] = 0
        validate_contents_response(data)  # size=0 is valid (empty file)

    def test_string_size_raises(self) -> None:
        data = self._valid()
        data["size"] = "5"
        with self.assertRaises(GitHubAPIResponseError):
            validate_contents_response(data)


class ValidateCommitsResponseTests(unittest.TestCase):
    def _valid(self) -> list:
        return [{"sha": "abc123def456abc123def456abc123def456abc1", "commit": {}}]

    def test_valid_response_passes(self) -> None:
        result = validate_commits_response(self._valid())
        self.assertEqual(len(result), 1)

    def test_not_a_list_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_commits_response({"sha": "abc"})

    def test_empty_list_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_commits_response([])

    def test_first_item_not_dict_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_commits_response(["not-a-dict"])

    def test_first_item_missing_sha_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_commits_response([{"commit": {}}])

    def test_first_item_empty_sha_raises(self) -> None:
        with self.assertRaises(GitHubAPIResponseError):
            validate_commits_response([{"sha": ""}])


class ValidateExternalPathTests(unittest.TestCase):
    def test_simple_path_passes(self) -> None:
        self.assertEqual(validate_external_path("docs/guidance.md"), "docs/guidance.md")

    def test_nested_path_passes(self) -> None:
        self.assertEqual(
            validate_external_path("a/b/c/file.txt"), "a/b/c/file.txt"
        )

    def test_dotdot_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("docs/../../../etc/passwd")

    def test_absolute_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("/etc/passwd")

    def test_tilde_component_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("~/.ssh/id_rsa")

    def test_tilde_user_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("~root/file.txt")

    def test_null_byte_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("docs/file\x00.md")

    def test_url_encoded_dotdot_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("docs/%2e%2e/etc/passwd")

    def test_double_url_encoded_dotdot_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("docs/%252e%252e/etc/passwd")

    def test_url_encoded_null_byte_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("docs/%00evil.md")

    def test_empty_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("")

    def test_non_string_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path(None)  # type: ignore[arg-type]

    def test_windows_backslash_absolute_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_external_path("\\windows\\system32\\file.txt")


class BuildAssetPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name).resolve()
        (self.repo_root / "raw" / "assets").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _valid_args(self) -> dict:
        return {
            "repo_root": self.repo_root,
            "owner": "cms-gov",
            "repo": "regulations",
            "commit_sha": "a" * 40,
            "file_path": "docs/guidance.md",
        }

    def test_valid_args_return_resolved_path(self) -> None:
        result = build_asset_path(**self._valid_args())
        expected = (
            self.repo_root / "raw" / "assets" / "cms-gov" / "regulations"
            / ("a" * 40) / "docs" / "guidance.md"
        ).resolve()
        self.assertEqual(result, expected)

    def test_owner_with_slash_raises(self) -> None:
        args = self._valid_args()
        args["owner"] = "cms/gov"
        with self.assertRaises(ValueError):
            build_asset_path(**args)

    def test_repo_with_dotdot_raises(self) -> None:
        args = self._valid_args()
        args["repo"] = "../secret"
        with self.assertRaises(ValueError):
            build_asset_path(**args)

    def test_short_commit_sha_raises(self) -> None:
        args = self._valid_args()
        args["commit_sha"] = "abc123"  # too short
        with self.assertRaises(ValueError):
            build_asset_path(**args)

    def test_uppercase_sha_raises(self) -> None:
        args = self._valid_args()
        args["commit_sha"] = "A" * 40  # must be lowercase hex
        with self.assertRaises(ValueError):
            build_asset_path(**args)

    def test_empty_owner_raises(self) -> None:
        args = self._valid_args()
        args["owner"] = ""
        with self.assertRaises(ValueError):
            build_asset_path(**args)


if __name__ == "__main__":
    unittest.main()
