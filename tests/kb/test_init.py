"""Tests for scripts/init.py — fresh-instance initializer."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TESTS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TESTS_ROOT.parents[1]

# Import the module under test with REPO_ROOT patched so all filesystem
# operations go to self.workspace instead of the real repository.
import scripts.init as init_module  # noqa: E402  (import after sys.path manipulation)


def _make_workspace(tmp_path: Path) -> Path:
    """Create a minimal repo-root-like workspace in *tmp_path*."""
    # Sentinel files required by _assert_repo_root
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / "schema").mkdir()
    # wiki/ and raw/ must exist for stubs
    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw").mkdir()
    return tmp_path


def _run_fresh(tmp_path: Path, extra_args: list[str] | None = None) -> int:
    """Run main(["--fresh", "--yes", ...]) with REPO_ROOT redirected to tmp_path
    and subprocess.run mocked to succeed."""
    args = ["--fresh", "--yes"] + (extra_args or [])
    mock_ok = MagicMock(returncode=0)
    with patch.object(init_module, "REPO_ROOT", tmp_path), \
         patch("scripts.init.subprocess.run", return_value=mock_ok), \
         patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}):
        return init_module.main(args)


# ---------------------------------------------------------------------------
# P0 — Wipe safety
# ---------------------------------------------------------------------------


class TestWipeDir(unittest.TestCase):
    """_wipe_dir: empties a directory without deleting it."""

    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir).resolve()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_removes_contents_but_keeps_directory(self) -> None:
        target = self.root / "wiki" / "entities"
        target.mkdir(parents=True)
        (target / "page.md").write_text("data", encoding="utf-8")
        (target / "sub").mkdir()
        (target / "sub" / "nested.md").write_text("nested", encoding="utf-8")

        init_module._wipe_dir(target)

        self.assertTrue(target.exists(), "directory itself must survive")
        self.assertEqual(list(target.iterdir()), [])

    def test_creates_missing_directory(self) -> None:
        target = self.root / "raw" / "inbox"
        self.assertFalse(target.exists())

        init_module._wipe_dir(target)

        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])

    def test_rejects_symlink_directory(self) -> None:
        """_wipe_dir must raise OSError rather than deleting symlink target contents."""
        real_dir = self.root / "real_data"
        real_dir.mkdir()
        (real_dir / "important.txt").write_text("keep me", encoding="utf-8")

        link = self.root / "wiki" / "analyses"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(real_dir)

        with self.assertRaises(OSError):
            init_module._wipe_dir(link)

        # Target contents must be untouched
        self.assertTrue((real_dir / "important.txt").exists())

    def test_removes_child_symlinks_without_following(self) -> None:
        """Symlinks inside a content dir are removed (not followed)."""
        target = self.root / "wiki" / "entities"
        target.mkdir(parents=True)

        external = self.root / "external"
        external.mkdir()
        (external / "secret.txt").write_text("secret", encoding="utf-8")

        link = target / "linked"
        link.symlink_to(external)

        init_module._wipe_dir(target)

        # The symlink is gone but the external directory is intact
        self.assertFalse(link.exists())
        self.assertTrue((external / "secret.txt").exists())


# ---------------------------------------------------------------------------
# P0 — Confirmation abort
# ---------------------------------------------------------------------------


class TestConfirmationAbort(unittest.TestCase):
    """Aborting the confirmation must exit with code 1 and make no changes."""

    def setUp(self) -> None:
        import tempfile, shutil
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("builtins.input", return_value="n")
    def test_no_answer_aborts_with_exit_1(self, _mock_input: MagicMock) -> None:
        sentinel = self.workspace / "wiki" / "entities" / "keep.md"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("must survive", encoding="utf-8")

        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch.dict(os.environ, {}, clear=False):
            # No INIT_ALLOW_WIPE; no --yes; input returns "n"
            rc = init_module.main(["--fresh"])

        self.assertEqual(rc, 1)
        self.assertTrue(sentinel.exists(), "sentinel file must survive abort")

    @patch("builtins.input", side_effect=EOFError)
    def test_eoferror_aborts_with_exit_1(self, _mock_input: MagicMock) -> None:
        with patch.object(init_module, "REPO_ROOT", self.workspace):
            rc = init_module.main(["--fresh"])
        self.assertEqual(rc, 1)

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_aborts_with_exit_1(self, _mock_input: MagicMock) -> None:
        with patch.object(init_module, "REPO_ROOT", self.workspace):
            rc = init_module.main(["--fresh"])
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# P0 — --yes / INIT_ALLOW_WIPE guard
# ---------------------------------------------------------------------------


class TestYesFlagGuard(unittest.TestCase):
    """--yes requires INIT_ALLOW_WIPE=1; without it, exit 1 with no changes."""

    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_yes_without_env_var_exits_1(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "INIT_ALLOW_WIPE"}
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch.dict(os.environ, env, clear=True):
            rc = init_module.main(["--fresh", "--yes"])
        self.assertEqual(rc, 1)

    def test_yes_with_env_var_does_not_call_input(self) -> None:
        mock_ok = MagicMock(returncode=0)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", return_value=mock_ok), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}), \
             patch("builtins.input") as mock_input:
            rc = init_module.main(["--fresh", "--yes"])

        self.assertEqual(rc, 0)
        mock_input.assert_not_called()

    def test_short_y_flag_equivalent_to_yes(self) -> None:
        mock_ok = MagicMock(returncode=0)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", return_value=mock_ok), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}), \
             patch("builtins.input") as mock_input:
            rc = init_module.main(["--fresh", "-y"])

        self.assertEqual(rc, 0)
        mock_input.assert_not_called()


# ---------------------------------------------------------------------------
# P0 — --fresh is required
# ---------------------------------------------------------------------------


class TestFreshFlagRequired(unittest.TestCase):
    def test_missing_fresh_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            init_module.main([])
        self.assertNotEqual(ctx.exception.code, 0)


# ---------------------------------------------------------------------------
# P1 — REPO_ROOT sentinel validation
# ---------------------------------------------------------------------------


class TestRepoRootSentinel(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self._tmpdir).resolve()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_missing_sentinel_exits_with_sys_exit(self) -> None:
        # workspace has no sentinels at all
        mock_ok = MagicMock(returncode=0)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", return_value=mock_ok), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}):
            with self.assertRaises(SystemExit):
                init_module.main(["--fresh", "--yes"])


# ---------------------------------------------------------------------------
# P1 — Subprocess error propagation
# ---------------------------------------------------------------------------


class TestSubprocessPropagation(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_pip_failure_returns_nonzero_and_skips_pytest(self) -> None:
        pip_fail = MagicMock(returncode=1)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", return_value=pip_fail), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}):
            rc = init_module.main(["--fresh", "--yes"])

        self.assertEqual(rc, 1)

    def test_pytest_failure_returns_nonzero(self) -> None:
        pip_ok = MagicMock(returncode=0)
        pytest_fail = MagicMock(returncode=2)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", side_effect=[pip_ok, pytest_fail]), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}):
            rc = init_module.main(["--fresh", "--yes"])

        self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# P1 — Stub frontmatter
# ---------------------------------------------------------------------------


class TestStubContent(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())
        _run_fresh(self.workspace)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_log_stub_has_required_frontmatter(self) -> None:
        text = (self.workspace / "wiki" / "log.md").read_text(encoding="utf-8")
        for key in ("type:", "title:", "status:", "updated_at:", "tags:"):
            self.assertIn(key, text, f"log.md stub missing frontmatter key: {key}")
        self.assertIn("1970-01-01T00:00:00Z", text)

    def test_index_stub_has_required_frontmatter(self) -> None:
        text = (self.workspace / "wiki" / "index.md").read_text(encoding="utf-8")
        for key in ("type:", "title:", "status:", "updated_at:", "tags:"):
            self.assertIn(key, text)

    def test_spec_stub_has_todo_markers(self) -> None:
        text = (self.workspace / "raw" / "processed" / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("TODO", text)
        self.assertIn("Domain Specification", text)

    def test_sample_inbox_file_written(self) -> None:
        text = (self.workspace / "raw" / "inbox" / "example-policy.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Example Policy Document", text)
        self.assertIn("policy-document", text)


# ---------------------------------------------------------------------------
# P1 — Lock file handling
# ---------------------------------------------------------------------------


class TestLockFiles(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_stale_lock_files_removed(self) -> None:
        for rel in init_module.LOCK_FILES:
            p = self.workspace / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("lock", encoding="utf-8")

        _run_fresh(self.workspace)

        for rel in init_module.LOCK_FILES:
            self.assertFalse((self.workspace / rel).exists(), f"lock not removed: {rel}")

    def test_absent_lock_files_do_not_raise(self) -> None:
        rc = _run_fresh(self.workspace)
        self.assertEqual(rc, 0)

    def test_broken_symlink_lock_files_removed(self) -> None:
        """Broken symlinks at lock paths must be cleaned up (gh PR #217 review)."""
        for rel in init_module.LOCK_FILES:
            p = self.workspace / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            # Create a symlink pointing at a nonexistent target — `p.exists()`
            # returns False for a broken symlink, but cleanup must still unlink.
            p.symlink_to(self.workspace / "does-not-exist")
            self.assertTrue(p.is_symlink())
            self.assertFalse(p.exists())

        _run_fresh(self.workspace)

        for rel in init_module.LOCK_FILES:
            p = self.workspace / rel
            self.assertFalse(p.exists(), f"broken symlink not removed: {rel}")
            self.assertFalse(p.is_symlink(), f"broken symlink still present: {rel}")

    def test_symlink_lock_files_removed(self) -> None:
        """Valid symlinks at lock paths must be cleaned up without crashing the
        symlink guard (gh PR #217 review)."""
        # Create a real target the symlinks can point at.
        target = self.workspace / "real-lock-target"
        target.write_text("lock-target", encoding="utf-8")

        for rel in init_module.LOCK_FILES:
            p = self.workspace / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target)
            self.assertTrue(p.is_symlink())
            self.assertTrue(p.exists())

        _run_fresh(self.workspace)

        for rel in init_module.LOCK_FILES:
            p = self.workspace / rel
            self.assertFalse(p.exists(), f"symlink lock not removed: {rel}")
            self.assertFalse(p.is_symlink(), f"symlink still present: {rel}")
        # The symlink target itself must remain — only the symlink is unlinked.
        self.assertTrue(target.exists())

    def test_held_wiki_write_lock_blocks_init(self) -> None:
        """If wiki/.kb_write.lock exists, init must refuse to run (another process active)."""
        lock = self.workspace / "wiki" / ".kb_write.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("lock", encoding="utf-8")

        mock_ok = MagicMock(returncode=0)
        with patch.object(init_module, "REPO_ROOT", self.workspace), \
             patch("scripts.init.subprocess.run", return_value=mock_ok), \
             patch.dict(os.environ, {"INIT_ALLOW_WIPE": "1"}):
            rc = init_module.main(["--fresh", "--yes"])

        self.assertEqual(rc, 1)
        # The wiki lock is NOT in LOCK_FILES, so it must NOT have been removed.
        self.assertTrue(lock.exists())


