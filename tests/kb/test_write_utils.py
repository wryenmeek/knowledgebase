"""Unit tests for write lock and state-change log helpers."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
import subprocess
import sys
import textwrap
from unittest.mock import patch

from scripts.kb import contracts
from scripts.kb import write_utils
from scripts.kb.write_utils import check_no_symlink_path
from tests.kb.harnesses import RuntimeWorkspaceTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]


class WriteUtilitiesTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        (self.workspace_root / "wiki").mkdir(parents=True, exist_ok=True)

    def _probe_lock_attempt(self) -> dict[str, object]:
        probe_script = textwrap.dedent(
            """
            import json
            import sys
            from scripts.kb.write_utils import LockUnavailableError, exclusive_write_lock

            repo_root = sys.argv[1]
            try:
                with exclusive_write_lock(repo_root):
                    print(json.dumps({"acquired": True}))
            except LockUnavailableError as exc:
                print(
                    json.dumps(
                        {
                            "acquired": False,
                            "reason_code": exc.reason_code,
                            "failure_reason": exc.failure_reason,
                        }
                    )
                )
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", probe_script, str(self.workspace_root)],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        )

        return json.loads(completed.stdout.strip().splitlines()[-1])

    def test_lock_unavailable_reason_returns_deterministic_string(self) -> None:
        # Default path
        self.assertEqual(
            write_utils.lock_unavailable_reason(),
            f"{contracts.ReasonCode.LOCK_UNAVAILABLE.value}:{contracts.WRITE_LOCK_PATH}",
        )
        # Custom path
        custom_path = "custom/lock.path"
        self.assertEqual(
            write_utils.lock_unavailable_reason(custom_path),
            f"{contracts.ReasonCode.LOCK_UNAVAILABLE.value}:{custom_path}",
        )

    def test_exclusive_write_lock_uses_spec_lock_path(self) -> None:
        with write_utils.exclusive_write_lock(self.workspace_root) as lock_path:
            self.assertEqual(lock_path, self.workspace_root / contracts.WRITE_LOCK_PATH)
            self.assertTrue(lock_path.exists())

    def test_exclusive_write_lock_treats_preexisting_unlocked_file_as_stale(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("stale\n", encoding="utf-8")

        with write_utils.exclusive_write_lock(self.workspace_root) as acquired_path:
            self.assertEqual(acquired_path, lock_path)

    def test_exclusive_write_lock_contention_returns_lock_unavailable_reason(self) -> None:
        with write_utils.exclusive_write_lock(self.workspace_root):
            probe_result = self._probe_lock_attempt()

        self.assertFalse(probe_result["acquired"])
        self.assertEqual(
            probe_result["reason_code"],
            contracts.ReasonCode.LOCK_UNAVAILABLE.value,
        )
        self.assertEqual(
            probe_result["failure_reason"],
            write_utils.lock_unavailable_reason(),
        )

    def test_governed_artifact_helpers_report_append_only_log_contract(self) -> None:
        contract = write_utils.governed_artifact_contract_for_path("wiki/log.md")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertTrue(write_utils.governed_artifact_requires_lock("wiki/log.md"))
        self.assertFalse(write_utils.governed_artifact_requires_atomic_replace("wiki/log.md"))
        self.assertEqual(
            contract.write_strategy,
            contracts.ArtifactWriteStrategy.APPEND_UNDER_LOCK.value,
        )

    def test_governed_artifact_helpers_report_atomic_replace_contracts(self) -> None:
        contract = write_utils.governed_artifact_contract_for_path("wiki/open-questions.md")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertTrue(write_utils.governed_artifact_requires_lock("wiki/open-questions.md"))
        self.assertTrue(
            write_utils.governed_artifact_requires_atomic_replace("wiki/open-questions.md")
        )
        self.assertEqual(
            contract.mutability,
            contracts.ArtifactMutability.MUTABLE.value,
        )

    def test_governed_artifact_helpers_return_none_for_non_governed_paths(self) -> None:
        self.assertIsNone(write_utils.governed_artifact_contract_for_path("wiki/entities/example.md"))
        self.assertFalse(write_utils.governed_artifact_requires_lock("wiki/entities/example.md"))
        self.assertFalse(
            write_utils.governed_artifact_requires_atomic_replace("wiki/entities/example.md")
        )

    def test_governed_artifact_helpers_reject_invalid_paths(self) -> None:
        for invalid_path in ("/wiki/log.md", "//wiki/log.md", "../wiki/log.md", "./wiki/log.md"):
            with self.subTest(path=invalid_path):
                self.assertIsNone(write_utils.governed_artifact_contract_for_path(invalid_path))
                self.assertFalse(write_utils.governed_artifact_requires_lock(invalid_path))
                self.assertFalse(
                    write_utils.governed_artifact_requires_atomic_replace(invalid_path)
                )

    def test_append_log_only_state_changes_appends_when_state_changes(self) -> None:
        log_path = self.workspace_root / "wiki" / "log.md"
        log_path.write_text("existing entry\n", encoding="utf-8")

        appended = write_utils.append_log_only_state_changes(
            self.workspace_root,
            "- state changed",
            state_changed=True,
        )

        self.assertTrue(appended)
        self.assertEqual(
            log_path.read_text(encoding="utf-8"),
            "existing entry\n- state changed\n",
        )

    def test_append_log_only_state_changes_is_noop_when_state_unchanged(self) -> None:
        log_path = self.workspace_root / "wiki" / "log.md"
        initial_content = "existing entry\n"
        log_path.write_text(initial_content, encoding="utf-8")

        appended = write_utils.append_log_only_state_changes(
            self.workspace_root,
            "- should not append",
            state_changed=False,
        )

        self.assertFalse(appended)
        self.assertEqual(log_path.read_text(encoding="utf-8"), initial_content)

    def test_append_log_only_state_changes_noop_does_not_create_log_file(self) -> None:
        log_path = self.workspace_root / "wiki" / "log.md"
        self.assertFalse(log_path.exists())

        appended = write_utils.append_log_only_state_changes(
            self.workspace_root,
            "- should not append",
            state_changed=False,
        )

        self.assertFalse(appended)
        self.assertFalse(log_path.exists())

    def test_atomic_replace_governed_artifact_rewrites_supported_snapshot(self) -> None:
        target_path = self.workspace_root / "wiki" / "status.md"
        target_path.write_text("before\n", encoding="utf-8")

        written_path = write_utils.atomic_replace_governed_artifact(
            self.workspace_root,
            "wiki/status.md",
            "after\n",
        )

        self.assertEqual(written_path, target_path)
        self.assertEqual(target_path.read_text(encoding="utf-8"), "after\n")
        self.assertFalse((self.workspace_root / "wiki" / ".status.md.kbtmp").exists())

    def test_atomic_replace_governed_artifact_rejects_unsupported_or_append_only_paths(self) -> None:
        for path in ("wiki/entities/example.md", "wiki/log.md"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    write_utils.atomic_replace_governed_artifact(
                        self.workspace_root,
                        path,
                        "content\n",
                    )

    def test_atomic_replace_governed_artifact_cleans_up_temp_file_on_failure(self) -> None:
        target_path = self.workspace_root / "wiki" / "status.md"
        target_path.write_text("before\n", encoding="utf-8")

        with patch.object(write_utils.os, "replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                write_utils.atomic_replace_governed_artifact(
                    self.workspace_root,
                    "wiki/status.md",
                    "after\n",
                )

        self.assertEqual(target_path.read_text(encoding="utf-8"), "before\n")
        self.assertFalse((self.workspace_root / "wiki" / ".status.md.kbtmp").exists())

    def test_atomic_replace_governed_artifact_recovers_from_stale_temp_file(self) -> None:
        target_path = self.workspace_root / "wiki" / "status.md"
        temp_path = self.workspace_root / "wiki" / ".status.md.kbtmp"
        target_path.write_text("before\n", encoding="utf-8")
        temp_path.write_text("stale\n", encoding="utf-8")

        written_path = write_utils.atomic_replace_governed_artifact(
            self.workspace_root,
            "wiki/status.md",
            "after\n",
        )

        self.assertEqual(written_path, target_path)
        self.assertEqual(target_path.read_text(encoding="utf-8"), "after\n")
        self.assertFalse(temp_path.exists())


class CheckNoSymlinkPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # Resolve to canonical path; on macOS /var is a symlink to /private/var
        self.tmp_path = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plain_file_passes(self) -> None:
        target = self.tmp_path / "file.txt"
        target.write_text("hello", encoding="utf-8")
        check_no_symlink_path(target)  # no exception

    def test_plain_directory_passes(self) -> None:
        subdir = self.tmp_path / "sub"
        subdir.mkdir()
        check_no_symlink_path(subdir)  # no exception

    def test_symlink_raises(self) -> None:
        target = self.tmp_path / "real.txt"
        target.write_text("data", encoding="utf-8")
        link = self.tmp_path / "link.txt"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            check_no_symlink_path(link)

    def test_symlinked_parent_raises(self) -> None:
        real_dir = self.tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = self.tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)
        child = link_dir / "file.txt"
        with self.assertRaises(OSError):
            check_no_symlink_path(child)

    def test_is_in_public_api(self) -> None:
        self.assertIn("check_no_symlink_path", write_utils.__all__)


class ExclusiveCreateWriteOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_creates_new_file_in_new_parent_dirs(self) -> None:
        target = self.tmp_path / "a" / "b" / "c.bin"
        write_utils.exclusive_create_write_once(target, b"hello")
        self.assertEqual(target.read_bytes(), b"hello")

    def test_idempotent_same_bytes(self) -> None:
        target = self.tmp_path / "asset.bin"
        write_utils.exclusive_create_write_once(target, b"data")
        write_utils.exclusive_create_write_once(target, b"data")  # second call: no-op
        self.assertEqual(target.read_bytes(), b"data")

    def test_raises_on_byte_mismatch(self) -> None:
        target = self.tmp_path / "asset.bin"
        write_utils.exclusive_create_write_once(target, b"original")
        with self.assertRaises(OSError):
            write_utils.exclusive_create_write_once(target, b"different")

    def test_raises_on_symlink_path(self) -> None:
        real = self.tmp_path / "real.bin"
        real.write_bytes(b"content")
        link = self.tmp_path / "link.bin"
        link.symlink_to(real)
        with self.assertRaises(OSError):
            write_utils.exclusive_create_write_once(link, b"content")

    def test_no_temp_file_remains_on_success(self) -> None:
        target = self.tmp_path / "asset.bin"
        write_utils.exclusive_create_write_once(target, b"hello")
        # Only the target file should exist; no .asset.bin.* temp files.
        files = list(self.tmp_path.iterdir())
        self.assertEqual([target], files)

    def test_is_in_public_api(self) -> None:
        self.assertIn("exclusive_create_write_once", write_utils.__all__)


if __name__ == "__main__":
    unittest.main()
