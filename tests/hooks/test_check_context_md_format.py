"""Tests for scripts.hooks.check_context_md_format."""

import textwrap
from pathlib import Path

from scripts.hooks.check_context_md_format import MAX_LINES, main

VALID_CONTENT = textwrap.dedent("""\
    ---
    scope: repo
    last_updated: 2025-07-01
    ---

    # CONTEXT

    ## Terms

    | Term | Definition |
    |------|------------|
    | foo | bar |

    ## Invariants

    | Invariant | Description |
    |-----------|-------------|
    | fail closed | Always. |

    ## File Roles

    | Path | Role |
    |------|------|
    | `wiki/` | Wiki pages. |
""")


def _write(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_valid_file_exits_0(tmp_path: Path) -> None:
    path = _write(tmp_path, "CONTEXT.md", VALID_CONTENT)
    assert main([path]) == 0


def test_missing_invariants_section_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("## Invariants\n", "").replace(
        "| Invariant | Description |\n|-----------|--------------|\n| fail closed | Always. |\n", ""
    )
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_missing_terms_section_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("## Terms\n", "").replace(
        "| Term | Definition |\n|------|------------|\n| foo | bar |\n", ""
    )
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_missing_file_roles_section_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("## File Roles\n", "").replace(
        "| Path | Role |\n|------|------|\n| `wiki/` | Wiki pages. |\n", ""
    )
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_lowercase_invariants_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("## Invariants", "## invariants")
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_exactly_200_lines_exits_0(tmp_path: Path) -> None:
    lines = VALID_CONTENT.splitlines()
    padding = MAX_LINES - len(lines)
    content = VALID_CONTENT + "\n" * padding
    # ⚡ Bolt Optimization: Avoid O(N) splitlines() array allocation
    assert (content.count("\n") + (0 if content.endswith("\n") else 1) if content else 0) == MAX_LINES
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 0


def test_201_lines_exits_1(tmp_path: Path) -> None:
    lines = VALID_CONTENT.splitlines()
    padding = (MAX_LINES + 1) - len(lines)
    content = VALID_CONTENT + "\n" * padding
    # ⚡ Bolt Optimization: Avoid O(N) splitlines() array allocation
    assert (content.count("\n") + (0 if content.endswith("\n") else 1) if content else 0) == MAX_LINES + 1
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_empty_file_exits_1_cleanly(tmp_path: Path) -> None:
    path = _write(tmp_path, "CONTEXT.md", "")
    assert main([path]) == 1


def test_missing_frontmatter_scope_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("scope: repo\n", "")
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_missing_frontmatter_last_updated_exits_1(tmp_path: Path) -> None:
    content = VALID_CONTENT.replace("last_updated: 2025-07-01\n", "")
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_section_inside_fenced_code_block_does_not_count(tmp_path: Path) -> None:
    content = textwrap.dedent("""\
        ---
        scope: repo
        last_updated: 2025-07-01
        ---

        # CONTEXT

        ## Terms

        | Term | Definition |
        |------|------------|
        | foo | bar |

        ```
        ## Invariants
        ## File Roles
        ```
    """)
    path = _write(tmp_path, "CONTEXT.md", content)
    assert main([path]) == 1


def test_empty_argv_exits_0() -> None:
    assert main([]) == 0
