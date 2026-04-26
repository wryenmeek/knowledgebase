"""Unit tests for the check_hooks_json.py pre-commit hook script."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_MODULE = "scripts.hooks.check_hooks_json"

_VALID_HOOKS = {
    "hooks": {
        "SessionStart": [{"command": "echo start"}],
        "PreToolUse": [{"command": "echo pre"}],
        "PostToolUse": [{"command": "echo post"}],
        "Stop": [{"command": "echo stop"}],
    }
}


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", HOOK_MODULE, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class CheckHooksJsonTests(unittest.TestCase):

    def test_valid_hooks_json_exits_0(self) -> None:
        result = _run([str(REPO_ROOT / ".github" / "hooks" / "hooks.json")])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_json_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hooks.json"
            p.write_text("{bad json", encoding="utf-8")
            result = _run([str(p)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR", result.stderr + result.stdout)

    def test_missing_event_key_exits_1(self) -> None:
        data = {
            "hooks": {
                "SessionStart": [{"command": "echo s"}],
                "Stop": [{"command": "echo x"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hooks.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            result = _run([str(p)])
        self.assertEqual(result.returncode, 1)

    def test_missing_command_field_exits_1(self) -> None:
        data = {
            "hooks": {
                "SessionStart": [{"notcommand": "echo s"}],
                "PreToolUse": [{"command": "echo pre"}],
                "PostToolUse": [{"command": "echo post"}],
                "Stop": [{"command": "echo stop"}],
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "hooks.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            result = _run([str(p)])
        self.assertEqual(result.returncode, 1)

    def test_no_args_exits_0(self) -> None:
        """Vacuous-pass: no files to check = nothing to fail."""
        result = _run([])
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
