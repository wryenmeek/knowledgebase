"""Shared runtime fixtures and assertions for knowledgebase test suites."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parent


class HarnessAssertionsTestCase(unittest.TestCase):
    def assert_wrapper_routing(
        self,
        observed_calls: list[list[str]] | list[tuple[list[str], Path, bool]],
        expected_commands: list[list[str]],
    ) -> None:
        normalized = [call[0] if isinstance(call, tuple) else call for call in observed_calls]
        self.assertEqual(normalized, expected_commands)

    def assert_boundary_decision(
        self,
        decision: Any,
        *,
        allowed: bool,
        reason_code: str,
    ) -> None:
        self.assertEqual(decision.allowed, allowed)
        self.assertEqual(decision.reason_code, reason_code)

    def assert_append_only(
        self,
        path: Path,
        before: str | bytes,
        *,
        expected_suffix: str | bytes | None = None,
    ) -> None:
        if isinstance(before, bytes):
            after = path.read_bytes()
        else:
            after = path.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))
        if expected_suffix is not None:
            self.assertTrue(after.endswith(expected_suffix))


class RuntimeWorkspaceTestCase(HarnessAssertionsTestCase):
    RUNTIME_ROOT_NAME = ".runtime"

    def setUp(self) -> None:
        self.runtime_root = TESTS_ROOT / self.RUNTIME_ROOT_NAME
        self.workspace = self.runtime_root / f"{self._testMethodName}-{os.getpid()}"
        if self.workspace.exists():
            self._remove_tree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            self._remove_tree(self.workspace)
        if self.runtime_root.exists() and not any(self.runtime_root.iterdir()):
            self.runtime_root.rmdir()

    def write_file(self, relative_path: str, content: str) -> Path:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def snapshot_workspace(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if file_path.is_file():
                snapshot[file_path.relative_to(self.workspace).as_posix()] = file_path.read_bytes()
        return snapshot

    def assert_workspace_unchanged(self, before: dict[str, bytes]) -> None:
        self.assertEqual(before, self.snapshot_workspace())

    @property
    def workspace_root(self) -> Path:
        return self.workspace

    @staticmethod
    def _remove_tree(path: Path) -> None:
        try:
            shutil.rmtree(path)
        except OSError:
            subprocess.run(["rm", "-rf", str(path)], check=True)

    @staticmethod
    def build_process_page(
        title: str,
        body: str = "",
        *,
        confidence: str = "3",
        tags: tuple[str, ...] = ("test",),
    ) -> str:
        tag_lines = ["tags:", *[f"  - {tag}" for tag in tags]]
        lines = [
            "---",
            "type: process",
            f'title: "{title}"',
            "status: active",
            "sources: []",
            "open_questions: []",
            f"confidence: {confidence}",
            "sensitivity: internal",
            'updated_at: "2024-01-01T00:00:00Z"',
            *tag_lines,
            "---",
            "",
            f"# {title}",
            "",
        ]
        if body:
            lines.extend([body, ""])
        return "\n".join(lines)


class KnowledgebaseWorkspaceTestCase(RuntimeWorkspaceTestCase):
    RAW_DIRS: tuple[str, ...] = ()
    WIKI_SECTIONS: tuple[str, ...] = ()
    AGENTS_TEXT: str | None = None
    LOG_TEXT: str | None = None

    def setUp(self) -> None:
        super().setUp()
        for raw_dir in self.RAW_DIRS:
            (self.workspace / raw_dir).mkdir(parents=True, exist_ok=True)
        self.wiki_root = self.workspace / "wiki"
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        for section in self.WIKI_SECTIONS:
            (self.wiki_root / section).mkdir(parents=True, exist_ok=True)
        if self.LOG_TEXT is not None:
            (self.wiki_root / "log.md").write_text(self.LOG_TEXT, encoding="utf-8")
        if self.AGENTS_TEXT is not None:
            (self.workspace / "AGENTS.md").write_text(self.AGENTS_TEXT, encoding="utf-8")

    def write_wiki_page(self, relative_path: str, content: str) -> Path:
        page = self.wiki_root / relative_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(content, encoding="utf-8")
        return page


class RuntimeWrapperFixtureTestCase(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_skill_wrappers"
    INIT_FIXTURE_REPO: bool = False

    def setUp(self) -> None:
        super().setUp()
        self.repo_root = self.workspace / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        if self.INIT_FIXTURE_REPO:
            self._init_fixture_repo()

    def _git(self, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            check=True,
            capture_output=capture_output,
            text=True,
        )

    def _init_fixture_repo(self) -> None:
        shutil.copytree(
            REPO_ROOT / "scripts" / "kb",
            self.repo_root / "scripts" / "kb",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for skill_name in ("validate-wiki-governance", "sync-knowledgebase-state"):
            shutil.copytree(
                REPO_ROOT / ".github" / "skills" / skill_name,
                self.repo_root / ".github" / "skills" / skill_name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

        qmd_path = self.repo_root / "bin" / "qmd"
        qmd_path.parent.mkdir(parents=True, exist_ok=True)
        qmd_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        qmd_path.chmod(0o755)
        self.fixture_path = os.pathsep.join((str(qmd_path.parent), os.environ.get("PATH", "")))

        (self.repo_root / ".qmd" / "index").mkdir(parents=True, exist_ok=True)
        wiki_root = self.repo_root / "wiki"
        (wiki_root / "sources").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "raw" / "processed").mkdir(parents=True, exist_ok=True)

        artifact_path = self.repo_root / "raw" / "processed" / "source-a.md"
        artifact_path.write_text("commit-bound bytes\n", encoding="utf-8")

        self._git("init")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.com")

        (wiki_root / "log.md").write_text(
            self._build_page("Knowledgebase Log", "- state changes"),
            encoding="utf-8",
        )
        (wiki_root / "index.md").write_text(
            self._build_page("Knowledgebase Index", "- [Log](log.md)\n- [Source A](sources/source-a.md)"),
            encoding="utf-8",
        )

        self._git("add", ".")
        self._git("commit", "-m", "seed authoritative artifact")
        commit_sha = self._git("rev-parse", "HEAD", capture_output=True).stdout.strip()
        checksum = self._sha256(artifact_path)
        repo_name = re.sub(r"[^A-Za-z0-9_.-]", "-", self.repo_root.name) or "repo"
        source_ref = (
            f"repo://local/{repo_name}/raw/processed/source-a.md@{commit_sha}"
            f"#asset?sha256={checksum}"
        )

        (wiki_root / "sources" / "source-a.md").write_text(
            "\n".join(
                [
                    "---",
                    "type: source",
                    'title: "Source A"',
                    "status: active",
                    "sources:",
                    f'  - "{source_ref}"',
                    "open_questions: []",
                    "confidence: 5",
                    "sensitivity: internal",
                    'updated_at: "2024-01-01T00:00:00Z"',
                    "tags: [source]",
                    "---",
                    "",
                    "# Source A",
                    "",
                    "- [Index](../index.md)",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(self.repo_root / "scripts" / "kb" / "update_index.py"),
                "--wiki-root",
                "wiki",
                "--write",
            ],
            cwd=self.repo_root,
            check=True,
        )

    def _build_page(self, title: str, body: str) -> str:
        return self.build_process_page(title, body)

    def _load_fixture_module(self, relative_path: str, module_name: str):
        return load_module(module_name, self.repo_root / relative_path)

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def fixture_lock(self) -> "_DummyLock":
        return _DummyLock(REPO_ROOT / "wiki" / ".kb_write.lock")

    def read_fixture_source_ref(self) -> str:
        current_lines = (self.repo_root / "wiki" / "sources" / "source-a.md").read_text(
            encoding="utf-8"
        ).splitlines()
        return next(
            line.strip()[2:].strip().strip('"')
            for line in current_lines
            if line.strip().startswith("- ") and "repo://" in line
        )

    def write_valid_source_page(
        self,
        *,
        source_ref: str | None = None,
        inline_sources: bool = False,
    ) -> None:
        resolved_source_ref = source_ref if source_ref is not None else self.read_fixture_source_ref()
        sources_lines = (
            [f'sources: "{resolved_source_ref}"']
            if inline_sources
            else ["sources:", f'  - "{resolved_source_ref}"']
        )
        body = "\n".join(
            [
                "## Summary",
                "Authoritative summary.",
                "",
                "## Evidence",
                f"- {resolved_source_ref}: supports Source A.",
                "",
                "## Open Questions",
                "- None.",
            ]
        )
        self.write_source_page(sources_lines=sources_lines, body=body)

    def write_source_page(self, *, sources_lines: list[str], body: str) -> Path:
        """Write ``wiki/sources/source-a.md`` with the given sources block and body."""
        source_path = self.repo_root / "wiki" / "sources" / "source-a.md"
        lines = [
            "---",
            "type: source",
            'title: "Source A"',
            "status: active",
            *sources_lines,
            "open_questions: []",
            "confidence: 5",
            "sensitivity: internal",
            'updated_at: "2024-01-01T00:00:00Z"',
            "tags: [source]",
            "---",
            "",
            "# Source A",
            "",
            body,
            "",
        ]
        source_path.write_text("\n".join(lines), encoding="utf-8")
        return source_path


class _DummyLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path

    def __enter__(self) -> Path:
        return self.lock_path

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def parse_frontmatter_fields(text: str, *, subject: str = "File") -> dict[str, str]:
    """Parse a simple ``key: value`` YAML frontmatter block.

    Raises AssertionError when frontmatter is missing, so callers inside tests
    get the same ``self.fail`` ergonomics without reimplementing the parser.
    """
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        raise AssertionError(f"{subject} missing YAML frontmatter")
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip()
    return result


def section_body(text: str, heading: str) -> str:
    """Return the body under ``heading`` up to the next ``## `` heading."""
    start = text.find(heading)
    if start == -1:
        raise AssertionError(f"Missing heading: {heading}")
    start = text.find("\n", start)
    if start == -1:
        return ""
    remaining = text[start + 1 :]
    match = re.search(r"^##\s+", remaining, flags=re.MULTILINE)
    if match is None:
        return remaining
    return remaining[: match.start()]


@contextmanager
def force_thread_pool(module: Any) -> Iterator[None]:
    """Swap ``ProcessPoolExecutor`` for ``ThreadPoolExecutor`` in ``update_index``.

    Wrapper tests that exercise ``update_index`` through a loaded skill module
    use this to avoid subprocess fork overhead and to keep patched print hooks
    reachable from the executor workers.
    """
    futures = module.update_index.concurrent.futures
    with patch.object(futures, "ProcessPoolExecutor", futures.ThreadPoolExecutor):
        yield
