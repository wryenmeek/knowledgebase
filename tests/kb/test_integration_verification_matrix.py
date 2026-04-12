"""Integration verification-matrix coverage for workflow trust, path policy, and query gating."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest

from scripts.kb import ingest, persist_query, write_utils


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci-2-analyst-diagnostics.yml"
_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_verification_integration"


class IntegrationVerificationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

        (self.workspace / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "processed").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "other").mkdir(parents=True, exist_ok=True)

        self.wiki_root = self.workspace / "wiki"
        for section in ("sources", "entities", "concepts", "analyses"):
            (self.wiki_root / section).mkdir(parents=True, exist_ok=True)

        (self.wiki_root / "log.md").write_text("\n", encoding="utf-8")
        (self.workspace / "AGENTS.md").write_text("schema fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

    def _snapshot_workspace(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if file_path.is_file():
                snapshot[file_path.relative_to(self.workspace).as_posix()] = file_path.read_bytes()
        return snapshot

    def _source(self, name: str, checksum_char: str) -> str:
        return (
            f"repo://owner/repo/raw/processed/{name}.md@abc1234#L1-L2"
            f"?sha256={checksum_char * 64}"
        )

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

    def _run_persist(self, *args: str) -> tuple[int, dict[str, object], str]:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = persist_query.run_cli(
            argv=list(args),
            repo_root=self.workspace,
            output_stream=stdout,
            error_stream=stderr,
        )
        return exit_code, json.loads(stdout.getvalue()), stderr.getvalue()

    def _run_persist_subprocess(self, *args: str) -> subprocess.CompletedProcess[str]:
        runner = textwrap.dedent(
            """
            import json
            import sys
            from scripts.kb import persist_query

            repo_root = sys.argv[1]
            cli_args = json.loads(sys.argv[2])
            raise SystemExit(persist_query.run_cli(argv=cli_args, repo_root=repo_root))
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

    def test_trusted_trigger_surface_is_limited_to_ci2_events(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists(), f"Missing workflow file: {WORKFLOW_PATH}")
        workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

        declared_events = self._parse_top_level_event_block(workflow_text)

        self.assertEqual(
            declared_events,
            {"push", "pull_request", "workflow_dispatch"},
        )

    def test_ingest_rejects_non_inbox_source_path_fail_closed(self) -> None:
        source_rel = "raw/other/non-inbox.md"
        (self.workspace / source_rel).write_text("untrusted\n", encoding="utf-8")
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

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("raw/inbox/**", payload["message"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_query_persistence_policy_gate_returns_no_write_envelope_shape(self) -> None:
        source_ref = self._source("source-a", "a")
        before = self._snapshot_workspace()

        exit_code, payload, stderr = self._run_persist(
            "--query",
            "What coverage applies?",
            "--confidence",
            "3",
            "--source",
            source_ref,
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            set(payload),
            {
                "status",
                "reason_code",
                "policy",
                "analysis_path",
                "index_updated",
                "log_appended",
                "sources",
            },
        )
        self.assertEqual(payload["status"], "no_write_policy")
        self.assertEqual(payload["reason_code"], "policy_confidence_below_min")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_query_persistence_lock_contention_fails_closed(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")

        with write_utils.exclusive_write_lock(self.workspace):
            pass
        before = self._snapshot_workspace()

        with write_utils.exclusive_write_lock(self.workspace):
            completed = self._run_persist_subprocess(
                "--query",
                "Which plans cover dialysis?",
                "--result-summary",
                "Deterministic summary.",
                "--confidence",
                "4",
                "--source",
                source_b,
                "--source",
                source_a,
                "--wiki-root",
                str(self.wiki_root),
                "--schema",
                str(self.workspace / "AGENTS.md"),
                "--result-json",
            )

        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reason_code"], "lock_unavailable")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(payload["sources"], sorted([source_a, source_b]))
        self.assertIn("lock_unavailable", completed.stderr)
        self.assertEqual(before, self._snapshot_workspace())

    @staticmethod
    def _parse_top_level_event_block(text: str) -> set[str]:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.strip() != "on:" or line.startswith(" "):
                continue

            events: set[str] = set()
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if not stripped:
                    continue
                if not candidate.startswith("  ") or candidate.startswith("    "):
                    break
                if stripped.startswith("#") or not stripped.endswith(":"):
                    continue
                events.add(stripped[:-1])
            return events

        raise AssertionError(f"Top-level 'on' block missing from {WORKFLOW_PATH}")


if __name__ == "__main__":
    unittest.main()
