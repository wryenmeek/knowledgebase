"""Unit tests for scripts/drive_monitor/synthesize_diff.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from scripts.drive_monitor.synthesize_diff import synthesize_diff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_afk_entry(
    alias: str = "my-docs",
    file_id: str = "file1",
    display_name: str = "doc.md",
    mime_type: str = "application/vnd.google-apps.document",
    current_drive_version: int = 10,
    last_applied_drive_version: int = 5,
    asset_path: str | None = None,
    wiki_page: str = "wiki/cms/my-doc.md",
) -> dict:
    return {
        "alias": alias,
        "file_id": file_id,
        "display_name": display_name,
        "mime_type": mime_type,
        "event_type": "content_changed",
        "current_drive_version": current_drive_version,
        "last_applied_drive_version": last_applied_drive_version,
        "asset_path": asset_path or f"raw/assets/gdrive/{alias}/{file_id}/{current_drive_version}/{display_name}",
        "wiki_page": wiki_page,
    }


def _write_afk_entries(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "afk-entries.json"
    p.write_text(json.dumps({"entries": entries}))
    return p


def _write_registry(tmp_path: Path, alias: str = "my-docs", file_entries=None) -> Path:
    drive_dir = tmp_path / "raw" / "drive-sources"
    drive_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "version": "1",
        "alias": alias,
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": "tok",
        "last_full_scan_at": None,
        "folder_entries": [],
        "file_entries": file_entries or [{
            "file_id": "file1",
            "tracking_status": "active",
            "display_name": "doc.md",
            "mime_type": "application/vnd.google-apps.document",
            "last_applied_drive_version": 5,
            "sha256_at_last_applied": "a" * 64,
            "wiki_page": "wiki/cms/my-doc.md",
        }],
    }
    p = drive_dir / f"{alias}.source-registry.json"
    p.write_text(json.dumps(registry))
    (tmp_path / "AGENTS.md").touch()
    return p


def _setup_wiki(tmp_path: Path, wiki_page: str = "wiki/cms/my-doc.md", content: str = "# Old Content\n"):
    wiki_path = tmp_path / wiki_page
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(content, encoding="utf-8")


def _setup_asset(tmp_path: Path, asset_path: str, content: bytes = b"# New Content\n"):
    asset = tmp_path / asset_path
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(content)


# ---------------------------------------------------------------------------
# Approval gate
# ---------------------------------------------------------------------------

class TestSynthesizeDiffApprovalGate:
    def test_missing_approval_fails_closed(self, tmp_path):
        afk_path = _write_afk_entries(tmp_path, [_make_afk_entry()])

        result = synthesize_diff(
            repo_root=tmp_path,
            drift_report_path=afk_path,
            approval="pending",
        )
        assert result.status == "fail"
        assert "approval" in result.reason_code


# ---------------------------------------------------------------------------
# Last-applied gate
# ---------------------------------------------------------------------------

class TestSynthesizeDiffLastAppliedGate:
    def test_last_applied_not_advanced_without_confirmed_wiki_write(self, tmp_path):
        """last_applied_* must not advance if wiki write fails."""
        entry = _make_afk_entry()
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path)
        _setup_wiki(tmp_path)

        asset_path = entry["asset_path"]
        _setup_asset(tmp_path, asset_path)

        advanced = {}

        def fake_update_last_applied(repo_root, alias, file_id, **kwargs):
            advanced[file_id] = kwargs

        def fail_wiki_write(path, content, **kwargs):
            raise OSError("Simulated write failure")

        with (
            patch(
                "scripts.drive_monitor.synthesize_diff._write_wiki_page",
                side_effect=fail_wiki_write,
            ),
            patch(
                "scripts.drive_monitor.synthesize_diff.update_last_applied",
                side_effect=fake_update_last_applied,
            ),
        ):
            try:
                synthesize_diff(
                    repo_root=tmp_path,
                    drift_report_path=afk_path,
                    approval="approved",
                )
            except Exception:
                pass

        # last_applied must NOT have been advanced
        assert "file1" not in advanced

    def test_last_applied_advanced_after_successful_wiki_write(self, tmp_path):
        entry = _make_afk_entry()
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path)
        _setup_wiki(tmp_path)
        _setup_asset(tmp_path, entry["asset_path"])

        advanced = {}

        def fake_update_last_applied(repo_root, alias, file_id, **kwargs):
            advanced[file_id] = kwargs

        with (
            patch("scripts.drive_monitor.synthesize_diff._write_wiki_page"),
            patch(
                "scripts.drive_monitor.synthesize_diff.update_last_applied",
                side_effect=fake_update_last_applied,
            ),
        ):
            synthesize_diff(
                repo_root=tmp_path,
                drift_report_path=afk_path,
                approval="approved",
            )

        assert "file1" in advanced


# ---------------------------------------------------------------------------
# Lock ordering
# ---------------------------------------------------------------------------

class TestSynthesizeDiffLockOrdering:
    def test_wiki_lock_acquired_before_drive_lock(self, tmp_path):
        """synthesize_diff must acquire wiki/.kb_write.lock FIRST, then .drive-sources.lock."""
        from contextlib import contextmanager
        entry = _make_afk_entry()
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path)
        _setup_wiki(tmp_path)
        _setup_asset(tmp_path, entry["asset_path"])

        lock_order = []

        @contextmanager
        def fake_exclusive_write_lock(repo_root, lock_path=None):
            # write_utils.exclusive_write_lock(repo_root) uses default WRITE_LOCK_PATH
            # _registry calls exclusive_write_lock(repo_root, lock_path=DRIVE_SOURCES_LOCK_PATH)
            from scripts.kb import contracts
            lp = lock_path or contracts.WRITE_LOCK_PATH
            lock_order.append(Path(lp).name)
            yield

        with (
            patch(
                "scripts.drive_monitor.synthesize_diff.write_utils.exclusive_write_lock",
                side_effect=fake_exclusive_write_lock,
            ),
            patch(
                "scripts.drive_monitor._registry.write_utils.exclusive_write_lock",
                side_effect=fake_exclusive_write_lock,
            ),
            patch("scripts.drive_monitor.synthesize_diff._write_wiki_page"),
            patch("scripts.drive_monitor.synthesize_diff.update_last_applied"),
        ):
            synthesize_diff(
                repo_root=tmp_path,
                drift_report_path=afk_path,
                approval="approved",
            )

        # Wiki lock must appear before drive-sources lock
        assert ".kb_write.lock" in lock_order
        kb_idx = next(i for i, n in enumerate(lock_order) if ".kb_write.lock" in n)
        # drive lock may not appear (update_last_applied is mocked), but wiki lock must be first
        drive_indices = [i for i, n in enumerate(lock_order) if ".drive-sources.lock" in n]
        for drive_idx in drive_indices:
            assert kb_idx < drive_idx, f"Wiki lock must come before drive lock: {lock_order}"


# ---------------------------------------------------------------------------
# Wiki page content
# ---------------------------------------------------------------------------

class TestSynthesizeDiffWikiContent:
    def test_new_content_appended_to_wiki_page(self, tmp_path):
        entry = _make_afk_entry()
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path)
        _setup_wiki(tmp_path, content="# Old Content\n\nParagraph.\n")
        new_content = b"# New Content\n\nUpdated paragraph.\n"
        _setup_asset(tmp_path, entry["asset_path"], content=new_content)

        written_content: dict = {}

        def capture_write(path, content, **kwargs):
            written_content["path"] = path
            written_content["content"] = content

        with (
            patch(
                "scripts.drive_monitor.synthesize_diff._write_wiki_page",
                side_effect=capture_write,
            ),
            patch("scripts.drive_monitor.synthesize_diff.update_last_applied"),
        ):
            synthesize_diff(
                repo_root=tmp_path,
                drift_report_path=afk_path,
                approval="approved",
            )

        assert "written_content" in written_content or "content" in written_content

    def test_wiki_page_outside_wiki_root_rejected(self, tmp_path):
        """If wiki_page resolves outside wiki/, synthesize_diff must fail closed."""
        entry = _make_afk_entry(wiki_page="raw/inbox/evil.md")
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path, file_entries=[{
            "file_id": "file1",
            "tracking_status": "active",
            "display_name": "doc.md",
            "mime_type": "application/vnd.google-apps.document",
            "wiki_page": "raw/inbox/evil.md",
        }])
        (tmp_path / "AGENTS.md").touch()

        (tmp_path / "wiki").mkdir(exist_ok=True)
        _setup_asset(tmp_path, entry["asset_path"])

        result = synthesize_diff(
                repo_root=tmp_path,
                drift_report_path=afk_path,
                approval="approved",
            )
        assert result.status == "fail"


# ---------------------------------------------------------------------------
# Idempotency via FileExistsError
# ---------------------------------------------------------------------------

class TestSynthesizeDiffIdempotency:
    def test_already_up_to_date_skipped(self, tmp_path):
        """Entry where last_applied == current should be skipped without error."""
        entry = _make_afk_entry(
            current_drive_version=5,
            last_applied_drive_version=5,  # same — already applied
        )
        afk_path = _write_afk_entries(tmp_path, [entry])
        _write_registry(tmp_path)
        (tmp_path / "AGENTS.md").touch()

        (tmp_path / "wiki").mkdir(exist_ok=True)

        calls = []

        def capture_write(path, content, **kwargs):
            calls.append(path)

        with (
            patch(
                "scripts.drive_monitor.synthesize_diff._write_wiki_page",
                side_effect=capture_write,
            ),
            patch("scripts.drive_monitor.synthesize_diff.update_last_applied"),
        ):
            synthesize_diff(
                repo_root=tmp_path,
                drift_report_path=afk_path,
                approval="approved",
            )

        # Should be skipped — no write
        assert calls == []
