"""Tests for policy-gated query persistence CLI behavior."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from scripts.kb import persist_query


_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_persist_query"


class PersistQueryCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)

        self.wiki_root = self.workspace / "wiki"
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        (self.wiki_root / "index.md").write_text("stale-index\n", encoding="utf-8")
        (self.wiki_root / "log.md").write_text(
            self._build_process_page("Knowledgebase Log"),
            encoding="utf-8",
        )
        (self.workspace / "AGENTS.md").write_text("agents contract\n", encoding="utf-8")

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

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

    def _run_cli(self, *args: str) -> tuple[int, dict[str, object]]:
        output = StringIO()
        exit_code = persist_query.run_cli(
            argv=list(args),
            output_stream=output,
            repo_root=self.workspace,
        )
        payload = json.loads(output.getvalue())
        return exit_code, payload

    def _snapshot_workspace(self) -> dict[str, bytes]:
        snapshot: dict[str, bytes] = {}
        for file_path in sorted(self.workspace.rglob("*")):
            if not file_path.is_file():
                continue
            snapshot[file_path.relative_to(self.workspace).as_posix()] = file_path.read_bytes()
        return snapshot

    def _source(self, name: str, checksum_char: str) -> str:
        return (
            f"repo://owner/repo/raw/processed/{name}.md@abc1234#L1-L2"
            f"?sha256={checksum_char * 64}"
        )

    def _assert_required_envelope_keys(self, payload: dict[str, object]) -> None:
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

    def test_policy_pass_writes_once_and_converges_on_equivalent_rerun(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")
        summary = "Dialysis coverage varies by plan and service context."

        first_exit_code, first_payload = self._run_cli(
            "--query",
            "  Which plans   cover dialysis?  ",
            "--result-summary",
            summary,
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

        self.assertEqual(first_exit_code, 0)
        self._assert_required_envelope_keys(first_payload)
        self.assertEqual(first_payload["status"], "written")
        self.assertEqual(first_payload["reason_code"], "ok")
        self.assertTrue(first_payload["index_updated"])
        self.assertTrue(first_payload["log_appended"])
        self.assertEqual(
            first_payload["sources"],
            sorted([source_a, source_b]),
        )
        first_analysis_path = first_payload["analysis_path"]
        self.assertIsInstance(first_analysis_path, str)
        self.assertTrue(first_analysis_path.startswith("wiki/analyses/"))
        self.assertTrue((self.workspace / first_analysis_path).is_file())

        log_after_first_run = (self.wiki_root / "log.md").read_text(encoding="utf-8")

        second_exit_code, second_payload = self._run_cli(
            "--query",
            "which plans cover DIALYSIS?",
            "--result-summary",
            summary,
            "--confidence",
            "4",
            "--source",
            source_a,
            "--source",
            source_b,
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(second_exit_code, 0)
        self._assert_required_envelope_keys(second_payload)
        self.assertEqual(second_payload["status"], "written")
        self.assertEqual(second_payload["reason_code"], "ok")
        self.assertEqual(second_payload["analysis_path"], first_analysis_path)
        self.assertFalse(second_payload["index_updated"])
        self.assertFalse(second_payload["log_appended"])
        self.assertEqual(
            (self.wiki_root / "log.md").read_text(encoding="utf-8"),
            log_after_first_run,
        )
        analysis_pages = list((self.wiki_root / "analyses").glob("*.md"))
        self.assertEqual(len(analysis_pages), 1)

    def test_policy_miss_returns_no_write_policy_and_makes_no_changes(self) -> None:
        source_a = self._source("source-a", "a")
        before = self._snapshot_workspace()

        exit_code, payload = self._run_cli(
            "--query",
            "What is covered?",
            "--confidence",
            "3",
            "--source",
            source_a,
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(exit_code, 0)
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], "no_write_policy")
        self.assertEqual(payload["reason_code"], "policy_confidence_below_min")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_policy_sources_below_min_returns_no_write_policy_without_mutation(self) -> None:
        source_a = self._source("source-a", "a")
        before = self._snapshot_workspace()

        exit_code, payload = self._run_cli(
            "--query",
            "What is covered?",
            "--confidence",
            "4",
            "--source",
            source_a,
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(exit_code, 0)
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], "no_write_policy")
        self.assertEqual(payload["reason_code"], "policy_sources_below_min")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_policy_unresolved_contradiction_returns_no_write_policy_without_mutation(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")
        before = self._snapshot_workspace()

        exit_code, payload = self._run_cli(
            "--query",
            "What is covered?",
            "--confidence",
            "4",
            "--source",
            source_a,
            "--source",
            source_b,
            "--has-unresolved-contradiction",
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(exit_code, 0)
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], "no_write_policy")
        self.assertEqual(payload["reason_code"], "policy_unresolved_contradiction")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_invalid_input_returns_failed_envelope_and_non_zero_exit(self) -> None:
        before = self._snapshot_workspace()

        exit_code, payload = self._run_cli(
            "--query",
            "What is covered?",
            "--confidence",
            "5",
            "--source",
            "repo://owner/repo/raw/processed/source.md@abc1234#L1-L2?sha256=deadbeef",
            "--wiki-root",
            str(self.wiki_root),
            "--schema",
            str(self.workspace / "AGENTS.md"),
            "--result-json",
        )

        self.assertEqual(exit_code, 1)
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())

    def test_index_failure_after_analysis_write_rolls_back_workspace_state(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")
        summary = "Dialysis coverage varies by plan and service context."
        (self.wiki_root / ".kb_write.lock").write_text("", encoding="utf-8")
        before = self._snapshot_workspace()

        def _fail_after_analysis_write(_wiki_root: Path) -> bool:
            self.assertEqual(len(list((self.wiki_root / "analyses").glob("*.md"))), 1)
            raise persist_query.update_index.IndexGenerationError("simulated index generation failure")

        with patch(
            "scripts.kb.persist_query._update_index_if_changed",
            side_effect=_fail_after_analysis_write,
        ):
            exit_code, payload = self._run_cli(
                "--query",
                "Which plans cover dialysis?",
                "--result-summary",
                summary,
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

        self.assertEqual(exit_code, 1)
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reason_code"], "write_failed")
        self.assertIsNone(payload["analysis_path"])
        self.assertFalse(payload["index_updated"])
        self.assertFalse(payload["log_appended"])
        self.assertEqual(before, self._snapshot_workspace())


if __name__ == "__main__":
    unittest.main()
