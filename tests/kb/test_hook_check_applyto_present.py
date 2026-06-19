"""Tests for scripts.hooks.check_instructions_applyto_present."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_MODULE = "scripts.hooks.check_instructions_applyto_present"
FIXTURE_DIR = REPO_ROOT / "tests/fixtures/qa-ab"


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    return repo


def _stage_file(repo: Path, rel_path: str, content: str) -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run_git(repo, "add", rel_path)


def _write_worktree_file(repo: Path, rel_path: str, content: str) -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_hook(repo: Path, *paths: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, "-m", HOOK_MODULE, *paths],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_staged_instruction_file_without_applyto_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/python.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            description: Python conventions
            ---

            # Python conventions
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert rel_path in result.stderr
    assert "applyTo" in result.stderr
    assert "Fix: add YAML frontmatter" in result.stderr


def test_staged_instruction_file_with_applyto_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/python.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "scripts/**/*.py"
            description: Python conventions
            ---

            # Python conventions
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


def test_non_matching_staged_markdown_file_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = "docs/regular.md"
    _stage_file(repo, rel_path, "# Regular markdown\n")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


def test_empty_instruction_file_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/empty.instructions.md"
    _stage_file(repo, rel_path, "")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "missing frontmatter" in result.stderr
    assert "applyTo" in result.stderr


def test_instruction_file_without_frontmatter_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/no-frontmatter.instructions.md"
    _stage_file(repo, rel_path, "# No frontmatter\n")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "missing frontmatter" in result.stderr


def test_instruction_file_with_empty_applyto_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/empty-applyto.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: ""
            ---

            # Empty applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "empty applyTo" in result.stderr


def test_hook_uses_staged_content_when_worktree_is_invalid(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/staged-valid.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "scripts/**/*.py"
            ---

            # Staged valid
            """
        ),
    )
    _write_worktree_file(repo, rel_path, "# Worktree invalid\n")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


