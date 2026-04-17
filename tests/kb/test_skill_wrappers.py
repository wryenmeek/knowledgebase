"""Tests for thin governance/state skill wrappers."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_skill_wrappers"
VALIDATE_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "validate-wiki-governance"
    / "logic"
    / "validate_wiki_governance.py"
)
SYNC_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "sync-knowledgebase-state"
    / "logic"
    / "sync_knowledgebase_state.py"
)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _RuntimeWrapperFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.repo_root = self.workspace / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if RUNTIME_ROOT.exists() and not any(RUNTIME_ROOT.iterdir()):
            RUNTIME_ROOT.rmdir()

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
        shutil.copytree(
            REPO_ROOT / ".github" / "skills" / "validate-wiki-governance",
            self.repo_root / ".github" / "skills" / "validate-wiki-governance",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            REPO_ROOT / ".github" / "skills" / "sync-knowledgebase-state",
            self.repo_root / ".github" / "skills" / "sync-knowledgebase-state",
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

        (wiki_root / "log.md").write_text(self._build_page("Knowledgebase Log", "- state changes"), encoding="utf-8")
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
        return "\n".join(
            [
                "---",
                "type: process",
                f'title: "{title}"',
                "status: active",
                "sources: []",
                "open_questions: []",
                "confidence: 3",
                "sensitivity: internal",
                'updated_at: "2024-01-01T00:00:00Z"',
                "tags: [test]",
                "---",
                "",
                f"# {title}",
                "",
                body,
                "",
            ]
        )

    def _load_fixture_module(self, relative_path: str, module_name: str):
        return _load_module(module_name, self.repo_root / relative_path)

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidateWikiGovernanceWrapperTests(unittest.TestCase):
    def test_wrapper_allowlist_matches_expected_scripts(self) -> None:
        module = _load_module("validate_wiki_governance_allowlist", VALIDATE_WRAPPER_PATH)

        self.assertEqual(
            tuple(command.script_relative_path for command in module.READ_ONLY_VALIDATORS),
            (
                "scripts/kb/qmd_preflight.py",
                "scripts/kb/update_index.py",
                "scripts/kb/lint_wiki.py",
            ),
        )

    def test_wrapper_runs_fixed_read_only_validation_sequence(self) -> None:
        module = _load_module("validate_wiki_governance", VALIDATE_WRAPPER_PATH)
        calls: list[tuple[list[str], Path, bool]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append((command, cwd, check))

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][1], REPO_ROOT)
        self.assertTrue(all(check is True for _command, _cwd, check in calls))
        self.assertEqual(
            calls[0][0],
            [
                module.sys.executable,
                str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                "--repo-root",
                str(REPO_ROOT),
                "--required-resource",
                ".qmd/index",
            ],
        )
        self.assertEqual(
            calls[1][0],
            [
                module.sys.executable,
                str(REPO_ROOT / "scripts" / "kb" / "update_index.py"),
                "--wiki-root",
                "wiki",
                "--check",
            ],
        )
        self.assertEqual(
            calls[2][0],
            [
                module.sys.executable,
                str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                "--wiki-root",
                "wiki",
                "--strict",
                "--authoritative-sourcerefs",
                "--repo-owner",
                "local",
                "--repo-name",
                "knowledgebase",
            ],
        )

    def test_wrapper_fails_closed_on_first_precheck_error(self) -> None:
        module = _load_module("validate_wiki_governance_fail", VALIDATE_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            raise module.subprocess.CalledProcessError(returncode=7, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main([])

        self.assertEqual(exit_code, 7)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1].endswith("qmd_preflight.py"))


class SyncKnowledgebaseStateWrapperTests(unittest.TestCase):
    def test_wrapper_allowlist_matches_expected_scripts(self) -> None:
        module = _load_module("sync_knowledgebase_state_allowlist", SYNC_WRAPPER_PATH)

        self.assertEqual(
            tuple(command.script_relative_path for command in module.READ_ONLY_PRECHECKS),
            (
                "scripts/kb/qmd_preflight.py",
                "scripts/kb/update_index.py",
                "scripts/kb/lint_wiki.py",
            ),
        )
        self.assertEqual(
            module.WRITE_INDEX_COMMAND.script_relative_path,
            "scripts/kb/update_index.py",
        )

    def test_check_only_mode_stays_read_only(self) -> None:
        module = _load_module("sync_knowledgebase_state_check", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--check-only"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            calls,
            [
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--required-resource",
                    ".qmd/index",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "update_index.py"),
                    "--wiki-root",
                    "wiki",
                    "--check",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
            ],
        )

    def test_apply_mode_runs_validation_before_single_write_step(self) -> None:
        module = _load_module("sync_knowledgebase_state_apply", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            calls,
            [
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--required-resource",
                    ".qmd/index",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--skip-orphan-check",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "update_index.py"),
                    "--wiki-root",
                    "wiki",
                    "--write",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
            ],
        )

    def test_write_mode_tolerates_stale_index_before_repair(self) -> None:
        module = _load_module("sync_knowledgebase_state_stale_index", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[1].endswith("update_index.py") and "--check" in command:
                raise AssertionError("write mode must not block on stale index drift")

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            calls[1][-6:],
            [
                "--skip-orphan-check",
                "--authoritative-sourcerefs",
                "--repo-owner",
                "local",
                "--repo-name",
                "knowledgebase",
            ],
        )
        self.assertEqual(calls[2][-1], "--write")
        self.assertEqual(
            calls[3][-6:],
            [
                "--strict",
                "--authoritative-sourcerefs",
                "--repo-owner",
                "local",
                "--repo-name",
                "knowledgebase",
            ],
        )

    def test_validation_failure_stops_before_write(self) -> None:
        module = _load_module("sync_knowledgebase_state_fail", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[1].endswith("lint_wiki.py"):
                raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(command[-1] == "--write" for command in calls))

    def test_write_failure_returns_non_zero_after_prechecks(self) -> None:
        module = _load_module("sync_knowledgebase_state_write_fail", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[-1] == "--write":
                raise module.subprocess.CalledProcessError(returncode=9, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 9)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][-1], "--write")


class ValidateWikiGovernanceWrapperRuntimeTests(_RuntimeWrapperFixture):
    def test_wrapper_runs_end_to_end_with_authoritative_lint(self) -> None:
        self._init_fixture_repo()
        module = self._load_fixture_module(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "validate_wiki_governance_runtime",
        )

        with patch.dict(os.environ, {"PATH": self.fixture_path}, clear=False):
            exit_code = module.main([])

        self.assertEqual(exit_code, 0)


class SyncKnowledgebaseStateWrapperRuntimeTests(_RuntimeWrapperFixture):
    def test_write_index_mode_runs_end_to_end_with_authoritative_lint(self) -> None:
        self._init_fixture_repo()
        module = self._load_fixture_module(
            ".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py",
            "sync_knowledgebase_state_runtime",
        )

        with patch.dict(os.environ, {"PATH": self.fixture_path}, clear=False):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
