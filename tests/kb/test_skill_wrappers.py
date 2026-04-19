"""Tests for thin governance/state skill wrappers."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.kb.harnesses import (
    HarnessAssertionsTestCase,
    REPO_ROOT,
    RuntimeWrapperFixtureTestCase as _RuntimeWrapperFixture,
    _DummyLock,
    force_thread_pool,
    load_module as _load_module,
)

VALIDATE_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "validate-wiki-governance"
    / "logic"
    / "validate_wiki_governance.py"
)
SYNC_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "sync-knowledgebase-state"
    / "logic"
    / "sync_knowledgebase_state.py"
)
BOUNDARY_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "enforce-repository-boundaries"
    / "logic"
    / "enforce_repository_boundaries.py"
)
PAGE_TEMPLATE_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "enforce-page-template"
    / "logic"
    / "enforce_page_template.py"
)
SOURCEREF_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "write-sourceref-citations"
    / "logic"
    / "write_sourceref_citations.py"
)
APPEND_LOG_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "append-log-entry"
    / "logic"
    / "append_log_entry.py"
)
MANAGE_REDIRECTS_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "manage-redirects-and-anchors"
    / "logic"
    / "manage_redirects.py"
)
COMPUTE_KPIS_WRAPPER_PATH = (
    REPO_ROOT / ".github" / "skills" / "compute-kpis" / "logic" / "compute_kpis.py"
)
ANALYZE_MISSED_QUERIES_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "analyze-missed-queries"
    / "logic"
    / "analyze_missed_queries.py"
)
VALIDATOR_WRAPPER_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "run-deterministic-validators"
    / "logic"
    / "run_deterministic_validators.py"
)
class ValidateWikiGovernanceWrapperTests(HarnessAssertionsTestCase):
    def test_validator_allowlist_matches_approved_post_mvp_checks(self) -> None:
        module = _load_module("validate_wiki_governance_allowlist", VALIDATE_WRAPPER_PATH)

        self.assertEqual(
            tuple(validator.value for validator in module.SUPPORTED_VALIDATORS),
            (
                "sourceref-shape",
                "page-template",
                "append-only-log",
                "topology-hygiene",
            ),
        )

    def test_freshness_threshold_is_opt_in_not_in_default_set(self) -> None:
        module = _load_module("validate_wiki_governance_freshness_optin", VALIDATE_WRAPPER_PATH)

        default_names = tuple(v.value for v in module.SUPPORTED_VALIDATORS)
        self.assertNotIn("freshness-threshold", default_names)
        self.assertIn("freshness-threshold", tuple(v.value for v in module.ALL_KNOWN_VALIDATORS))

    def test_freshness_threshold_recognized_when_explicitly_requested(self) -> None:
        module = _load_module("validate_wiki_governance_freshness_recognized", VALIDATE_WRAPPER_PATH)

        selected, unsupported = module.resolve_validators(["freshness-threshold"])
        self.assertIn(module.ValidatorName.FRESHNESS_THRESHOLD, selected)
        self.assertEqual(unsupported, ())

    def test_freshness_threshold_not_invoked_without_flag(self) -> None:
        module = _load_module("validate_wiki_governance_freshness_no_flag", VALIDATE_WRAPPER_PATH)

        with patch.object(module, "_validate_freshness_threshold") as freshness_mock:
            with patch.object(module, "print"):
                module.main([])

        freshness_mock.assert_not_called()

    def test_freshness_threshold_subprocess_prereq_missing_fails_closed(self) -> None:
        module = _load_module("validate_wiki_governance_freshness_prereq", VALIDATE_WRAPPER_PATH)
        import tempfile, pathlib

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = pathlib.Path(tmp)
            (repo_root / "wiki").mkdir()
            (repo_root / "wiki" / "log.md").write_text("- entry\n")
            # check_doc_freshness.py does NOT exist in this temp root
            findings = module._validate_freshness_threshold(repo_root, [])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].status, "fail")
        self.assertEqual(findings[0].reason_code, "prereq_missing")

    def test_protected_paths_default_to_blocking_mode(self) -> None:
        module = _load_module("validate_wiki_governance_modes", VALIDATE_WRAPPER_PATH)

        self.assertEqual(
            module.resolve_validation_mode(None, ("wiki/index.md",)),
            module.ValidationMode.BLOCKING,
        )
        self.assertEqual(
            module.resolve_validation_mode(None, ("README.md",)),
            module.ValidationMode.SIGNAL,
        )

    def test_unsupported_validator_hard_fails_for_protected_path(self) -> None:
        module = _load_module("validate_wiki_governance_unsupported", VALIDATE_WRAPPER_PATH)

        with patch.object(module, "print") as print_mock:
            exit_code = module.main(
                ["--mode", "signal", "--validator", "freshness", "--path", "wiki/index.md"]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn('"unsupported_validators": ["freshness"]', print_mock.call_args.args[0])

    def test_partial_results_hard_fail_for_protected_path(self) -> None:
        module = _load_module("validate_wiki_governance_partial", VALIDATE_WRAPPER_PATH)

        with patch.object(module, "print") as print_mock:
            exit_code = module.main(
                ["--mode", "signal", "--validator", "page-template", "--path", "wiki/log.md"]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn('"reason_code": "partial_results"', print_mock.call_args.args[0])

    def test_signal_mode_keeps_non_protected_partial_results_non_blocking(self) -> None:
        module = _load_module("validate_wiki_governance_signal", VALIDATE_WRAPPER_PATH)

        with patch.object(module, "print") as print_mock:
            exit_code = module.main(
                ["--mode", "signal", "--validator", "page-template", "--path", "README.md"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"effective_mode": "signal"', print_mock.call_args.args[0])


class SyncKnowledgebaseStateWrapperTests(HarnessAssertionsTestCase):
    def test_wrapper_allowlist_matches_expected_scripts(self) -> None:
        module = _load_module("sync_knowledgebase_state_allowlist", SYNC_WRAPPER_PATH)

        self.assertEqual(
            tuple(command.script_relative_path for command in module.READ_ONLY_PRECHECKS),
            (
                "scripts/kb/qmd_preflight.py",
                "scripts/kb/update_index.py",
                "scripts/kb/lint_wiki.py",
            ),
        )
        self.assertEqual(
            module.WRITE_INDEX_COMMAND.script_relative_path,
            "scripts/kb/update_index.py",
        )
        self.assertEqual(module.SUPPORTED_ARTIFACTS, module.contracts.GOVERNED_ARTIFACT_PATHS)

    def test_check_only_mode_stays_read_only(self) -> None:
        module = _load_module("sync_knowledgebase_state_check", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--check-only"])

        self.assertEqual(exit_code, 0)
        self.assert_wrapper_routing(
            calls,
            [
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--required-resource",
                    ".qmd/index",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "update_index.py"),
                    "--wiki-root",
                    "wiki",
                    "--check",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
            ],
        )

    def test_check_only_rejects_unsupported_artifact(self) -> None:
        module = _load_module("sync_knowledgebase_state_unsupported", SYNC_WRAPPER_PATH)

        exit_code = module.main(["--check-only", "--artifact", "wiki/entities/example.md"])

        self.assertEqual(exit_code, 1)

    def test_check_only_accepts_supported_non_index_artifact_without_running_scripts(self) -> None:
        module = _load_module("sync_knowledgebase_state_non_index_check", SYNC_WRAPPER_PATH)

        with patch.object(module.subprocess, "run") as run_mock:
            exit_code = module.main(["--check-only", "--artifact", "wiki/status.md"])

        self.assertEqual(exit_code, 0)
        run_mock.assert_not_called()

    def test_apply_mode_runs_validation_before_single_write_step(self) -> None:
        module = _load_module("sync_knowledgebase_state_apply", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)
        self.assert_wrapper_routing(
            calls,
            [
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--required-resource",
                    ".qmd/index",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--skip-orphan-check",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "update_index.py"),
                    "--wiki-root",
                    "wiki",
                    "--write",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
            ],
        )

    def test_write_mode_tolerates_stale_index_before_repair(self) -> None:
        module = _load_module("sync_knowledgebase_state_stale_index", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[1].endswith("update_index.py") and "--check" in command:
                raise AssertionError("write mode must not block on stale index drift")

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            calls[1][-6:],
            [
                "--skip-orphan-check",
                "--authoritative-sourcerefs",
                "--repo-owner",
                "local",
                "--repo-name",
                "knowledgebase",
            ],
        )
        self.assertEqual(calls[2][-1], "--write")
        self.assertEqual(
            calls[3][-6:],
            [
                "--strict",
                "--authoritative-sourcerefs",
                "--repo-owner",
                "local",
                "--repo-name",
                "knowledgebase",
            ],
        )

    def test_validation_failure_stops_before_write(self) -> None:
        module = _load_module("sync_knowledgebase_state_fail", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[1].endswith("lint_wiki.py"):
                raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(len(calls), 2)
        self.assertFalse(any(command[-1] == "--write" for command in calls))

    def test_write_failure_returns_non_zero_after_prechecks(self) -> None:
        module = _load_module("sync_knowledgebase_state_write_fail", SYNC_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)
            if command[-1] == "--write":
                raise module.subprocess.CalledProcessError(returncode=9, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 9)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1][-1], "--write")

    def test_append_log_mode_uses_lock_and_append_only_helper(self) -> None:
        module = _load_module("sync_knowledgebase_state_log", SYNC_WRAPPER_PATH)
        with patch.object(
            module.write_utils,
            "exclusive_write_lock",
            return_value=_DummyLock(REPO_ROOT / "wiki" / ".kb_write.lock"),
        ) as lock_mock, patch.object(
            module.write_utils,
            "append_log_only_state_changes",
            return_value=True,
        ) as append_mock:
            exit_code = module.main(["--append-log-entry", "- state changed", "--state-changed"])

        self.assertEqual(exit_code, 0)
        lock_mock.assert_called_once_with(module.REPO_ROOT)
        append_mock.assert_called_once_with(
            module.REPO_ROOT,
            "- state changed",
            state_changed=True,
        )

    def test_append_log_mode_noops_without_state_change(self) -> None:
        module = _load_module("sync_knowledgebase_state_log_noop", SYNC_WRAPPER_PATH)

        with patch.object(module.write_utils, "exclusive_write_lock") as lock_mock, patch.object(
            module.write_utils,
            "append_log_only_state_changes",
        ) as append_mock:
            exit_code = module.main(["--append-log-entry", "- state changed"])

        self.assertEqual(exit_code, 0)
        lock_mock.assert_not_called()
        append_mock.assert_not_called()

    def test_snapshot_write_mode_uses_lock_and_atomic_replace(self) -> None:
        module = _load_module("sync_knowledgebase_state_status", SYNC_WRAPPER_PATH)
        with patch.object(module, "_read_staged_repo_file", return_value="next\n") as read_mock, patch.object(
            module.write_utils,
            "exclusive_write_lock",
            return_value=_DummyLock(REPO_ROOT / "wiki" / ".kb_write.lock"),
        ) as lock_mock, patch.object(
            module.write_utils,
            "atomic_replace_governed_artifact",
            return_value=REPO_ROOT / "wiki" / "status.md",
        ) as replace_mock:
            exit_code = module.main(["--write-status-from", "wiki/status.next.md"])

        self.assertEqual(exit_code, 0)
        read_mock.assert_called_once_with("wiki/status.next.md")
        lock_mock.assert_called_once_with(module.REPO_ROOT)
        replace_mock.assert_called_once_with(module.REPO_ROOT, "wiki/status.md", "next\n")

    def test_snapshot_write_mode_fails_closed_on_lock_contention(self) -> None:
        module = _load_module("sync_knowledgebase_state_status_lock", SYNC_WRAPPER_PATH)

        with patch.object(module, "_read_staged_repo_file", return_value="next\n"), patch.object(
            module.write_utils,
            "exclusive_write_lock",
            side_effect=module.write_utils.LockUnavailableError(),
        ), patch.object(module.write_utils, "atomic_replace_governed_artifact") as replace_mock:
            exit_code = module.main(["--write-status-from", "wiki/status.next.md"])

        self.assertEqual(exit_code, 1)
        replace_mock.assert_not_called()

    def test_read_staged_repo_file_rejects_symlink_before_resolution(self) -> None:
        module = _load_module("sync_knowledgebase_state_symlink_reject", SYNC_WRAPPER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "wiki").mkdir(parents=True)
            external_target = repo_root / "external-secret.txt"
            external_target.write_text("secret\n", encoding="utf-8")
            staged_link = repo_root / "wiki" / "status.next.md"
            staged_link.symlink_to(external_target)

            with patch.object(module, "REPO_ROOT", repo_root):
                with self.assertRaises(module.SyncArgumentError) as exc:
                    module._read_staged_repo_file("wiki/status.next.md")

        self.assertEqual(
            exc.exception.reason_code,
            module.SyncReasonCode.INVALID_ARGUMENTS.value,
        )

    def test_read_staged_repo_file_rejects_symlinked_parent_directory(self) -> None:
        module = _load_module("sync_knowledgebase_state_symlink_parent_reject", SYNC_WRAPPER_PATH)
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            staged_root = repo_root / "staged"
            staged_root.mkdir(parents=True)
            (staged_root / "status.next.md").write_text("next\n", encoding="utf-8")
            (repo_root / "wiki-link").symlink_to(staged_root, target_is_directory=True)

            with patch.object(module, "REPO_ROOT", repo_root):
                with self.assertRaises(module.SyncArgumentError) as exc:
                    module._read_staged_repo_file("wiki-link/status.next.md")

        self.assertEqual(
            exc.exception.reason_code,
            module.SyncReasonCode.INVALID_ARGUMENTS.value,
        )

    def test_main_surfaces_sync_argument_errors_to_stderr(self) -> None:
        module = _load_module("sync_knowledgebase_state_error_output", SYNC_WRAPPER_PATH)

        with patch.object(
            module,
            "run_sync",
            side_effect=module.SyncArgumentError(
                module.SyncReasonCode.UNSUPPORTED_ARTIFACT,
                "unsupported governed artifact: wiki/entities/example.md",
            ),
        ), patch.object(module, "print") as print_mock:
            exit_code = module.main(["--check-only", "--artifact", "wiki/entities/example.md"])

        self.assertEqual(exit_code, 1)
        print_mock.assert_called_once()
        self.assertIn("unsupported governed artifact", print_mock.call_args.args[0])
        self.assertEqual(print_mock.call_args.kwargs["file"], module.sys.stderr)

    def test_main_surfaces_os_errors_to_stderr(self) -> None:
        module = _load_module("sync_knowledgebase_state_oserror_output", SYNC_WRAPPER_PATH)

        with patch.object(module, "run_sync", side_effect=OSError("disk full")), patch.object(
            module, "print"
        ) as print_mock:
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 1)
        print_mock.assert_called_once_with("disk full", file=module.sys.stderr)


class EnforceRepositoryBoundariesWrapperTests(HarnessAssertionsTestCase):
    def test_write_boundary_allowlist_matches_contract_paths(self) -> None:
        module = _load_module("enforce_repository_boundaries_allowlist", BOUNDARY_WRAPPER_PATH)

        self.assertEqual(module.WRITE_ALLOWLIST_GLOBS, module.contracts.WRITE_ALLOWLIST_PATHS)

    def test_write_boundary_accepts_allowlisted_paths_and_rejects_others(self) -> None:
        module = _load_module("enforce_repository_boundaries_paths", BOUNDARY_WRAPPER_PATH)

        allowed = module.enforce_repository_boundary("wiki/index.md", mode=module.AccessMode.WRITE)
        denied = module.enforce_repository_boundary(
            "docs/architecture.md",
            mode=module.AccessMode.WRITE,
        )
        traversal = module.enforce_repository_boundary(
            "../wiki/index.md",
            mode=module.AccessMode.WRITE,
        )

        self.assert_boundary_decision(
            allowed,
            allowed=True,
            reason_code=module.BoundaryReasonCode.OK.value,
        )
        self.assert_boundary_decision(
            denied,
            allowed=False,
            reason_code=module.BoundaryReasonCode.PATH_NOT_ALLOWLISTED.value,
        )
        self.assert_boundary_decision(
            traversal,
            allowed=False,
            reason_code=module.BoundaryReasonCode.PATH_TRAVERSAL.value,
        )

    def test_write_boundary_rejects_non_canonical_path_forms(self) -> None:
        module = _load_module("enforce_repository_boundaries_noncanonical", BOUNDARY_WRAPPER_PATH)

        dotted = module.enforce_repository_boundary("./wiki/index.md", mode=module.AccessMode.WRITE)
        doubled = module.enforce_repository_boundary("wiki//index.md", mode=module.AccessMode.WRITE)

        self.assert_boundary_decision(
            dotted,
            allowed=False,
            reason_code=module.BoundaryReasonCode.INVALID_PATH.value,
        )
        self.assert_boundary_decision(
            doubled,
            allowed=False,
            reason_code=module.BoundaryReasonCode.INVALID_PATH.value,
        )


class EnforcePageTemplateWrapperTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True

    def test_wrapper_rejects_traversal_outside_wiki_root(self) -> None:
        module = _load_module("enforce_page_template_traversal", PAGE_TEMPLATE_WRAPPER_PATH)
        docs_path = self.repo_root / "docs"
        docs_path.mkdir(parents=True, exist_ok=True)
        (docs_path / "escape.md").write_text("# Escape\n", encoding="utf-8")

        report = module.validate_page_template("wiki/../docs/escape.md", repo_root=self.repo_root)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.violations[0].code, "invalid-page-path")

    def test_wrapper_rejects_non_canonical_page_paths(self) -> None:
        module = _load_module("enforce_page_template_noncanonical", PAGE_TEMPLATE_WRAPPER_PATH)

        for candidate in ("./wiki/sources/source-a.md", "wiki//sources/source-a.md", "wiki/./sources/source-a.md"):
            with self.subTest(candidate=candidate):
                report = module.validate_page_template(candidate, repo_root=self.repo_root)
                self.assertFalse(report.is_valid)
                self.assertEqual(report.violations[0].code, "invalid-page-path")

    def test_wrapper_accepts_valid_source_page(self) -> None:
        module = _load_module("enforce_page_template_valid", PAGE_TEMPLATE_WRAPPER_PATH)
        source_ref = (
            "repo://local/repo/raw/processed/source-a.md@aaaaaaaa#asset"
            "?sha256=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )
        self.write_source_page(
            sources_lines=["sources:", f'  - "{source_ref}"'],
            body="\n".join(
                [
                    "## Summary",
                    "Authoritative summary.",
                    "",
                    "## Evidence",
                    f"- {source_ref}: supports Source A.",
                    "",
                    "## Open Questions",
                    "- None.",
                ]
            ),
        )

        report = module.validate_page_template("wiki/sources/source-a.md", repo_root=self.repo_root)

        self.assertTrue(report.is_valid)
        self.assertEqual(report.violations, ())

    def test_wrapper_requires_actual_section_headings_not_body_substrings(self) -> None:
        module = _load_module("enforce_page_template_heading", PAGE_TEMPLATE_WRAPPER_PATH)
        self.write_source_page(
            sources_lines=["sources: []"],
            body=(
                "## Summary\n"
                "This paragraph mentions ## Evidence and ## Open Questions but never defines those headings."
            ),
        )

        report = module.validate_page_template("wiki/sources/source-a.md", repo_root=self.repo_root)

        self.assertFalse(report.is_valid)
        self.assertEqual(
            tuple(violation.code for violation in report.violations),
            ("missing-body-section", "missing-body-section"),
        )

    def test_wrapper_ignores_heading_like_text_inside_fenced_code_blocks(self) -> None:
        module = _load_module("enforce_page_template_fenced", PAGE_TEMPLATE_WRAPPER_PATH)
        self.write_source_page(
            sources_lines=["sources: []"],
            body="\n".join(
                [
                    "## Summary",
                    "The real page omits the required sections.",
                    "",
                    "```md",
                    "## Evidence",
                    "## Open Questions",
                    "```",
                ]
            ),
        )

        report = module.validate_page_template("wiki/sources/source-a.md", repo_root=self.repo_root)

        self.assertFalse(report.is_valid)
        self.assertEqual(
            tuple(violation.code for violation in report.violations),
            ("missing-body-section", "missing-body-section"),
        )

    def test_wrapper_reports_missing_required_sections(self) -> None:
        module = _load_module("enforce_page_template_invalid", PAGE_TEMPLATE_WRAPPER_PATH)
        self.write_source_page(
            sources_lines=["sources: []"],
            body="## Summary\nMissing the rest.",
        )

        report = module.validate_page_template("wiki/sources/source-a.md", repo_root=self.repo_root)

        self.assertFalse(report.is_valid)
        self.assertEqual(
            tuple(violation.code for violation in report.violations),
            ("missing-body-section", "missing-body-section"),
        )


class WriteSourceRefCitationsWrapperTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True

    def test_wrapper_generates_authoritative_citation_for_committed_artifact(self) -> None:
        module = _load_module("write_sourceref_citations_runtime", SOURCEREF_WRAPPER_PATH)

        result = module.build_sourceref_citation(
            source_path="raw/processed/source-a.md",
            anchor="asset",
            git_ref="HEAD",
            repo_root=self.repo_root,
        )

        self.assertTrue(result.source_ref.startswith("repo://local/repo/raw/processed/source-a.md@"))
        self.assertIn("#asset?sha256=", result.source_ref)
        self.assertEqual(result.source_path, "raw/processed/source-a.md")

    def test_wrapper_rejects_paths_outside_raw_allowlist(self) -> None:
        module = _load_module("write_sourceref_citations_invalid", SOURCEREF_WRAPPER_PATH)

        with self.assertRaises(module.SourceRefCitationError) as exc:
            module.build_sourceref_citation(
                source_path="wiki/index.md",
                anchor="asset",
                git_ref="HEAD",
                repo_root=self.repo_root,
            )

        self.assertEqual(
            exc.exception.reason_code,
            module.CitationReasonCode.PATH_NOT_ALLOWLISTED.value,
        )

    def test_wrapper_rejects_non_canonical_raw_paths(self) -> None:
        module = _load_module("write_sourceref_citations_noncanonical", SOURCEREF_WRAPPER_PATH)

        for candidate in (
            "raw//processed/source-a.md",
            "./raw/processed/source-a.md",
            "raw/./processed/source-a.md",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(module.SourceRefCitationError) as exc:
                    module.build_sourceref_citation(
                        source_path=candidate,
                        anchor="asset",
                        git_ref="HEAD",
                        repo_root=self.repo_root,
                    )

                self.assertEqual(
                    exc.exception.reason_code,
                    module.CitationReasonCode.INVALID_PATH.value,
                )


class AppendLogEntryWrapperTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True

    def test_wrapper_appends_only_when_state_changes(self) -> None:
        module = _load_module("append_log_entry_runtime", APPEND_LOG_WRAPPER_PATH)

        result = module.append_log_entry(
            "- state changed",
            state_changed=True,
            repo_root=self.repo_root,
        )

        self.assertTrue(result.appended)
        self.assert_append_only(
            self.repo_root / "wiki" / "log.md",
            self._build_page("Knowledgebase Log", "- state changes"),
            expected_suffix="- state changed\n",
        )

    def test_wrapper_noops_without_state_change(self) -> None:
        module = _load_module("append_log_entry_noop", APPEND_LOG_WRAPPER_PATH)
        before = (self.repo_root / "wiki" / "log.md").read_text(encoding="utf-8")

        result = module.append_log_entry(
            "- no change",
            state_changed=False,
            repo_root=self.repo_root,
        )

        self.assertFalse(result.appended)
        self.assertEqual((self.repo_root / "wiki" / "log.md").read_text(encoding="utf-8"), before)

    def test_wrapper_rejects_multiline_entries(self) -> None:
        module = _load_module("append_log_entry_multiline", APPEND_LOG_WRAPPER_PATH)

        with self.assertRaises(module.LogAppendError) as exc:
            module.append_log_entry(
                "- first line\n- second line",
                state_changed=True,
                repo_root=self.repo_root,
            )

        self.assertEqual(exc.exception.reason_code, module.LogReasonCode.INVALID_ENTRY.value)

    def test_main_returns_deterministic_lock_unavailable_payload(self) -> None:
        module = _load_module("append_log_entry_locked", APPEND_LOG_WRAPPER_PATH)
        with patch.object(
            module.write_utils,
            "exclusive_write_lock",
            side_effect=module.write_utils.LockUnavailableError(),
        ), patch.object(module, "print") as print_mock:
            exit_code = module.main(["--entry", "- state changed", "--state-changed"])

        self.assertEqual(exit_code, 1)
        self.assertIn(module.LogReasonCode.LOCK_UNAVAILABLE.value, print_mock.call_args.args[0])


class RunDeterministicValidatorsWrapperTests(HarnessAssertionsTestCase):
    def test_validator_allowlist_matches_expected_scripts(self) -> None:
        module = _load_module("run_deterministic_validators_allowlist", VALIDATOR_WRAPPER_PATH)

        self.assertEqual(
            tuple(spec.script_relative_path for spec in module.VALIDATOR_ALLOWLIST.values()),
            (
                "scripts/kb/qmd_preflight.py",
                "scripts/kb/update_index.py",
                "scripts/kb/lint_wiki.py",
            ),
        )

    def test_wrapper_runs_selected_validator_subset_in_declared_order(self) -> None:
        module = _load_module("run_deterministic_validators_subset", VALIDATOR_WRAPPER_PATH)
        calls: list[list[str]] = []

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            calls.append(command)

        with patch.object(module.subprocess, "run", side_effect=fake_run):
            exit_code = module.main(["--validator", "qmd-preflight", "--validator", "lint-strict"])

        self.assertEqual(exit_code, 0)
        self.assert_wrapper_routing(
            calls,
            [
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "qmd_preflight.py"),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--required-resource",
                    ".qmd/index",
                ],
                [
                    module.sys.executable,
                    str(REPO_ROOT / "scripts" / "kb" / "lint_wiki.py"),
                    "--wiki-root",
                    "wiki",
                    "--strict",
                    "--authoritative-sourcerefs",
                    "--repo-owner",
                    "local",
                    "--repo-name",
                    "knowledgebase",
                ],
            ],
        )

    def test_wrapper_rejects_unknown_validator_names(self) -> None:
        module = _load_module("run_deterministic_validators_invalid", VALIDATOR_WRAPPER_PATH)

        exit_code = module.main(["--validator", "not-a-validator"])

        self.assertEqual(exit_code, 2)

    def test_wrapper_emits_failure_payload_for_validator_errors(self) -> None:
        module = _load_module("run_deterministic_validators_failure", VALIDATOR_WRAPPER_PATH)

        def fake_run(command: list[str], *, cwd: Path, check: bool) -> None:
            raise module.subprocess.CalledProcessError(returncode=7, cmd=command)

        with patch.object(module.subprocess, "run", side_effect=fake_run), patch.object(module, "print") as print_mock:
            exit_code = module.main(["--validator", "qmd-preflight"])

        self.assertEqual(exit_code, 7)
        self.assertIn('"reason_code": "validator_failed"', print_mock.call_args.args[0])


class ValidateWikiGovernanceWrapperRuntimeTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True

    def test_wrapper_runs_end_to_end_with_approved_checks(self) -> None:
        self.write_valid_source_page()
        module = self._load_fixture_module(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "validate_wiki_governance_runtime",
        )

        with force_thread_pool(module):
            exit_code = module.main([])

        self.assertEqual(exit_code, 0)

    def test_wrapper_accepts_inline_single_source_frontmatter(self) -> None:
        self.write_valid_source_page(inline_sources=True)
        module = self._load_fixture_module(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "validate_wiki_governance_inline_source",
        )

        with force_thread_pool(module):
            exit_code = module.main(["--validator", "sourceref-shape"])

        self.assertEqual(exit_code, 0)

    def test_missing_log_prerequisite_hard_fails_for_protected_path(self) -> None:
        self.write_valid_source_page()
        (self.repo_root / "wiki" / "log.md").unlink()
        module = self._load_fixture_module(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "validate_wiki_governance_missing_log",
        )

        with patch.object(module, "print") as print_mock, force_thread_pool(module):
            exit_code = module.main(["--mode", "signal", "--validator", "append-only-log", "--path", "wiki/log.md"])

        self.assertEqual(exit_code, 1)
        self.assertIn('"reason_code": "prereq_missing"', print_mock.call_args.args[0])

    def test_topology_drift_hard_fails_for_protected_path(self) -> None:
        self.write_valid_source_page()
        (self.repo_root / "wiki" / "index.md").write_text(self._build_page("Knowledgebase Index", "- drifted"), encoding="utf-8")
        module = self._load_fixture_module(
            ".github/skills/validate-wiki-governance/logic/validate_wiki_governance.py",
            "validate_wiki_governance_drift",
        )

        with patch.object(module, "print") as print_mock, force_thread_pool(module):
            exit_code = module.main(["--mode", "signal", "--validator", "topology-hygiene", "--path", "wiki/index.md"])

        self.assertEqual(exit_code, 1)
        self.assertIn('wiki/index.md must match deterministic topology output', print_mock.call_args.args[0])


class SyncKnowledgebaseStateWrapperRuntimeTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True


    def test_write_index_mode_runs_end_to_end_with_authoritative_lint(self) -> None:
        module = self._load_fixture_module(
            ".github/skills/sync-knowledgebase-state/logic/sync_knowledgebase_state.py",
            "sync_knowledgebase_state_runtime",
        )

        with patch.dict(os.environ, {"PATH": self.fixture_path}, clear=False):
            exit_code = module.main(["--write-index"])

        self.assertEqual(exit_code, 0)


class ManageRedirectsWrapperTests(_RuntimeWrapperFixture):
    INIT_FIXTURE_REPO = True

    def setUp(self) -> None:
        super().setUp()
        (self.repo_root / "AGENTS.md").write_text("knowledgebase fixture\n", encoding="utf-8")

    def _run_redirects(self, **kwargs):
        module = _load_module("manage_redirects", MANAGE_REDIRECTS_WRAPPER_PATH)
        return module.run_manage_redirects(repo_root=self.repo_root, **kwargs)

    def test_propose_mode_is_read_only_and_returns_preview(self) -> None:
        result = self._run_redirects(
            mode="propose",
            old_slug="old-page",
            new_slug="new-page",
            reason="renamed",
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.mode, "propose")
        self.assertIn("old-page", result.items[0]["proposed_row"])
        self.assertIn("new-page", result.items[0]["proposed_row"])
        self.assertFalse((self.repo_root / "wiki" / "redirects.md").exists())

    def test_apply_mode_requires_approval(self) -> None:
        result = self._run_redirects(
            mode="apply",
            old_slug="old-page",
            new_slug="new-page",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "approval_required")
        self.assertFalse((self.repo_root / "wiki" / "redirects.md").exists())

    def test_apply_mode_creates_redirects_file_with_row(self) -> None:
        result = self._run_redirects(
            mode="apply",
            old_slug="old-page",
            new_slug="new-page",
            reason="renamed by maintainer",
            approval="approved",
        )

        self.assertEqual(result.status, "pass")
        redirects_path = self.repo_root / "wiki" / "redirects.md"
        self.assertTrue(redirects_path.exists())
        content = redirects_path.read_text(encoding="utf-8")
        self.assertIn("| old-page |", content)
        self.assertIn("| new-page |", content)
        self.assertIn("renamed by maintainer", content)

    def test_apply_mode_rejects_duplicate_redirect(self) -> None:
        self._run_redirects(
            mode="apply",
            old_slug="old-page",
            new_slug="new-page",
            reason="first",
            approval="approved",
        )
        result = self._run_redirects(
            mode="apply",
            old_slug="old-page",
            new_slug="new-page",
            reason="duplicate attempt",
            approval="approved",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.reason_code, "duplicate_redirect")

    def test_slug_normalization_lowercases_and_hyphenates(self) -> None:
        result = self._run_redirects(
            mode="propose",
            old_slug="Medicare Advantage Part C",
            new_slug="New Name",
        )

        self.assertEqual(result.summary["old_slug"], "medicare-advantage-part-c")
        self.assertEqual(result.summary["new_slug"], "new-name")

    def test_removed_new_slug_is_accepted(self) -> None:
        result = self._run_redirects(
            mode="apply",
            old_slug="deleted-page",
            new_slug="REMOVED",
            reason="page deleted",
            approval="approved",
        )

        self.assertEqual(result.status, "pass")
        content = (self.repo_root / "wiki" / "redirects.md").read_text(encoding="utf-8")
        self.assertIn("| REMOVED |", content)

    def test_apply_mode_rejects_pipe_in_reason_does_not_corrupt_table(self) -> None:
        result = self._run_redirects(
            mode="apply",
            old_slug="old-page",
            new_slug="new-page",
            reason="see history | was split from Part-C",
            approval="approved",
        )

        self.assertEqual(result.status, "pass")
        content = (self.repo_root / "wiki" / "redirects.md").read_text(encoding="utf-8")
        # Pipe in reason must be sanitized; the row must have exactly 4 columns
        for line in content.splitlines():
            if line.startswith("| old-page |"):
                self.assertEqual(line.count("|"), 5)  # 4 cells = 5 separators

    def test_apply_mode_no_false_positive_on_target_slug_as_new_old_slug(self) -> None:
        # Chain redirect: first foo→bar, then bar→baz
        self._run_redirects(
            mode="apply",
            old_slug="foo",
            new_slug="bar",
            reason="renamed",
            approval="approved",
        )
        # bar is already a new_slug — should NOT be treated as duplicate old_slug
        result = self._run_redirects(
            mode="apply",
            old_slug="bar",
            new_slug="baz",
            reason="renamed again",
            approval="approved",
        )

        self.assertEqual(result.status, "pass")
        content = (self.repo_root / "wiki" / "redirects.md").read_text(encoding="utf-8")
        self.assertIn("| foo | bar |", content)
        self.assertIn("| bar | baz |", content)


class ComputeKpisWrapperTests(_RuntimeWrapperFixture):
    """Tests for compute-kpis read-only KPI snapshot logic."""

    def setUp(self) -> None:
        super().setUp()
        (self.repo_root / "AGENTS.md").write_text("knowledgebase fixture\n")
        (self.repo_root / "wiki" / "reports").mkdir(parents=True, exist_ok=True)

    def _run_kpis(self, **kwargs):
        module = _load_module("compute_kpis", COMPUTE_KPIS_WRAPPER_PATH)
        return module.run_compute_kpis(repo_root=self.repo_root, **kwargs)

    def test_no_score_files_returns_empty_snapshot(self) -> None:
        result = self._run_kpis(mode="snapshot")
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["artifact_count"], 0)
        self.assertEqual(result.summary["kpis"], {})
        self.assertIn("empty", result.message)

    def test_score_file_computes_kpis(self) -> None:
        artifact = {
            "report_type": "quality-scores",
            "generated_at": "2025-01-01T00:00:00Z",
            "scope": "wiki",
            "findings": [
                {"page_path": "wiki/page-a.md", "score": 0.9},
                {"page_path": "wiki/page-b.md", "score": 0.3},
                {"page_path": "wiki/page-c.md", "score": 0.7},
            ],
        }
        import json
        (self.repo_root / "wiki" / "reports" / "quality-scores-2025-01-01.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
        result = self._run_kpis(mode="snapshot")
    def test_score_file_skips_malformed_json_gracefully(self) -> None:
        import json
        (self.repo_root / "wiki" / "reports" / "quality-scores-good.json").write_text(
            json.dumps({"findings": [{"page_path": "wiki/p.md", "score": 0.8}]}),
            encoding="utf-8",
        )
        (self.repo_root / "wiki" / "reports" / "quality-scores-bad.json").write_text(
            "not valid json {{", encoding="utf-8"
        )
        result = self._run_kpis(mode="snapshot")
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["artifact_count"], 2)
        # malformed file is skipped; KPIs are computed from the valid file only
        self.assertEqual(result.summary["kpis"]["page_count"], 1)

    def test_findings_without_numeric_scores_returns_zero_page_count(self) -> None:
        import json
        # Findings exist but none have numeric "score" fields
        artifact = {"findings": [{"page_path": "wiki/p.md"}, {"page_path": "wiki/q.md"}]}
        (self.repo_root / "wiki" / "reports" / "quality-scores-noscores.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
        result = self._run_kpis(mode="snapshot")
        self.assertEqual(result.status, "pass")
        kpis = result.summary["kpis"]
        self.assertEqual(kpis["page_count"], 2)  # len(all_findings), not len(scores)
        self.assertIsNone(kpis["avg_score"])


class AnalyzeMissedQueriesWrapperTests(_RuntimeWrapperFixture):
    """Tests for analyze-missed-queries read-only coverage gap scan."""

    def setUp(self) -> None:
        super().setUp()
        (self.repo_root / "AGENTS.md").write_text("knowledgebase fixture\n")
        (self.repo_root / "wiki").mkdir(parents=True, exist_ok=True)

    def _run_scan(self, **kwargs):
        module = _load_module("analyze_missed_queries", ANALYZE_MISSED_QUERIES_WRAPPER_PATH)
        return module.run_analyze_missed_queries(repo_root=self.repo_root, **kwargs)

    def test_clean_page_no_gaps(self) -> None:
        (self.repo_root / "wiki" / "clean-page.md").write_text(
            "---\ntitle: Clean\n---\n\nAll good here.\n", encoding="utf-8"
        )
        result = self._run_scan(paths=["wiki/clean-page.md"])
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["gap_page_count"], 0)
        self.assertEqual(result.summary["scanned_count"], 1)

    def test_todo_page_detected_as_gap(self) -> None:
        (self.repo_root / "wiki" / "stub-page.md").write_text(
            "---\ntitle: Stub\n---\n\nTODO: add content here.\n", encoding="utf-8"
        )
        result = self._run_scan(paths=["wiki/stub-page.md"])
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["gap_page_count"], 1)
        items = result.items
        self.assertEqual(len(items), 1)
        self.assertIn("placeholder TODO marker", [g["gap_type"] for g in items[0]["gaps"]])

    def test_empty_sources_frontmatter_detected_as_gap(self) -> None:
        (self.repo_root / "wiki" / "no-sources.md").write_text(
            "---\ntitle: No Sources\nsources: []\n---\n\nSome body text.\n", encoding="utf-8"
        )
        result = self._run_scan(paths=["wiki/no-sources.md"])
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.summary["gap_page_count"], 1)
        gap_types = [g["gap_type"] for g in result.items[0]["gaps"]]
        self.assertIn("empty sources list in frontmatter", gap_types)

    def test_path_escape_rejected(self) -> None:
        result = self._run_scan(paths=["raw/inbox/some-file.md"])
        self.assertEqual(result.status, "fail")


if __name__ == "__main__":
    unittest.main()
