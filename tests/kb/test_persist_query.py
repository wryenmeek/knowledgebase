"""Tests for policy-gated query persistence CLI behavior."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.kb import persist_query
from tests.kb.harnesses import RuntimeWorkspaceTestCase


class PersistQueryCliTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_persist_query"

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

    def _run_cli(self, *args: str) -> tuple[int, dict[str, object]]:
        output = StringIO()
        exit_code = persist_query.run_cli(
            argv=list(args),
            output_stream=output,
            repo_root=self.workspace,
        )
        payload = json.loads(output.getvalue())
        return exit_code, payload

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

    def _assert_envelope_values(
        self,
        payload: dict[str, object],
        *,
        status: str,
        reason_code: str,
        analysis_path: str | None = None,
        index_updated: bool = False,
        log_appended: bool = False,
        sources: list[str] | None = None,
    ) -> None:
        self._assert_required_envelope_keys(payload)
        self.assertEqual(payload["status"], status)
        self.assertEqual(payload["reason_code"], reason_code)
        self.assertEqual(payload["analysis_path"], analysis_path)
        self.assertEqual(payload["index_updated"], index_updated)
        self.assertEqual(payload["log_appended"], log_appended)
        if sources is not None:
            self.assertEqual(payload["sources"], sources)

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
        self._assert_envelope_values(
            first_payload,
            status="written",
            reason_code="ok",
            index_updated=True,
            log_appended=True,
            sources=sorted([source_a, source_b]),
            analysis_path=first_payload["analysis_path"],  # type: ignore
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
        self._assert_envelope_values(
            second_payload,
            status="written",
            reason_code="ok",
            analysis_path=first_analysis_path,  # type: ignore
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(
            (self.wiki_root / "log.md").read_text(encoding="utf-8"),
            log_after_first_run,
        )
        analysis_pages = list((self.wiki_root / "analyses").glob("*.md"))
        self.assertEqual(len(analysis_pages), 1)

    def test_policy_miss_returns_no_write_policy_and_makes_no_changes(self) -> None:
        source_a = self._source("source-a", "a")
        before = self.snapshot_workspace()

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
        self._assert_envelope_values(
            payload,
            status="no_write_policy",
            reason_code="policy_confidence_below_min",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(before, self.snapshot_workspace())

    def test_policy_sources_below_min_returns_no_write_policy_without_mutation(self) -> None:
        source_a = self._source("source-a", "a")
        before = self.snapshot_workspace()

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
        self._assert_envelope_values(
            payload,
            status="no_write_policy",
            reason_code="policy_sources_below_min",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(before, self.snapshot_workspace())

    def test_policy_unresolved_contradiction_returns_no_write_policy_without_mutation(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")
        before = self.snapshot_workspace()

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
        self._assert_envelope_values(
            payload,
            status="no_write_policy",
            reason_code="policy_unresolved_contradiction",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(before, self.snapshot_workspace())

    def test_invalid_input_returns_failed_envelope_and_non_zero_exit(self) -> None:
        before = self.snapshot_workspace()

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
        self._assert_envelope_values(
            payload,
            status="failed",
            reason_code="invalid_input",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(before, self.snapshot_workspace())

    def test_index_failure_after_analysis_write_rolls_back_workspace_state(self) -> None:
        source_a = self._source("source-a", "a")
        source_b = self._source("source-b", "b")
        summary = "Dialysis coverage varies by plan and service context."
        (self.wiki_root / ".kb_write.lock").write_text("", encoding="utf-8")
        before = self.snapshot_workspace()

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
        self._assert_envelope_values(
            payload,
            status="failed",
            reason_code="write_failed",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
        )
        self.assertEqual(before, self.snapshot_workspace())

    def test_default_envelope_wiring_on_invalid_input(self) -> None:
        """Verify envelope defaults when PersistRequest/Outcome are absent."""
        # Query is empty -> PersistRequest won't be created
        exit_code, payload = self._run_cli(
            "--query",
            "",
            "--confidence",
            "5",
            "--result-json",
        )

        self.assertEqual(exit_code, 1)
        self._assert_envelope_values(
            payload,
            status="failed",
            reason_code="invalid_input",
            analysis_path=None,
            index_updated=False,
            log_appended=False,
            sources=[],
        )


if __name__ == "__main__":
    unittest.main()
