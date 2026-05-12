"""Tests for scripts.hooks.check_no_staged_locks."""

import unittest

from scripts.hooks.check_no_staged_locks import main


class CheckNoStagedLocksTests(unittest.TestCase):
    def test_no_files_exits_0(self) -> None:
        self.assertEqual(main([]), 0)

    def test_governance_lock_kb_write_exits_1(self) -> None:
        self.assertEqual(main([".kb_write.lock"]), 1)

    def test_governance_lock_github_sources_exits_1(self) -> None:
        self.assertEqual(main([".github-sources.lock"]), 1)

    def test_governance_lock_rejection_registry_exits_1(self) -> None:
        self.assertEqual(main([".rejection-registry.lock"]), 1)

    def test_non_governance_lock_exits_0(self) -> None:
        self.assertEqual(main(["poetry.lock"]), 0)

    def test_non_governance_lock_package_lock_exits_0(self) -> None:
        self.assertEqual(main(["package-lock.json"]), 0)

    def test_governance_lock_in_path_exits_1(self) -> None:
        # Full path — basename is still a governance lock file.
        self.assertEqual(main(["wiki/.kb_write.lock"]), 1)

    def test_substring_not_exact_basename_exits_0(self) -> None:
        # ".kb_write.lock.backup" has a different basename — should pass.
        self.assertEqual(main([".kb_write.lock.backup"]), 0)

    def test_multiple_files_lock_among_them_exits_1(self) -> None:
        self.assertEqual(main(["README.md", ".kb_write.lock", "pyproject.toml"]), 1)

    def test_multiple_files_no_lock_exits_0(self) -> None:
        self.assertEqual(main(["README.md", "pyproject.toml"]), 0)

    def test_staged_deletion_path_still_exits_1(self) -> None:
        # Pre-commit passes the filename regardless of git status (D = deleted).
        # However, staging a deletion means the file is being *removed*, which
        # is permitted — this edge case depends on how pre-commit is configured.
        # For a bare deletion the file won't be in argv from pre-commit's
        # pass_filenames: true, but if it is passed, the hook should still
        # exit 1 on a governance lock name. Operators should use `git rm`
        # through the declared process, not stage raw lock files.
        self.assertEqual(main([".kb_write.lock"]), 1)


if __name__ == "__main__":
    unittest.main()
