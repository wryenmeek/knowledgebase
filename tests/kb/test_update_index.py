"""Tests for deterministic wiki index generation and write policy behavior."""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from scripts.kb import update_index
from scripts.kb import contracts
from scripts.kb import write_utils


REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_INDEX_SCRIPT = REPO_ROOT / "scripts" / "kb" / "update_index.py"

WIKI_SECTIONS = ("sources", "entities", "concepts", "analyses")  # keep in sync with page_template_utils.TOPICAL_NAMESPACES


def _build_page(title: str, page_type: str, confidence: str = "3") -> str:
    return f"""---
type: {page_type}
title: "{title}"
status: active
sources: []
open_questions: []
confidence: {confidence}
sensitivity: internal
updated_at: "2024-01-01T00:00:00Z"
tags:
  - test
---

# {title}

Fixture page.
"""


def _write_wiki_page(wiki_root: Path, relative_path: str, content: str) -> Path:
    page = wiki_root / relative_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    return page


def _run_command(*args: str) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = update_index.main(list(args))
    return exit_code, stdout.getvalue(), stderr.getvalue()


def _run_cli_command(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(REPO_ROOT)
        if not existing_pythonpath
        else f"{REPO_ROOT}{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(
        [sys.executable, str(UPDATE_INDEX_SCRIPT), *args],
        capture_output=True,
        check=False,
        cwd=workspace,
        env=env,
        text=True,
    )


def _snapshot_hashes(workspace: Path) -> dict[str, str]:
    digest_map: dict[str, str] = {}
    for file_path in sorted(workspace.rglob("*")):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(workspace).as_posix()
        if relative_path == "wiki/.kb_write.lock":
            # Lock-file metadata is operational state (holder pid/start-time), not
            # user-visible workspace content drift.
            digest_map[relative_path] = hashlib.sha256(b"").hexdigest()
            continue
        digest_map[relative_path] = hashlib.sha256(file_path.read_bytes()).hexdigest()
    return digest_map


@dataclass
class CommandWorkspace:
    workspace: Path
    wiki_root: Path


@pytest.fixture()
def command_workspace(tmp_path: Path) -> CommandWorkspace:
    workspace = tmp_path
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "raw" / "sentinel.txt").write_text("raw-is-immutable\n", encoding="utf-8")
    (workspace / contracts.GOVERNANCE_META_LOCK_PATH).write_text("", encoding="utf-8")

    wiki_root = workspace / "wiki"
    for section in WIKI_SECTIONS:
        (wiki_root / section).mkdir(parents=True, exist_ok=True)

    (wiki_root / "index.md").write_text("stale-index\n", encoding="utf-8")
    (wiki_root / ".kb_write.lock").write_text("", encoding="utf-8")
    (wiki_root / "log.md").write_text("log-should-not-change\n", encoding="utf-8")

    _write_wiki_page(wiki_root, "sources/zeta-source.md", _build_page("Zeta Source", "source", "2"))
    _write_wiki_page(wiki_root, "sources/alpha-source.md", _build_page("Alpha Source", "source", "4"))
    _write_wiki_page(wiki_root, "entities/beneficiary.md", _build_page("Beneficiary", "entity", "5"))
    _write_wiki_page(
        wiki_root, "concepts/network-adequacy.md", _build_page("Network Adequacy", "concept", "3")
    )
    _write_wiki_page(
        wiki_root, "analyses/prior-auth-review.md", _build_page("Prior Auth Review", "analysis", "4")
    )

    return CommandWorkspace(workspace=workspace, wiki_root=wiki_root)