def test_hook_uses_staged_content_when_worktree_is_valid(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/staged-invalid.instructions.md"
    _stage_file(repo, rel_path, "# Staged invalid\n")
    _write_worktree_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "scripts/**/*.py"
            ---

            # Worktree valid
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "missing frontmatter" in result.stderr


def test_nested_instruction_path_matching_pre_commit_regex_exits_1(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/nested/python.instructions.md"
    _stage_file(repo, rel_path, "# Nested instruction without frontmatter\n")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert rel_path in result.stderr


def test_suffix_instruction_like_path_outside_root_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = "docs/.github/instructions/python.instructions.md"
    _stage_file(repo, rel_path, "# Not a root instruction file\n")

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


def test_instruction_path_with_parent_component_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    result = _run_hook(repo, ".github/instructions/../escape.instructions.md")

    assert result.returncode == 1
    assert "invalid .github/instructions path" in result.stderr


def test_instruction_path_with_backslash_component_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    slash_path = ".github/instructions/nested/valid.instructions.md"
    backslash_path = ".github/instructions/nested\\valid.instructions.md"
    _stage_file(
        repo,
        slash_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "scripts/**/*.py"
            ---

            # Valid slash path
            """
        ),
    )
    _stage_file(repo, backslash_path, "# Invalid backslash path\n")

    result = _run_hook(repo, backslash_path)

    assert result.returncode == 1
    assert "invalid .github/instructions path" in result.stderr


def test_matching_instruction_path_missing_from_index_exits_0(tmp_path: Path) -> None:
    """A path not in the git index represents a staged deletion (or an
    invocation outside of pre-commit). gh PR #219 review: skip instead of
    blocking, so ``git rm`` can complete on instruction files."""
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/missing.instructions.md"

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert "cannot read staged content" not in result.stderr


def test_staged_deletion_of_instruction_file_exits_0(tmp_path: Path) -> None:
    """Regression for gh PR #219 review: staging a deletion of an instruction
    file must not block the commit. The hook should skip deletions because
    ``git show :<path>`` fails for a path that is no longer in the index."""
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/to-delete.instructions.md"

    # First commit the file with a valid applyTo so the initial state is clean.
    valid = textwrap.dedent(
        """\
        ---
        applyTo: "src/**"
        ---
        body
        """
    )
    _stage_file(repo, rel_path, valid)
    _run_git(repo, "commit", "-m", "initial: add instruction file")

    # Now stage its deletion.
    _run_git(repo, "rm", rel_path)

    # The hook must skip the deletion rather than fail.
    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert "cannot read staged content" not in result.stderr


@pytest.mark.parametrize("applyto_value", ["[]", "null", "Null", "NULL", "~", "# comment"])
def test_yaml_semantic_empty_applyto_values_exit_1(
    tmp_path: Path, applyto_value: str
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/semantic-empty.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            f"""\
            ---
            applyTo: {applyto_value}
            ---

            # Semantic empty applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "empty applyTo" in result.stderr


def test_yaml_semantic_empty_list_with_spaces_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/empty-list-spaces.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: [ ]
            ---

            # Empty list applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "empty applyTo" in result.stderr


@pytest.mark.parametrize("applyto_value", ['"null"', '"[]"', "'~'"])
def test_quoted_yaml_keywords_are_non_empty_applyto_values(
    tmp_path: Path, applyto_value: str
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/quoted-keyword.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            f"""\
            ---
            applyTo: {applyto_value}
            ---

            # Quoted keyword applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize("applyto_value", ['"" # comment', "'' # comment", '"   " # comment'])
def test_quoted_empty_applyto_with_inline_comment_exits_1(
    tmp_path: Path, applyto_value: str
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/quoted-empty-comment.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            f"""\
            ---
            applyTo: {applyto_value}
            ---

            # Quoted empty applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "empty applyTo" in result.stderr


def test_quoted_applyto_hash_character_with_inline_comment_exits_0(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/quoted-hash.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "docs/#draft/**" # comment
            ---

            # Quoted hash applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0
    assert result.stderr == ""


def test_quoted_applyto_with_escaped_quote_and_comment_exits_0(
    tmp_path: Path,
) -> None:
    """Regression for gh PR #219 review: ``_strip_unquoted_inline_comment``
    must respect ``\\\"`` escaped quotes inside double-quoted strings so the
    quote-tracker does not desync and prematurely truncate the value.

    Without the escape fix, the parser sees the ``\\\"`` as a closing quote,
    treats the rest of the line as outside-quote, and strips at the ``#``,
    yielding an empty string and incorrectly flagging the file as empty.
    """
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/escaped-quote.instructions.md"
    # The value contains an escaped quote followed by a ``#`` that must
    # remain inside the quoted scalar, then a real inline comment.
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo: "docs/\\"odd\\"/#draft/**" # real comment
            ---

            # Escaped quotes in applyTo value
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0, f"unexpected stderr: {result.stderr}"
    assert result.stderr == ""


def test_pre_commit_config_registers_applyto_hook() -> None:
    config = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "id: instructions-applyto-present" in config
    assert "entry: python -m scripts.hooks.check_instructions_applyto_present" in config
    assert "files: '^\\.github/instructions/.*\\.instructions\\.md$'" in config
    assert "types: [markdown]" in config
    assert "pass_filenames: true" in config


def test_multiline_yaml_list_applyto_with_one_item_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/multiline-one.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo:
              - "scripts/**/*.py"
            ---

            # Multi-line list applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0, (
        f"expected exit 0 for multi-line applyTo: list; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert result.stderr == ""


def test_multiline_yaml_list_applyto_with_multiple_items_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/multiline-multi.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo:
              - "scripts/**/*.py"
              - "tests/**/*.py"
            ---

            # Multi-item list applyTo
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 0, (
        f"expected exit 0 for multi-item applyTo: list; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert result.stderr == ""


def test_multiline_yaml_list_applyto_with_empty_items_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/multiline-empty.instructions.md"
    _stage_file(
        repo,
        rel_path,
        textwrap.dedent(
            """\
            ---
            applyTo:
              - ""
              - ""
            ---

            # Multi-line list with empty strings
            """
        ),
    )

    result = _run_hook(repo, rel_path)

    assert result.returncode == 1
    assert "empty applyTo" in result.stderr


@pytest.mark.parametrize(
    ("fixture_name", "expected_code", "error_fragment"),
    (
        ("applyto-empty.instructions.md", 1, "empty applyTo"),
        ("applyto-invalid-regex.instructions.md", 0, ""),
        ("applyto-missing.instructions.md", 1, "missing required non-empty applyTo"),
    ),
)
def test_qa_ab_applyto_adversarial_fixtures(
    tmp_path: Path, fixture_name: str, expected_code: int, error_fragment: str
) -> None:
    repo = _init_repo(tmp_path)
    rel_path = ".github/instructions/qa-ab.instructions.md"
    _stage_file(repo, rel_path, _fixture_text(fixture_name))

    result = _run_hook(repo, rel_path)

    assert result.returncode == expected_code
    if error_fragment:
        assert error_fragment in result.stderr
    else:
        assert result.stderr == ""
