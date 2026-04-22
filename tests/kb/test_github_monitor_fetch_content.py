"""Unit tests for fetch_content.py (Phase 2) and _registry.py helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import unittest
import urllib.error
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.github_monitor._types import (
    DRIFT_REPORT_VERSION,
    REGISTRY_VERSION,
)
from scripts.github_monitor._registry import (
    find_registry_for,
    update_last_fetched,
)
from scripts.github_monitor.fetch_content import (
    SURFACE,
    fetch_content,
    run_cli,
)
from scripts._optional_surface_common import STATUS_FAIL, STATUS_PASS, APPROVAL_APPROVED
from scripts.kb.contracts import GitHubMonitorReasonCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(owner: str = "test-org", repo: str = "test-repo", entries: list | None = None) -> dict:
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
) -> dict:
    return {
        "path": path,
        "tracking_status": "active",
        "last_applied_commit_sha": last_applied_commit_sha,
        "last_applied_blob_sha": last_applied_blob_sha,
        "last_applied_at": "2024-01-01T00:00:00Z",
        "last_fetched_commit_sha": None,
        "last_fetched_blob_sha": None,
        "sha256_at_last_applied": None,
        "wiki_page": "wiki/pages/topical/guide.md",
        "notes": "",
    }


def _drift_report(
    registry: str = "raw/github-sources/org-repo.source-registry.json",
    drifted: list | None = None,
) -> dict:
    return {
        "version": DRIFT_REPORT_VERSION,
        "generated_at": "2024-01-01T00:00:00+00:00",
        "registry": registry,
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
        "compare_url": (
            f"https://github.com/{owner}/{repo}/compare/"
            f"{last_applied_commit_sha[:7]}...{current_commit_sha[:7]}"
        ),
    }


def _mock_contents_response(blob_sha: str, content: bytes = b"hello world") -> dict:
    return {
        "sha": blob_sha,
        "content": base64.b64encode(content).decode() + "\n",
        "encoding": "base64",
        "size": len(content),
        "name": "guide.md",
        "path": "docs/guide.md",
    }


def _make_urlopen_mock(body: dict) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


# ---------------------------------------------------------------------------
# find_registry_for tests
# ---------------------------------------------------------------------------


class FindRegistryForTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)

    def test_finds_matching_registry(self) -> None:
        reg = _make_registry("test-org", "test-repo")
        p = self._repo_root / "raw" / "github-sources" / "test-org-test-repo.source-registry.json"
        p.write_text(json.dumps(reg))
        result = find_registry_for(self._repo_root, "test-org", "test-repo")
        self.assertEqual(result, p)

    def test_returns_none_when_no_match(self) -> None:
        result = find_registry_for(self._repo_root, "other-org", "other-repo")
        self.assertIsNone(result)

    def test_skips_malformed_json(self) -> None:
        p = self._repo_root / "raw" / "github-sources" / "bad.source-registry.json"
        p.write_text("not json")
        result = find_registry_for(self._repo_root, "test-org", "test-repo")
        self.assertIsNone(result)

    def test_owner_repo_mismatch_returns_none(self) -> None:
        reg = _make_registry("other-org", "other-repo")
        p = self._repo_root / "raw" / "github-sources" / "other.source-registry.json"
        p.write_text(json.dumps(reg))
        result = find_registry_for(self._repo_root, "test-org", "test-repo")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# update_last_fetched tests
# ---------------------------------------------------------------------------


class UpdateLastFetchedTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)
        self._reg_path = (
            self._repo_root / "raw" / "github-sources" / "test.source-registry.json"
        )

    def _write_registry(self, entries: list) -> None:
        reg = _make_registry(entries=entries)
        self._reg_path.write_text(json.dumps(reg))

    def test_updates_last_fetched_fields(self) -> None:
        self._write_registry([_active_entry()])
        result = update_last_fetched(
            self._repo_root,
            self._reg_path,
            "docs/guide.md",
            commit_sha="d" * 40,
            blob_sha="b" * 40,
        )
        self.assertTrue(result)
        updated = json.loads(self._reg_path.read_text())
        entry = updated["entries"][0]
        self.assertEqual(entry["last_fetched_commit_sha"], "d" * 40)
        self.assertEqual(entry["last_fetched_blob_sha"], "b" * 40)

    def test_does_not_modify_last_applied(self) -> None:
        self._write_registry([_active_entry()])
        update_last_fetched(
            self._repo_root,
            self._reg_path,
            "docs/guide.md",
            commit_sha="d" * 40,
            blob_sha="b" * 40,
        )
        updated = json.loads(self._reg_path.read_text())
        entry = updated["entries"][0]
        self.assertEqual(entry["last_applied_commit_sha"], "c" * 40)
        self.assertEqual(entry["last_applied_blob_sha"], "a" * 40)

    def test_returns_false_for_missing_path(self) -> None:
        self._write_registry([_active_entry()])
        result = update_last_fetched(
            self._repo_root,
            self._reg_path,
            "nonexistent/path.md",
            commit_sha="d" * 40,
            blob_sha="b" * 40,
        )
        self.assertFalse(result)

    def test_atomic_replace_is_valid_json(self) -> None:
        self._write_registry([_active_entry()])
        update_last_fetched(
            self._repo_root,
            self._reg_path,
            "docs/guide.md",
            commit_sha="d" * 40,
            blob_sha="b" * 40,
        )
        parsed = json.loads(self._reg_path.read_text())
        self.assertEqual(parsed["version"], REGISTRY_VERSION)


# ---------------------------------------------------------------------------
# fetch_content tests
# ---------------------------------------------------------------------------


class FetchContentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)
        (self._repo_root / "raw" / "assets").mkdir(parents=True)
        # Registry
        self._reg_path = (
            self._repo_root / "raw" / "github-sources" / "test.source-registry.json"
        )
        self._reg_path.write_text(json.dumps(_make_registry(entries=[_active_entry()])))

    def _write_drift_report(self, drifted: list) -> Path:
        p = self._repo_root / "drift-report.json"
        p.write_text(json.dumps(_drift_report(drifted=drifted)))
        return p

    def test_no_drifted_entries_passes(self) -> None:
        p = self._write_drift_report([])
        result = fetch_content(
            repo_root=self._repo_root,
            drift_report_path=p,
            github_token="test-token",
        )
        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.reason_code, str(GitHubMonitorReasonCode.NO_DRIFT))

    def test_fetch_writes_asset_and_updates_registry(self) -> None:
        content = b"# Guide\n\nHello world."
        blob_sha = "b" * 40
        entry = _drifted_entry(current_blob_sha=blob_sha)
        p = self._write_drift_report([entry])

        mock_resp = _make_urlopen_mock(
            _mock_contents_response(blob_sha, content)
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content(
                repo_root=self._repo_root,
                drift_report_path=p,
                github_token="test-token",
            )

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.summary["fetched_count"], 1)
        self.assertEqual(result.summary["error_count"], 0)

        # Asset file should exist.
        asset = (
            self._repo_root / "raw" / "assets" / "test-org" / "test-repo"
            / ("d" * 40) / "docs" / "guide.md"
        )
        self.assertTrue(asset.exists())
        self.assertEqual(asset.read_bytes(), content)

        # Registry should be updated.
        updated = json.loads(self._reg_path.read_text())
        reg_entry = updated["entries"][0]
        self.assertEqual(reg_entry["last_fetched_blob_sha"], blob_sha)
        self.assertEqual(reg_entry["last_fetched_commit_sha"], "d" * 40)
        # last_applied_* must NOT change.
        self.assertEqual(reg_entry["last_applied_blob_sha"], "a" * 40)

    def test_blob_sha_mismatch_returns_error(self) -> None:
        entry = _drifted_entry(current_blob_sha="b" * 40)
        p = self._write_drift_report([entry])

        # API returns a different blob SHA than what drift report says.
        mock_resp = _make_urlopen_mock(
            _mock_contents_response("c" * 40, b"content")
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content(
                repo_root=self._repo_root,
                drift_report_path=p,
                github_token="test-token",
            )

        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_api_404_returns_error(self) -> None:
        entry = _drifted_entry()
        p = self._write_drift_report([entry])

        http_err = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = fetch_content(
                repo_root=self._repo_root,
                drift_report_path=p,
                github_token="test-token",
            )

        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)
        self.assertEqual(
            result.items[0]["reason_code"],
            str(GitHubMonitorReasonCode.UNREACHABLE),
        )

    def test_no_registry_for_entry_returns_error(self) -> None:
        entry = _drifted_entry(owner="unknown-org", repo="unknown-repo")
        p = self._write_drift_report([entry])

        content = b"data"
        blob_sha = "b" * 40
        entry["current_blob_sha"] = blob_sha
        p.write_text(json.dumps(_drift_report(drifted=[entry])))

        mock_resp = _make_urlopen_mock(
            _mock_contents_response(blob_sha, content)
        )
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content(
                repo_root=self._repo_root,
                drift_report_path=p,
                github_token="test-token",
            )

        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_idempotent_fetch_same_bytes(self) -> None:
        """Re-fetching with same bytes is a no-op (exclusive_create_write_once)."""
        content = b"same content"
        blob_sha = "b" * 40
        commit_sha = "d" * 40

        # Pre-write the asset.
        asset = (
            self._repo_root / "raw" / "assets" / "test-org" / "test-repo"
            / commit_sha / "docs" / "guide.md"
        )
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(content)

        entry = _drifted_entry(
            current_commit_sha=commit_sha,
            current_blob_sha=blob_sha,
        )
        p = self._write_drift_report([entry])
        mock_resp = _make_urlopen_mock(_mock_contents_response(blob_sha, content))

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetch_content(
                repo_root=self._repo_root,
                drift_report_path=p,
                github_token="test-token",
            )

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.summary["fetched_count"], 1)

    def test_malformed_drift_report_returns_fail(self) -> None:
        p = self._repo_root / "bad-report.json"
        p.write_text("not json")
        result = fetch_content(
            repo_root=self._repo_root,
            drift_report_path=p,
            github_token="test-token",
        )
        self.assertEqual(result.status, STATUS_FAIL)

    def test_path_traversal_in_drifted_entry_returns_error(self) -> None:
        entry = _drifted_entry(path="../evil/attack.md")
        p = self._write_drift_report([entry])
        result = fetch_content(
            repo_root=self._repo_root,
            drift_report_path=p,
            github_token="test-token",
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)


# ---------------------------------------------------------------------------
# run_cli tests
# ---------------------------------------------------------------------------


class FetchContentRunCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)

    def test_no_approval_returns_error(self) -> None:
        report = self._repo_root / "drift-report.json"
        report.write_text(json.dumps(_drift_report()))
        out = StringIO()
        with patch.dict(os.environ, {"GITHUB_APP_TOKEN": "tok"}):
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
        with patch.dict(os.environ, {"GITHUB_APP_TOKEN": "tok"}):
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
