"""Unit tests for write lock and state-change log helpers."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest

from scripts.kb import contracts
from scripts.kb import write_utils


REPO_ROOT = Path(__file__).resolve().parents[2]


class WriteUtilitiesTests(unittest.TestCase):
    def setUp(self) -> None:
        test_name = self.id().replace(".", "_")
        self.workspace_root = REPO_ROOT / "tests" / "kb" / ".scratch" / test_name
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)
        (self.workspace_root / "wiki").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace_root.exists():
            shutil.rmtree(self.workspace_root)

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


if __name__ == "__main__":
    unittest.main()
