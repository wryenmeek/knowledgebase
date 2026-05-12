"""Interface and fail-closed checks for optional heavy script families."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.kb.harnesses import RuntimeWorkspaceTestCase, load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGE_CONTEXT_PATH = REPO_ROOT / "scripts" / "context" / "manage_context_pages.py"
FILL_CONTEXT_PATH = REPO_ROOT / "scripts" / "context" / "fill_context_pages.py"
GENERATE_DOCS_PATH = REPO_ROOT / "scripts" / "maintenance" / "generate_docs.py"
CONVERT_SOURCES_PATH = REPO_ROOT / "scripts" / "ingest" / "convert_sources_to_md.py"
SNAPSHOT_PATH = REPO_ROOT / "scripts" / "validation" / "snapshot_knowledgebase.py"
QUALITY_REPORT_PATH = REPO_ROOT / "scripts" / "reporting" / "content_quality_report.py"
QUALITY_RUNTIME_PATH = REPO_ROOT / "scripts" / "reporting" / "quality_runtime.py"


class OptionalSurfaceScriptTests(RuntimeWorkspaceTestCase):
    RUNTIME_ROOT_NAME = ".runtime_optional_surfaces"

    def setUp(self) -> None:
        super().setUp()
        (self.workspace / "AGENTS.md").write_text("knowledgebase fixture\n", encoding="utf-8")
        self.write_file(
            "docs/guide.md",
            '---\nupdated_at: "2024-01-01T00:00:00Z"\nsources: []\n---\n\n# Guide\n\nTODO\n',
        )
        self.write_file("schema/contract.md", "# Contract\n\n{{fill}}\n")
        self.write_file(".github/skills/demo/SKILL.md", "# Demo Skill\n\nTBD\n")
        self.write_file("docs/staged/status.md", "# Status\n")
        self.write_file("wiki/page.md", '---\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# Page\n\nTODO\n')
        self.write_file("scripts/demo.py", "print('demo')\n")
        self.write_file("raw/inbox/source.txt", "plain source body\n")
        self.write_file("raw/inbox/source.pdf", "%PDF-1.7\n")
        self.write_file("raw/processed/source.md", "# Processed\n")

    def _run_script(self, script_path: Path, *args: str) -> tuple[int, dict[str, object]]:
        completed = subprocess.run(
            [sys.executable, str(script_path), *args],
            cwd=self.workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_declared_interface_shapes_exist(self) -> None:
        expectations = {
            "manage_context": (MANAGE_CONTEXT_PATH, ("inventory", "plan-fill", "publish-status")),
            "fill_context": (FILL_CONTEXT_PATH, ("preview", "apply")),
            "generate_docs": (GENERATE_DOCS_PATH, ("inventory", "plan", "apply")),
            "convert_sources": (CONVERT_SOURCES_PATH, ("inspect", "preview", "apply")),
            "snapshot": (SNAPSHOT_PATH, ("capture", "compare")),
            "quality_report": (QUALITY_REPORT_PATH, ("summary", "placeholder-audit", "persist")),
            "quality_runtime": (QUALITY_RUNTIME_PATH, ("recommend", "score-update", "report")),
        }
        for module_name, (module_path, modes) in expectations.items():
            module = load_module(f"{module_name}_{self._testMethodName}", module_path)
            with self.subTest(module=module_name):
                self.assertEqual(module.SUPPORTED_MODES, modes)
                self.assertTrue(hasattr(module, "run_cli"))

    def test_manage_context_supports_repo_root_execution_and_reports_path_rules(self) -> None:
        exit_code, payload = self._run_script(
            MANAGE_CONTEXT_PATH,
            "--mode",
            "inventory",
            "--path",
            "docs",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["mode"], "inventory")
        self.assertIn("docs", payload["path_rules"]["allowlisted_roots"])
        self.assertEqual(payload["summary"]["selected_count"], 2)

    def test_manage_context_publish_status_requires_approval_and_declares_lock(self) -> None:
        module = load_module(f"manage_publish_{self._testMethodName}", MANAGE_CONTEXT_PATH)

        stdout = StringIO()
        exit_code = module.run_cli(
            [
                "--repo-root",
                str(self.workspace),
                "--mode",
                "publish-status",
                "--staged-status-path",
                "docs/staged/status.md",
            ],
            output_stream=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "approval_required")
        self.assertTrue(payload["lock_required"])
        self.assertEqual(payload["lock_path"], "wiki/.kb_write.lock")

    def test_manage_context_publish_status_delegates_to_sync_wrapper(self) -> None:
        module = load_module(f"manage_delegate_{self._testMethodName}", MANAGE_CONTEXT_PATH)
        stdout = StringIO()
        with patch.object(module.subprocess, "run") as run_mock:
            exit_code = module.run_cli(
                [
                    "--repo-root",
                    str(self.workspace),
                    "--mode",
                    "publish-status",
                    "--staged-status-path",
                    "docs/staged/status.md",
                    "--approval",
                    "approved",
                ],
                output_stream=stdout,
            )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload["summary"]["delegated_writer"],
            ".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py",
        )
        delegated_command = run_mock.call_args.args[0]
        self.assertIn(
            ".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py",
            delegated_command[1],
        )
        self.assertEqual(delegated_command[-2:], ["--write-status-from", "docs/staged/status.md"])

    def test_manage_context_publish_status_rejects_staged_status_outside_allowlist(self) -> None:
        self.write_file("schema/status.md", "# Wrong place\n")

        exit_code, payload = self._run_script(
            MANAGE_CONTEXT_PATH,
            "--mode",
            "publish-status",
            "--staged-status-path",
            "schema/status.md",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("outside the declared scope", payload["message"])

    def test_fill_context_apply_requires_staged_fills_path(self) -> None:
        # apply without --staged-fills-path should fail with invalid_input
        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("staged-fills-path", payload["message"])

    def test_fill_context_apply_writes_fills_from_manifest(self) -> None:
        # Produce a valid fill manifest and verify apply mode writes the file.
        import hashlib
        target_rel = "docs/guide.md"
        existing_text = (self.workspace / target_rel).read_text(encoding="utf-8")
        sha = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
        filled_content = "---\nupdated_at: \"2024-01-01T00:00:00Z\"\nsources: []\n---\n\n# Guide\n\nFilled content.\n"
        manifest = {"items": [{"path": target_rel, "content": filled_content, "expected_before_sha256": sha}]}
        self.write_file("docs/staged/fills.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--staged-fills-path",
            "docs/staged/fills.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["summary"]["written_count"], 1)
        self.assertEqual((self.workspace / target_rel).read_text(encoding="utf-8"), filled_content)

    def test_fill_context_apply_rejects_remaining_placeholders(self) -> None:
        manifest = {"items": [{"path": "docs/guide.md", "content": "# Guide\n\nTODO still here\n"}]}
        self.write_file("docs/staged/fills-bad.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--staged-fills-path",
            "docs/staged/fills-bad.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("placeholder", payload["message"])

    def test_fill_context_apply_rejects_schema_write_target(self) -> None:
        manifest = {"items": [{"path": "schema/contract.md", "content": "# Contract\n\nFilled.\n"}]}
        self.write_file("docs/staged/fills-schema.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--staged-fills-path",
            "docs/staged/fills-schema.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("declared write scope", payload["message"])

    def test_fill_context_apply_rejects_docs_staged_write_target(self) -> None:
        manifest = {"items": [{"path": "docs/staged/output.md", "content": "# Output\n"}]}
        self.write_file("docs/staged/fills-staging.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--staged-fills-path",
            "docs/staged/fills-staging.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("denied write root", payload["message"])

    def test_fill_context_apply_rejects_sha_mismatch(self) -> None:
        manifest = {"items": [{"path": "docs/guide.md", "content": "# Guide\n\nFilled.\n", "expected_before_sha256": "a" * 64}]}
        self.write_file("docs/staged/fills-sha.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            FILL_CONTEXT_PATH,
            "--mode",
            "apply",
            "--staged-fills-path",
            "docs/staged/fills-sha.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("SHA mismatch", payload["message"])

    def test_generate_docs_apply_requires_staged_docs_path(self) -> None:
        exit_code, payload = self._run_script(
            GENERATE_DOCS_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("staged-docs-path", payload["message"])

    def test_generate_docs_apply_writes_new_doc_from_manifest(self) -> None:
        new_doc_content = "# Scripts Reference\n\nAuto-generated.\n"
        manifest = {"items": [{"path": "docs/scripts-reference.md", "content": new_doc_content}]}
        self.write_file("docs/staged/docs-manifest.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            GENERATE_DOCS_PATH,
            "--mode",
            "apply",
            "--staged-docs-path",
            "docs/staged/docs-manifest.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["summary"]["written_count"], 1)
        self.assertEqual((self.workspace / "docs/scripts-reference.md").read_text(encoding="utf-8"), new_doc_content)

    def test_generate_docs_apply_rejects_write_outside_docs(self) -> None:
        manifest = {"items": [{"path": "wiki/generated.md", "content": "# Generated\n"}]}
        self.write_file("docs/staged/docs-bad.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            GENERATE_DOCS_PATH,
            "--mode",
            "apply",
            "--staged-docs-path",
            "docs/staged/docs-bad.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("declared write scope", payload["message"])

    def test_generate_docs_apply_rejects_docs_staged_write_target(self) -> None:
        manifest = {"items": [{"path": "docs/staged/output.md", "content": "# Output\n"}]}
        self.write_file("docs/staged/docs-staging.json", json.dumps(manifest))

        exit_code, payload = self._run_script(
            GENERATE_DOCS_PATH,
            "--mode",
            "apply",
            "--staged-docs-path",
            "docs/staged/docs-staging.json",
            "--approval",
            "approved",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("denied write root", payload["message"])

    def test_generate_docs_inventory_runs_from_repo_root(self) -> None:
        exit_code, payload = self._run_script(
            GENERATE_DOCS_PATH,
            "--mode",
            "inventory",
            "--path",
            "docs",
            "--path",
            "scripts",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertGreaterEqual(payload["summary"]["document_targets"], 1)
        self.assertIn("docs", payload["path_rules"]["allowlisted_roots"])

    def test_convert_sources_preview_is_read_only_and_rejects_path_escape(self) -> None:
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "preview",
            "--path",
            "../outside.txt",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("path escapes repository root", payload["message"])

    def test_convert_sources_preview_returns_markdown_for_supported_text_and_fails_for_pdf(self) -> None:
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "preview",
            "--path",
            "raw/inbox/source.txt",
            "--path",
            "raw/inbox/source.pdf",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "unsupported_source_type")
        text_item = next(item for item in payload["items"] if "preview_markdown" in item)
        pdf_item = next(item for item in payload["items"] if item.get("reason_code") == "unsupported_source_type")
        self.assertIn("# Source", text_item["preview_markdown"])
        self.assertEqual(pdf_item["reason_code"], "unsupported_source_type")

    def test_convert_sources_apply_requires_approval(self) -> None:
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "apply",
            "--path",
            "raw/inbox/source.txt",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "approval_required")

    def test_convert_sources_apply_rejects_assets_path(self) -> None:
        self.write_file("raw/assets/vendor.md", "# Vendored Asset\n")
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
            "--path",
            "raw/assets/vendor.md",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("raw/inbox", payload["message"])

    def test_convert_sources_apply_writes_md_and_meta(self) -> None:
        self.write_file("raw/inbox/my-source.txt", "Hello world\n")
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
            "--path",
            "raw/inbox/my-source.txt",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["converted_count"], 1)
        self.assertEqual(payload["summary"]["error_count"], 0)
        item = payload["items"][0]
        self.assertEqual(item["status"], "pass")
        self.assertEqual(item["output_path"], "raw/processed/my-source.md")
        self.assertEqual(item["meta_path"], "raw/processed/my-source.meta.json")
        self.assertIn("source_sha256", item)
        # verify files actually exist in the workspace
        md_path = self.workspace / "raw/processed/my-source.md"
        meta_path = self.workspace / "raw/processed/my-source.meta.json"
        self.assertTrue(md_path.exists())
        self.assertTrue(meta_path.exists())
        meta = json.loads(meta_path.read_text())
        self.assertIn("source_sha256", meta)
        self.assertEqual(meta["surface"], "scripts/ingest/convert_sources_to_md.py")

    def test_convert_sources_apply_immutability_guard(self) -> None:
        self.write_file("raw/inbox/existing.txt", "First run\n")
        self.write_file("raw/processed/existing.md", "# Existing\n")
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
            "--path",
            "raw/inbox/existing.txt",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "conversion_errors")
        item = payload["items"][0]
        self.assertEqual(item["reason_code"], "output_already_exists")

    def test_convert_sources_apply_slug_collision_rejected(self) -> None:
        self.write_file("raw/inbox/report.txt", "text version\n")
        self.write_file("raw/inbox/report.html", "<html>html version</html>\n")
        exit_code, payload = self._run_script(
            CONVERT_SOURCES_PATH,
            "--mode",
            "apply",
            "--approval",
            "approved",
            "--path",
            "raw/inbox/report.txt",
            "--path",
            "raw/inbox/report.html",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("slug collision", payload["message"])

    def test_snapshot_capture_and_compare_run_from_repo_root(self) -> None:
        capture_exit, capture_payload = self._run_script(
            SNAPSHOT_PATH,
            "--mode",
            "capture",
            "--path",
            "wiki",
        )
        self.assertEqual(capture_exit, 0)
        snapshot_path = self.write_file("docs/staged/snapshot.json", json.dumps(capture_payload))
        self.write_file(
            "wiki/page.md",
            '---\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# Page\n\nChanged\n',
        )

        compare_exit, compare_payload = self._run_script(
            SNAPSHOT_PATH,
            "--mode",
            "compare",
            "--path",
            "wiki",
            "--snapshot",
            snapshot_path.relative_to(self.workspace).as_posix(),
        )
        self.assertEqual(compare_exit, 0)
        self.assertIn("wiki/page.md", compare_payload["summary"]["changed"])

    def test_content_quality_report_summary_counts_placeholders(self) -> None:
        summary_exit, summary_payload = self._run_script(
            QUALITY_REPORT_PATH,
            "--mode",
            "summary",
            "--path",
            "wiki",
            "--path",
            "docs",
        )
        self.assertEqual(summary_exit, 0)
        self.assertEqual(summary_payload["summary"]["placeholder_file_count"], 2)

    def test_content_quality_persist_requires_approval(self) -> None:
        exit_code, payload = self._run_script(
            QUALITY_REPORT_PATH,
            "--mode",
            "persist",
            "--path",
            "wiki",
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "approval_required")
        self.assertTrue(payload["lock_required"])

    def test_content_quality_persist_writes_artifact(self) -> None:
        before = self.snapshot_workspace()
        exit_code, payload = self._run_script(
            QUALITY_REPORT_PATH,
            "--mode",
            "persist",
            "--path",
            "wiki",
            "--approval",
            "approved",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertIn("written_path", payload["summary"])
        written = payload["summary"]["written_path"]
        self.assertTrue(written.startswith("wiki/reports/content-quality-"))
        self.assertTrue(written.endswith(".json"))
        after = self.snapshot_workspace()
        self.assertNotEqual(before, after)
        self.assertIn(written, after)

    def test_content_quality_persist_artifact_is_schema_conformant(self) -> None:
        exit_code, payload = self._run_script(
            QUALITY_REPORT_PATH,
            "--mode",
            "persist",
            "--path",
            "wiki",
            "--approval",
            "approved",
        )
        self.assertEqual(exit_code, 0)
        written = payload["summary"]["written_path"]
        artifact = json.loads((self.workspace / written).read_text(encoding="utf-8"))
        for field in ("report_type", "generated_at", "scope", "surface", "findings", "summary"):
            self.assertIn(field, artifact)
        self.assertEqual(artifact["report_type"], "content-quality")
        self.assertEqual(artifact["surface"], "scripts/reporting/content_quality_report.py")
        for item in artifact["findings"]:
            for key in ("path", "missing_sources", "missing_updated_at", "placeholder_count"):
                self.assertIn(key, item)
        for key in ("selected_count", "missing_sources_count", "missing_updated_at_count", "placeholder_file_count"):
            self.assertIn(key, artifact["summary"])

    def test_content_quality_persist_collision_produces_counter_suffix(self) -> None:
        for _ in range(2):
            exit_code, payload = self._run_script(
                QUALITY_REPORT_PATH,
                "--mode",
                "persist",
                "--path",
                "wiki",
                "--approval",
                "approved",
            )
            self.assertEqual(exit_code, 0)
        files = list((self.workspace / "wiki" / "reports").iterdir())
        self.assertEqual(len(files), 2)
        names = {f.name for f in files}
        self.assertTrue(any("-2" in n for n in names), f"Expected counter suffix in: {names}")

    def test_quality_runtime_recommend_mode_prioritizes_repo_evidence_without_mutation(self) -> None:
        self.write_file(
            "wiki/high-priority.md",
            '---\nconfidence: 2\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# High Priority\n\nTODO\n',
        )
        self.write_file(
            "wiki/low-priority.md",
            '---\nsources: []\nconfidence: 5\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# Low Priority\n',
        )
        self.write_file(
            "docs/query-evidence.json",
            json.dumps(
                [
                    {
                        "query": "dialysis prior authorization",
                        "target_path": "wiki/high-priority.md",
                        "missed": True,
                        "demand": 3,
                    },
                    {
                        "query": "general guidance",
                        "target_path": "wiki/low-priority.md",
                        "missed": False,
                        "demand": 1,
                    },
                ]
            ),
        )
        before = self.snapshot_workspace()

        exit_code, payload = self._run_script(
            QUALITY_RUNTIME_PATH,
            "--mode",
            "recommend",
            "--path",
            "wiki/high-priority.md",
            "--path",
            "wiki/low-priority.md",
            "--query-evidence",
            "docs/query-evidence.json",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertTrue(payload["summary"]["recommendation_only"])
        self.assertEqual(payload["summary"]["scoring_mode"], "recommendation-only")
        self.assertEqual(payload["items"][0]["path"], "wiki/high-priority.md")
        self.assertEqual(payload["items"][0]["missed_query_count"], 1)
        self.assertGreater(payload["items"][0]["priority_score"], payload["items"][1]["priority_score"])
        self.assertEqual(before, self.snapshot_workspace())

    def test_quality_runtime_score_update_requires_approval(self) -> None:
        exit_code, payload = self._run_script(
            QUALITY_RUNTIME_PATH,
            "--mode",
            "score-update",
            "--path",
            "wiki",
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "approval_required")
        self.assertTrue(payload["lock_required"])

    def test_quality_runtime_score_update_writes_quality_scores_artifact(self) -> None:
        self.write_file(
            "wiki/high-priority.md",
            '---\nconfidence: 2\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# High Priority\n\nTODO\n',
        )
        before = self.snapshot_workspace()
        exit_code, payload = self._run_script(
            QUALITY_RUNTIME_PATH,
            "--mode",
            "score-update",
            "--path",
            "wiki/high-priority.md",
            "--approval",
            "approved",
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "pass")
        self.assertIn("written_path", payload["summary"])
        written = payload["summary"]["written_path"]
        self.assertTrue(written.startswith("wiki/reports/quality-scores-"))
        self.assertNotEqual(before, self.snapshot_workspace())

    def test_quality_runtime_report_writes_quality_report_artifact(self) -> None:
        self.write_file(
            "wiki/page2.md",
            '---\nsources: []\nconfidence: 4\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# Page 2\n',
        )
        exit_code, payload = self._run_script(
            QUALITY_RUNTIME_PATH,
            "--mode",
            "report",
            "--path",
            "wiki/page2.md",
            "--approval",
            "approved",
        )
        self.assertEqual(exit_code, 0)
        written = payload["summary"]["written_path"]
        self.assertTrue(written.startswith("wiki/reports/quality-report-"))

    def test_quality_runtime_score_update_artifact_is_schema_conformant(self) -> None:
        self.write_file(
            "wiki/scored.md",
            '---\nconfidence: 3\nupdated_at: "2024-01-01T00:00:00Z"\n---\n\n# Scored\n',
        )
        exit_code, payload = self._run_script(
            QUALITY_RUNTIME_PATH,
            "--mode",
            "score-update",
            "--path",
            "wiki/scored.md",
            "--approval",
            "approved",
        )
        self.assertEqual(exit_code, 0)
        written = payload["summary"]["written_path"]
        artifact = json.loads((self.workspace / written).read_text(encoding="utf-8"))
        for field in ("report_type", "generated_at", "scope", "surface", "findings", "summary"):
            self.assertIn(field, artifact)
        self.assertEqual(artifact["report_type"], "quality-scores")
        self.assertFalse(artifact["summary"]["recommendation_only"])
        self.assertEqual(artifact["summary"]["scoring_mode"], "score-update")
        for item in artifact["findings"]:
            for key in ("path", "priority_score", "confidence", "missing_sources",
                        "missing_updated_at", "placeholder_count",
                        "missed_query_count", "missed_query_demand", "recommended_next_step"):
                self.assertIn(key, item)

    def test_content_quality_report_ignores_body_mentions_of_frontmatter_keys(self) -> None:
        self.write_file("docs/body-only.md", "# Body Only\n\nsources: body mention only\nupdated_at: body mention only\n")

        exit_code, payload = self._run_script(
            QUALITY_REPORT_PATH,
            "--mode",
            "summary",
            "--path",
            "docs/body-only.md",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["missing_sources_count"], 1)
        self.assertEqual(payload["summary"]["missing_updated_at_count"], 1)

    def test_snapshot_compare_rejects_malformed_snapshot_shape(self) -> None:
        self.write_file("docs/staged/bad-snapshot.json", "[]")

        exit_code, payload = self._run_script(
            SNAPSHOT_PATH,
            "--mode",
            "compare",
            "--path",
            "wiki",
            "--snapshot",
            "docs/staged/bad-snapshot.json",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["reason_code"], "invalid_input")
        self.assertIn("items", payload["message"])

    def test_missing_repo_root_fails_closed_for_optional_surfaces(self) -> None:
        empty_workspace = self.runtime_root / "missing-repo-root"
        if empty_workspace.exists():
            shutil.rmtree(empty_workspace)
        empty_workspace.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [sys.executable, str(QUALITY_REPORT_PATH), "--mode", "summary", "--path", "docs"],
            cwd=empty_workspace,
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["reason_code"], "prereq_missing:repo_root")


if __name__ == "__main__":
    unittest.main()
