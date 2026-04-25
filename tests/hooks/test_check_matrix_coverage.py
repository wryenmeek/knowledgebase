"""Tests for scripts.hooks.check_matrix_coverage."""

import textwrap
import unittest
from unittest.mock import MagicMock, patch


class CheckMatrixCoverageTests(unittest.TestCase):
    """Tests for the matrix coverage hook.

    The hook integrates with git and the filesystem, so we mock those
    boundary calls and test the core logic independently.
    """

    def _run_main(
        self,
        files: list[str],
        matrix_surfaces: set[str],
        has_head: bool = True,
        new_files: set[str] | None = None,
    ) -> int:
        """Run main() with controlled mocks."""
        if new_files is None:
            new_files = set(files)

        from scripts.hooks import check_matrix_coverage as mod

        def fake_normalize(path_str: str) -> str | None:
            if ":" in path_str:
                return None
            return path_str.replace("\\", "/")

        def fake_is_new(repo_rel: str) -> bool:
            return repo_rel in new_files

        with (
            patch.object(mod, "_normalize", side_effect=fake_normalize),
            patch.object(mod, "_has_head", return_value=has_head),
            patch.object(mod, "_is_new_file", side_effect=fake_is_new),
            patch("scripts.kb.agents_matrix_utils.parse_matrix_surfaces", return_value=matrix_surfaces),
        ):
            # Patch the import inside main() as well.
            with patch.dict(
                "sys.modules",
                {
                    "scripts.kb.agents_matrix_utils": MagicMock(
                        parse_matrix_surfaces=lambda _: matrix_surfaces
                    )
                },
            ):
                return mod.main(files)

    def test_covered_new_file_passes(self) -> None:
        result = self._run_main(
            files=["scripts/hooks/new_hook.py"],
            matrix_surfaces={"scripts/hooks/**"},
        )
        self.assertEqual(result, 0)

    def test_uncovered_new_file_fails(self) -> None:
        result = self._run_main(
            files=["scripts/experimental/foo.py"],
            matrix_surfaces={"scripts/kb/**"},  # does not cover experimental
        )
        self.assertEqual(result, 1)

    def test_existing_uncovered_file_passes(self) -> None:
        """Modifying a pre-existing file that isn't covered is grandfathered."""
        result = self._run_main(
            files=["scripts/experimental/old.py"],
            matrix_surfaces={"scripts/kb/**"},
            new_files=set(),  # not a new file
        )
        self.assertEqual(result, 0)

    def test_no_head_treats_all_files_as_new(self) -> None:
        """On initial commit (no HEAD), all files are treated as new."""
        result = self._run_main(
            files=["scripts/kb/new_module.py"],
            matrix_surfaces={"scripts/kb/**"},
            has_head=False,
        )
        self.assertEqual(result, 0)

    def test_no_head_uncovered_file_fails(self) -> None:
        result = self._run_main(
            files=["scripts/experimental/brand_new.py"],
            matrix_surfaces={"scripts/kb/**"},
            has_head=False,
        )
        self.assertEqual(result, 1)

    def test_non_script_file_skipped(self) -> None:
        """Non-script files (e.g., .md, .yaml) are not checked."""
        result = self._run_main(
            files=["README.md"],
            matrix_surfaces=set(),
        )
        self.assertEqual(result, 0)

    def test_empty_argv_exits_0(self) -> None:
        from scripts.hooks.check_matrix_coverage import main
        self.assertEqual(main([]), 0)

    def test_path_with_colon_skipped(self) -> None:
        """Paths containing colons are unsafe and skipped (not errored)."""
        result = self._run_main(
            files=["scripts/kb/bad:path.py"],
            matrix_surfaces={"scripts/kb/**"},
        )
        # Skipped paths don't cause failures.
        self.assertEqual(result, 0)

    def test_skill_logic_file_covered(self) -> None:
        result = self._run_main(
            files=[".github/skills/my-skill/logic/my_logic.py"],
            matrix_surfaces={".github/skills/my-skill/logic/**"},
        )
        self.assertEqual(result, 0)

    def test_skill_logic_file_uncovered(self) -> None:
        result = self._run_main(
            files=[".github/skills/new-skill/logic/impl.py"],
            matrix_surfaces={".github/skills/existing-skill/logic/**"},
        )
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
