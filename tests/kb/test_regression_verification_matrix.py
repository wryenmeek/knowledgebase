"""Regression verification-matrix coverage for mutation-free linting and fail-closed writes."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest

from scripts.kb import ingest, write_utils


REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_SCRIPT = REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"
_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_verification_regression"


class RegressionVerificationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

        (self.workspace / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "processed").mkdir(parents=True, exist_ok=True)

        self.wiki_root = self.workspace / "wiki"
        self.wiki_root.mkdir(parents=True, exist_ok=True)

        (self.workspace / "AGENTS.md").write_text("schema fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

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

    def _write_wiki_page(self, relative_path: str, content: str) -> None:
        page = self.wiki_root / relative_path
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(content, encoding="utf-8")

    def _snapshot_workspace(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for path in sorted(self.workspace.rglob("*")):
            if path.is_file():
                snapshot[path.relative_to(self.workspace).as_posix()] = path.read_bytes()
        return snapshot

    def _run_ingest(self, *args: str) -> tuple[int, dict[str, object], str]:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = ingest.run_cli(
            argv=args,
            repo_root=self.workspace,
            output_stream=stdout,
            error_stream=stderr,
        )
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def _run_ingest_subprocess(self, *args: str) -> subprocess.CompletedProcess[str]:
        runner = textwrap.dedent(
            """
            import json
            import sys
            from scripts.kb import ingest

            repo_root = sys.argv[1]
            cli_args = json.loads(sys.argv[2])
            raise SystemExit(ingest.run_cli(argv=cli_args, repo_root=repo_root))
            """
        )
        return subprocess.run(
            [
                sys.executable,
                "-c",
                runner,
                str(self.workspace),
                json.dumps(list(args)),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_strict_lint_failures_remain_mutation_free(self) -> None:
        self._write_wiki_page(
            "index.md",
            self._build_page("Knowledgebase Index", "- [Missing](sources/missing.md)"),
        )
        self._write_wiki_page(
            "sources/orphan.md",
            self._build_page("Orphan", "This page is intentionally unreferenced."),
        )
        self._write_wiki_page(
            "sources/contradiction.md",
            self._build_page("Contradiction", "[CONTRADICTION] unresolved evidence conflict."),
        )
        before = self._snapshot_workspace()

        result = subprocess.run(
            [
                sys.executable,
                str(LINT_SCRIPT),
                "--wiki-root",
                str(self.wiki_root),
                "--strict",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing-link-target", result.stdout)
        self.assertEqual(before, self._snapshot_workspace())

    def test_ingest_lock_contention_returns_failed_envelope_without_writes(self) -> None:
        source_rel = "raw/inbox/alpha-source.md"
        (self.workspace / source_rel).write_text("alpha\n", encoding="utf-8")

        with write_utils.exclusive_write_lock(self.workspace):
            pass
        before = self._snapshot_workspace()

        with write_utils.exclusive_write_lock(self.workspace):
            completed = self._run_ingest_subprocess(
                "--source",
                source_rel,
                "--wiki-root",
                "wiki",
                "--schema",
                "AGENTS.md",
                "--report-json",
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reason_code"], "lock_unavailable")
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertIn("lock_unavailable", payload["message"])
        self.assertTrue((self.workspace / source_rel).exists())
        self.assertEqual(before, self._snapshot_workspace())

    def test_ingest_no_state_change_does_not_append_log(self) -> None:
        source_rel = "raw/inbox/missing-source.md"
        log_path = self.workspace / "wiki" / "log.md"
        with write_utils.exclusive_write_lock(self.workspace):
            pass
        before = self._snapshot_workspace()

        exit_code, payload, stderr = self._run_ingest(
            "--source",
            source_rel,
            "--wiki-root",
            "wiki",
            "--schema",
            "AGENTS.md",
            "--report-json",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "partial_success")
        self.assertEqual(payload["reason_code"], "per_source_failures")
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertFalse(log_path.exists())
        self.assertEqual(before, self._snapshot_workspace())


if __name__ == "__main__":
    unittest.main()
