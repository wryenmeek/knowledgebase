import unittest
from pathlib import Path

from scripts.kb.path_utils import (
    ERROR_KIND_INVALID_PATH,
    ERROR_KIND_PATH_TRAVERSAL,
    RepoRelativePathError,
    normalize_repo_relative_path,
    resolve_within_repo,
    try_normalize_repo_relative_path,
)

class TestPathUtils(unittest.TestCase):
    def test_try_normalize_repo_relative_path_valid(self):
        # Valid string
        self.assertEqual(try_normalize_repo_relative_path("wiki/pages/index.md"), ("wiki/pages/index.md", None))
        # Valid Path object
        self.assertEqual(try_normalize_repo_relative_path(Path("wiki/pages/index.md")), ("wiki/pages/index.md", None))

    def test_try_normalize_repo_relative_path_invalid(self):
        # Empty string
        self.assertEqual(try_normalize_repo_relative_path("")[1], ERROR_KIND_INVALID_PATH)
        # Leading slash
        self.assertEqual(try_normalize_repo_relative_path("/wiki/pages")[1], ERROR_KIND_INVALID_PATH)
        # Backslash
        self.assertEqual(try_normalize_repo_relative_path("wiki\\pages")[1], ERROR_KIND_INVALID_PATH)
        # Double slash
        self.assertEqual(try_normalize_repo_relative_path("wiki//pages")[1], ERROR_KIND_INVALID_PATH)
        # Dot segment
        self.assertEqual(try_normalize_repo_relative_path("wiki/./pages")[1], ERROR_KIND_INVALID_PATH)

    def test_try_normalize_repo_relative_path_traversal(self):
        self.assertEqual(try_normalize_repo_relative_path("wiki/../pages")[1], ERROR_KIND_PATH_TRAVERSAL)
        self.assertEqual(try_normalize_repo_relative_path("../wiki/pages")[1], ERROR_KIND_PATH_TRAVERSAL)

    def test_normalize_repo_relative_path_valid(self):
        self.assertEqual(normalize_repo_relative_path("wiki/pages/index.md"), "wiki/pages/index.md")
        self.assertEqual(normalize_repo_relative_path(Path("wiki/pages/index.md")), "wiki/pages/index.md")

    def test_normalize_repo_relative_path_invalid(self):
        with self.assertRaises(RepoRelativePathError):
            normalize_repo_relative_path("/wiki/pages")
        with self.assertRaises(RepoRelativePathError):
            normalize_repo_relative_path("wiki/../pages")

    def test_resolve_within_repo_valid(self):
        repo_root = Path("/fake/repo").resolve()

        # Relative path within repo
        self.assertEqual(resolve_within_repo(repo_root, "wiki/pages"), repo_root / "wiki/pages")

        # Absolute path within repo
        self.assertEqual(resolve_within_repo(repo_root, str(repo_root / "wiki/pages")), repo_root / "wiki/pages")

    def test_resolve_within_repo_invalid(self):
        repo_root = Path("/fake/repo").resolve()

        # Relative path escaping repo
        with self.assertRaises(RepoRelativePathError):
            resolve_within_repo(repo_root, "../outside")

        # Absolute path escaping repo
        with self.assertRaises(RepoRelativePathError):
            resolve_within_repo(repo_root, "/outside/repo")

if __name__ == '__main__':
    unittest.main()
