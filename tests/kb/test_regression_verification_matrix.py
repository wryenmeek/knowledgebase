"""Regression verification-matrix coverage for mutation-free linting and fail-closed writes."""

from __future__ import annotations

import json
from io import StringIO
import subprocess
import sys
import textwrap
import unittest

from scripts.kb import ingest, write_utils
from tests.kb.harnesses import KnowledgebaseWorkspaceTestCase, REPO_ROOT


LINT_SCRIPT = REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"


class RegressionVerificationMatrixTests(KnowledgebaseWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_verification_regression"
    RAW_DIRS = ("raw/inbox", "raw/processed")
    AGENTS_TEXT = "schema fixture\n"

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
        self.write_wiki_page(
            "index.md",
            self.build_process_page("Knowledgebase Index", "- [Missing](sources/missing.md)"),
        )
        self.write_wiki_page(
            "sources/orphan.md",
            self.build_process_page("Orphan", "This page is intentionally unreferenced."),
        )
        self.write_wiki_page(
            "sources/contradiction.md",
            self.build_process_page("Contradiction", "[CONTRADICTION] unresolved evidence conflict."),
        )
        before = self.snapshot_workspace()

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
        self.assert_workspace_unchanged(before)

    def test_ingest_lock_contention_returns_failed_envelope_without_writes(self) -> None:
        source_rel = "raw/inbox/alpha-source.md"
        (self.workspace / source_rel).write_text("alpha\n", encoding="utf-8")

        with write_utils.exclusive_write_lock(self.workspace):
            pass
        before = self.snapshot_workspace()

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
        self.assert_workspace_unchanged(before)

    def test_ingest_no_state_change_does_not_append_log(self) -> None:
        source_rel = "raw/inbox/missing-source.md"
        log_path = self.workspace / "wiki" / "log.md"
        with write_utils.exclusive_write_lock(self.workspace):
            pass
        before = self.snapshot_workspace()

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
        self.assert_workspace_unchanged(before)


if __name__ == "__main__":
    unittest.main()
