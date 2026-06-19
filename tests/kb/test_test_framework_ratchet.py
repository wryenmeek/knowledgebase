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


def test_unittest_file_count_does_not_exceed_contract() -> None:
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
    assert not check_test_framework.contains_unittest_testcase(
        "def test_pytest_style():\n    assert 1 == 1\n"
    )
    assert not check_test_framework.contains_unittest_testcase(
        'def test_docs():\n    text = "unittest.' + 'TestCase example"\n    assert text\n'
    )


def test_hook_ignores_comment_and_docstring_only_changes() -> None:
    old = "\n".join(
        [
            '"""old module docs"""',
            "# old comment",
            "def test_x():",
            "    assert 1 == 1",
        ]
    )
    new = "\n".join(
        [
            '"""new module docs"""',
            "# new comment",
            "def test_x():",
            "    assert 1 == 1",
        ]
    )

    assert not check_test_framework._test_logic_changed(old, new)


def test_hook_ignores_inline_comment_and_formatting_only_changes() -> None:
    old = "def test_x():\n    value = 1  # old comment\n    assert value == 1\n"
    new = "def test_x():\n  value = 1  # new comment\n  assert value == 1\n"

    assert not check_test_framework._test_logic_changed(old, new)


def test_hook_treats_non_docstring_triple_quoted_strings_as_logic() -> None:
    old = 'def test_x():\n    payload = """old"""\n    assert payload\n'
    new = 'def test_x():\n    payload = """new"""\n    assert payload\n'

    assert check_test_framework._test_logic_changed(old, new)


def test_hook_treats_hash_lines_inside_strings_as_logic() -> None:
    old = 'def test_x():\n    payload = """\\n# old\\n"""\n    assert payload\n'
    new = 'def test_x():\n    payload = """\\n# new\\n"""\n    assert payload\n'

    assert check_test_framework._test_logic_changed(old, new)


def test_hook_detects_test_logic_changes() -> None:
    old = "def test_x():\n    assert 1 == 1\n"
    new = "def test_x():\n    assert 2 == 2\n"

    assert check_test_framework._test_logic_changed(old, new)


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
    git_output = "\n".join(
        [
            "C100\ttests/source_test.py\ttests/copied_test.py",
            "R100\tlegacy/old_test.py\ttests/renamed_test.py",
            "M\ttests/modified_test.py",
        ]
    )
    monkeypatch.setattr(
        check_test_framework,
        "_run_git",
        lambda *args: (0, git_output, ""),
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


def test_hook_requests_rename_and_copy_detection(monkeypatch) -> None:
    captured_args = []

    def fake_run_git(*args):
        captured_args.append(args)
        return 0, "", ""

    monkeypatch.setattr(check_test_framework, "_run_git", fake_run_git)

    staged, error = check_test_framework._staged_test_paths()

    assert staged == []
    assert error is None
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


def test_hook_rejects_modified_unittest_style_test_logic(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_test_framework,
        "_staged_test_paths",
        lambda: ([check_test_framework.StagedTestPath("M", "tests/old_test.py")], None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_staged_content",
        lambda path: (_dotted_case_source().replace("1, 1", "2, 2"), None),
    )
    monkeypatch.setattr(
        check_test_framework,
        "_get_head_content",
        lambda path: (_dotted_case_source(), None),
    )

    assert check_test_framework.main([]) == 1
    captured = capsys.readouterr()
    assert "Migrate this file to pytest" in captured.err
