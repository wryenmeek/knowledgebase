"""Unit tests for repo-relative path utilities."""

from __future__ import annotations

from pathlib import Path
import unittest
import shutil

from scripts.kb.path_utils import (
    ERROR_KIND_INVALID_PATH,
    ERROR_KIND_PATH_TRAVERSAL,
    RepoRelativePathError,
    normalize_repo_relative_path,
    resolve_within_repo,
    try_normalize_repo_relative_path,
)

_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_path_utils"


class TestPathUtils(unittest.TestCase):
    def setUp(self) -> None:
        if _RUNTIME_ROOT.exists():
            shutil.rmtree(_RUNTIME_ROOT)
        _RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if _RUNTIME_ROOT.exists():
            shutil.rmtree(_RUNTIME_ROOT)

    def test_try_normalize_repo_relative_path_valid(self) -> None:
        cases = [
            ("foo/bar.md", "foo/bar.md"),
            ("a/b/c", "a/b/c"),
            ("file.txt", "file.txt"),
        ]
        for input_path, expected in cases:
            with self.subTest(input_path=input_path):
                normalized, error_kind = try_normalize_repo_relative_path(input_path)
                self.assertEqual(normalized, expected)
                self.assertIsNone(error_kind)

    def test_try_normalize_repo_relative_path_invalid(self) -> None:
        cases = [
            ("", ERROR_KIND_INVALID_PATH),
            ("/a/b", ERROR_KIND_INVALID_PATH),
            ("a\\b", ERROR_KIND_INVALID_PATH),
            ("a//b", ERROR_KIND_INVALID_PATH),
            ("a/./b", ERROR_KIND_INVALID_PATH),
            ("a/", ERROR_KIND_INVALID_PATH),
            ("//a", ERROR_KIND_INVALID_PATH),
        ]
        for input_path, expected_kind in cases:
            with self.subTest(input_path=input_path):
                normalized, error_kind = try_normalize_repo_relative_path(input_path)
                self.assertEqual(normalized, input_path)
                self.assertEqual(error_kind, expected_kind)

    def test_try_normalize_repo_relative_path_traversal(self) -> None:
        cases = [
            ("a/../b", ERROR_KIND_PATH_TRAVERSAL),
            ("../a", ERROR_KIND_PATH_TRAVERSAL),
            ("a/..", ERROR_KIND_PATH_TRAVERSAL),
        ]
        for input_path, expected_kind in cases:
            with self.subTest(input_path=input_path):
                normalized, error_kind = try_normalize_repo_relative_path(input_path)
                self.assertEqual(normalized, input_path)
                self.assertEqual(error_kind, expected_kind)

    def test_try_normalize_repo_relative_path_path_object(self) -> None:
        input_path = Path("foo/bar.md")
        normalized, error_kind = try_normalize_repo_relative_path(input_path)
        self.assertEqual(normalized, "foo/bar.md")
        self.assertIsNone(error_kind)

    def test_normalize_repo_relative_path_success(self) -> None:
        self.assertEqual(normalize_repo_relative_path("foo/bar.md"), "foo/bar.md")

    def test_normalize_repo_relative_path_exceptions(self) -> None:
        # Invalid path exceptions
        with self.assertRaises(RepoRelativePathError) as cm:
            normalize_repo_relative_path("/abs/path")
        self.assertIn("repository-relative POSIX paths", str(cm.exception))

        with self.assertRaises(RepoRelativePathError) as cm:
            normalize_repo_relative_path("a/./b")
        self.assertIn("traversal or non-canonical segments", str(cm.exception))

        # Traversal exception
        with self.assertRaises(RepoRelativePathError) as cm:
            normalize_repo_relative_path("a/../b")
        self.assertIn("traversal or non-canonical segments", str(cm.exception))

    def test_resolve_within_repo(self) -> None:
        repo_root = _RUNTIME_ROOT.resolve()

        # Within repo
        file_path = repo_root / "foo" / "bar.md"
        file_path.parent.mkdir()
        file_path.touch()

        resolved = resolve_within_repo(repo_root, "foo/bar.md")
        self.assertEqual(resolved, file_path)

        resolved = resolve_within_repo(repo_root, str(file_path))
        self.assertEqual(resolved, file_path)

        # Escaping repo
        with self.assertRaises(RepoRelativePathError) as cm:
            resolve_within_repo(repo_root, "../outside.txt")
        self.assertIn("path escapes repository boundary", str(cm.exception))

        # Escaping via absolute path (on most systems /etc/passwd is outside _RUNTIME_ROOT)
        with self.assertRaises(RepoRelativePathError) as cm:
            resolve_within_repo(repo_root, "/etc/passwd")
        self.assertIn("path escapes repository boundary", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
