"""Pytest migration ratchet checks."""

from __future__ import annotations

from pathlib import Path

from scripts.hooks import check_test_framework
from scripts.kb.contracts import MAX_UNITTEST_FILES

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = REPO_ROOT / "tests"


def _unittest_test_files() -> list[Path]:
    files: list[Path] = []
    for path in TESTS_ROOT.glob("**/*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if check_test_framework.contains_unittest_testcase(text):
            files.append(path)
    return sorted(files)


def _dotted_case_source() -> str:
    return "\n".join(
        [
            "import unittest",
            "class TestNew(unittest." + "TestCase):",
            "    def test_x(self):",
            "        self.assertEqual(1, 1)",
        ]
    )


def _from_import_case_source() -> str:
    return "\n".join(
        [
            "from unittest import " + "TestCase",
            "class TestNew(TestCase):",
            "    def test_x(self):",
            "        self.assertEqual(1, 1)",
        ]
    )


def test_unittest_file_count_matches_contract_exactly() -> None:
    files = _unittest_test_files()

    assert len(files) == MAX_UNITTEST_FILES, (
        f"{len(files)} unittest-style test files must equal MAX_UNITTEST_FILES="
        f"{MAX_UNITTEST_FILES}: "
        + ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in files)
    )


def test_hook_detects_unittest_testcase_styles() -> None:
    assert check_test_framework.contains_unittest_testcase(_dotted_case_source())
    assert check_test_framework.contains_unittest_testcase(_from_import_case_source())
    assert check_test_framework.contains_unittest_testcase(
        "class TestNew(unittest." + "TestCase):\n    pass\n"
    )
    assert check_test_framework.contains_unittest_testcase(
        "\n".join(
            [
                "from unittest import mock, " + "TestCase",
                "class TestNew(TestCase):",
                "    def test_x(self):",
                "        self.assertEqual(1, 1)",
            ]
        )
    )
    assert check_test_framework.contains_unittest_testcase(
        "\n".join(
            [
                "import unittest as ut",
                "class TestNew(ut.TestCase):",
                "    def test_x(self):",
                "        self.assertEqual(1, 1)",
            ]
        )
    )
    assert check_test_framework.contains_unittest_testcase(
        "class TestNew(unittest.case.TestCase):\n    pass\n"
    )
    assert check_test_framework.contains_unittest_testcase(
        "\n".join(
            [
                "from unittest.case import " + "TestCase",
                "class TestNew(TestCase):",
                "    pass",
            ]
        )
    )
    assert check_test_framework.contains_unittest_testcase(
        "\n".join(
            [
                "import unittest",
                "Case = unittest.TestCase",
                "class TestAlias(Case):",
                "    pass",
            ]
        )
    )
    assert not check_test_framework.contains_unittest_testcase(
        "def test_pytest_style():\n    assert 1 == 1\n"
    )
    assert not check_test_framework.contains_unittest_testcase(
        'def test_docs():\n    text = "unittest.' + 'TestCase example"\n    assert text\n'
    )


def test_hook_rejects_new_unittest_style_test(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: ([check_test_framework.StagedTestPath("A", "tests/new_test.py")], None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_staged_content",
        lambda path: (_dotted_case_source(), None),
    )

    assert check_test_framework.main([]) == 1
    captured = capsys.readouterr()
    assert "new tests must use pytest" in captured.err


def test_hook_parses_copied_and_renamed_test_paths(monkeypatch) -> None:
    captured_args = []
    git_output = "\0".join(
        [
            "C100",
            "tests/source_test.py",
            "tests/copied_test.py",
            "R100",
            "legacy/old_test.py",
            "tests/renamed_test.py",
            "M",
            "tests/modified_test.py",
            "",
        ]
    )
    monkeypatch.setattr(
        check_test_framework,
        "_run_git",
        lambda *args: (captured_args.append(args) or (0, git_output, "")),
    )

    staged, error = check_test_framework._staged_test_paths()

    assert error is None
    assert staged == [
        check_test_framework.StagedTestPath(
            "C100", "tests/copied_test.py", "tests/source_test.py"
        ),
        check_test_framework.StagedTestPath(
            "R100", "tests/renamed_test.py", "legacy/old_test.py"
        ),
        check_test_framework.StagedTestPath("M", "tests/modified_test.py"),
    ]
    assert "-z" in captured_args[0]


def test_hook_requests_rename_and_copy_detection(monkeypatch) -> None:
    captured_args = []

    def fake_run_git(*args):
        captured_args.append(args)
        return 0, "", ""

    monkeypatch.setattr(check_test_framework, "_run_git", fake_run_git)

    staged, error = check_test_framework._staged_test_paths()

    assert staged == []
    assert error is None
    assert "-z" in captured_args[0]
    assert "--find-renames" in captured_args[0]
    assert "--find-copies" in captured_args[0]


def test_hook_rejects_copied_unittest_style_test(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: (
            [
                check_test_framework.StagedTestPath(
                    "C100", "tests/copied_test.py", "tests/source_test.py"
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_staged_content",
        lambda path: (_dotted_case_source(), None),
    )

    assert check_test_framework.main([]) == 1
    captured = capsys.readouterr()
    assert "new tests must use pytest" in captured.err


def test_hook_rejects_any_modified_unittest_style_test(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: ([check_test_framework.StagedTestPath("M", "tests/old_test.py")], None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_current_content",
        lambda path, base_ref: (_dotted_case_source(), None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_previous_content",
        lambda path, base_ref: (_dotted_case_source().replace("1, 1", "1, 2"), None),
    )

    assert check_test_framework.main([]) == 1
    captured = capsys.readouterr()
    assert "non-docstring changes" in captured.err


def test_hook_allows_docstring_only_change_on_existing_unittest_file(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: ([check_test_framework.StagedTestPath("M", "tests/old_test.py")], None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_previous_content",
        lambda path, base_ref: (
            "import unittest\nclass TestOld(unittest.TestCase):\n    def test_x(self):\n        \"\"\"old\"\"\"\n        self.assertEqual(1, 1)\n",
            None,
        ),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_current_content",
        lambda path, base_ref: (
            "import unittest\nclass TestOld(unittest.TestCase):\n    def test_x(self):\n        \"\"\"new\"\"\"\n        self.assertEqual(1, 1)\n",
            None,
        ),
    )

    assert check_test_framework.main([]) == 0
    captured = capsys.readouterr()
    assert "ERROR:" not in captured.err


def test_hook_allows_modified_file_after_pytest_migration(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: ([check_test_framework.StagedTestPath("M", "tests/old_test.py")], None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_previous_content",
        lambda path, base_ref: (_dotted_case_source(), None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_current_content",
        lambda path, base_ref: ("def test_now_pytest_style():\n    assert 1 == 1\n", None),
    )

    assert check_test_framework.main([]) == 0
    captured = capsys.readouterr()
    assert "ERROR:" not in captured.err


def test_hook_uses_ci_diff_mode_when_base_ref_env_is_set(monkeypatch) -> None:
    monkeypatch.setenv("KB_TEST_FRAMEWORK_RATCHET_BASE_REF", "origin/main")
    monkeypatch.setattr(check_test_framework, "_ci_test_paths", lambda base_ref: ([], None))
    monkeypatch.setattr(check_test_framework, "_staged_test_paths", lambda: ([], "unexpected"))
    assert check_test_framework.main([]) == 0
