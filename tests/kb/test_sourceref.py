"""Unit tests for SourceRef parsing and validation."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import unittest

from scripts.kb.sourceref import (
    SourceRefReasonCode,
    SourceRefValidationError,
    _validate_source_path,
    parse_sourceref,
    validate_sourceref,
)


_RUNTIME_ROOT = Path(__file__).resolve().parent / ".runtime_sourceref"


class SourceRefValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checksum = "a" * 64
        self.workspace = _RUNTIME_ROOT / self._testMethodName
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        (self.workspace / "raw" / "processed").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        if _RUNTIME_ROOT.exists() and not any(_RUNTIME_ROOT.iterdir()):
            _RUNTIME_ROOT.rmdir()

    def _git(self, *args: str, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            check=True,
            capture_output=capture_output,
            text=True,
        )

    def _init_git_repo(self) -> None:
        self._git("init")
        self._git("config", "user.name", "Test User")
        self._git("config", "user.email", "test@example.com")

    def _commit_all(self, message: str) -> str:
        self._git("add", ".")
        self._git("commit", "--allow-empty", "-m", message)
        return self._git("rev-parse", "HEAD", capture_output=True).stdout.strip()

    def test_parse_valid_sourceref(self) -> None:
        source_ref = parse_sourceref(
            "repo://owner/repo/raw/processed/source.md@abc1234"
            f"#L1-L2?sha256={self.checksum}"
        )

        self.assertEqual(source_ref.owner, "owner")
        self.assertEqual(source_ref.repo, "repo")
        self.assertEqual(source_ref.path, "raw/processed/source.md")
        self.assertEqual(source_ref.git_sha, "abc1234")
        self.assertEqual(source_ref.anchor, "L1-L2")
        self.assertEqual(source_ref.sha256, self.checksum)

    def test_missing_or_invalid_anchor(self) -> None:
        cases = (
            (
                "repo://owner/repo/raw/inbox/source.md@abc1234"
                f"?sha256={self.checksum}",
                "missing_anchor",
            ),
            (
                "repo://owner/repo/raw/inbox/source.md@abc1234"
                f"#bad anchor?sha256={self.checksum}",
                "invalid_anchor",
            ),
        )

        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    parse_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)

    def test_invalid_checksum(self) -> None:
        with self.assertRaises(SourceRefValidationError) as ctx:
            parse_sourceref(
                "repo://owner/repo/raw/assets/chart.png@abc1234"
                "#asset?sha256=deadbeef"
            )

        self.assertEqual(ctx.exception.reason_code, "invalid_checksum")

    def test_disallowed_path_or_traversal(self) -> None:
        cases = (
            (
                "repo://owner/repo/raw/other/source.md@abc1234"
                f"#L1-L2?sha256={self.checksum}",
                SourceRefReasonCode.PATH_NOT_ALLOWLISTED,
            ),
            (
                "repo://owner/repo/raw/inbox/../secrets.md@abc1234"
                f"#L1-L2?sha256={self.checksum}",
                SourceRefReasonCode.PATH_TRAVERSAL,
            ),
        )

        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    parse_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)

    def test_empty_string(self) -> None:
        cases = ("", "   ", "\n", "\t", "\r\n")
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    validate_sourceref(value)
                self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_FORMAT)

    def test_validate_source_path_invalid(self) -> None:
        cases = (
            ("/", SourceRefReasonCode.INVALID_PATH),
            ("/raw/inbox/file.md", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/file.md/", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/file\\md", SourceRefReasonCode.INVALID_PATH),
            ("raw//inbox/file.md", SourceRefReasonCode.INVALID_PATH),
            ("raw/inbox/.", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/./file.md", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/..", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/inbox/../file.md", SourceRefReasonCode.PATH_TRAVERSAL),
            ("raw/other/file.md", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
            ("something/else", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
            ("raw", SourceRefReasonCode.PATH_NOT_ALLOWLISTED),
        )
        for value, expected_reason in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    _validate_source_path(value)
                self.assertEqual(ctx.exception.reason_code, expected_reason)



    def test_validate_source_path_valid(self) -> None:
        valid_paths = (
            "raw/inbox/file.md",
            "raw/processed/some/dir/file.md",
            "raw/assets/image.png",
        )
        for path in valid_paths:
            with self.subTest(path=path):
                # Should not raise any exception
                _validate_source_path(path)

    def test_validate_source_path_empty(self) -> None:
        with self.assertRaises(SourceRefValidationError) as ctx:
            _validate_source_path("")
        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_PATH)

    def test_non_string_input(self) -> None:
        cases = (None, 123)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    validate_sourceref(value)  # type: ignore[arg-type]
                self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_STRUCTURE)

    def test_placeholder_git_sha_is_still_shape_valid_outside_authoritative_mode(self) -> None:
        parsed = validate_sourceref(
            f"repo://owner/repo/raw/processed/source.md@{'0' * 40}#asset?sha256={self.checksum}"
        )

        self.assertEqual(parsed.git_sha, "0" * 40)

    def test_authoritative_validation_rejects_placeholder_git_sha(self) -> None:
        self._init_git_repo()
        artifact_path = self.workspace / "raw" / "processed" / "source.md"
        artifact_path.write_text("authoritative\n", encoding="utf-8")
        self._commit_all("seed authoritative artifact")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        placeholder_shas = (
            "0" * 40,
            "f" * 40,
            "deadbeef" * 5,
        )

        for placeholder_sha in placeholder_shas:
            with self.subTest(git_sha=placeholder_sha):
                with self.assertRaises(SourceRefValidationError) as ctx:
                    validate_sourceref(
                        f"repo://owner/repo/raw/processed/source.md@{placeholder_sha}#asset?sha256={checksum}",
                        authoritative=True,
                        repo_root=self.workspace,
                    )

                self.assertEqual(
                    ctx.exception.reason_code,
                    SourceRefReasonCode.PLACEHOLDER_GIT_SHA,
                )

    def test_authoritative_validation_rejects_missing_git_revision(self) -> None:
        self._init_git_repo()
        artifact_path = self.workspace / "raw" / "processed" / "source.md"
        artifact_path.write_text("authoritative\n", encoding="utf-8")
        self._commit_all("seed authoritative artifact")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/repo/raw/processed/source.md@{'1' * 40}#asset?sha256={checksum}",
                authoritative=True,
                repo_root=self.workspace,
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.GIT_REVISION_MISSING)

    def test_authoritative_validation_rejects_missing_artifact_at_revision(self) -> None:
        self._init_git_repo()
        self._git("commit", "--allow-empty", "-m", "empty repository root")
        commit_sha = self._git("rev-parse", "HEAD", capture_output=True).stdout.strip()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/repo/raw/processed/missing.md@{commit_sha}#asset?sha256={self.checksum}",
                authoritative=True,
                repo_root=self.workspace,
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.ARTIFACT_MISSING)

    def test_authoritative_validation_rejects_checksum_mismatch_against_revision_content(self) -> None:
        self._init_git_repo()
        artifact_path = self.workspace / "raw" / "processed" / "source.md"
        artifact_path.write_text("committed bytes\n", encoding="utf-8")
        commit_sha = self._commit_all("seed authoritative artifact")
        artifact_path.write_text("working tree bytes\n", encoding="utf-8")
        working_tree_checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                (
                    "repo://owner/repo/raw/processed/source.md@"
                    f"{commit_sha}#asset?sha256={working_tree_checksum}"
                ),
                authoritative=True,
                repo_root=self.workspace,
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.CHECKSUM_MISMATCH)

    def test_authoritative_validation_accepts_existing_matching_artifact(self) -> None:
        self._init_git_repo()
        artifact_path = self.workspace / "raw" / "processed" / "source.md"
        artifact_path.write_text("authoritative\n", encoding="utf-8")
        commit_sha = self._commit_all("seed authoritative artifact")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        parsed = validate_sourceref(
            f"repo://owner/repo/raw/processed/source.md@{commit_sha}#asset?sha256={checksum}",
            authoritative=True,
            repo_root=self.workspace,
        )

        self.assertEqual(parsed.path, "raw/processed/source.md")
        self.assertEqual(parsed.sha256, checksum)

    def test_authoritative_validation_rejects_repo_identity_mismatch(self) -> None:
        self._init_git_repo()
        artifact_path = self.workspace / "raw" / "processed" / "source.md"
        artifact_path.write_text("authoritative\n", encoding="utf-8")
        commit_sha = self._commit_all("seed authoritative artifact")
        checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/other/raw/processed/source.md@{commit_sha}#asset?sha256={checksum}",
                authoritative=True,
                repo_root=self.workspace,
                expected_owner="owner",
                expected_repo="repo",
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.INVALID_REPO)

    def test_authoritative_validation_rejects_symlinked_artifact_in_raw_zone(self) -> None:
        self._init_git_repo()
        target_path = self.workspace / "raw" / "processed" / "actual.md"
        target_path.write_text("authoritative\n", encoding="utf-8")
        linked_path = self.workspace / "raw" / "processed" / "linked.md"
        linked_path.symlink_to(target_path)
        commit_sha = self._commit_all("seed symlinked artifact")
        checksum = hashlib.sha256(target_path.read_bytes()).hexdigest()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/repo/raw/processed/linked.md@{commit_sha}#asset?sha256={checksum}",
                authoritative=True,
                repo_root=self.workspace,
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.SYMLINKED_ARTIFACT)

    def test_authoritative_validation_rejects_resolved_path_outside_raw_zones(self) -> None:
        self._init_git_repo()
        redirected_target = self.workspace / "wiki" / "outside.md"
        redirected_target.parent.mkdir(parents=True, exist_ok=True)
        redirected_target.write_text("authoritative\n", encoding="utf-8")
        linked_path = self.workspace / "raw" / "processed" / "linked.md"
        linked_path.symlink_to(redirected_target)
        commit_sha = self._commit_all("seed redirected artifact")
        checksum = hashlib.sha256(redirected_target.read_bytes()).hexdigest()

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/repo/raw/processed/linked.md@{commit_sha}#asset?sha256={checksum}",
                authoritative=True,
                repo_root=self.workspace,
            )

        self.assertEqual(ctx.exception.reason_code, SourceRefReasonCode.PATH_NOT_ALLOWLISTED)

    def test_authoritative_validation_rejects_directory_artifact_at_revision(self) -> None:
        self._init_git_repo()
        artifact_dir = self.workspace / "raw" / "processed" / "bundle"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "item.txt").write_text("nested\n", encoding="utf-8")
        commit_sha = self._commit_all("seed directory artifact")

        with self.assertRaises(SourceRefValidationError) as ctx:
            validate_sourceref(
                f"repo://owner/repo/raw/processed/bundle@{commit_sha}#asset?sha256={self.checksum}",
                authoritative=True,
                repo_root=self.workspace,
            )

    def test_authoritative_validation_accepts_external_asset_path(self) -> None:
        """SourceRef pointing to raw/assets/{owner}/{repo}/{sha}/{path} passes validation.

        This is the regression test for ADR-012 / GitHub source monitoring:
        once a vendored external asset is committed, its SourceRef must pass
        authoritative validation via the normal raw/assets/** allowlist.
        """
        self._init_git_repo()
        asset_path = (
            self.workspace
            / "raw"
            / "assets"
            / "ext-owner"
            / "ext-repo"
            / ("a" * 40)
            / "docs"
            / "guide.md"
        )
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_text("# External guide\n", encoding="utf-8")
        commit_sha = self._commit_all("vendor external asset")
        checksum = hashlib.sha256(asset_path.read_bytes()).hexdigest()

        rel_path = asset_path.relative_to(self.workspace)
        parsed = validate_sourceref(
            f"repo://owner/repo/{rel_path}@{commit_sha}#asset?sha256={checksum}",
            authoritative=True,
            repo_root=self.workspace,
        )

        self.assertEqual(parsed.path, str(rel_path))
        self.assertEqual(parsed.sha256, checksum)


if __name__ == "__main__":
    unittest.main()