def test_preview_is_deterministic_and_read_only(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    before = _snapshot_hashes(workspace)

    first_code, first_stdout, first_stderr = _run_command("--wiki-root", str(wiki_root))
    second_code, second_stdout, second_stderr = _run_command("--wiki-root", str(wiki_root))

    assert first_code == 0
    assert second_code == 0
    assert first_stderr == ""
    assert second_stderr == ""
    assert first_stdout == second_stdout
    assert first_stdout == update_index.generate_index_content(wiki_root)
    assert before == _snapshot_hashes(workspace)


def test_write_updates_only_index_file_when_needed(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    before = _snapshot_hashes(workspace)

    exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--write")

    assert exit_code == 0
    assert stderr == ""
    assert stdout == "written\n"

    after = _snapshot_hashes(workspace)
    changed_paths = {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }
    assert changed_paths == {"wiki/index.md"}
    assert (wiki_root / "index.md").read_text(encoding="utf-8") == update_index.generate_index_content(
        wiki_root
    )


def test_check_mode_fails_closed_when_index_is_stale(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    before = _snapshot_hashes(workspace)

    exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--check")

    assert exit_code == 1
    assert stderr == ""
    assert stdout == "drifted\n"
    assert before == _snapshot_hashes(workspace)


def test_check_mode_passes_when_index_is_current(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    generated = update_index.generate_index_content(wiki_root)
    (wiki_root / "index.md").write_text(generated, encoding="utf-8")
    before = _snapshot_hashes(workspace)

    exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--check")

    assert exit_code == 0
    assert stderr == ""
    assert stdout == "unchanged\n"
    assert before == _snapshot_hashes(workspace)


def test_relative_wiki_root_cli_check_succeeds_from_workspace_root(
    command_workspace: CommandWorkspace,
) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    generated = update_index.generate_index_content(wiki_root)
    (wiki_root / "index.md").write_text(generated, encoding="utf-8")

    completed = _run_cli_command(workspace, "--wiki-root", "wiki", "--check")

    assert completed.returncode == 0
    assert completed.stdout == "unchanged\n"
    assert completed.stderr == ""


def test_write_is_noop_when_index_is_already_current(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    generated = update_index.generate_index_content(wiki_root)
    (wiki_root / "index.md").write_text(generated, encoding="utf-8")
    before = _snapshot_hashes(workspace)

    first_code, first_stdout, first_stderr = _run_command("--wiki-root", str(wiki_root), "--write")
    second_code, second_stdout, second_stderr = _run_command("--wiki-root", str(wiki_root), "--write")

    assert first_code == 0
    assert second_code == 0
    assert first_stderr == ""
    assert second_stderr == ""
    assert first_stdout == "unchanged\n"
    assert second_stdout == "unchanged\n"
    assert before == _snapshot_hashes(workspace)


def test_write_preserves_existing_index_when_atomic_replace_fails(
    command_workspace: CommandWorkspace,
) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    before = _snapshot_hashes(workspace)
    stale_index = (wiki_root / "index.md").read_text(encoding="utf-8")

    with patch("scripts.kb.update_index.os.replace", side_effect=OSError("boom")):
        exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--write")

    assert exit_code == 1
    assert stdout == ""
    assert "unable to write index" in stderr
    assert (wiki_root / "index.md").read_text(encoding="utf-8") == stale_index
    assert not (wiki_root / "index.md.tmp").exists()
    after = _snapshot_hashes(workspace)
    assert before == after


def test_write_rejects_preexisting_temp_symlink(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    external_target = workspace / "outside-target.md"
    external_target.write_text("external-target\n", encoding="utf-8")
    temp_index_path = wiki_root / "index.md.tmp"
    temp_index_path.symlink_to(external_target)
    stale_index = (wiki_root / "index.md").read_text(encoding="utf-8")

    exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--write")

    assert exit_code == 1
    assert stdout == ""
    assert "unable to write index" in stderr
    assert external_target.read_text(encoding="utf-8") == "external-target\n"
    assert (wiki_root / "index.md").read_text(encoding="utf-8") == stale_index
    assert temp_index_path.is_symlink()


def test_write_fails_closed_when_write_lock_is_held(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    stale_index = (wiki_root / "index.md").read_text(encoding="utf-8")

    with write_utils.exclusive_write_lock(workspace):
        completed = _run_cli_command(workspace, "--wiki-root", "wiki", "--write")

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "lock_unavailable" in completed.stderr
    assert ".kb_write.lock" in completed.stderr
    assert (wiki_root / "index.md").read_text(encoding="utf-8") == stale_index


def test_generate_index_rejects_symlinked_markdown_page(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    outside_page = workspace / "outside-source.md"
    outside_page.write_text(
        "\n".join(
            [
                "---",
                "type: source",
                'title: "Outside Source"',
                "status: active",
                "sources: []",
                "open_questions: []",
                "confidence: 1",
                "sensitivity: internal",
                'updated_at: "2024-01-01T00:00:00Z"',
                "tags:",
                "  - test",
                "---",
            ]
        ),
        encoding="utf-8",
    )
    linked_page = wiki_root / "sources" / "outside-source.md"
    linked_page.symlink_to(outside_page)

    with pytest.raises(update_index.IndexGenerationError) as ctx:
        update_index.generate_index_content(wiki_root)

    assert "symlinked markdown pages are not allowed" in str(ctx.value)


def test_generate_index_rejects_nested_topical_page(command_workspace: CommandWorkspace) -> None:
    wiki_root = command_workspace.wiki_root
    _write_wiki_page(
        wiki_root,
        "concepts/coverage/nested-concept.md",
        _build_page("Nested Concept", "concept", "3"),
    )

    with pytest.raises(update_index.IndexGenerationError) as ctx:
        update_index.generate_index_content(wiki_root)

    assert "nested topical markdown pages are not allowed" in str(ctx.value)


def test_cli_check_fails_closed_for_nested_topical_page(command_workspace: CommandWorkspace) -> None:
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    _write_wiki_page(
        wiki_root,
        "entities/medicare/beneficiary.md",
        _build_page("Nested Beneficiary", "entity", "5"),
    )

    completed = _run_cli_command(workspace, "--wiki-root", "wiki", "--check")

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "nested topical markdown pages are not allowed" in completed.stderr


def test_pool_parse_error(command_workspace: CommandWorkspace) -> None:
    workspace = command_workspace.workspace
    wiki_root = workspace / "test_wiki_root"
    wiki_root.mkdir(exist_ok=True)

    source_root = wiki_root / "sources"
    source_root.mkdir(exist_ok=True)

    # simulate multiple files to test executor parsing
    for i in range(55):
        page = source_root / f"good{i}.md"
        page.write_text(
            f"""---
type: source
title: "Good {i}"
status: active
sources: []
open_questions: []
confidence: 1
sensitivity: internal
updated_at: "2024-01-01T00:00:00Z"
tags:
  - test
---""",
            encoding="utf-8",
        )

    page = source_root / "bad.md"
    page.write_text("---bad", encoding="utf-8")

    with pytest.raises(update_index.IndexGenerationError):
        update_index.generate_index_content(wiki_root)

    exit_code, stdout, stderr = _run_command("--wiki-root", str(wiki_root), "--write")

    assert exit_code == 1
    assert "sources/bad.md: missing YAML frontmatter start delimiter" in stderr

    index_path = wiki_root / "index.md"
    assert not index_path.exists()


def test_write_rejects_symlinked_index_destination(command_workspace: CommandWorkspace) -> None:
    """write mode must fail closed when wiki/index.md itself is a symlink."""
    workspace, wiki_root = command_workspace.workspace, command_workspace.wiki_root
    external_target = workspace / "external-index.md"
    external_target.write_text("external\n", encoding="utf-8")
    index_path = wiki_root / "index.md"
    index_path.unlink()
    index_path.symlink_to(external_target)

    completed = _run_cli_command(workspace, "--wiki-root", "wiki", "--write")

    assert completed.returncode == 1
    assert "symlinked path component is not allowed" in completed.stderr
    assert external_target.read_text(encoding="utf-8") == "external\n"


def test_write_rejects_symlinked_wiki_directory(command_workspace: CommandWorkspace) -> None:
    """write mode must fail closed when the wiki/ dir itself is a symlink."""
    workspace = command_workspace.workspace
    external_wiki = workspace / "external-wiki"
    external_wiki.mkdir()
    (external_wiki / "index.md").write_text("external-wiki-index\n", encoding="utf-8")
    symlinked_wiki = workspace / "wiki-link"
    symlinked_wiki.symlink_to(external_wiki)

    completed = _run_cli_command(workspace, "--wiki-root", str(symlinked_wiki), "--write")

    assert completed.returncode == 1
    assert "symlinked path component is not allowed" in completed.stderr
    assert (external_wiki / "index.md").read_text(encoding="utf-8") == "external-wiki-index\n"


# ---------------------------------------------------------------------------
# Regression tests for #18: single lstat() per page in update_index.
#
# These guard the invariant that the output ordering is deterministic and
# symlink detection still works after replacing is_file() + is_symlink()
# with a single os.lstat() call in _validate_section_page_path.
# ---------------------------------------------------------------------------


@pytest.fixture()
def optimization_wiki_root(tmp_path: Path) -> Path:
    wiki_root = tmp_path / "wiki"
    for section in WIKI_SECTIONS:
        (wiki_root / section).mkdir(parents=True, exist_ok=True)
    (wiki_root / ".kb_write.lock").write_text("", encoding="utf-8")
    return wiki_root


def test_index_output_is_deterministic_across_multiple_calls(optimization_wiki_root: Path) -> None:
    """generate_index_content must produce identical output across two calls."""
    wiki_root = optimization_wiki_root
    _write_wiki_page(wiki_root, "sources/z.md", _build_page("Z Source", "source"))
    _write_wiki_page(wiki_root, "sources/a.md", _build_page("A Source", "source"))
    _write_wiki_page(wiki_root, "concepts/c.md", _build_page("Concept", "concept"))

    first = update_index.generate_index_content(wiki_root)
    second = update_index.generate_index_content(wiki_root)
    assert first == second


def test_sort_order_is_alphabetical_by_title(optimization_wiki_root: Path) -> None:
    """Sources section must sort entries alphabetically by title."""
    wiki_root = optimization_wiki_root
    _write_wiki_page(wiki_root, "sources/z-source.md", _build_page("Z Source", "source"))
    _write_wiki_page(wiki_root, "sources/a-source.md", _build_page("A Source", "source"))
    content = update_index.generate_index_content(wiki_root)
    pos_a = content.find("A Source")
    pos_z = content.find("Z Source")
    assert pos_a < pos_z, "A Source must appear before Z Source in index"


def test_symlinked_page_raises_index_generation_error(optimization_wiki_root: Path) -> None:
    """Symlinked pages must still raise IndexGenerationError after lstat optimization."""
    wiki_root = optimization_wiki_root
    real = wiki_root / "sources" / "real.md"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(_build_page("Real", "source"), encoding="utf-8")
    link = wiki_root / "sources" / "linked.md"
    os.symlink(real, link)

    with pytest.raises(update_index.IndexGenerationError) as ctx:
        update_index.generate_index_content(wiki_root)
    assert "symlinked" in str(ctx.value)


def test_validate_section_page_path_returns_none_for_non_regular_file() -> None:
    """_validate_section_page_path must return None for non-regular files (dirs, etc.)."""
    # Patch os.lstat to return a directory-mode stat so we exercise the
    # 'not S_ISREG(st.st_mode)' branch — the actual new code path added in #18.
    # (Passing a nonexistent path only exercises the OSError branch.)
    with tempfile.TemporaryDirectory() as td:
        wiki = Path(td).resolve()
        sources = wiki / "sources"
        sources.mkdir()
        real_file = sources / "dir-mode.md"
        real_file.write_text("", encoding="utf-8")
        dir_stat = os.stat_result((stat.S_IFDIR | 0o755, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        with patch("os.lstat", return_value=dir_stat):
            result = update_index._validate_section_page_path(real_file, wiki)
        assert result is None


def test_validate_section_page_path_returns_none_on_lstat_oserror() -> None:
    """_validate_section_page_path must return None and not raise when os.lstat raises OSError."""
    with tempfile.TemporaryDirectory() as td:
        wiki = Path(td).resolve()
        sources = wiki / "sources"
        sources.mkdir()
        real_file = sources / "disappears.md"
        real_file.write_text("", encoding="utf-8")
        with patch("os.lstat", side_effect=OSError("permission denied")):
            result = update_index._validate_section_page_path(real_file, wiki)
        assert result is None


def test_collect_section_entries_passes_lazy_generator_to_executor_map(
    optimization_wiki_root: Path,
) -> None:
    """Regression test for #553: `_collect_section_entries` must hand
    `executor.map()` a lazy generator (not a pre-built list) so chunked
    dispatch can begin without first materializing every path, and it
    must preserve the documented chunksize=100 contract."""
    wiki_root = optimization_wiki_root

    class _RecordingExecutor:
        def __init__(self) -> None:
            self.received_iterable_type: type | None = None
            self.received_chunksize: int | None = None

        def map(self, func, page_paths, repeated_wiki_root, chunksize=None):
            self.received_iterable_type = type(page_paths)
            self.received_chunksize = chunksize
            # Consume lazily, mirroring ProcessPoolExecutor.map's contract.
            return [
                func(page_path, wiki_root)
                for page_path, wiki_root in zip(page_paths, repeated_wiki_root)
            ]

    _write_wiki_page(wiki_root, "sources/z-source.md", _build_page("Z Source", "source"))
    _write_wiki_page(wiki_root, "sources/a-source.md", _build_page("A Source", "source"))

    executor = _RecordingExecutor()
    entries = update_index._collect_section_entries(wiki_root, "sources", executor=executor)

    assert executor.received_iterable_type.__name__ == "generator"
    assert executor.received_chunksize == 100
    assert [entry.title for entry in entries] == ["A Source", "Z Source"]


def test_collect_section_entries_ordering_matches_with_and_without_executor(
    optimization_wiki_root: Path,
) -> None:
    """Regression test for #553: the lazy-generator refactor must not
    change output content or ordering between the executor-dispatched
    path and the sequential (executor=None) path."""
    wiki_root = optimization_wiki_root

    class _RecordingExecutor:
        def map(self, func, page_paths, repeated_wiki_root, chunksize=None):
            return [
                func(page_path, wiki_root)
                for page_path, wiki_root in zip(page_paths, repeated_wiki_root)
            ]

    _write_wiki_page(wiki_root, "sources/z-source.md", _build_page("Z Source", "source"))
    _write_wiki_page(wiki_root, "sources/a-source.md", _build_page("A Source", "source"))
    _write_wiki_page(wiki_root, "sources/m-source.md", _build_page("M Source", "source"))

    sequential = update_index._collect_section_entries(wiki_root, "sources", executor=None)
    parallel = update_index._collect_section_entries(
        wiki_root, "sources", executor=_RecordingExecutor()
    )

    sequential_keys = [(entry.title, entry.relative_path) for entry in sequential]
    parallel_keys = [(entry.title, entry.relative_path) for entry in parallel]
    assert sequential_keys == parallel_keys
    assert sequential_keys == [
        ("A Source", "sources/a-source.md"),
        ("M Source", "sources/m-source.md"),
        ("Z Source", "sources/z-source.md"),
    ]
