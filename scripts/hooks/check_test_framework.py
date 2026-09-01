#!/usr/bin/env python3
"""Git hook: ratchet tests toward pytest as the canonical framework.

New staged test files may not introduce unittest ``TestCase`` tests. Existing
unittest-style test files may not receive non-docstring changes until migrated.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts._redaction import redact_stderr  # noqa: E402

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
    return result.returncode, result.stdout, redact_stderr(result.stderr)


def _normalize_path(path: str) -> str:
    normalized = path
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _has_control_characters(path: str) -> bool:
    return any(ord(char) < 32 for char in path)


def _is_test_python_path(path: str) -> bool:
    parts = path.split("/")
    return (
        path.startswith("tests/")
        and path.endswith(".py")
        and "__pycache__" not in parts
        and ".." not in parts
        and "" not in parts
    )


def _parse_name_status_z(
    output: str,
) -> tuple[list[StagedTestPath], str | None]:
    fields = output.split("\0")
    if fields and fields[-1] == "":
        fields.pop()

    parsed: list[StagedTestPath] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        status_code = status[:1]
        if status_code in {"C", "R"}:
            if index + 1 >= len(fields):
                return [], f"malformed -z name-status output for {status!r}"
            old_path = _normalize_path(fields[index])
            path = _normalize_path(fields[index + 1])
            index += 2
        else:
            if index >= len(fields):
                return [], f"malformed -z name-status output for {status!r}"
            old_path = None
            path = _normalize_path(fields[index])
            index += 1

        if _has_control_characters(path) or (
            old_path is not None and _has_control_characters(old_path)
        ):
            return [], "name-status output contains unsupported control characters"

        if status_code in {"A", "C", "M", "R"} and _is_test_python_path(path):
            parsed.append(StagedTestPath(status=status, path=path, old_path=old_path))
    return parsed, None


def _test_paths_from_git_diff(*diff_args: str) -> tuple[list[StagedTestPath], str | None]:
    rc, out, err = _run_git(
        "diff",
        "--name-status",
        "-z",
        "--find-renames",
        "--find-copies",
        *diff_args,
        "--",
        "tests",
    )
    if rc != 0:
        return [], f"cannot enumerate changed test paths: {err.strip() or out.strip()}"
    return _parse_name_status_z(out)


def _staged_test_paths() -> tuple[list[StagedTestPath], str | None]:
    return _test_paths_from_git_diff("--cached")


def _ci_test_paths(base_ref: str) -> tuple[list[StagedTestPath], str | None]:
    return _test_paths_from_git_diff(f"{base_ref}...HEAD")


def _get_staged_content(path: str) -> tuple[str, str | None]:
    rc, out, err = _run_git("show", f":{path}")
    if rc != 0:
        return "", f"{path}: cannot read staged content: {err.strip() or out.strip()}"
    return out, None


def _get_current_content(path: str, base_ref: str | None) -> tuple[str, str | None]:
    if base_ref:
        rc, out, err = _run_git("show", f"HEAD:{path}")
        if rc != 0:
            return "", f"{path}: cannot read HEAD content: {err.strip() or out.strip()}"
        return out, None
    return _get_staged_content(path)


def _get_previous_content(path: str, base_ref: str | None) -> tuple[str, str | None]:
    revision = f"{base_ref}:{path}" if base_ref else f"HEAD:{path}"
    rc, out, err = _run_git("show", revision)
    if rc != 0:
        return "", f"{path}: cannot read previous content from {revision}: {err.strip() or out.strip()}"
    return out, None


class _DocstringStripper(ast.NodeTransformer):
    @staticmethod
    def _strip_leading_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            return body[1:]
        return body

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._strip_leading_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.body = self._strip_leading_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.body = self._strip_leading_docstring(node.body)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.body = self._strip_leading_docstring(node.body)
        self.generic_visit(node)
        return node


def _ast_signature_without_docstrings(text: str) -> str | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    stripped = _DocstringStripper().visit(tree)
    ast.fix_missing_locations(stripped)
    return ast.dump(stripped, include_attributes=False)


def _contains_non_docstring_change(previous_text: str, current_text: str) -> bool:
    if previous_text == current_text:
        return False
    previous_signature = _ast_signature_without_docstrings(previous_text)
    current_signature = _ast_signature_without_docstrings(current_text)
    if previous_signature is not None and current_signature is not None:
        return previous_signature != current_signature
    previous_normalized = "\n".join(
        line.strip() for line in previous_text.splitlines() if line.strip()
    )
    current_normalized = "\n".join(
        line.strip() for line in current_text.splitlines() if line.strip()
    )
    return previous_normalized != current_normalized


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

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                value = _dotted_name(node.value)
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                value = _dotted_name(node.value) if node.value is not None else None
                targets = [node.target]
            else:
                continue
            if value is None:
                continue

            is_testcase_alias = value in testcase_names
            if not is_testcase_alias:
                for alias in unittest_aliases | {"unittest"}:
                    if value in {f"{alias}.TestCase", f"{alias}.case.TestCase"}:
                        is_testcase_alias = True
                        break
            if not is_testcase_alias:
                for alias in unittest_case_aliases | {"unittest.case"}:
                    if value == f"{alias}.TestCase":
                        is_testcase_alias = True
                        break
            if not is_testcase_alias:
                continue

            for target in targets:
                if isinstance(target, ast.Name) and target.id not in testcase_names:
                    testcase_names.add(target.id)
                    changed = True

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


def _new_file_error(path: str) -> str:
    return (
        f"{path}: new tests must use pytest, not unittest TestCase. "
        f"Migrate the file to pytest-style functions or fixtures before staging."
    )


def _modified_file_error(path: str) -> str:
    return (
        f"{path}: existing unittest TestCase test files cannot receive non-docstring "
        "changes. Migrate this file to pytest in the same change."
    )


def main(argv: list[str] | None = None) -> int:
    _ = argv
    ci_base_ref = os.getenv("KB_TEST_FRAMEWORK_RATCHET_BASE_REF", "").strip() or None
    if ci_base_ref:
        staged_paths, path_error = _ci_test_paths(ci_base_ref)
    else:
        staged_paths, path_error = _staged_test_paths()
    errors: list[str] = []
    if path_error is not None:
        errors.append(path_error)

    for staged in staged_paths:
        staged_text, staged_error = _get_current_content(staged.path, ci_base_ref)
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

        if status_code not in {"M", "R"}:
            continue

        previous_path = staged.old_path or staged.path
        previous_text, previous_error = _get_previous_content(previous_path, ci_base_ref)
        if previous_error is not None:
            errors.append(previous_error)
            continue

        if not contains_unittest_testcase(previous_text):
            continue
        if not contains_unittest_testcase(staged_text):
            continue
        if _contains_non_docstring_change(previous_text, staged_text):
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
