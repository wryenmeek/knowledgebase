"""Integration-style tests for scripts.kb.ingest."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

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
        self.assertEqual(
            first_payload["source_provenance"],
            [
                {
                    "authoritative": False,
                    "git_sha": ingest._PROVISIONAL_GIT_SHA,
                    "git_sha_kind": "placeholder",
                    "reconciliation": "commit_bound_pending",
                    "review_mode": "authoritative_review_required",
                    "status": "provisional",
                }
            ],
        )
        self.assertEqual(
            first_payload["per_source"][0]["provenance"],
            first_payload["source_provenance"][0],
        )

        processed_path = self.workspace / "raw" / "processed" / "alpha-source.md"
        source_page = self.workspace / "wiki" / "sources" / "alpha-source.md"
        self.assertFalse((self.workspace / source_rel).exists())
        self.assertTrue(processed_path.exists())
        self.assertEqual(processed_path.read_text(encoding="utf-8"), source_content)
        self.assertTrue(source_page.exists())
        source_page_text = source_page.read_text(encoding="utf-8")
        self.assertIn("type: source", source_page_text)
        self.assertIn(first_payload["per_source"][0]["source_ref"], source_page_text)
        self.assertIn("- provenance_status: `provisional`", source_page_text)
        self.assertIn("- provenance_review_mode: `authoritative_review_required`", source_page_text)
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

    def test_symlinked_source_file_is_rejected_fail_closed(self) -> None:
        real_source = self.workspace / "raw" / "inbox" / "real.md"
        real_source.write_text("real\n", encoding="utf-8")
        linked_source = self.workspace / "raw" / "inbox" / "linked.md"
        linked_source.symlink_to(real_source)
        before = self._snapshot_workspace()

        exit_code, stdout, stderr = self._run_ingest(
            "--source",
            "raw/inbox/linked.md",
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
        self.assertIn("path must not use symlinks", payload["message"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_symlinked_sources_manifest_is_rejected_fail_closed(self) -> None:
        self._write_file("raw/inbox/alpha.md", "alpha\n")
        manifest_target = self.workspace / "raw" / "inbox" / "manifest-target.txt"
        manifest_target.write_text("raw/inbox/alpha.md\n", encoding="utf-8")
        manifest_link = self.workspace / "raw" / "inbox" / "manifest.txt"
        manifest_link.symlink_to(manifest_target)
        before = self._snapshot_workspace()

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

        self.assertEqual(exit_code, 1)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.FAILED.value)
        self.assertEqual(payload["reason_code"], contracts.ReasonCode.INVALID_INPUT.value)
        self.assertIn("path must not use symlinks", payload["message"])
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

    def test_ingest_rejects_symlinked_source_page_parent(self) -> None:
        source_rel = "raw/inbox/alpha-source.md"
        self._write_file(source_rel, "alpha\n")
        external_sources_dir = self.workspace / "external-sources"
        external_sources_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.workspace / "wiki")
        (self.workspace / "wiki").mkdir(parents=True, exist_ok=True)
        (self.workspace / "wiki" / "sources").symlink_to(external_sources_dir, target_is_directory=True)

        exit_code, stdout, stderr = self._run_ingest(
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
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.PARTIAL_SUCCESS.value)
        self.assertEqual(
            payload["per_source"][0]["reason_code"],
            contracts.ReasonCode.WRITE_FAILED.value,
        )
        self.assertIn("symlinked path component is not allowed", payload["per_source"][0]["message"])
        self.assertTrue((self.workspace / source_rel).exists())
        self.assertEqual(list(external_sources_dir.iterdir()), [])

    def test_ingest_rejects_symlinked_processed_parent(self) -> None:
        source_rel = "raw/inbox/alpha-source.md"
        self._write_file(source_rel, "alpha\n")
        external_processed_dir = self.workspace / "external-processed"
        external_processed_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.workspace / "raw" / "processed")
        (self.workspace / "raw" / "processed").symlink_to(
            external_processed_dir,
            target_is_directory=True,
        )

        exit_code, stdout, stderr = self._run_ingest(
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
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], contracts.ResultStatus.PARTIAL_SUCCESS.value)
        self.assertEqual(
            payload["per_source"][0]["reason_code"],
            contracts.ReasonCode.WRITE_FAILED.value,
        )
        self.assertIn("symlinked path component is not allowed", payload["per_source"][0]["message"])
        self.assertTrue((self.workspace / source_rel).exists())
        self.assertEqual(list(external_processed_dir.iterdir()), [])


class IngestSourceRefBuilderTests(unittest.TestCase):
    def test_build_source_ref_uses_provisional_placeholder_sha_until_reconciled(self) -> None:
        repo_root = Path("/repo")
        checksum = "a" * 64

        with patch.object(ingest, "validate_sourceref") as validate_mock:
            source_ref = ingest._build_source_ref(repo_root, "raw/processed/source.md", checksum)

        self.assertIn(f"@{ingest._PROVISIONAL_GIT_SHA}#", source_ref)
        validate_mock.assert_called_once_with(source_ref)

    def test_build_provisional_source_provenance_marks_placeholder_sha_structurally(self) -> None:
        provenance = ingest._build_provisional_source_provenance()

        self.assertEqual(
            provenance.to_dict(),
            {
                "authoritative": False,
                "git_sha": ingest._PROVISIONAL_GIT_SHA,
                "git_sha_kind": "placeholder",
                "reconciliation": "commit_bound_pending",
                "review_mode": "authoritative_review_required",
                "status": "provisional",
            },
        )


class IngestWriteSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

    def test_write_text_if_changed_rejects_symlink_target(self) -> None:
        external_target = self.workspace / "external.md"
        external_target.write_text("external target\n", encoding="utf-8")
        symlink_path = self.workspace / "wiki" / "sources" / "linked.md"
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.symlink_to(external_target)

        with self.assertRaises(OSError):
            ingest._write_text_if_changed(symlink_path, "updated\n")

        self.assertEqual(external_target.read_text(encoding="utf-8"), "external target\n")
        self.assertTrue(symlink_path.is_symlink())

    def test_restore_previous_content_rejects_symlink_target(self) -> None:
        external_target = self.workspace / "external.md"
        external_target.write_text("external target\n", encoding="utf-8")
        symlink_path = self.workspace / "wiki" / "sources" / "linked.md"
        symlink_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.symlink_to(external_target)

        with self.assertRaises(OSError):
            ingest._restore_previous_content(symlink_path, "restored\n")

        self.assertEqual(external_target.read_text(encoding="utf-8"), "external target\n")
        self.assertTrue(symlink_path.is_symlink())

    def test_write_index_if_changed_rejects_preexisting_temp_symlink(self) -> None:
        wiki_root = self.workspace / "wiki"
        wiki_root.mkdir(parents=True, exist_ok=True)
        index_path = wiki_root / "index.md"
        index_path.write_text("stale\n", encoding="utf-8")
        external_target = self.workspace / "external.md"
        external_target.write_text("external target\n", encoding="utf-8")
        temp_index_path = wiki_root / "index.md.tmp"
        temp_index_path.symlink_to(external_target)

        with (
            patch.object(ingest.update_index, "generate_index_content", return_value="fresh\n"),
            self.assertRaises(ingest.IngestError) as ctx,
        ):
            ingest._write_index_if_changed(wiki_root)

        self.assertEqual(ctx.exception.reason_code, contracts.ReasonCode.WRITE_FAILED.value)
        self.assertEqual(index_path.read_text(encoding="utf-8"), "stale\n")
        self.assertEqual(external_target.read_text(encoding="utf-8"), "external target\n")
        self.assertTrue(temp_index_path.is_symlink())


if __name__ == "__main__":
    unittest.main()
