"""Integration-style tests for scripts.kb.ingest."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import unittest

from scripts.kb import contracts, ingest


_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_ingest"


class IngestCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

        (self.workspace / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
        (self.workspace / "raw" / "processed").mkdir(parents=True, exist_ok=True)
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        (self.workspace / "AGENTS.md").write_text("schema fixture\n", encoding="utf-8")

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

    def _write_file(self, relative_path: str, content: str) -> None:
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _run_ingest(self, *args: str) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = ingest.run_cli(
            argv=args,
            repo_root=self.workspace,
            output_stream=stdout,
            error_stream=stderr,
        )
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _snapshot_workspace(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if file_path.is_file():
                snapshot[file_path.relative_to(self.workspace).as_posix()] = file_path.read_bytes()
        return snapshot

    def test_single_source_success_and_noop_rerun(self) -> None:
        source_rel = "raw/inbox/alpha-source.md"
        source_content = "# Alpha source\n\nDeterministic content.\n"
        self._write_file(source_rel, source_content)

        first_code, first_stdout, first_stderr = self._run_ingest(
            "--source",
            source_rel,
            "--wiki-root",
            "wiki",
            "--schema",
            "AGENTS.md",
            "--report-json",
        )

        self.assertEqual(first_code, 0)
        self.assertEqual(first_stderr, "")
        first_payload = json.loads(first_stdout)
        self.assertEqual(first_payload["status"], contracts.ResultStatus.WRITTEN.value)
        self.assertEqual(first_payload["reason_code"], contracts.ReasonCode.OK.value)
        self.assertTrue(first_payload["index_updated"])
        self.assertTrue(first_payload["log_appended"])
        self.assertEqual(len(first_payload["per_source"]), 1)

        processed_path = self.workspace / "raw" / "processed" / "alpha-source.md"
        source_page = self.workspace / "wiki" / "sources" / "alpha-source.md"
        self.assertFalse((self.workspace / source_rel).exists())
        self.assertTrue(processed_path.exists())
        self.assertEqual(processed_path.read_text(encoding="utf-8"), source_content)
        self.assertTrue(source_page.exists())
        source_page_text = source_page.read_text(encoding="utf-8")
        self.assertIn("type: source", source_page_text)
        self.assertIn(first_payload["per_source"][0]["source_ref"], source_page_text)
        self.assertIn("Source: Alpha Source", (self.workspace / "wiki" / "index.md").read_text("utf-8"))

        log_before = (self.workspace / "wiki" / "log.md").read_text(encoding="utf-8")
        page_before = source_page.read_text(encoding="utf-8")

        second_code, second_stdout, _second_stderr = self._run_ingest(
            "--source",
            source_rel,
            "--wiki-root",
            "wiki",
            "--schema",
            "AGENTS.md",
            "--report-json",
        )

        self.assertEqual(second_code, 2)
        second_payload = json.loads(second_stdout)
        self.assertEqual(second_payload["status"], contracts.ResultStatus.PARTIAL_SUCCESS.value)
        self.assertEqual(second_payload["reason_code"], contracts.ReasonCode.PER_SOURCE_FAILURES.value)
        self.assertEqual((self.workspace / "wiki" / "log.md").read_text(encoding="utf-8"), log_before)
        self.assertEqual(source_page.read_text(encoding="utf-8"), page_before)

    def test_mixed_batch_partial_failure_continues_and_reports(self) -> None:
        self._write_file("raw/inbox/alpha.md", "alpha\n")
        self._write_file("raw/inbox/beta.md", "beta\n")
        self._write_file(
            "raw/inbox/manifest.txt",
            "\n".join(
                [
                    "raw/inbox/alpha.md",
                    "raw/inbox/missing.md",
                    "raw/inbox/beta.md",
                ]
            )
            + "\n",
        )

        exit_code, stdout, stderr = self._run_ingest(
            "--sources-manifest",
            "raw/inbox/manifest.txt",
            "--batch-policy",
            contracts.PolicyId.CONTINUE_AND_REPORT_PER_SOURCE.value,
            "--wiki-root",
            "wiki",
            "--schema",
            "AGENTS.md",
            "--report-json",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.PARTIAL_SUCCESS.value)
        self.assertEqual(payload["reason_code"], contracts.ReasonCode.PER_SOURCE_FAILURES.value)
        self.assertEqual(
            [item["status"] for item in payload["per_source"]],
            [
                contracts.ResultStatus.WRITTEN.value,
                contracts.ResultStatus.FAILED.value,
                contracts.ResultStatus.WRITTEN.value,
            ],
        )
        self.assertEqual(payload["per_source"][1]["source"], "raw/inbox/missing.md")
        self.assertEqual(
            payload["per_source"][1]["reason_code"],
            contracts.ReasonCode.INVALID_INPUT.value,
        )

        self.assertTrue((self.workspace / "raw" / "processed" / "alpha.md").exists())
        self.assertTrue((self.workspace / "raw" / "processed" / "beta.md").exists())
        self.assertFalse((self.workspace / "raw" / "inbox" / "alpha.md").exists())
        self.assertFalse((self.workspace / "raw" / "inbox" / "beta.md").exists())
        self.assertTrue((self.workspace / "wiki" / "sources" / "alpha.md").exists())
        self.assertTrue((self.workspace / "wiki" / "sources" / "beta.md").exists())

    def test_path_traversal_is_rejected_fail_closed(self) -> None:
        before = self._snapshot_workspace()

        exit_code, stdout, stderr = self._run_ingest(
            "--source",
            "../outside.md",
            "--wiki-root",
            "wiki",
            "--schema",
            "AGENTS.md",
            "--report-json",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.FAILED.value)
        self.assertEqual(payload["reason_code"], contracts.ReasonCode.INVALID_INPUT.value)
        self.assertIn("path escapes repository boundary", payload["message"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_index_generation_failure_rolls_back_source_mutations(self) -> None:
        source_rel = "raw/inbox/rollback.md"
        source_content = "rollback\n"
        self._write_file(source_rel, source_content)
        self._write_file("wiki/entities/invalid.md", "# missing frontmatter\n")

        exit_code, stdout, stderr = self._run_ingest(
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
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.FAILED.value)
        self.assertEqual(payload["reason_code"], contracts.ReasonCode.WRITE_FAILED.value)
        self.assertIn("unable to generate index", payload["message"])
        self.assertEqual(len(payload["per_source"]), 1)
        self.assertEqual(payload["per_source"][0]["source"], source_rel)
        self.assertEqual(payload["per_source"][0]["status"], contracts.ResultStatus.FAILED.value)
        self.assertEqual(
            payload["per_source"][0]["reason_code"],
            contracts.ReasonCode.WRITE_FAILED.value,
        )
        self.assertIn(
            "rolled back due fatal ingest failure",
            payload["per_source"][0]["message"],
        )

        self.assertTrue((self.workspace / source_rel).exists())
        self.assertEqual((self.workspace / source_rel).read_text(encoding="utf-8"), source_content)
        self.assertFalse((self.workspace / "raw" / "processed" / "rollback.md").exists())
        self.assertFalse((self.workspace / "wiki" / "sources" / "rollback.md").exists())
        self.assertFalse((self.workspace / "wiki" / "index.md").exists())
        self.assertFalse((self.workspace / "wiki" / "log.md").exists())


if __name__ == "__main__":
    unittest.main()
