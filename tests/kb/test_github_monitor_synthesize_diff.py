"""Unit tests for synthesize_diff.py (Phase 3)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.github_monitor._types import (
    DRIFT_REPORT_VERSION,
    REGISTRY_VERSION,
)
from scripts.github_monitor.synthesize_diff import (
    SURFACE,
    _build_change_note,
    _is_binary,
    _render_diff,
    synthesize_diff,
    run_cli,
)
from scripts._optional_surface_common import STATUS_FAIL, STATUS_PASS, APPROVAL_APPROVED
from scripts.kb.contracts import GitHubMonitorReasonCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(
    owner: str = "test-org",
    repo: str = "test-repo",
    entries: list | None = None,
) -> dict:
    return {
        "version": REGISTRY_VERSION,
        "owner": owner,
        "repo": repo,
        "github_app_installation_id": None,
        "entries": entries or [],
    }


def _active_entry(
    path: str = "docs/guide.md",
    last_applied_blob_sha: str = "a" * 40,
    last_applied_commit_sha: str = "c" * 40,
    last_fetched_blob_sha: str = "b" * 40,
    last_fetched_commit_sha: str = "d" * 40,
    wiki_page: str = "wiki/pages/topical/guide.md",
) -> dict:
    return {
        "path": path,
        "tracking_status": "active",
        "last_applied_commit_sha": last_applied_commit_sha,
        "last_applied_blob_sha": last_applied_blob_sha,
        "last_applied_at": "2024-01-01T00:00:00Z",
        "last_fetched_commit_sha": last_fetched_commit_sha,
        "last_fetched_blob_sha": last_fetched_blob_sha,
        "sha256_at_last_applied": None,
        "wiki_page": wiki_page,
        "notes": "",
    }


def _drift_report(drifted: list | None = None) -> dict:
    return {
        "version": DRIFT_REPORT_VERSION,
        "generated_at": "2024-01-01T00:00:00+00:00",
        "registry": "raw/github-sources/org-repo.source-registry.json",
        "has_drift": bool(drifted),
        "drifted": drifted or [],
        "up_to_date": [],
        "uninitialized": [],
        "errors": [],
    }


def _drifted_entry(
    owner: str = "test-org",
    repo: str = "test-repo",
    path: str = "docs/guide.md",
    current_commit_sha: str = "d" * 40,
    current_blob_sha: str = "b" * 40,
    last_applied_commit_sha: str = "c" * 40,
    last_applied_blob_sha: str = "a" * 40,
) -> dict:
    return {
        "owner": owner,
        "repo": repo,
        "path": path,
        "current_commit_sha": current_commit_sha,
        "current_blob_sha": current_blob_sha,
        "last_applied_commit_sha": last_applied_commit_sha,
        "last_applied_blob_sha": last_applied_blob_sha,
        "compare_url": f"https://github.com/{owner}/{repo}/compare/old...new",
    }


# ---------------------------------------------------------------------------
# _is_binary tests
# ---------------------------------------------------------------------------


class IsBinaryTests(unittest.TestCase):
    def test_text_is_not_binary(self) -> None:
        self.assertFalse(_is_binary(b"Hello, world!\n"))

    def test_null_byte_is_binary(self) -> None:
        self.assertTrue(_is_binary(b"Hello\x00world"))

    def test_empty_is_not_binary(self) -> None:
        self.assertFalse(_is_binary(b""))


# ---------------------------------------------------------------------------
# _render_diff tests
# ---------------------------------------------------------------------------


class RenderDiffTests(unittest.TestCase):
    def test_simple_diff(self) -> None:
        old = "line one\nline two\n"
        new = "line one\nline three\n"
        diff = _render_diff(old, new, "file.md", "file.md")
        self.assertIn("-line two", diff)
        self.assertIn("+line three", diff)

    def test_identical_content_returns_empty(self) -> None:
        content = "same content\n"
        diff = _render_diff(content, content, "file.md", "file.md")
        self.assertEqual(diff, "")

    def test_new_file_all_additions(self) -> None:
        diff = _render_diff("", "new content\n", "file.md", "file.md")
        self.assertIn("+new content", diff)

    def test_truncation_at_limit(self) -> None:
        # Every line is different → diff has ~2× as many lines as input lines.
        old_lines = "\n".join(f"old_{i}" for i in range(200)) + "\n"
        new_lines = "\n".join(f"new_{i}" for i in range(200)) + "\n"
        diff = _render_diff(old_lines, new_lines, "file.md", "file.md")
        self.assertIn("truncated", diff)


# ---------------------------------------------------------------------------
# _build_change_note tests
# ---------------------------------------------------------------------------


class BuildChangeNoteTests(unittest.TestCase):
    _NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    def _entry(self) -> dict:
        return _drifted_entry()

    def test_change_note_contains_date(self) -> None:
        note = _build_change_note(self._entry(), "diff text", now=self._NOW)
        self.assertIn("2024-01-15", note)

    def test_change_note_contains_source_ref(self) -> None:
        note = _build_change_note(self._entry(), "diff text", now=self._NOW)
        self.assertIn("test-org/test-repo/docs/guide.md", note)

    def test_change_note_contains_diff(self) -> None:
        note = _build_change_note(self._entry(), "+new line\n-old line", now=self._NOW)
        self.assertIn("+new line", note)
        self.assertIn("-old line", note)

    def test_binary_note_has_no_diff(self) -> None:
        note = _build_change_note(
            self._entry(), "", is_binary=True, now=self._NOW
        )
        self.assertIn("Binary file", note)
        self.assertNotIn("~~~~diff", note)

    def test_empty_diff_shows_no_change_message(self) -> None:
        note = _build_change_note(self._entry(), "", now=self._NOW)
        self.assertIn("identical", note)

    def test_compare_url_in_note(self) -> None:
        entry = _drifted_entry()
        entry["compare_url"] = "https://github.com/test-org/test-repo/compare/abc...def"
        note = _build_change_note(entry, "diff", now=self._NOW)
        self.assertIn("compare on GitHub", note)

    def test_uses_tilde_fence_not_backtick(self) -> None:
        """Diff containing backticks must still be safe."""
        note = _build_change_note(
            self._entry(), "+```python\n+print('hello')\n+```", now=self._NOW
        )
        self.assertIn("~~~~diff", note)


# ---------------------------------------------------------------------------
# synthesize_diff integration tests
# ---------------------------------------------------------------------------


class SynthesizeDiffTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)
        (self._repo_root / "raw" / "assets").mkdir(parents=True)
        (self._repo_root / "wiki" / "pages" / "topical").mkdir(parents=True)

    def _write_registry(self, entries: list) -> Path:
        p = self._repo_root / "raw" / "github-sources" / "test.source-registry.json"
        p.write_text(json.dumps(_make_registry(entries=entries)))
        return p

    def _write_drift_report(self, drifted: list) -> Path:
        p = self._repo_root / "drift-report.json"
        p.write_text(json.dumps(_drift_report(drifted=drifted)))
        return p

    def _write_asset(self, commit_sha: str, path: str, content: bytes) -> Path:
        asset = self._repo_root / "raw" / "assets" / "test-org" / "test-repo" / commit_sha
        for part in path.split("/"):
            asset = asset / part
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(content)
        return asset

    def _write_wiki_page(self, path: str, content: str) -> Path:
        p = self._repo_root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def test_no_drifted_entries_passes(self) -> None:
        p = self._write_drift_report([])
        result = synthesize_diff(repo_root=self._repo_root, drift_report_path=p)
        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.reason_code, str(GitHubMonitorReasonCode.NO_DRIFT))

    def test_synthesizes_change_note(self) -> None:
        old_content = b"# Guide\n\nOld content.\n"
        new_content = b"# Guide\n\nNew content added.\n"
        old_commit = "c" * 40
        new_commit = "d" * 40
        blob_sha = "b" * 40

        self._write_asset(old_commit, "docs/guide.md", old_content)
        self._write_asset(new_commit, "docs/guide.md", new_content)
        wiki_page = self._write_wiki_page(
            "wiki/pages/topical/guide.md",
            "# Guide\n\nWiki content.\n",
        )

        entry = _active_entry(
            last_applied_commit_sha=old_commit,
            last_applied_blob_sha="a" * 40,
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
        )
        self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
            last_applied_commit_sha=old_commit,
            last_applied_blob_sha="a" * 40,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.summary["synthesized_count"], 1)
        self.assertEqual(result.summary["error_count"], 0)

        # Wiki page should contain the change note.
        wiki_content = wiki_page.read_text()
        self.assertIn("Change Note", wiki_content)
        self.assertIn("test-org/test-repo/docs/guide.md", wiki_content)

    def test_registry_last_applied_advances_after_wiki_write(self) -> None:
        old_commit = "c" * 40
        new_commit = "d" * 40
        blob_sha = "b" * 40

        self._write_asset(old_commit, "docs/guide.md", b"old content\n")
        self._write_asset(new_commit, "docs/guide.md", b"new content\n")
        self._write_wiki_page("wiki/pages/topical/guide.md", "# Guide\n")

        entry = _active_entry(
            last_applied_commit_sha=old_commit,
            last_applied_blob_sha="a" * 40,
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
        )
        reg_path = self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
            last_applied_commit_sha=old_commit,
            last_applied_blob_sha="a" * 40,
        )
        report_path = self._write_drift_report([drifted])

        synthesize_diff(repo_root=self._repo_root, drift_report_path=report_path)

        updated = json.loads(reg_path.read_text())
        reg_entry = updated["entries"][0]
        self.assertEqual(reg_entry["last_applied_commit_sha"], new_commit)
        self.assertEqual(reg_entry["last_applied_blob_sha"], blob_sha)
        self.assertIsNotNone(reg_entry["sha256_at_last_applied"])
        self.assertIsNotNone(reg_entry["last_applied_at"])

    def test_last_applied_not_fetched_yet_returns_error(self) -> None:
        """Drift report says drifted, but last_fetched_blob_sha doesn't match."""
        new_commit = "d" * 40
        blob_sha = "b" * 40

        # Registry has last_fetched_blob_sha = None (fetch_content not run yet)
        entry = _active_entry(
            last_fetched_blob_sha=None,  # type: ignore[arg-type]
            last_fetched_commit_sha=None,  # type: ignore[arg-type]
        )
        # Override to set None explicitly
        entry["last_fetched_blob_sha"] = None
        entry["last_fetched_commit_sha"] = None
        self._write_registry([entry])

        self._write_wiki_page("wiki/pages/topical/guide.md", "# Guide\n")

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_missing_new_asset_returns_error(self) -> None:
        """New asset not yet written to raw/assets/ → error."""
        new_commit = "d" * 40
        blob_sha = "b" * 40
        old_commit = "c" * 40

        self._write_asset(old_commit, "docs/guide.md", b"old\n")
        # Do NOT write new asset.
        self._write_wiki_page("wiki/pages/topical/guide.md", "# Guide\n")

        entry = _active_entry(
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
        )
        self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_binary_file_gets_change_note_without_diff(self) -> None:
        new_commit = "d" * 40
        blob_sha = "b" * 40
        old_commit = "c" * 40

        self._write_asset(old_commit, "docs/guide.md", b"old\n")
        # Binary file (contains null bytes).
        self._write_asset(new_commit, "docs/guide.md", b"\x00binary\x00data")
        wiki_page = self._write_wiki_page(
            "wiki/pages/topical/guide.md", "# Guide\n"
        )

        entry = _active_entry(
            last_applied_commit_sha=old_commit,
            last_applied_blob_sha="a" * 40,
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
        )
        self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )

        self.assertEqual(result.status, STATUS_PASS)
        wiki_content = wiki_page.read_text()
        self.assertIn("Binary file", wiki_content)
        self.assertNotIn("~~~~diff", wiki_content)

    def test_missing_wiki_page_returns_error(self) -> None:
        new_commit = "d" * 40
        blob_sha = "b" * 40

        self._write_asset(new_commit, "docs/guide.md", b"new\n")

        entry = _active_entry(
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
            wiki_page="wiki/pages/topical/nonexistent.md",
        )
        self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_no_wiki_page_field_returns_error(self) -> None:
        new_commit = "d" * 40
        blob_sha = "b" * 40

        self._write_asset(new_commit, "docs/guide.md", b"new\n")

        entry = _active_entry(
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
            wiki_page="",
        )
        entry["wiki_page"] = ""
        self._write_registry([entry])

        drifted = _drifted_entry(
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )
        self.assertEqual(result.status, STATUS_FAIL)

    def test_malformed_drift_report_returns_fail(self) -> None:
        p = self._repo_root / "bad.json"
        p.write_text("not json")
        result = synthesize_diff(repo_root=self._repo_root, drift_report_path=p)
        self.assertEqual(result.status, STATUS_FAIL)

    def test_path_traversal_returns_error(self) -> None:
        new_commit = "d" * 40
        blob_sha = "b" * 40

        entry = _active_entry(
            path="../evil.md",
            last_fetched_commit_sha=new_commit,
            last_fetched_blob_sha=blob_sha,
        )
        entry["path"] = "../evil.md"
        self._write_registry([entry])

        drifted = _drifted_entry(
            path="../evil.md",
            current_commit_sha=new_commit,
            current_blob_sha=blob_sha,
        )
        report_path = self._write_drift_report([drifted])

        result = synthesize_diff(
            repo_root=self._repo_root,
            drift_report_path=report_path,
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)


# ---------------------------------------------------------------------------
# run_cli tests
# ---------------------------------------------------------------------------


class SynthesizeDiffRunCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")

    def test_no_approval_returns_error(self) -> None:
        report = self._repo_root / "drift-report.json"
        report.write_text(json.dumps(_drift_report()))
        out = StringIO()
        code = run_cli(
            [
                "--drift-report", str(report),
                "--repo-root", str(self._repo_root),
            ],
            output_stream=out,
        )
        self.assertNotEqual(code, 0)

    def test_missing_drift_report_returns_error(self) -> None:
        out = StringIO()
        code = run_cli(
            [
                "--drift-report", str(self._repo_root / "nonexistent.json"),
                "--approval", "approved",
                "--repo-root", str(self._repo_root),
            ],
            output_stream=out,
        )
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
