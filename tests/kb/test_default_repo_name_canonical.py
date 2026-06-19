"""Regression tests for the canonical repository-name fallback helper."""

from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch

from scripts.kb.repo_identity import default_repo_name
from tests.kb.harnesses import REPO_ROOT, RuntimeWorkspaceTestCase, load_module


SKILL_LOGIC_ROOT = REPO_ROOT / ".github" / "skills"


class DefaultRepoNameCanonicalTests(RuntimeWorkspaceTestCase):
    def test_skill_logic_files_do_not_define_private_default_repo_name(self) -> None:
        offenders: list[str] = []
        for path in sorted(SKILL_LOGIC_ROOT.rglob("logic/*.py")):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=path.as_posix())
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "_default_repo_name"
                ):
                    offenders.append(path.relative_to(REPO_ROOT).as_posix())

        self.assertEqual(
            [],
            offenders,
            "Skill logic must import scripts.kb.repo_identity.default_repo_name instead of "
            "defining private _default_repo_name helpers.",
        )

    def test_skill_wrappers_share_worktree_aware_default_repo_name(self) -> None:
        worktree_root = self._create_synthetic_worktree()
        self._copy_skill_runtime_surface(worktree_root)
        validator_module = load_module(
            "canonical_repo_name_validators",
            worktree_root
            / ".github"
            / "skills"
            / "run-deterministic-validators"
            / "logic"
            / "run_deterministic_validators.py",
        )
        sync_module = load_module(
            "canonical_repo_name_sync",
            worktree_root
            / ".github"
            / "skills"
            / "sync-knowledgebase-state"
            / "logic"
            / "sync_knowledgebase_state.py",
        )
        sourceref_module = load_module(
            "canonical_repo_name_sourceref",
            worktree_root
            / ".github"
            / "skills"
            / "write-sourceref-citations"
            / "logic"
            / "write_sourceref_citations.py",
        )

        validator_repo_name = validator_module.default_repo_name(worktree_root)
        sync_repo_name = sync_module.default_repo_name(worktree_root)
        with patch.object(
            sourceref_module,
            "_resolve_git_ref",
            return_value="a" * 40,
        ), patch.object(
            sourceref_module,
            "_read_revision_bytes",
            return_value=b"commit-bound bytes\n",
        ), patch.object(sourceref_module.sourceref, "validate_sourceref"):
            citation = sourceref_module.build_sourceref_citation(
                source_path="raw/processed/source-a.md",
                anchor="asset",
                git_ref="HEAD",
                repo_root=worktree_root,
            )

        self.assertEqual("knowledgebase", validator_repo_name)
        self.assertEqual("knowledgebase", validator_module.REPO_NAME)
        self.assertEqual("knowledgebase", sync_module.REPO_NAME)
        self.assertEqual(validator_repo_name, sync_repo_name)
        self.assertTrue(
            citation.source_ref.startswith(
                f"repo://local/{validator_repo_name}/raw/processed/source-a.md@"
            )
        )

    def test_default_repo_name_discards_remote_query_and_fragment(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="https://example.test/local/knowledgebase.git?token=SECRET#fragment\n",
            stderr="",
        )

        with patch("scripts.kb.repo_identity.subprocess.run", return_value=completed):
            self.assertEqual("knowledgebase", default_repo_name(Path("ignored-worktree-name")))

    def _create_synthetic_worktree(self) -> Path:
        repo_root = self.workspace / "knowledgebase"
        worktree_root = self.workspace / "knowledgebase.worktrees" / "issue-275"
        repo_root.mkdir(parents=True, exist_ok=True)
        self._git(repo_root, "init")
        self._git(repo_root, "config", "user.name", "Test User")
        self._git(repo_root, "config", "user.email", "test@example.com")
        self._git(
            repo_root,
            "config",
            "remote.origin.url",
            "https://github.com/local/knowledgebase.git",
        )
        (repo_root / "README.md").write_text("# Knowledgebase\n", encoding="utf-8")
        self._git(repo_root, "add", "README.md")
        self._git(repo_root, "commit", "-m", "seed repo")
        self._git(repo_root, "worktree", "add", "-b", "issue-275", str(worktree_root))
        return worktree_root

    @staticmethod
    def _copy_skill_runtime_surface(worktree_root: Path) -> None:
        shutil.copytree(
            REPO_ROOT / "scripts" / "kb",
            worktree_root / "scripts" / "kb",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for skill_name in (
            "run-deterministic-validators",
            "sync-knowledgebase-state",
            "write-sourceref-citations",
        ):
            shutil.copytree(
                REPO_ROOT / ".github" / "skills" / skill_name,
                worktree_root / ".github" / "skills" / skill_name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
