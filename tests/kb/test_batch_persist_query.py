"""Tests for batch policy-gated query persistence CLI behavior."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any
import unittest
from unittest.mock import patch

from scripts.kb import batch_persist_query, persist_query, update_index, write_utils
from tests.kb.harnesses import RuntimeWorkspaceTestCase


class BatchPersistQueryCliTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_batch_persist_query"

    # ------------------------------------------------------------------
    # Test fixtures
    # ------------------------------------------------------------------

    def setUp(self) -> None:
        super().setUp()
        self.wiki_root = self.workspace / "wiki"
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        (self.wiki_root / "index.md").write_text("stale-index\n", encoding="utf-8")
        (self.wiki_root / "log.md").write_text(
            self._build_process_page("Knowledgebase Log"),
            encoding="utf-8",
        )
        (self.workspace / "AGENTS.md").write_text("agents contract\n", encoding="utf-8")

    def _build_process_page(self, title: str) -> str:
        return "\n".join(
            [
                "---",
                "type: process",
                f'title: "{title}"',
                "status: active",
                "sources: []",
                "open_questions: []",
                "confidence: 1",
                "sensitivity: internal",
                'updated_at: "1970-01-01T00:00:00Z"',
                "tags: [audit]",
                "---",
                "",
                f"# {title}",
                "",
            ]
        )

    def _source(self, name: str, checksum_char: str) -> str:
        return (
            f"repo://owner/repo/raw/processed/{name}.md@abc1234#L1-L2"
            f"?sha256={checksum_char * 64}"
        )

    def _valid_entry(
        self,
        query: str = "What does Medicare cover?",
        *,
        confidence: int = 4,
        sources: list[str] | None = None,
        unresolved_contradiction: bool = False,
        sensitivity: str = "internal",
        result_summary: str = "Medicare covers Part A and B.",
    ) -> dict[str, Any]:
        if sources is None:
            sources = [
                self._source("source-a", "a"),
                self._source("source-b", "b"),
            ]
        return {
            "query": query,
            "result_summary": result_summary,
            "sources": sources,
            "confidence": confidence,
            "unresolved_contradiction": unresolved_contradiction,
            "sensitivity": sensitivity,
        }

    def _write_batch_file(self, entries: list[dict[str, Any]]) -> Path:
        batch_path = self.workspace / "batch.json"
        batch_path.write_text(json.dumps(entries), encoding="utf-8")
        return batch_path

    def _run_cli(
        self,
        batch_file: str | Path,
        *extra_args: str,
    ) -> tuple[int, dict[str, Any]]:
        output = StringIO()
        error = StringIO()
        exit_code = batch_persist_query.run_batch_cli(
            argv=[
                "--batch-file", str(batch_file),
                "--wiki-root", str(self.wiki_root),
                "--schema", str(self.workspace / "AGENTS.md"),
                *extra_args,
            ],
            output_stream=output,
            error_stream=error,
            repo_root=self.workspace,
        )
        payload = json.loads(output.getvalue())
        return exit_code, payload

    def _assert_envelope_shape(self, payload: dict[str, Any]) -> None:
        """Check top-level envelope keys are present."""
        required = {
            "status", "surface", "mode", "reason_code",
            "total", "written", "skipped", "failed", "entries",
        }
        self.assertEqual(set(payload.keys()), required)
        self.assertEqual(payload["surface"], batch_persist_query.SURFACE)
        self.assertEqual(payload["mode"], "apply")

    # ------------------------------------------------------------------
    # Test 1: Valid batch of 2 entries → 2 written, status "pass"
    # ------------------------------------------------------------------

    def test_valid_batch_two_entries_both_written(self) -> None:
        entry_a = self._valid_entry("What does Part A cover?")
        entry_b = self._valid_entry(
            "What does Part B cover?",
            sources=[
                self._source("source-c", "c"),
                self._source("source-d", "d"),
            ],
            result_summary="Part B covers outpatient services.",
        )
        batch_path = self._write_batch_file([entry_a, entry_b])

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["reason_code"], "ok")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["written"], 2)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["failed"], 0)

        # Both entries should be "written" with an analysis_path
        entries = payload["entries"]
        self.assertEqual(len(entries), 2)
        for entry in entries:
            self.assertEqual(entry["status"], "written")
            self.assertEqual(entry["reason_code"], "ok")
            self.assertIsNotNone(entry["analysis_path"])
            self.assertTrue(entry["analysis_path"].startswith("wiki/analyses/"))
            self.assertTrue((self.workspace / entry["analysis_path"]).is_file())

    # ------------------------------------------------------------------
    # Test 2: Lock unavailable → all entries "failed", exit code 1
    # ------------------------------------------------------------------

    def test_lock_unavailable_marks_all_entries_failed_exit_1(self) -> None:
        entry_a = self._valid_entry("What does Part A cover?")
        entry_b = self._valid_entry(
            "What does Part B cover?",
            sources=[
                self._source("source-c", "c"),
                self._source("source-d", "d"),
            ],
        )
        batch_path = self._write_batch_file([entry_a, entry_b])
        before = self.snapshot_workspace()

        def _raise_lock(*args: object, **kwargs: object):
            raise write_utils.LockUnavailableError()

        with patch("scripts.kb.write_utils.exclusive_write_lock", side_effect=_raise_lock):
            exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 1)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "lock_unavailable")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["failed"], 2)

        for entry in payload["entries"]:
            self.assertEqual(entry["status"], "failed")
            self.assertEqual(entry["reason_code"], "lock_unavailable")
            self.assertIsNone(entry["analysis_path"])

        # No files should have been written
        self.assertEqual(before, self.snapshot_workspace())

    # ------------------------------------------------------------------
    # Test 3: Policy rejection (confidence too low) → skipped, not failed
    # ------------------------------------------------------------------

    def test_policy_rejection_confidence_too_low_is_skipped(self) -> None:
        low_confidence_entry = self._valid_entry(
            "What does Part D cover?",
            confidence=2,  # below DEFAULT_MIN_CONFIDENCE (4)
        )
        batch_path = self._write_batch_file([low_confidence_entry])
        before = self.snapshot_workspace()

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["failed"], 0)

        entry = payload["entries"][0]
        self.assertEqual(entry["status"], "skipped")
        self.assertEqual(entry["reason_code"], "policy_confidence_below_min")
        self.assertIsNone(entry["analysis_path"])

        # No new analysis files should have been created
        analyses_dir = self.wiki_root / "analyses"
        self.assertFalse(analyses_dir.exists())

    # ------------------------------------------------------------------
    # Test 4: Invalid batch JSON (not an array) → exit code 1, reason invalid_input
    # ------------------------------------------------------------------

    def test_invalid_batch_json_not_array_exits_1_with_invalid_input(self) -> None:
        batch_path = self.workspace / "bad_batch.json"
        batch_path.write_text('{"query": "not an array"}', encoding="utf-8")

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 1)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["total"], 0)

    # ------------------------------------------------------------------
    # Test 5: Batch file does not exist → exit code 1, reason invalid_input
    # ------------------------------------------------------------------

    def test_batch_file_not_found_exits_1_with_invalid_input(self) -> None:
        missing_path = self.workspace / "no_such_file.json"

        exit_code, payload = self._run_cli(missing_path)

        self.assertEqual(exit_code, 1)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["total"], 0)

    # ------------------------------------------------------------------
    # Test 6: Empty batch (empty array) → status "pass", total 0, written 0
    # ------------------------------------------------------------------

    def test_empty_batch_succeeds_with_zero_counts(self) -> None:
        batch_path = self._write_batch_file([])
        before = self.snapshot_workspace()

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["reason_code"], "ok")
        self.assertEqual(payload["total"], 0)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["entries"], [])

        # No state changes
        self.assertEqual(before, self.snapshot_workspace())

    # ------------------------------------------------------------------
    # Test 7: Mixed batch — 1 passes policy, 1 fails policy → 1 written, 1 skipped, "pass"
    # ------------------------------------------------------------------

    def test_mixed_batch_one_written_one_skipped(self) -> None:
        passing_entry = self._valid_entry("What does hospice care cover?")
        failing_entry = self._valid_entry(
            "What does skilled nursing cover?",
            confidence=1,  # below threshold → policy_confidence_below_min
        )
        batch_path = self._write_batch_file([passing_entry, failing_entry])

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self._assert_envelope_shape(payload)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["written"], 1)
        self.assertEqual(payload["skipped"], 1)
        self.assertEqual(payload["failed"], 0)

        # Verify individual entry statuses (keys are raw query text as supplied)
        statuses = {e["query"]: e["status"] for e in payload["entries"]}
        self.assertEqual(statuses["What does hospice care cover?"], "written")
        self.assertEqual(statuses["What does skilled nursing cover?"], "skipped")

        # Verify the written analysis file exists
        written_entry = next(e for e in payload["entries"] if e["status"] == "written")
        self.assertIsNotNone(written_entry["analysis_path"])
        self.assertTrue((self.workspace / written_entry["analysis_path"]).is_file())

    # ------------------------------------------------------------------
    # Additional integration tests
    # ------------------------------------------------------------------

    def test_surface_and_modes_constants(self) -> None:
        self.assertEqual(batch_persist_query.SURFACE, "scripts/kb/batch_persist_query.py")
        self.assertIn("apply", batch_persist_query.SUPPORTED_MODES)

    def test_all_exports_present(self) -> None:
        for name in ("SURFACE", "SUPPORTED_MODES", "MAX_BATCH_SIZE", "run_batch_cli", "main"):
            self.assertIn(name, batch_persist_query.__all__)

    def test_single_lock_acquisition_for_entire_batch(self) -> None:
        """Confirm the lock is acquired exactly once regardless of entry count."""
        entries = [
            self._valid_entry(f"Query number {i}?") for i in range(3)
        ]
        batch_path = self._write_batch_file(entries)

        lock_calls: list[int] = []
        real_lock = write_utils.exclusive_write_lock

        def counting_lock(*args: object, **kwargs: object):
            lock_calls.append(1)
            return real_lock(*args, **kwargs)

        with patch("scripts.kb.write_utils.exclusive_write_lock", side_effect=counting_lock):
            exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        # Lock should have been called at most once (could be 0 if all skipped,
        # but with 3 valid entries all passing policy it must be exactly 1).
        self.assertEqual(len(lock_calls), 1, "Lock must be acquired exactly once for the whole batch")
        self.assertEqual(payload["written"], 3)

    def test_idempotent_second_run_does_not_create_duplicate_analyses(self) -> None:
        """Re-running the same batch should not create a second analysis file."""
        entry = self._valid_entry("What is the deductible?")
        batch_path = self._write_batch_file([entry])

        exit_code_1, payload_1 = self._run_cli(batch_path)
        self.assertEqual(exit_code_1, 0)
        self.assertEqual(payload_1["written"], 1)
        analyses_before = list((self.wiki_root / "analyses").glob("*.md"))

        exit_code_2, payload_2 = self._run_cli(batch_path)
        self.assertEqual(exit_code_2, 0)
        # File already existed — still reported as "written" (idempotent write)
        self.assertEqual(payload_2["written"], 1)
        analyses_after = list((self.wiki_root / "analyses").glob("*.md"))

        # Only one analysis file for the same query fingerprint
        self.assertEqual(len(analyses_before), len(analyses_after))

    def test_malformed_json_in_batch_file_exits_1(self) -> None:
        batch_path = self.workspace / "malformed.json"
        batch_path.write_text("{this is not valid json", encoding="utf-8")

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")

    def test_log_appended_once_after_batch_with_writes(self) -> None:
        """Exactly one log entry should be appended for the entire batch."""
        log_path = self.wiki_root / "log.md"
        log_before = log_path.read_text(encoding="utf-8")

        entries = [
            self._valid_entry("Does Medicare cover vision?"),
            self._valid_entry(
                "Does Medicare cover hearing?",
                sources=[
                    self._source("source-c", "c"),
                    self._source("source-d", "d"),
                ],
            ),
        ]
        batch_path = self._write_batch_file(entries)

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["written"], 2)

        log_after = log_path.read_text(encoding="utf-8")
        self.assertTrue(log_after.startswith(log_before))

        # Only one batch_persist_query log line should have been appended
        new_lines = log_after[len(log_before):].strip().splitlines()
        batch_lines = [l for l in new_lines if "batch_persist_query" in l]
        self.assertEqual(len(batch_lines), 1, "Exactly one batch log entry expected")

    def test_batch_entry_with_invalid_sensitivity_fails_pre_validation(self) -> None:
        """A batch entry with a disallowed sensitivity value must fail pre-validation."""
        entry = self._valid_entry("What does Part A cover?")
        entry["sensitivity"] = "public\ninjected_key: injected_value"
        batch_path = self._write_batch_file([entry])

        exit_code, payload = self._run_cli(batch_path)

        # All entries failed pre-validation → hard fail (not a partial-skip; no work ran).
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["failed"], 1)
        entry_result = payload["entries"][0]
        self.assertEqual(entry_result["status"], "failed")
        self.assertEqual(entry_result["reason_code"], "invalid_input")
        analyses_dir = self.wiki_root / "analyses"
        self.assertFalse(analyses_dir.exists())

    def test_batch_file_absolute_path_outside_repo_rejected(self) -> None:
        """An absolute --batch-file path outside the repo root must fail closed."""
        outside_path = Path("/outside-repo-batch.json")

        exit_code, payload = self._run_cli(outside_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(payload["total"], 0)

    def test_batch_exceeding_max_size_fails_closed(self) -> None:
        """A batch larger than MAX_BATCH_SIZE must fail closed before acquiring the lock."""
        from scripts.kb.batch_persist_query import MAX_BATCH_SIZE

        entries = [
            self._valid_entry(f"Query {i}?", sources=[self._source(f"src-{i}", str(i % 10))])
            for i in range(MAX_BATCH_SIZE + 1)
        ]
        batch_path = self._write_batch_file(entries)
        before = self.snapshot_workspace()

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertEqual(before, self.snapshot_workspace())

    def test_per_entry_write_failure_mid_batch_rollback_and_continue(self) -> None:
        """An OSError on entry 1's write: entry 0 stays written, entry 1 is rolled back and marked failed, entry 2 is processed and written."""
        from unittest.mock import patch as _patch

        entry_0 = self._valid_entry("What does Part A cover?")
        entry_1 = self._valid_entry(
            "What does Part B cover?",
            sources=[self._source("src-b1", "b"), self._source("src-b2", "c")],
        )
        entry_2 = self._valid_entry(
            "What does Part C cover?",
            sources=[self._source("src-c1", "d"), self._source("src-c2", "e")],
        )
        batch_path = self._write_batch_file([entry_0, entry_1, entry_2])

        call_count = [0]
        real_write = write_utils.write_text_capturing_previous_safe

        def _fail_on_second_call(path, content, **kw):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("simulated disk error on entry 1")
            return real_write(path, content, **kw)

        with _patch(
            "scripts.kb.batch_persist_query.write_text_capturing_previous_safe",
            side_effect=_fail_on_second_call,
        ):
            exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["written"], 2)
        self.assertEqual(payload["failed"], 1)

        statuses = {e["query"]: e["status"] for e in payload["entries"]}
        self.assertEqual(statuses["What does Part A cover?"], "written")
        self.assertEqual(statuses["What does Part B cover?"], "failed")
        self.assertEqual(statuses["What does Part C cover?"], "written")

        written = [e for e in payload["entries"] if e["status"] == "written"]
        for written_entry in written:
            self.assertTrue((self.workspace / written_entry["analysis_path"]).is_file())
        failed = [e for e in payload["entries"] if e["status"] == "failed"]
        self.assertIsNone(failed[0]["analysis_path"])

    def test_out_of_scope_wiki_root_all_entries_fail_pre_validation(self) -> None:
        """An invalid --wiki-root causes all entries to fail pre-validation; top-level passes."""
        entry_a = self._valid_entry("What does Part A cover?")
        entry_b = self._valid_entry("What does Part B cover?")
        batch_path = self._write_batch_file([entry_a, entry_b])

        output = StringIO()
        error = StringIO()
        exit_code = batch_persist_query.run_batch_cli(
            argv=[
                "--batch-file", str(batch_path),
                "--wiki-root", "not-wiki",
                "--schema", str(self.workspace / "AGENTS.md"),
            ],
            output_stream=output,
            error_stream=error,
            repo_root=self.workspace,
        )
        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["failed"], 2)
        for entry in payload["entries"]:
            self.assertEqual(entry["status"], "failed")
            self.assertEqual(entry["reason_code"], "invalid_input")

    def test_duplicate_queries_in_batch_idempotent(self) -> None:
        """Two entries with identical normalized query + sources produce the same analysis path. The second write is a no-op and both entries are reported as written."""
        entry = self._valid_entry("What does Part A cover?")
        batch_path = self._write_batch_file([entry, entry])

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["written"], 2)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["failed"], 0)

        paths = [e["analysis_path"] for e in payload["entries"]]
        self.assertEqual(paths[0], paths[1])
        analyses = list((self.wiki_root / "analyses").glob("*.md"))
        self.assertEqual(len(analyses), 1)

    def test_log_entry_truncates_paths_beyond_five(self) -> None:
        """When more than 5 entries are written, the log entry uses '... (N more)'."""
        entries = [
            self._valid_entry(
                f"Query {i} about Medicare?",
                sources=[self._source(f"src-{i}a", str(i)), self._source(f"src-{i}b", chr(ord("a") + i))],
            )
            for i in range(6)
        ]
        batch_path = self._write_batch_file(entries)

        exit_code, payload = self._run_cli(batch_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["written"], 6)

        log_text = (self.workspace / write_utils.LOG_PATH).read_text(encoding="utf-8")
        self.assertIn("batch_persist_query: 6 written", log_text)
        self.assertIn("... (1 more)", log_text)

    def test_analysis_path_boundary_assertion_prevents_escaped_write(self) -> None:
        """The is_relative_to(wiki/analyses) boundary check must raise OSError
        (fail-closed) when _analysis_relative_path returns a path outside wiki/analyses/."""
        from unittest.mock import patch as _patch

        entry = self._valid_entry("What does Part A cover?")
        batch_path = self._write_batch_file([entry])

        # Inject an escaped path: wiki/sources/ is outside wiki/analyses/
        with _patch(
            "scripts.kb.batch_persist_query._analysis_relative_path",
            return_value=Path("wiki/sources/escaped.md"),
        ):
            with self.assertRaises(OSError, msg="boundary violation must raise OSError"):
                self._run_cli(batch_path)

    def test_missing_schema_file_all_entries_fail_pre_validation(self) -> None:
        """When the --schema file does not exist, all entries fail pre-validation."""
        entry = self._valid_entry("What does Part A cover?")
        batch_path = self._write_batch_file([entry])

        output = StringIO()
        error = StringIO()
        exit_code = batch_persist_query.run_batch_cli(
            argv=[
                "--batch-file", str(batch_path),
                "--wiki-root", str(self.wiki_root),
                "--schema", str(self.workspace / "MISSING_AGENTS.md"),
            ],
            output_stream=output,
            error_stream=error,
            repo_root=self.workspace,
        )
        payload = json.loads(output.getvalue())

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["written"], 0)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(payload["entries"][0]["status"], "failed")
        self.assertEqual(payload["entries"][0]["reason_code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
