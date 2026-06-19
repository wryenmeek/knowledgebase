"""Unit tests for write lock and state-change log helpers."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
import subprocess
import sys
import textwrap
from unittest.mock import patch

from scripts._optional_surface_common import lock_unavailable_result
from scripts.kb import contracts
from scripts.kb import write_utils
from scripts.kb.write_utils import check_no_symlink_path
from tests.kb.harnesses import RuntimeWorkspaceTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]


class WriteUtilitiesTests(RuntimeWorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        (self.workspace_root / "wiki").mkdir(parents=True, exist_ok=True)

    def _probe_lock_attempt(
        self,
        lock_path: str = contracts.WRITE_LOCK_PATH,
    ) -> dict[str, object]:
        probe_script = textwrap.dedent(
            """
            import json
            import sys
            from scripts.kb.write_utils import LockUnavailableError, exclusive_write_lock

            repo_root = sys.argv[1]
            lock_path = sys.argv[2]
            try:
                with exclusive_write_lock(repo_root, lock_path=lock_path):
                    print(json.dumps({"acquired": True}))
            except LockUnavailableError as exc:
                print(
                    json.dumps(
                        {
                            "acquired": False,
                            "reason_code": exc.reason_code,
                            "failure_reason": exc.failure_reason,
                            "holder_pid": exc.holder_pid,
                            "holder_alive": exc.holder_alive,
                            "holder_started_at": exc.holder_started_at,
                            "message": str(exc),
                        }
                    )
                )
            """
        )

        completed = subprocess.run(
            [sys.executable, "-c", probe_script, str(self.workspace_root), lock_path],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        )

        return json.loads(completed.stdout.strip().splitlines()[-1])

    def _race_probe_lock_attempt(self, lock_path: str, gate_dir: Path) -> subprocess.Popen[str]:
        probe_script = textwrap.dedent(
            """
            import json
            import os
            from pathlib import Path
            import sys
            import time
            from scripts.kb.write_utils import LockUnavailableError, exclusive_write_lock

            repo_root = sys.argv[1]
            lock_path = sys.argv[2]
            gate_dir = Path(sys.argv[3])
            ready_path = gate_dir / f"{os.getpid()}.ready"
            go_path = gate_dir / "go.signal"

            ready_path.write_text("ready\\n", encoding="utf-8")
            deadline = time.time() + 10.0
            while not go_path.exists():
                if time.time() > deadline:
                    print(json.dumps({"acquired": False, "lock_path": lock_path, "timeout": True}))
                    raise SystemExit(0)
                time.sleep(0.005)

            try:
                with exclusive_write_lock(repo_root, lock_path=lock_path):
                    time.sleep(0.1)
                    print(json.dumps({"acquired": True, "lock_path": lock_path}))
            except LockUnavailableError as exc:
                print(
                    json.dumps(
                        {
                            "acquired": False,
                            "lock_path": lock_path,
                            "reason_code": exc.reason_code,
                            "failure_reason": exc.failure_reason,
                        }
                    )
                )
            """
        )
        return subprocess.Popen(
            [sys.executable, "-c", probe_script, str(self.workspace_root), lock_path, str(gate_dir)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _collect_probe_process_result(self, process: subprocess.Popen[str]) -> dict[str, object]:
        stdout, stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, msg=stderr)
        self.assertTrue(stdout.strip(), msg=stderr)
        return json.loads(stdout.strip().splitlines()[-1])

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
        self.assertFalse(write_utils.is_write_lock_held(self.workspace_root))
        with write_utils.exclusive_write_lock(self.workspace_root) as lock_path:
            self.assertEqual(lock_path, self.workspace_root / contracts.WRITE_LOCK_PATH)
            self.assertTrue(lock_path.exists())
            self.assertTrue(write_utils.is_write_lock_held(self.workspace_root))
        self.assertFalse(write_utils.is_write_lock_held(self.workspace_root))

    def test_exclusive_write_lock_writes_pid_and_start_time_metadata(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        with write_utils.exclusive_write_lock(self.workspace_root):
            raw = lock_path.read_text(encoding="utf-8").strip()

        pid_text, started_at_text = raw.split("\t", 1)
        self.assertEqual(int(pid_text), os.getpid())
        self.assertGreater(float(started_at_text), 0.0)

    def test_exclusive_write_lock_tracking_survives_nested_same_process_lock(self) -> None:
        with write_utils.exclusive_write_lock(self.workspace_root):
            self.assertTrue(write_utils.is_write_lock_held(self.workspace_root))
            with write_utils.exclusive_write_lock(self.workspace_root):
                self.assertTrue(write_utils.is_write_lock_held(self.workspace_root))
            self.assertTrue(write_utils.is_write_lock_held(self.workspace_root))
        self.assertFalse(write_utils.is_write_lock_held(self.workspace_root))

    def test_exclusive_write_lock_treats_preexisting_unlocked_file_as_stale(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("stale\n", encoding="utf-8")

        with write_utils.exclusive_write_lock(self.workspace_root) as acquired_path:
            self.assertEqual(acquired_path, lock_path)

    def test_governance_sibling_locks_treat_preexisting_unlocked_file_as_stale(self) -> None:
        for lock_path in sorted(contracts.GOVERNANCE_SIBLING_LOCKS):
            with self.subTest(lock_path=lock_path):
                abs_lock_path = self.workspace_root / lock_path
                abs_lock_path.parent.mkdir(parents=True, exist_ok=True)
                abs_lock_path.write_text("stale\n", encoding="utf-8")

                with write_utils.exclusive_write_lock(
                    self.workspace_root,
                    lock_path=lock_path,
                ) as acquired_path:
                    self.assertEqual(acquired_path, abs_lock_path)

    def test_exclusive_write_lock_rejects_symlinked_lock_file(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        target = self.workspace_root / "redirect.lock"
        target.write_text("", encoding="utf-8")
        try:
            os.symlink(target, lock_path)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaises(write_utils.LockUnavailableError):
            with write_utils.exclusive_write_lock(self.workspace_root):
                pass

    def test_exclusive_write_lock_rejects_symlinked_lock_parent(self) -> None:
        wiki_path = self.workspace_root / "wiki"
        wiki_path.rmdir()
        target = self.workspace_root / "redirect-wiki"
        target.mkdir()
        try:
            os.symlink(target, wiki_path)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaises(write_utils.LockUnavailableError):
            with write_utils.exclusive_write_lock(self.workspace_root):
                pass

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

    def test_customizations_lock_fails_when_sibling_governance_lock_is_held(self) -> None:
        for held_lock in sorted(
            contracts.GOVERNANCE_SIBLING_LOCKS - {contracts.CUSTOMIZATIONS_LOCK_PATH}
        ):
            with self.subTest(held_lock=held_lock):
                with write_utils.exclusive_write_lock(self.workspace_root, lock_path=held_lock):
                    probe_result = self._probe_lock_attempt(contracts.CUSTOMIZATIONS_LOCK_PATH)

                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(held_lock),
                )

    def test_sibling_governance_lock_fails_when_customizations_lock_is_held(self) -> None:
        for attempted_lock in sorted(
            contracts.GOVERNANCE_SIBLING_LOCKS - {contracts.CUSTOMIZATIONS_LOCK_PATH}
        ):
            with self.subTest(attempted_lock=attempted_lock):
                with write_utils.exclusive_write_lock(
                    self.workspace_root,
                    lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
                ):
                    probe_result = self._probe_lock_attempt(attempted_lock)

                self.assertFalse(probe_result["acquired"])
                self.assertEqual(
                    probe_result["reason_code"],
                    contracts.ReasonCode.LOCK_UNAVAILABLE.value,
                )
                self.assertEqual(
                    probe_result["failure_reason"],
                    write_utils.lock_unavailable_reason(contracts.CUSTOMIZATIONS_LOCK_PATH),
                )

    def test_governance_lock_uses_meta_lock_even_with_noncanonical_target_path(self) -> None:
        noncanonical_write_lock_path = "wiki/../wiki/.kb_write.lock"
        with write_utils.exclusive_write_lock(
            self.workspace_root,
            lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        ):
            probe_result = self._probe_lock_attempt(noncanonical_write_lock_path)

        self.assertFalse(probe_result["acquired"])
        self.assertEqual(
            probe_result["reason_code"],
            contracts.ReasonCode.LOCK_UNAVAILABLE.value,
        )
        self.assertEqual(
            probe_result["failure_reason"],
            write_utils.lock_unavailable_reason(contracts.CUSTOMIZATIONS_LOCK_PATH),
        )

    def test_governance_sibling_race_allows_exactly_one_winner(self) -> None:
        lock_a = contracts.CUSTOMIZATIONS_LOCK_PATH
        lock_b = contracts.REJECTION_REGISTRY_LOCK_PATH

        with tempfile.TemporaryDirectory(dir=self.workspace_root) as tmp:
            gate_dir = Path(tmp)
            process_a = self._race_probe_lock_attempt(lock_a, gate_dir)
            process_b = self._race_probe_lock_attempt(lock_b, gate_dir)
            try:
                deadline = time.time() + 10.0
                while True:
                    ready_count = len(list(gate_dir.glob("*.ready")))
                    if ready_count >= 2:
                        break
                    if time.time() > deadline:
                        self.fail("timed out waiting for race probe readiness files")
                    time.sleep(0.005)
                (gate_dir / "go.signal").write_text("go\n", encoding="utf-8")
                result_a = self._collect_probe_process_result(process_a)
                result_b = self._collect_probe_process_result(process_b)
            finally:
                if process_a.poll() is None:
                    process_a.kill()
                if process_b.poll() is None:
                    process_b.kill()

        acquired_count = int(bool(result_a["acquired"])) + int(bool(result_b["acquired"]))
        self.assertEqual(acquired_count, 1)

        loser = result_a if not result_a["acquired"] else result_b
        self.assertEqual(
            loser.get("reason_code"),
            contracts.ReasonCode.LOCK_UNAVAILABLE.value,
        )
        self.assertIn(
            loser.get("failure_reason"),
            {
                write_utils.lock_unavailable_reason(lock_a),
                write_utils.lock_unavailable_reason(lock_b),
                write_utils.lock_unavailable_reason(contracts.GOVERNANCE_META_LOCK_PATH),
            },
        )
        # The meta-lock is a persistent sentinel; it must remain on disk.
        self.assertTrue(
            (self.workspace_root / contracts.GOVERNANCE_META_LOCK_PATH).exists()
        )

    def test_meta_lock_file_is_created_when_missing_and_persists(self) -> None:
        meta_lock_path = self.workspace_root / contracts.GOVERNANCE_META_LOCK_PATH
        with contextlib.suppress(FileNotFoundError):
            meta_lock_path.unlink()

        with write_utils.exclusive_write_lock(
            self.workspace_root,
            lock_path=contracts.CUSTOMIZATIONS_LOCK_PATH,
        ):
            self.assertTrue(meta_lock_path.exists())

        self.assertTrue(meta_lock_path.exists())

    def test_write_lock_allows_same_process_nesting_for_monitor_registry_locks(self) -> None:
        with write_utils.exclusive_write_lock(self.workspace_root):
            with write_utils.exclusive_write_lock(
                self.workspace_root,
                lock_path=contracts.GITHUB_SOURCES_LOCK_PATH,
            ):
                self.assertTrue(
                    write_utils.is_write_lock_held(
                        self.workspace_root,
                        lock_path=contracts.GITHUB_SOURCES_LOCK_PATH,
                    )
                )
            with write_utils.exclusive_write_lock(
                self.workspace_root,
                lock_path=contracts.DRIVE_SOURCES_LOCK_PATH,
            ):
                self.assertTrue(
                    write_utils.is_write_lock_held(
                        self.workspace_root,
                        lock_path=contracts.DRIVE_SOURCES_LOCK_PATH,
                    )
                )

    def test_exclusive_write_lock_contention_reports_live_holder_metadata(self) -> None:
        with write_utils.exclusive_write_lock(self.workspace_root):
            probe_result = self._probe_lock_attempt()

        self.assertEqual(probe_result["holder_pid"], os.getpid())
        self.assertTrue(probe_result["holder_alive"])
        self.assertIsInstance(probe_result["holder_started_at"], str)
        self.assertIn("retry shortly", probe_result["message"])

    def test_lock_unavailable_error_reports_dead_holder(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("4242\t1717711294.0\n", encoding="utf-8")

        with patch.object(write_utils.os, "kill", side_effect=ProcessLookupError):
            exc = write_utils.LockUnavailableError(
                contracts.WRITE_LOCK_PATH,
                lock_file_path=lock_path,
            )

        self.assertEqual(exc.holder_pid, 4242)
        self.assertFalse(exc.holder_alive)
        self.assertEqual(exc.holder_started_at, "2024-06-06T22:01:34Z")
        self.assertIn("stale lock from dead PID 4242; safe to remove", str(exc))

    def test_lock_unavailable_error_detects_pid_reuse_via_start_time_mismatch(self) -> None:
        lock_path = self.workspace_root / contracts.WRITE_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("4242\t100.0\n", encoding="utf-8")

        with (
            patch.object(write_utils.os, "kill", return_value=None),
            patch.object(
                write_utils,
                "_linux_pid_start_time_unix_seconds",
                return_value=200.0,
            ),
        ):
            exc = write_utils.LockUnavailableError(
                contracts.WRITE_LOCK_PATH,
                lock_file_path=lock_path,
            )

        self.assertEqual(exc.holder_pid, 4242)
        self.assertFalse(exc.holder_alive)
        self.assertEqual(exc.holder_started_at, "1970-01-01T00:01:40Z")
        self.assertIn("stale lock from dead PID 4242; safe to remove", str(exc))

    def test_lock_unavailable_error_unreadable_lock_file_falls_back(self) -> None:
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            exc = write_utils.LockUnavailableError(contracts.WRITE_LOCK_PATH)

        self.assertEqual(exc.holder_pid, None)
        self.assertEqual(exc.holder_alive, None)
        self.assertEqual(exc.holder_started_at, None)
        self.assertEqual(
            str(exc),
            f"{write_utils.lock_unavailable_reason()} — "
            "retry after the competing process completes, or remove the lock file if it is stale",
        )

    def test_lock_unavailable_result_includes_holder_context(self) -> None:
        exc = RuntimeError("lock unavailable")
        setattr(exc, "holder_pid", 12345)
        setattr(exc, "holder_alive", False)
        setattr(exc, "holder_started_at", "2026-06-06T22:01:34Z")

        result = lock_unavailable_result(
            surface="test-surface",
            mode="apply",
            approval="approved",
            path_rules={"allowlisted_roots": ["wiki"]},
            exc=exc,
        )

        self.assertEqual(
            result.context,
            {
                "holder_pid": 12345,
                "holder_alive": False,
                "holder_started_at": "2026-06-06T22:01:34Z",
            },
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

    def test_append_log_only_state_changes_rejects_symlinked_log_file(self) -> None:
        log_path = self.workspace_root / "wiki" / "log.md"
        target = self.workspace_root / "redirect-log.md"
        target.write_text("", encoding="utf-8")
        try:
            os.symlink(target, log_path)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaises(OSError):
            write_utils.append_log_only_state_changes(
                self.workspace_root,
                "- state changed",
                state_changed=True,
            )

    def test_append_log_only_state_changes_rejects_symlinked_log_parent(self) -> None:
        wiki_path = self.workspace_root / "wiki"
        wiki_path.rmdir()
        target = self.workspace_root / "redirect-wiki"
        target.mkdir()
        try:
            os.symlink(target, wiki_path)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaises(OSError):
            write_utils.append_log_only_state_changes(
                self.workspace_root,
                "- state changed",
                state_changed=True,
            )

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

    def test_atomic_replace_governed_artifact_rejects_symlinked_parent(self) -> None:
        shutil_target = self.workspace_root / "redirect-target"
        shutil_target.mkdir()
        wiki_path = self.workspace_root / "wiki"
        for child in wiki_path.iterdir():
            if child.is_dir():
                for grandchild in child.iterdir():
                    grandchild.unlink()
                child.rmdir()
            else:
                child.unlink()
        wiki_path.rmdir()
        try:
            os.symlink(shutil_target, wiki_path)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        with self.assertRaises(OSError):
            write_utils.atomic_replace_governed_artifact(
                self.workspace_root,
                "wiki/status.md",
                "after\n",
            )


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


class WriteTextCapturingPreviousSafeSymlinkTests(unittest.TestCase):
    """Regression tests: write_text_capturing_previous_safe must reject symlinked paths."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_rejects_symlink_at_target_path(self) -> None:
        """write_text_capturing_previous_safe must raise OSError when the target is a symlink."""
        real_file = self.tmp_path / "real.md"
        real_file.write_text("original\n", encoding="utf-8")
        link = self.tmp_path / "link.md"
        link.symlink_to(real_file)

        with self.assertRaises(OSError):
            write_utils.write_text_capturing_previous_safe(link, "updated\n")

        # Original file must be untouched.
        self.assertEqual(real_file.read_text(encoding="utf-8"), "original\n")

    def test_rejects_symlinked_parent_directory(self) -> None:
        """write_text_capturing_previous_safe must raise OSError when a parent dir is a symlink."""
        real_dir = self.tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = self.tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)
        target = link_dir / "file.md"

        with self.assertRaises(OSError):
            write_utils.write_text_capturing_previous_safe(target, "data\n")

    def test_plain_path_succeeds(self) -> None:
        """write_text_capturing_previous_safe must write normally when no symlinks are present."""
        target = self.tmp_path / "subdir" / "page.md"
        target.parent.mkdir()
        write_utils.write_text_capturing_previous_safe(target, "content\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "content\n")


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
