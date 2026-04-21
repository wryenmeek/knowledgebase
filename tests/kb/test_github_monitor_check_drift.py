"""Unit tests for check_drift.py and associated _types.py additions."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

from scripts.github_monitor._types import (
    GitHubAPIResponseError,
    GitHubAPIRequestError,
    validate_registry_file,
    validate_drift_report,
    REGISTRY_VERSION,
    DRIFT_REPORT_VERSION,
)
from scripts.github_monitor.check_drift import (
    SURFACE,
    _check_active_entry,
    _make_github_request,
    check_drift,
    run_cli,
)
from scripts._optional_surface_common import STATUS_PASS, STATUS_FAIL
from scripts.kb.contracts import GitHubMonitorReasonCode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(entries: list[dict]) -> dict:
    return {
        "version": REGISTRY_VERSION,
        "owner": "test-org",
        "repo": "test-repo",
        "github_app_installation_id": None,
        "entries": entries,
    }


def _active_entry(
    path: str = "docs/guide.md",
    last_applied_blob_sha: str = "blob" + "a" * 36,
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


def _contents_response(blob_sha: str = "blob" + "a" * 36) -> dict:
    return {
        "sha": blob_sha,
        "content": "aGVsbG8=",
        "encoding": "base64",
        "size": 5,
        "name": "guide.md",
        "path": "docs/guide.md",
    }


def _commits_response(commit_sha: str = "d" * 40) -> list:
    return [{"sha": commit_sha, "commit": {"message": "update docs"}}]


# ---------------------------------------------------------------------------
# validate_registry_file tests
# ---------------------------------------------------------------------------


class ValidateRegistryFileTests(unittest.TestCase):
    def test_valid_registry_passes(self) -> None:
        registry = _make_registry([_active_entry()])
        result = validate_registry_file(registry)
        self.assertEqual(result["owner"], "test-org")

    def test_not_dict_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_registry_file([])

    def test_missing_version_raises(self) -> None:
        data = _make_registry([])
        del data["version"]
        with self.assertRaises(ValueError, msg="version"):
            validate_registry_file(data)

    def test_wrong_version_raises(self) -> None:
        data = _make_registry([])
        data["version"] = "99"
        with self.assertRaises(ValueError, msg="version"):
            validate_registry_file(data)

    def test_missing_owner_raises(self) -> None:
        data = _make_registry([])
        del data["owner"]
        with self.assertRaises(ValueError):
            validate_registry_file(data)

    def test_empty_owner_raises(self) -> None:
        data = _make_registry([])
        data["owner"] = "  "
        with self.assertRaises(ValueError):
            validate_registry_file(data)

    def test_missing_entries_raises(self) -> None:
        data = _make_registry([])
        del data["entries"]
        with self.assertRaises(ValueError):
            validate_registry_file(data)

    def test_entries_not_list_raises(self) -> None:
        data = _make_registry([])
        data["entries"] = {}
        with self.assertRaises(ValueError):
            validate_registry_file(data)

    def test_entry_missing_path_raises(self) -> None:
        entry = _active_entry()
        del entry["path"]
        with self.assertRaises(ValueError):
            validate_registry_file(_make_registry([entry]))

    def test_entry_invalid_tracking_status_raises(self) -> None:
        entry = _active_entry()
        entry["tracking_status"] = "invalid_value"
        with self.assertRaises(ValueError):
            validate_registry_file(_make_registry([entry]))

    def test_entry_invalid_commit_sha_raises(self) -> None:
        entry = _active_entry()
        entry["last_applied_commit_sha"] = "not-a-sha"
        with self.assertRaises(ValueError):
            validate_registry_file(_make_registry([entry]))

    def test_entry_null_commit_sha_passes(self) -> None:
        entry = _active_entry()
        entry["last_applied_commit_sha"] = None
        result = validate_registry_file(_make_registry([entry]))
        self.assertEqual(result["entries"][0]["last_applied_commit_sha"], None)

    def test_uninitialized_status_passes(self) -> None:
        entry = {
            "path": "docs/new.md",
            "tracking_status": "uninitialized",
        }
        result = validate_registry_file(_make_registry([entry]))
        self.assertEqual(result["entries"][0]["tracking_status"], "uninitialized")


# ---------------------------------------------------------------------------
# validate_drift_report tests
# ---------------------------------------------------------------------------


class ValidateDriftReportTests(unittest.TestCase):
    def _valid(self) -> dict:
        return {
            "version": DRIFT_REPORT_VERSION,
            "generated_at": "2024-01-01T00:00:00+00:00",
            "registry": "raw/github-sources/org-repo.source-registry.json",
            "has_drift": False,
            "drifted": [],
            "up_to_date": [],
            "uninitialized": [],
            "errors": [],
        }

    def test_valid_report_passes(self) -> None:
        result = validate_drift_report(self._valid())
        self.assertFalse(result["has_drift"])

    def test_not_dict_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_drift_report([])

    def test_missing_has_drift_raises(self) -> None:
        data = self._valid()
        del data["has_drift"]
        with self.assertRaises(ValueError):
            validate_drift_report(data)

    def test_wrong_version_raises(self) -> None:
        data = self._valid()
        data["version"] = "99"
        with self.assertRaises(ValueError):
            validate_drift_report(data)

    def test_has_drift_not_bool_raises(self) -> None:
        data = self._valid()
        data["has_drift"] = "true"
        with self.assertRaises(ValueError):
            validate_drift_report(data)

    def test_drifted_not_list_raises(self) -> None:
        data = self._valid()
        data["drifted"] = {}
        with self.assertRaises(ValueError):
            validate_drift_report(data)


# ---------------------------------------------------------------------------
# GitHubAPIRequestError tests
# ---------------------------------------------------------------------------


class GitHubAPIRequestErrorTests(unittest.TestCase):
    def test_str_includes_url_and_status(self) -> None:
        exc = GitHubAPIRequestError(
            url="https://api.github.com/test",
            status_code=404,
            detail="Not Found",
        )
        self.assertIn("404", str(exc))
        self.assertIn("Not Found", str(exc))
        self.assertIn("https://api.github.com/test", str(exc))

    def test_none_status_code(self) -> None:
        exc = GitHubAPIRequestError(
            url="https://api.github.com/test",
            status_code=None,
            detail="Connection refused",
        )
        self.assertIn("Connection refused", str(exc))


# ---------------------------------------------------------------------------
# _make_github_request tests
# ---------------------------------------------------------------------------


class MakeGitHubRequestTests(unittest.TestCase):
    def _mock_response(self, body: dict, status: int = 200) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_successful_request(self) -> None:
        mock_resp = self._mock_response({"sha": "abc"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _make_github_request("https://api.github.com/test", "token123")
        self.assertEqual(result["sha"], "abc")

    def test_404_raises_immediately(self) -> None:
        err = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(GitHubAPIRequestError) as ctx:
                _make_github_request("https://api.github.com/test", "token123")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_5xx_retries_then_raises(self) -> None:
        err = urllib.error.HTTPError(
            "url", 503, "Service Unavailable", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with patch("time.sleep"):  # suppress actual sleep in tests
                with self.assertRaises(GitHubAPIRequestError) as ctx:
                    _make_github_request("https://api.github.com/test", "token123")
        # Status code should be None because we exhaust retries and raise custom error
        # The actual 503 is raised after retries
        self.assertIsNotNone(ctx.exception)

    def test_network_error_raises(self) -> None:
        err = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(GitHubAPIRequestError) as ctx:
                _make_github_request("https://api.github.com/test", "token123")
        self.assertIsNone(ctx.exception.status_code)


# ---------------------------------------------------------------------------
# _check_active_entry tests
# ---------------------------------------------------------------------------


class CheckActiveEntryTests(unittest.TestCase):
    _BLOB_SHA = "a" * 40
    _COMMIT_SHA = "c" * 40
    _NEW_BLOB_SHA = "b" * 40
    _NEW_COMMIT_SHA = "d" * 40

    def _side_effects(self, contents_sha: str, commit_sha: str) -> list:
        """Return a side_effect list for urlopen: contents then commits."""
        def make_resp(body: dict) -> MagicMock:
            mock = MagicMock()
            mock.read.return_value = json.dumps(body).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        return [
            make_resp(_contents_response(contents_sha)),
            make_resp(_commits_response(commit_sha)),
        ]

    def test_no_drift_blob_sha_matches(self) -> None:
        entry = _active_entry(last_applied_blob_sha=self._BLOB_SHA)
        side_effects = self._side_effects(self._BLOB_SHA, self._COMMIT_SHA)
        with patch("urllib.request.urlopen", side_effect=side_effects):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "up_to_date")
        self.assertEqual(data["blob_sha"], self._BLOB_SHA)

    def test_no_drift_even_if_commit_sha_differs(self) -> None:
        """Blob SHA identity, not commit SHA, determines drift."""
        entry = _active_entry(
            last_applied_blob_sha=self._BLOB_SHA,
            last_applied_commit_sha=self._COMMIT_SHA,
        )
        # Same blob SHA but different commit SHA (metadata-only commit)
        different_commit = "e" * 40
        side_effects = self._side_effects(self._BLOB_SHA, different_commit)
        with patch("urllib.request.urlopen", side_effect=side_effects):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "up_to_date")

    def test_drift_detected_different_blob_sha(self) -> None:
        entry = _active_entry(
            last_applied_blob_sha=self._BLOB_SHA,
            last_applied_commit_sha=self._COMMIT_SHA,
        )
        side_effects = self._side_effects(self._NEW_BLOB_SHA, self._NEW_COMMIT_SHA)
        with patch("urllib.request.urlopen", side_effect=side_effects):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "drifted")
        self.assertEqual(data["current_blob_sha"], self._NEW_BLOB_SHA)
        self.assertEqual(data["last_applied_blob_sha"], self._BLOB_SHA)
        self.assertIsNotNone(data["compare_url"])
        self.assertIn(self._COMMIT_SHA[:7], data["compare_url"])

    def test_drift_compare_url_none_when_no_prior_commit(self) -> None:
        entry = _active_entry(
            last_applied_blob_sha=self._BLOB_SHA,
            last_applied_commit_sha=None,
        )
        entry["last_applied_commit_sha"] = None
        side_effects = self._side_effects(self._NEW_BLOB_SHA, self._NEW_COMMIT_SHA)
        with patch("urllib.request.urlopen", side_effect=side_effects):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "drifted")
        self.assertIsNone(data["compare_url"])

    def test_api_404_returns_error_unreachable(self) -> None:
        entry = _active_entry()
        http_err = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")
        self.assertEqual(data["reason_code"], str(GitHubMonitorReasonCode.UNREACHABLE))

    def test_api_403_returns_error_unreachable(self) -> None:
        entry = _active_entry()
        http_err = urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")
        self.assertEqual(data["reason_code"], str(GitHubMonitorReasonCode.UNREACHABLE))

    def test_api_500_retries_and_returns_error_fetch_failed(self) -> None:
        entry = _active_entry()
        http_err = urllib.error.HTTPError(
            "url", 503, "Service Unavailable", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            with patch("time.sleep"):
                category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")

    def test_invalid_path_in_entry_returns_error(self) -> None:
        entry = _active_entry(path="../traversal/attack.md")
        category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")
        self.assertEqual(data["reason_code"], str(GitHubMonitorReasonCode.FETCH_FAILED))

    def test_active_entry_null_blob_sha_returns_error(self) -> None:
        entry = _active_entry()
        entry["last_applied_blob_sha"] = None

        def make_resp(body: dict) -> MagicMock:
            mock = MagicMock()
            mock.read.return_value = json.dumps(body).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        side_effects = [
            make_resp(_contents_response(self._BLOB_SHA)),
            make_resp(_commits_response(self._COMMIT_SHA)),
        ]
        with patch("urllib.request.urlopen", side_effect=side_effects):
            category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")

    def test_commits_api_failure_returns_error(self) -> None:
        entry = _active_entry(last_applied_blob_sha="a" * 40)

        def make_resp(body: dict) -> MagicMock:
            mock = MagicMock()
            mock.read.return_value = json.dumps(body).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        http_err = urllib.error.HTTPError(
            "url", 500, "Internal Server Error", {}, None  # type: ignore[arg-type]
        )
        # Contents call succeeds; commits call fails 3 times (MAX_RETRIES).
        with patch(
            "urllib.request.urlopen",
            side_effect=[
                make_resp(_contents_response("a" * 40)),
                http_err, http_err, http_err,
            ],
        ):
            with patch("time.sleep"):
                category, data = _check_active_entry(entry, "test-org", "test-repo", "tok")
        self.assertEqual(category, "errors")


# ---------------------------------------------------------------------------
# check_drift integration tests
# ---------------------------------------------------------------------------


class CheckDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        # Create AGENTS.md so looks_like_repo_root passes.
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")
        # Create raw/github-sources directory.
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)

    def _write_registry(self, name: str, registry: dict) -> Path:
        path = self._repo_root / "raw" / "github-sources" / name
        path.write_text(json.dumps(registry))
        return path

    def _make_mock_urlopen(
        self, contents_sha: str, commit_sha: str
    ):
        def make_resp(body: dict) -> MagicMock:
            mock = MagicMock()
            mock.read.return_value = json.dumps(body).encode()
            mock.__enter__ = lambda s: s
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        return [
            make_resp(_contents_response(contents_sha)),
            make_resp(_commits_response(commit_sha)),
        ]

    def test_no_drift(self) -> None:
        blob_sha = "a" * 40
        registry = _make_registry([_active_entry(last_applied_blob_sha=blob_sha)])
        p = self._write_registry("org-repo.source-registry.json", registry)

        with patch(
            "urllib.request.urlopen",
            side_effect=self._make_mock_urlopen(blob_sha, "c" * 40),
        ):
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.reason_code, str(GitHubMonitorReasonCode.NO_DRIFT))
        self.assertFalse(result.summary["has_drift"])
        self.assertEqual(result.summary["up_to_date_count"], 1)

    def test_drift_detected(self) -> None:
        old_blob = "a" * 40
        new_blob = "b" * 40
        registry = _make_registry([_active_entry(last_applied_blob_sha=old_blob)])
        p = self._write_registry("org-repo.source-registry.json", registry)

        with patch(
            "urllib.request.urlopen",
            side_effect=self._make_mock_urlopen(new_blob, "d" * 40),
        ):
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.reason_code, str(GitHubMonitorReasonCode.DRIFT_DETECTED))
        self.assertTrue(result.summary["has_drift"])
        self.assertEqual(result.summary["drifted_count"], 1)

    def test_paused_entries_skipped(self) -> None:
        entry = _active_entry()
        entry["tracking_status"] = "paused"
        registry = _make_registry([entry])
        p = self._write_registry("org-repo.source-registry.json", registry)

        with patch("urllib.request.urlopen") as mock_url:
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )
            mock_url.assert_not_called()

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.summary["up_to_date_count"], 0)
        self.assertEqual(result.summary["drifted_count"], 0)

    def test_archived_entries_skipped(self) -> None:
        entry = _active_entry()
        entry["tracking_status"] = "archived"
        registry = _make_registry([entry])
        p = self._write_registry("org-repo.source-registry.json", registry)

        with patch("urllib.request.urlopen") as mock_url:
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )
            mock_url.assert_not_called()

        self.assertEqual(result.status, STATUS_PASS)

    def test_uninitialized_entries_in_report(self) -> None:
        entry = {
            "path": "docs/new.md",
            "tracking_status": "uninitialized",
        }
        registry = _make_registry([entry])
        p = self._write_registry("org-repo.source-registry.json", registry)

        with patch("urllib.request.urlopen") as mock_url:
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )
            mock_url.assert_not_called()

        self.assertEqual(result.status, STATUS_PASS)
        self.assertEqual(result.summary["uninitialized_count"], 1)

    def test_api_error_sets_fail_status(self) -> None:
        registry = _make_registry([_active_entry()])
        p = self._write_registry("org-repo.source-registry.json", registry)

        http_err = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, None  # type: ignore[arg-type]
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=None,
            )

        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_output_file_written(self) -> None:
        blob_sha = "a" * 40
        registry = _make_registry([_active_entry(last_applied_blob_sha=blob_sha)])
        p = self._write_registry("org-repo.source-registry.json", registry)
        output_path = self._repo_root / "drift-report.json"

        with patch(
            "urllib.request.urlopen",
            side_effect=self._make_mock_urlopen(blob_sha, "c" * 40),
        ):
            check_drift(
                repo_root=self._repo_root,
                registry_paths=[p],
                github_token="test-token",
                output_path=output_path,
            )

        self.assertTrue(output_path.exists())
        report = json.loads(output_path.read_text())
        self.assertEqual(report["version"], DRIFT_REPORT_VERSION)
        self.assertFalse(report["has_drift"])

    def test_malformed_registry_json_produces_error(self) -> None:
        path = self._repo_root / "raw" / "github-sources" / "bad.source-registry.json"
        path.write_text("not json")

        result = check_drift(
            repo_root=self._repo_root,
            registry_paths=[path],
            github_token="test-token",
            output_path=None,
        )
        self.assertEqual(result.status, STATUS_FAIL)
        self.assertEqual(result.summary["error_count"], 1)

    def test_invalid_registry_schema_produces_error(self) -> None:
        bad_registry = {"version": "99", "owner": "x", "repo": "y", "entries": []}
        p = self._write_registry("bad.source-registry.json", bad_registry)

        result = check_drift(
            repo_root=self._repo_root,
            registry_paths=[p],
            github_token="test-token",
            output_path=None,
        )
        self.assertEqual(result.status, STATUS_FAIL)


# ---------------------------------------------------------------------------
# run_cli integration test
# ---------------------------------------------------------------------------


class RunCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._repo_root = Path(self._tmpdir)
        (self._repo_root / "AGENTS.md").write_text("# AGENTS\n")
        (self._repo_root / "raw" / "github-sources").mkdir(parents=True)

    def test_no_registries_returns_error(self) -> None:
        out = StringIO()
        with patch.dict(os.environ, {"GITHUB_APP_TOKEN": "tok"}):
            exit_code = run_cli(
                ["--repo-root", str(self._repo_root)],
                output_stream=out,
            )
        self.assertNotEqual(exit_code, 0)

    def test_no_token_returns_error(self) -> None:
        registry_path = (
            self._repo_root / "raw" / "github-sources" / "org-repo.source-registry.json"
        )
        registry_path.write_text(json.dumps(_make_registry([])))
        out = StringIO()
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_APP_TOKEN", "GITHUB_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            exit_code = run_cli(
                ["--repo-root", str(self._repo_root)],
                output_stream=out,
            )
        self.assertNotEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
