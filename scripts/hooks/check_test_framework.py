#!/usr/bin/env python3
"""Git hook: ratchet tests toward pytest as the canonical framework.

New staged test files may not introduce unittest ``TestCase`` tests. Existing
unittest-style tests may not change test logic without first migrating the file
to pytest.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re
import subprocess
import sys

ADR_REFERENCE = "ADR-029"

_DOTTED_TESTCASE_RE = re.compile(r"\bunittest[.]TestCase\b")
_FROM_IMPORT_TESTCASE_RE = re.compile(
    r"^\s*from\s+unittest\s+import\s+"
    r"(?:[A-Za-z_]\w*\s*,\s*)*"
    r"TestCase(?:\s+as\s+[A-Za-z_]\w*)?"
    r"(?:\s*,|\s*(?:#.*)?$)",
    re.MULTILINE,
)
_IMPORT_UNITTEST_RE = re.compile(
    r"^\s*import\s+unittest(?:\s+as\s+[A-Za-z_]\w*)?(?:\s*#.*)?$",
    re.MULTILINE,
)
_TESTCASE_REFERENCE_RE = re.compile(r"\bTestCase\b")


@dataclass(frozen=True, slots=True)
class StagedTestPath:
    status: str
    path: str
    old_path: str | None = None


def _run_git(*args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_test_python_path(path: str) -> bool:
    parts = path.split("/")
    return (
        path.startswith("tests/")
        and path.endswith(".py")
        and "__pycache__" not in parts
        and ".." not in parts
        and "" not in parts
    )


def _staged_test_paths() -> tuple[list[StagedTestPath], str | None]:
    rc, out, err = _run_git(
        "diff",
        "--cached",
        "--name-status",
        "--find-renames",
        "--find-copies",
        "--",
        "tests",
    )
    if rc != 0:
        return [], f"cannot enumerate staged test paths: {err.strip() or out.strip()}"

    staged: list[StagedTestPath] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            return [], f"unexpected git name-status line: {line!r}"
        status = parts[0]
        status_code = status[:1]
        path = _normalize_path(parts[-1])
        old_path = (
            _normalize_path(parts[1])
            if status_code in {"C", "R"} and len(parts) >= 3
            else None
        )
        if status_code in {"A", "C", "M", "R"} and _is_test_python_path(path):
            staged.append(StagedTestPath(status=status, path=path, old_path=old_path))
    return staged, None


def _get_staged_content(path: str) -> tuple[str, str | None]:
    rc, out, err = _run_git("show", f":{path}")
    if rc != 0:
        return "", f"{path}: cannot read staged content: {err.strip() or out.strip()}"
    return out, None


def _get_head_content(path: str) -> tuple[str, str | None]:
    rc, out, err = _run_git("show", f"HEAD:{path}")
    if rc != 0:
        return "", f"{path}: cannot read HEAD content: {err.strip() or out.strip()}"
    return out, None


def _contains_unittest_testcase_fallback(text: str) -> bool:
    if _DOTTED_TESTCASE_RE.search(text) or _FROM_IMPORT_TESTCASE_RE.search(text):
        return True
    return bool(_IMPORT_UNITTEST_RE.search(text) and _TESTCASE_REFERENCE_RE.search(text))


def contains_unittest_testcase(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _contains_unittest_testcase_fallback(text)

    unittest_aliases: set[str] = set()
    unittest_case_aliases: set[str] = set()
    testcase_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "unittest":
                    unittest_aliases.add(alias.asname or alias.name)
                elif alias.name == "unittest.case":
                    unittest_case_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module in {
            "unittest",
            "unittest.case",
        }:
            for alias in node.names:
                if alias.name in {"TestCase", "*"}:
                    testcase_names.add(alias.asname or "TestCase")
                    return True
                if node.module == "unittest" and alias.name == "case":
                    unittest_case_aliases.add(alias.asname or "case")

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            dotted_base = _dotted_name(base)
            if dotted_base:
                for alias in unittest_aliases | {"unittest"}:
                    if dotted_base in {f"{alias}.TestCase", f"{alias}.case.TestCase"}:
                        return True
                for alias in unittest_case_aliases | {"unittest.case"}:
                    if dotted_base == f"{alias}.TestCase":
                        return True
            if isinstance(base, ast.Name) and (
                base.id in testcase_names
                or (unittest_aliases and base.id == "TestCase")
            ):
                return True

    if unittest_aliases:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "TestCase":
                return True
    return False


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def _contains_unittest_testcase(text: str) -> bool:
    return contains_unittest_testcase(text)


def _docstring_line_numbers(text: str) -> set[int]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()

    docstring_lines: set[int] = set()
    docstring_owners = (
        ast.Module,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
    )
    for node in ast.walk(tree):
        if not isinstance(node, docstring_owners) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            start = getattr(first, "lineno", None)
            end = getattr(first, "end_lineno", start)
            if start is not None and end is not None:
                docstring_lines.update(range(start, end + 1))
    return docstring_lines


def _logic_signature(text: str) -> list[str]:
    signature: list[str] = []
    docstring_lines = _docstring_line_numbers(text)

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if line_number in docstring_lines:
            continue
        if not stripped or stripped.startswith("#"):
            continue
        signature.append(stripped)

    return signature


class _DocstringStripper(ast.NodeTransformer):
    def visit_Module(self, node: ast.Module) -> ast.Module:
        self.generic_visit(node)
        node.body = _without_leading_docstring(node.body)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        self.generic_visit(node)
        node.body = _without_leading_docstring(node.body)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        self.generic_visit(node)
        node.body = _without_leading_docstring(node.body)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        self.generic_visit(node)
        node.body = _without_leading_docstring(node.body)
        return node


def _without_leading_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _normalized_logic_ast(text: str) -> str | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    tree = _DocstringStripper().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False)


def _test_logic_changed(old_text: str, new_text: str) -> bool:
    old_ast = _normalized_logic_ast(old_text)
    new_ast = _normalized_logic_ast(new_text)
    if old_ast is not None and new_ast is not None:
        return old_ast != new_ast
    return _logic_signature(old_text) != _logic_signature(new_text)


def _new_file_error(path: str) -> str:
    return (
        f"{path}: new tests must use pytest, not unittest TestCase. "
        f"Migrate the file to pytest-style functions or fixtures before staging."
    )


def _modified_file_error(path: str) -> str:
    return (
        f"{path}: staged test logic changes touch an existing unittest TestCase file. "
        f"Migrate this file to pytest before changing its test logic."
    )


def main(argv: list[str] | None = None) -> int:
    _ = argv
    staged_paths, path_error = _staged_test_paths()
    errors: list[str] = []
    if path_error is not None:
        errors.append(path_error)

    for staged in staged_paths:
        staged_text, staged_error = _get_staged_content(staged.path)
        if staged_error is not None:
            errors.append(staged_error)
            continue

        status_code = staged.status[:1]
        renamed_from_outside_tests = (
            status_code == "R"
            and staged.old_path is not None
            and not _is_test_python_path(staged.old_path)
        )

        if status_code in {"A", "C"} or renamed_from_outside_tests:
            if contains_unittest_testcase(staged_text):
                errors.append(_new_file_error(staged.path))
            continue

        if status_code in {"M", "R"} and contains_unittest_testcase(staged_text):
            head_path = (
                staged.old_path if status_code == "R" and staged.old_path else staged.path
            )
            head_text, head_error = _get_head_content(head_path)
            if head_error is not None:
                errors.append(head_error)
            elif _test_logic_changed(head_text, staged_text):
                errors.append(_modified_file_error(staged.path))

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(
            "\nPytest is the canonical framework. See "
            f"{ADR_REFERENCE}; use --no-verify only for an intentional local "
            "escape hatch, and expect CI ratchet checks to enforce the baseline.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
