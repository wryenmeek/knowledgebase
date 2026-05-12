"""Unit tests for scripts/drive_monitor/_registry.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.drive_monitor import _registry as registry_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(
    alias: str = "my-docs",
    changes_page_token: str | None = "tok_old",
    file_entries: list[dict] | None = None,
) -> dict:
    return {
        "version": "1",
        "alias": alias,
        "credential_secret_name": "GDRIVE_SA_KEY",
        "changes_page_token": changes_page_token,
        "last_full_scan_at": None,
        "folder_entries": [
            {
                "folder_id": "FOLDER1",
                "folder_name": "Test Folder",
                "wiki_namespace": "cms/",
                "tracking_status": "active",
            }
        ],
        "file_entries": file_entries or [],
    }


def _write_registry(tmp_path: Path, registry: dict) -> Path:
    drive_dir = tmp_path / "raw" / "drive-sources"
    drive_dir.mkdir(parents=True, exist_ok=True)
    p = drive_dir / f"{registry['alias']}.source-registry.json"
    p.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    # Required for looks_like_repo_root() and lock path
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "wiki").mkdir(exist_ok=True)
    return p


def _make_file_entry(
    file_id: str = "FILE_ABC",
    tracking_status: str = "active",
    **overrides: object,
) -> dict:
    entry: dict = {
        "file_id": file_id,
        "display_name": "Test Doc",
        "display_path": "Test Folder/Test Doc",
        "mime_type": "application/vnd.google-apps.document",
        "tracking_status": tracking_status,
        "wiki_page": "wiki/cms/test-doc.md",
        "drive_version": None,
        "last_applied_drive_version": None,
        "last_applied_at": None,
        "sha256_at_last_applied": None,
        "last_fetched_drive_version": None,
        "last_fetched_at": None,
        "sha256_at_last_fetched": None,
        "md5_checksum_at_last_applied": None,
        "md5_checksum_at_last_fetched": None,
        "notes": "",
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# Atomic replace tests
# ---------------------------------------------------------------------------


class TestAtomicReplace:
    """_atomic_replace_registry writes atomically — failure leaves old file intact."""

    def test_successful_replace(self, tmp_path):
        reg = _make_registry()
        reg_path = _write_registry(tmp_path, reg)
        original_content = reg_path.read_text(encoding="utf-8")

        # Modify and replace
        reg["changes_page_token"] = "tok_new"
        registry_mod._atomic_replace_registry(reg_path, reg)

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        assert updated["changes_page_token"] == "tok_new"

    def test_failed_replace_preserves_original(self, tmp_path, monkeypatch):
        """If os.replace fails, the original file must survive."""
        reg = _make_registry()
        reg_path = _write_registry(tmp_path, reg)
        original = json.loads(reg_path.read_text(encoding="utf-8"))

        import os as _os

        real_replace = _os.replace

        def failing_replace(src, dst):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(_os, "replace", failing_replace)

        with pytest.raises(OSError, match="simulated disk failure"):
            registry_mod._atomic_replace_registry(reg_path, {"broken": True})

        # Original file must be unchanged
        preserved = json.loads(reg_path.read_text(encoding="utf-8"))
        assert preserved == original


# ---------------------------------------------------------------------------
# Cursor persistence tests
# ---------------------------------------------------------------------------


class TestUpdateChangesCursor:
    """update_changes_cursor() round-trip: write → read → verify."""

    def test_cursor_round_trip(self, tmp_path):
        reg = _make_registry(changes_page_token="tok_old")
        reg_path = _write_registry(tmp_path, reg)

        registry_mod.update_changes_cursor(tmp_path, reg_path, "tok_brand_new")

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        assert updated["changes_page_token"] == "tok_brand_new"

    def test_cursor_update_preserves_other_fields(self, tmp_path):
        entry = _make_file_entry(file_id="FILE_1")
        reg = _make_registry(file_entries=[entry])
        reg_path = _write_registry(tmp_path, reg)

        registry_mod.update_changes_cursor(tmp_path, reg_path, "tok_updated")

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        assert updated["changes_page_token"] == "tok_updated"
        assert updated["alias"] == "my-docs"
        assert len(updated["file_entries"]) == 1
        assert updated["file_entries"][0]["file_id"] == "FILE_1"


# ---------------------------------------------------------------------------
# update_last_fetched tests
# ---------------------------------------------------------------------------


class TestUpdateLastFetched:
    """update_last_fetched() advances fetched fields without touching applied."""

    def test_updates_fetched_fields(self, tmp_path):
        entry = _make_file_entry(file_id="FILE_A")
        reg = _make_registry(file_entries=[entry])
        reg_path = _write_registry(tmp_path, reg)

        result = registry_mod.update_last_fetched(
            tmp_path,
            reg_path,
            "FILE_A",
            drive_version=42,
            sha256="a" * 64,
        )
        assert result is True

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        e = updated["file_entries"][0]
        assert e["last_fetched_drive_version"] == 42
        assert e["sha256_at_last_fetched"] == "a" * 64
        assert e["last_fetched_at"] is not None
        # Applied fields must be untouched
        assert e["last_applied_drive_version"] is None

    def test_returns_false_for_unknown_file_id(self, tmp_path):
        reg = _make_registry(file_entries=[_make_file_entry(file_id="FILE_X")])
        reg_path = _write_registry(tmp_path, reg)

        result = registry_mod.update_last_fetched(
            tmp_path, reg_path, "NONEXISTENT"
        )
        assert result is False


# ---------------------------------------------------------------------------
# update_last_applied tests (state machine transition)
# ---------------------------------------------------------------------------


class TestUpdateLastApplied:
    """update_last_applied() advances applied fields and resets fetched."""

    def test_applied_resets_fetched_fields(self, tmp_path):
        entry = _make_file_entry(
            file_id="FILE_B",
            last_fetched_drive_version=10,
            sha256_at_last_fetched="b" * 64,
            last_fetched_at="2024-01-01T00:00:00+00:00",
        )
        reg = _make_registry(file_entries=[entry])
        reg_path = _write_registry(tmp_path, reg)

        result = registry_mod.update_last_applied(
            tmp_path,
            reg_path,
            "FILE_B",
            drive_version=10,
            sha256="b" * 64,
        )
        assert result is True

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        e = updated["file_entries"][0]
        assert e["last_applied_drive_version"] == 10
        assert e["sha256_at_last_applied"] == "b" * 64
        assert e["last_applied_at"] is not None
        assert e["drive_version"] == 10
        # Fetched fields must be reset to None
        assert e["last_fetched_drive_version"] is None
        assert e["sha256_at_last_fetched"] is None
        assert e["last_fetched_at"] is None


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------


class TestAddFileEntryDedup:
    """add_file_entry() skips duplicates — same file_id is not added twice."""

    def test_duplicate_file_id_not_added(self, tmp_path):
        entry = _make_file_entry(file_id="EXISTING_FILE")
        reg = _make_registry(file_entries=[entry])
        reg_path = _write_registry(tmp_path, reg)

        registry_mod.add_file_entry(
            tmp_path,
            reg_path,
            "EXISTING_FILE",
            display_name="Dup Doc",
            display_path="Folder/Dup Doc",
            mime_type="application/vnd.google-apps.document",
            wiki_namespace="cms/",
        )

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        assert len(updated["file_entries"]) == 1

    def test_new_file_id_is_added(self, tmp_path):
        reg = _make_registry(file_entries=[])
        reg_path = _write_registry(tmp_path, reg)

        registry_mod.add_file_entry(
            tmp_path,
            reg_path,
            "BRAND_NEW_FILE",
            display_name="New Doc",
            display_path="Folder/New Doc",
            mime_type="application/vnd.google-apps.document",
            wiki_namespace="cms/",
        )

        updated = json.loads(reg_path.read_text(encoding="utf-8"))
        assert len(updated["file_entries"]) == 1
        assert updated["file_entries"][0]["file_id"] == "BRAND_NEW_FILE"
        assert updated["file_entries"][0]["tracking_status"] == "uninitialized"
        assert updated["file_entries"][0]["wiki_page"] == "wiki/cms/new-doc.md"


# ---------------------------------------------------------------------------
# Lock semantics tests
# ---------------------------------------------------------------------------


class TestRegistryLockSemantics:
    """Registry mutations require the advisory lock."""

    def test_lock_file_created_during_update(self, tmp_path):
        reg = _make_registry()
        reg_path = _write_registry(tmp_path, reg)

        registry_mod.update_changes_cursor(tmp_path, reg_path, "tok_lock_test")

        lock_path = tmp_path / "raw" / ".drive-sources.lock"
        # Lock file should have been created (though released after context)
        assert lock_path.exists()

    def test_find_registry_files(self, tmp_path):
        reg1 = _make_registry(alias="alpha")
        reg2 = _make_registry(alias="bravo")
        _write_registry(tmp_path, reg1)
        _write_registry(tmp_path, reg2)

        found = registry_mod.find_registry_files(tmp_path)
        aliases = [json.loads(p.read_text())["alias"] for p in found]
        assert "alpha" in aliases
        assert "bravo" in aliases

    def test_find_registry_by_alias(self, tmp_path):
        reg = _make_registry(alias="target")
        _write_registry(tmp_path, reg)

        result = registry_mod.find_registry_by_alias(tmp_path, "target")
        assert result is not None
        assert result.name == "target.source-registry.json"

        assert registry_mod.find_registry_by_alias(tmp_path, "nonexistent") is None
