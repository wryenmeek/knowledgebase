"""Tests for scripts.hooks.check_mixed_scope."""

from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import patch

from scripts.hooks import check_mixed_scope


class CheckMixedScopeTests(unittest.TestCase):
    def test_no_staged_files_exits_0(self) -> None:
        with patch.object(check_mixed_scope, "_git_lines", return_value=set()):
            self.assertEqual(check_mixed_scope.main([]), 0)

    def test_staged_mixed_scope_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(check_mixed_scope, "_current_branch_paths", return_value=set()),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["raw/inbox/source.md", "scripts/init.py"])
        self.assertEqual(rc, 1)
        self.assertIn("mixed-scope staged commit detected", stderr.getvalue())

    def test_staged_path_normalization_fails_for_windows_paths(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(check_mixed_scope, "_current_branch_paths", return_value=set()),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["raw\\inbox\\source.md", "scripts\\init.py"])
        self.assertEqual(rc, 1)
        self.assertIn("mixed-scope staged commit detected", stderr.getvalue())

    def test_inbox_plus_benign_non_inbox_passes(self) -> None:
        with patch.object(check_mixed_scope, "_current_branch_paths", return_value=set()):
            self.assertEqual(
                check_mixed_scope.main(
                    [
                        "raw/inbox/source.md",
                        "docs/notes.md",
                        "tests/kb/test_ci1_workflow.py",
                        "wiki/sources/README.md",
                        "wiki/pages/home.md",
                        "README.md",
                        "LICENSE",
                    ]
                ),
                0,
            )

    def test_benign_only_staged_changes_skip_branch_scope_lookup(self) -> None:
        with patch.object(
            check_mixed_scope,
            "_current_branch_paths",
            side_effect=RuntimeError("should not be called for benign-only staged files"),
        ):
            self.assertEqual(check_mixed_scope.main(["docs/notes.md", "README.md"]), 0)

    def test_license_like_non_legal_file_is_treated_as_sensitive(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(check_mixed_scope, "_current_branch_paths", return_value=set()),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["raw/inbox/source.md", "LICENSE.py"])
        self.assertEqual(rc, 1)
        self.assertIn("mixed-scope staged commit detected", stderr.getvalue())

    def test_branch_transition_to_mixed_scope_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(
                check_mixed_scope,
                "_current_branch_paths",
                return_value={"raw/inbox/intake.md"},
            ),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["scripts/init.py"])
        self.assertEqual(rc, 1)
        self.assertIn("would make the branch mixed-scope", stderr.getvalue())

    def test_branch_transition_reverse_direction_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(
                check_mixed_scope,
                "_current_branch_paths",
                return_value={"scripts/init.py"},
            ),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["raw/inbox/intake.md"])
        self.assertEqual(rc, 1)
        self.assertIn("would make the branch mixed-scope", stderr.getvalue())

    def test_already_mixed_branch_does_not_block_unrelated_staged_file(self) -> None:
        with patch.object(
            check_mixed_scope,
            "_current_branch_paths",
            return_value={"raw/inbox/intake.md", "scripts/init.py"},
        ):
            self.assertEqual(check_mixed_scope.main(["docs/notes.md"]), 0)

    def test_already_mixed_branch_allows_non_benign_sensitive_staged_file(self) -> None:
        with patch.object(
            check_mixed_scope,
            "_current_branch_paths",
            return_value={"raw/inbox/intake.md", "scripts/init.py"},
        ):
            self.assertEqual(check_mixed_scope.main(["scripts/another_change.py"]), 0)

    def test_inbox_only_branch_and_inbox_only_staged_pass(self) -> None:
        with patch.object(
            check_mixed_scope,
            "_current_branch_paths",
            return_value={"raw/inbox/existing.md"},
        ):
            self.assertEqual(check_mixed_scope.main(["raw/inbox/new_source.md"]), 0)

    def test_sensitive_only_branch_and_sensitive_only_staged_pass(self) -> None:
        with patch.object(
            check_mixed_scope,
            "_current_branch_paths",
            return_value={"scripts/existing.py"},
        ):
            self.assertEqual(check_mixed_scope.main(["schema/new-contract.md"]), 0)

    def test_argv_empty_mixed_cached_paths_fails(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(
                check_mixed_scope,
                "_git_lines",
                return_value={"raw/inbox/source.md", "scripts/init.py"},
            ),
            patch.object(check_mixed_scope, "_current_branch_paths", return_value=set()),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main([])
        self.assertEqual(rc, 1)
        self.assertIn("mixed-scope staged commit detected", stderr.getvalue())

    def test_branch_scope_evaluation_error_fails_closed(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(
                check_mixed_scope,
                "_current_branch_paths",
                side_effect=RuntimeError("cannot resolve default branch"),
            ),
            redirect_stderr(stderr),
        ):
            rc = check_mixed_scope.main(["raw/inbox/source.md"])
        self.assertEqual(rc, 1)
        self.assertIn("could not evaluate branch mixed-scope status", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
