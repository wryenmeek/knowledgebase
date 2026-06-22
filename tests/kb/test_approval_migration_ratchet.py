"""Approval-flag migration ratchet checks."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from scripts.hooks import check_approval_flag
from scripts.kb.contracts import MAX_APPROVAL_FLAG_SCRIPTS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"


def _legacy_approval_script_files() -> list[Path]:
    files: list[Path] = []
    for path in SCRIPTS_ROOT.glob("**/*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "--approval" in text:
            files.append(path)
    return sorted(files)


def test_approval_flag_script_count_matches_contract_exactly() -> None:
    files = _legacy_approval_script_files()
    assert len(files) == MAX_APPROVAL_FLAG_SCRIPTS, (
        f"{len(files)} scripts still use --approval but MAX_APPROVAL_FLAG_SCRIPTS="
        f"{MAX_APPROVAL_FLAG_SCRIPTS}: "
        + ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in files)
    )


def test_hook_rejects_new_script_with_approval(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: ([check_approval_flag.StagedScriptPath("A", "scripts/new_tool.py")], None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('parser.add_argument("--approval", default="none")\n', None),
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "new scripts may not introduce legacy --approval" in captured.err


def test_hook_rejects_modified_legacy_script_without_migration(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: (
            [check_approval_flag.StagedScriptPath("M", "scripts/drive_monitor/advance_cursor.py")],
            None,
        ),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('parser.add_argument("--approval", default="none")\n', None),
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "modified legacy script still uses --approval" in captured.err


def test_hook_allows_migrated_modified_legacy_script(monkeypatch) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: (
            [check_approval_flag.StagedScriptPath("M", "scripts/drive_monitor/fetch_content.py")],
            None,
        ),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ("add_approval_arg(parser)\n", None),
    )

    assert check_approval_flag.main([]) == 0


def test_hook_treats_renamed_legacy_script_as_modified(monkeypatch, capsys) -> None:
    def fake_run_git(*args: str) -> tuple[int, str, str]:
        if args[:2] == ("diff", "--cached"):
            return (
                0,
                "R100\tscripts/legacy_tool.py\tscripts/drive_monitor/advance_cursor.py\n",
                "",
            )
        if args[0] == "show":
            return 0, 'parser.add_argument("--approval", default="none")\n', ""
        raise AssertionError(f"unexpected git args: {args!r}")

    monkeypatch.setattr(check_approval_flag, "_run_git", fake_run_git)

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "modified legacy script still uses --approval" in captured.err


def test_hook_returns_zero_when_no_scripts_staged(monkeypatch) -> None:
    monkeypatch.setattr(check_approval_flag, "_staged_script_paths", lambda: ([], None))

    assert check_approval_flag.main([]) == 0


def test_pre_commit_config_registers_approval_flag_ratchet() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    hooks = {
        hook["id"]: hook
        for repo in config["repos"]
        if repo["repo"] == "local"
        for hook in repo["hooks"]
    }
    hook = hooks["approval-flag-ratchet"]

    assert hook["entry"] == "python -m scripts.hooks.check_approval_flag"
    assert hook["stages"] == ["pre-commit"]
    assert hook["files"] == "^scripts/"
    assert hook["pass_filenames"] is False


def test_hooks_json_registers_approval_flag_posttooluse_command() -> None:
    hooks = json.loads(
        (REPO_ROOT / ".github/hooks/hooks.json").read_text(encoding="utf-8")
    )

    post_tool_use = hooks["hooks"]["PostToolUse"]
    assert any(
        entry.get("command") == "python3 scripts/hooks/check_approval_flag.py"
        for entry in post_tool_use
    )


def test_hook_rejects_posttooluse_worktree_edit_with_legacy_approval(monkeypatch, tmp_path, capsys) -> None:
    script_path = tmp_path / "scripts" / "tool.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text('parser.add_argument("--approval", default="none")\n', encoding="utf-8")

    payload = {
        "hookEventName": "PostToolUse",
        "tool_name": "edit",
        "tool_result": {"success": True},
        "cwd": str(tmp_path),
        "tool_input": {"path": "scripts/tool.py"},
    }
    monkeypatch.setenv("COPILOT_HOOK_EVENT_PAYLOAD", json.dumps(payload))
    monkeypatch.chdir(tmp_path)

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "modified legacy script still uses --approval" in captured.err


def test_hook_rejects_approval_equals_after_deadline(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: ([check_approval_flag.StagedScriptPath("M", "scripts/drive_monitor/advance_cursor.py")], None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('argv = ["--approval=approved"]\n', None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_migration_deadline_passed",
        lambda today=None: True,
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "--approval=<value> is forbidden after" in captured.err


def test_hook_allows_approval_equals_before_deadline(monkeypatch, capsys) -> None:
    path = "scripts/non_exempt.py"
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: ([check_approval_flag.StagedScriptPath("M", path)], None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('argv = ["--approval=approved"]\n', None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_migration_deadline_passed",
        lambda today=None: False,
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "modified legacy script still uses --approval" in captured.err
    assert "--approval=<value> is forbidden after" not in captured.err


def test_hook_allows_exempt_approval_equals_after_deadline(monkeypatch) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: (
            [
                check_approval_flag.StagedScriptPath(
                    "M",
                    "scripts/_optional_surface_common.py",
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('argv = ["--approval=approved"]\n', None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_migration_deadline_passed",
        lambda today=None: True,
    )

    assert check_approval_flag.main([]) == 0


def test_exempt_paths_membership_locked() -> None:
    """Force PR-review scrutiny on any change to _EXEMPT_PATHS.

    Membership confers two bypasses: the new-legacy-script check and (after
    APPROVAL_EQUALS_REJECTION_DEADLINE) the equals-form rejection. Growing this
    set silently extends the deprecation window for additional files, so any
    addition must be deliberate — this test fails closed when the set drifts.
    Locked per security-auditor LOW-1 finding on PR #363.
    """
    assert check_approval_flag._EXEMPT_PATHS == frozenset(
        {
            "scripts/_optional_surface_common.py",
            "scripts/kb/checkpoint_registry.py",
        }
    )


def test_hook_rejects_approval_equals_for_non_exempt_path(monkeypatch, capsys) -> None:
    path = "scripts/non_exempt.py"
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: ([check_approval_flag.StagedScriptPath("M", path)], None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('argv = ["--approval=approved"]\n', None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_migration_deadline_passed",
        lambda today=None: True,
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "--approval=<value> is forbidden after" in captured.err


def test_hook_handles_mixed_exempt_and_nonexempt_paths(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        check_approval_flag,
        "_staged_script_paths",
        lambda: (
            [
                check_approval_flag.StagedScriptPath("M", "scripts/_optional_surface_common.py"),
                check_approval_flag.StagedScriptPath("M", "scripts/non_exempt.py"),
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_get_staged_content",
        lambda path: ('argv = ["--approval=approved"]\n', None),
    )
    monkeypatch.setattr(
        check_approval_flag,
        "_migration_deadline_passed",
        lambda today=None: True,
    )

    assert check_approval_flag.main([]) == 1
    captured = capsys.readouterr()
    assert "scripts/non_exempt.py: --approval=<value> is forbidden after" in captured.err
    assert "scripts/_optional_surface_common.py" not in captured.err


def test_approval_flag_deadline_tripwire() -> None:
    """ADR-030 deadline tripwire: after the migration deadline, all --approval must be removed.

    This test is dormant until ``APPROVAL_EQUALS_REJECTION_DEADLINE`` (2026-12-31).
    Once the deadline passes it enforces the removal criteria stated in ADR-030
    §Decision item 7:

      - ``MAX_APPROVAL_FLAG_SCRIPTS`` must be ``0`` in ``scripts/kb/contracts.py``
      - No ``scripts/**/*.py`` file may still contain the legacy ``--approval`` spelling

    Failing this test after the deadline forces explicit closure of the migration
    window — it cannot silently slip past 2026-12-31.
    """
    today = date.today()
    if today <= check_approval_flag.APPROVAL_EQUALS_REJECTION_DEADLINE:
        return  # Dormant before deadline; the ratchet count test handles enforcement.

    deadline_str = check_approval_flag.APPROVAL_EQUALS_REJECTION_DEADLINE.isoformat()
    assert MAX_APPROVAL_FLAG_SCRIPTS == 0, (
        f"ADR-030 deadline ({deadline_str}) has passed but MAX_APPROVAL_FLAG_SCRIPTS="
        f"{MAX_APPROVAL_FLAG_SCRIPTS}. "
        "Set MAX_APPROVAL_FLAG_SCRIPTS=0 in scripts/kb/contracts.py after migrating all "
        "remaining --approval scripts to --apply."
    )
    files = _legacy_approval_script_files()
    assert len(files) == 0, (
        f"ADR-030 deadline ({deadline_str}) has passed but {len(files)} script(s) still "
        "contain legacy --approval and must be migrated to --apply: "
        + ", ".join(path.relative_to(REPO_ROOT).as_posix() for path in files)
    )
