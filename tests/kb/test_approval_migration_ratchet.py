"""Approval-flag migration ratchet checks."""

from __future__ import annotations

import json
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


def test_approval_flag_script_count_does_not_exceed_contract() -> None:
    files = _legacy_approval_script_files()
    assert len(files) <= MAX_APPROVAL_FLAG_SCRIPTS, (
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