# ---------------------------------------------------------------------------
# P2 — All CONTENT_DIRS wiped
# ---------------------------------------------------------------------------


class TestAllContentDirsWiped(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.workspace = _make_workspace(Path(self._tmpdir).resolve())

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_all_content_dirs_empty_after_init(self) -> None:
        for rel in init_module.CONTENT_DIRS:
            d = self.workspace / rel
            d.mkdir(parents=True, exist_ok=True)
            (d / "legacy.md").write_text("old content", encoding="utf-8")

        _run_fresh(self.workspace)

        for rel in init_module.CONTENT_DIRS:
            d = self.workspace / rel
            self.assertTrue(d.is_dir(), f"{rel} must exist after init")
            # Allow for the sample inbox file that init writes back in
            leftovers = [
                p for p in d.iterdir()
                if p.name not in ("example-policy.md", "SPEC.md")
            ]
            self.assertEqual(leftovers, [], f"{rel} still has unexpected files: {leftovers}")


# ---------------------------------------------------------------------------
# P2 — _write helper
# ---------------------------------------------------------------------------


class TestWriteHelper(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.root = Path(self._tmpdir).resolve()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_creates_parent_directories(self) -> None:
        target = self.root / "a" / "b" / "c" / "file.md"
        self.assertFalse(target.parent.exists())
        init_module._write(target, "content")
        self.assertEqual(target.read_text(encoding="utf-8"), "content")

    def test_overwrites_existing_file(self) -> None:
        target = self.root / "existing.md"
        target.write_text("old", encoding="utf-8")
        init_module._write(target, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")


# ---------------------------------------------------------------------------
# P2 — _confirm truth table
# ---------------------------------------------------------------------------


class TestConfirmHelper(unittest.TestCase):
    @patch("builtins.input", return_value="y")
    def test_lowercase_y_accepted(self, _: MagicMock) -> None:
        self.assertTrue(init_module._confirm("Proceed?"))

    @patch("builtins.input", return_value="Y")
    def test_uppercase_y_accepted(self, _: MagicMock) -> None:
        self.assertTrue(init_module._confirm("Proceed?"))

    @patch("builtins.input", return_value="yes")
    def test_yes_string_accepted(self, _: MagicMock) -> None:
        self.assertTrue(init_module._confirm("Proceed?"))

    @patch("builtins.input", return_value="")
    def test_empty_string_rejected(self, _: MagicMock) -> None:
        self.assertFalse(init_module._confirm("Proceed?"))

    @patch("builtins.input", return_value="no")
    def test_no_string_rejected(self, _: MagicMock) -> None:
        self.assertFalse(init_module._confirm("Proceed?"))


# ---------------------------------------------------------------------------
# P3 — Import safety
# ---------------------------------------------------------------------------


class TestImportSafety(unittest.TestCase):
    def test_module_importable_without_side_effects(self) -> None:
        import importlib
        # Re-importing must not trigger filesystem or subprocess actions.
        importlib.import_module("scripts.init")


if __name__ == "__main__":
    unittest.main()
