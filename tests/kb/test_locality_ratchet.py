"""Tests for scripts.hooks.check_locality_ratchet."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_MODULE = "scripts.hooks.check_locality_ratchet"

COPILOT_PATH = ".github/copilot-instructions.md"
AGENTS_PATH = "AGENTS.md"

COPILOT_BASE = textwrap.dedent(
    """\
    # Copilot project instructions

    ## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

    Override text is exempt from the locality ratchet.

    ## Build, test, and verify commands

    Existing global rule.
    """
)

AGENTS_BASE = textwrap.dedent(
    """\
    # AGENTS

    ## Mission

    Existing global guidance.

    ## Write-surface matrix

    Matrix introduction.

    | Surface | Runtime mode | Writable paths | Read-only / prerequisite paths | Lock requirements | Artifact / schema owners | Hard-fail behavior |
    |---|---|---|---|---|---|---|
    | `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |

    ## Other section

    Existing AGENTS rule.
    """
)


def _local_pre_commit_hooks() -> dict[str, dict[str, object]]:
    config = yaml.safe_load(
        (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    for repo_config in config["repos"]:
        if repo_config["repo"] == "local":
            return {hook["id"]: hook for hook in repo_config["hooks"]}
    raise AssertionError("local pre-commit repo configuration not found")


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def _write(repo: Path, rel_path: str, content: str) -> None:
    path = repo / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _stage(repo: Path, rel_path: str, content: str) -> None:
    _write(repo, rel_path, content)
    _run_git(repo, "add", rel_path)


def _commit(repo: Path, subject: str, trailer: str | None = None) -> None:
    command = ["commit", "-m", subject]
    if trailer is not None:
        command.extend(["-m", trailer])
    _run_git(repo, *command)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test User")
    _write(repo, COPILOT_PATH, COPILOT_BASE)
    _write(repo, AGENTS_PATH, AGENTS_BASE)
    _run_git(repo, "add", COPILOT_PATH, AGENTS_PATH)
    _run_git(repo, "commit", "-m", "baseline")
    return repo


def _run_hook(
    repo: Path,
    *paths: str,
    commit_message: str | None = None,
    commit_msg_file: Path | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    command = [sys.executable, "-m", HOOK_MODULE]
    if commit_message is not None:
        command.extend(["--commit-message", commit_message])
    if commit_msg_file is not None:
        command.extend(["--commit-msg-file", str(commit_msg_file)])
    command.extend(paths)
    return subprocess.run(
        command,
        cwd=repo,
        env=env,
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )


def test_pure_addition_without_trailer_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(repo, COPILOT_PATH)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "Locality-4-Justification:" in result.stderr
    assert "paired deletion" in result.stderr


def test_addition_with_trailer_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add global rule\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_addition_with_lowercase_trailer_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add global rule\n\n"
            "locality-4-justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_addition_with_absolute_commit_msg_file_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")
    message_file = repo / "COMMIT_EDITMSG"
    message_file.write_text(
        "Add global rule\n\n"
        "Locality-4-Justification: applies before scoped context can load\n",
        encoding="utf-8",
    )

    result = _run_hook(repo, COPILOT_PATH, commit_msg_file=message_file.resolve())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_addition_with_trailer_from_stdin_payload_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        stdin_text=json.dumps(
            {
                "staged_files": [COPILOT_PATH],
                "commit_message": (
                    "Add global rule\n\n"
                    "Locality-4-Justification: applies before scoped context can load\n"
                ),
            }
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_trailer_with_no_prior_trailers_in_window_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add global rule\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_trailer_with_one_prior_trailer_in_window_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    prior_content = COPILOT_BASE + "\nPrior always-on rule.\n"
    _stage(repo, COPILOT_PATH, prior_content)
    _commit(
        repo,
        "Add prior global rule",
        "Locality-4-Justification: applies before scoped context can load",
    )
    _stage(repo, COPILOT_PATH, prior_content + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add another global rule\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "soft budget" in result.stderr
    assert "already has 1" in result.stderr


def test_existing_budget_violation_does_not_gate_non_locality_commit(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    first_content = COPILOT_BASE + "\nFirst prior always-on rule.\n"
    _stage(repo, COPILOT_PATH, first_content)
    _commit(
        repo,
        "Add first prior global rule",
        "Locality-4-Justification: applies before scoped context can load",
    )
    second_content = first_content + "\nSecond prior always-on rule.\n"
    _stage(repo, COPILOT_PATH, second_content)
    _commit(
        repo,
        "Add second prior global rule",
        "Locality-4-Justification: applies before scoped context can load",
    )
    _stage(repo, "docs/regular.md", "# Regular markdown\n")

    result = _run_hook(
        repo,
        "docs/regular.md",
        commit_message=(
            "Update regular docs\n\n"
            "Locality-4-Justification: not relevant to this commit\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_paired_deletion_restores_trailer_budget_headroom(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    prior_content = COPILOT_BASE + "\nPrior always-on rule.\n"
    _stage(repo, COPILOT_PATH, prior_content)
    _commit(
        repo,
        "Add prior global rule",
        "Locality-4-Justification: applies before scoped context can load",
    )
    _stage(repo, COPILOT_PATH, COPILOT_BASE)
    _commit(repo, "Remove stale global rule")
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(
        repo,
        COPILOT_PATH,
        commit_message=(
            "Add replacement global rule\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_trailer_budget_is_tracked_per_file(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nPrior always-on rule.\n")
    _commit(
        repo,
        "Add prior copilot global rule",
        "Locality-4-Justification: applies before scoped context can load",
    )
    _stage(repo, AGENTS_PATH, AGENTS_BASE + "\nNew AGENTS global rule.\n")

    result = _run_hook(
        repo,
        AGENTS_PATH,
        commit_message=(
            "Add AGENTS global rule\n\n"
            "Locality-4-Justification: applies before scoped context can load\n"
        ),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_addition_with_paired_deletion_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        COPILOT_PATH,
        COPILOT_BASE.replace("Existing global rule.", "Replacement global rule."),
    )

    result = _run_hook(repo, COPILOT_PATH)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_pure_deletion_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE.replace("\nExisting global rule.\n", "\n"))

    result = _run_hook(repo, COPILOT_PATH)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_no_touch_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    result = _run_hook(repo)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_no_arg_staged_locality_4_addition_exits_1(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")

    result = _run_hook(repo)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "Locality-4-Justification:" in result.stderr


def test_staged_file_outside_locality_4_paths_exits_0(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, "docs/regular.md", "# Regular markdown\n")

    result = _run_hook(repo, "docs/regular.md")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_cross_file_deletion_does_not_pair_addition(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(repo, COPILOT_PATH, COPILOT_BASE + "\nNew always-on rule.\n")
    _stage(repo, AGENTS_PATH, AGENTS_BASE.replace("\nExisting AGENTS rule.\n", "\n"))

    result = _run_hook(repo, COPILOT_PATH, AGENTS_PATH)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr
    assert "net +2" in result.stderr


def test_malformed_copilot_heading_structure_fails_closed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        COPILOT_PATH,
        textwrap.dedent(
            """\
            # Copilot project instructions

            ## ⚠️ Slash-Command Override: /chronicle improve → audit-knowledgebase-workspace skill

            Override text.

            New always-on rule without the expected second H2 boundary.
            """
        ),
    )

    result = _run_hook(repo, COPILOT_PATH)

    assert result.returncode == 1
    assert COPILOT_PATH in result.stderr


def test_agents_write_surface_matrix_row_addition_is_exempt(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stage(
        repo,
        AGENTS_PATH,
        AGENTS_BASE.replace(
            "| `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n",
            "| `scripts/hooks/existing.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n"
            "| `scripts/hooks/new.py` | `read-only only`. | None. | Reads staged files. | None. | Existing. | Existing failures. |\n",
        ),
    )

    result = _run_hook(repo, AGENTS_PATH)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_pre_commit_config_registers_precommit_locality_ratchet() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    hook = _local_pre_commit_hooks()["locality-ratchet-pre-commit"]

    assert "pre-commit" in config["default_install_hook_types"]
    assert "commit-msg" in config["default_install_hook_types"]
    assert hook["entry"] == "python -m scripts.hooks.check_locality_ratchet"
    assert hook["stages"] == ["pre-commit"]
    assert hook["files"] == "^(\\.github/copilot-instructions\\.md|AGENTS\\.md)$"
    assert hook["pass_filenames"] is True


def test_pre_commit_config_registers_commitmsg_locality_ratchet() -> None:
    hook = _local_pre_commit_hooks()["locality-ratchet-commit-msg"]

    assert hook["entry"] == "python -m scripts.hooks.check_locality_ratchet"
    assert hook["stages"] == ["commit-msg"]
    assert hook["args"] == ["--commit-msg-file"]
    assert hook["pass_filenames"] is True


def test_hooks_json_does_not_register_nonstandard_git_hook_events() -> None:
    hooks = json.loads(
        (REPO_ROOT / ".github/hooks/hooks.json").read_text(encoding="utf-8")
    )

    assert "PreCommit" not in hooks["hooks"]
    assert "CommitMsg" not in hooks["hooks"]
