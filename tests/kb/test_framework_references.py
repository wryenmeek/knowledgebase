"""Self-audit checks for framework docs, skills, and wrapper references."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK_SKILLS = (
    "information-architecture-and-taxonomy",
    "ontology-and-entity-modeling",
    "knowledge-schema-and-metadata-governance",
    "entity-resolution-and-canonicalization",
    "search-and-discovery-optimization",
    "validate-wiki-governance",
    "sync-knowledgebase-state",
    "review-wiki-plan",
)
MARKDOWN_FILES = (
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "decisions" / "ADR-007-control-plane-layering-and-packaging.md",
    REPO_ROOT / "docs" / "ideas" / "wiki-curation-agent-framework.md",
    REPO_ROOT / "docs" / "mvp-runbook.md",
    *(
        REPO_ROOT / ".github" / "skills" / skill_name / "SKILL.md"
        for skill_name in FRAMEWORK_SKILLS
    ),
)
CANONICAL_SPEC_FILES = (
    REPO_ROOT / "AGENTS.md",
    *(REPO_ROOT / "docs" / "decisions").glob("*.md"),
)
WRAPPER_FILES = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "validate-wiki-governance"
    / "logic"
    / "validate_wiki_governance.py",
    REPO_ROOT
    / ".github"
    / "skills"
    / "sync-knowledgebase-state"
    / "logic"
    / "sync_knowledgebase_state.py",
)

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
BACKTICK_PATH_RE = re.compile(
    r"`((?:\.github|docs|schema|scripts|tests|wiki|raw)/[^`*<>]+|AGENTS\.md|README\.md)`"
)
PYTHON_COMMAND_RE = re.compile(r"(?:^|\s)python3\s+([./A-Za-z0-9_-]+\.py)\b", re.MULTILINE)
WRAPPER_SCRIPT_RE = re.compile(r'script_relative_path="([^"]+)"')
DEFERRED_SCRIPT_PREFIXES = (
    "scripts/validation/",
    "scripts/reporting/",
    "scripts/context/",
    "scripts/maintenance/",
    "scripts/ingest/",
)


class FrameworkReferenceAuditTests(unittest.TestCase):
    def test_markdown_links_resolve(self) -> None:
        for path in MARKDOWN_FILES:
            text = path.read_text(encoding="utf-8")
            for raw_target in MARKDOWN_LINK_RE.findall(text):
                target = raw_target.split("#", 1)[0]
                if not target or "://" in target:
                    continue
                with self.subTest(file=path.relative_to(REPO_ROOT).as_posix(), target=target):
                    self.assertFalse(target.startswith("/"))
                    self.assertTrue(self._resolve_doc_target(path, target).exists())

    def test_backticked_repo_paths_resolve(self) -> None:
        for path in MARKDOWN_FILES:
            text = path.read_text(encoding="utf-8")
            for target in BACKTICK_PATH_RE.findall(text):
                if target.startswith(DEFERRED_SCRIPT_PREFIXES):
                    continue
                if target not in {"AGENTS.md", "README.md"} and Path(target).suffix not in {
                    ".md",
                    ".py",
                }:
                    continue
                with self.subTest(file=path.relative_to(REPO_ROOT).as_posix(), target=target):
                    self.assertTrue((REPO_ROOT / target).exists())

    def test_python_commands_reference_real_scripts(self) -> None:
        for path in MARKDOWN_FILES:
            text = path.read_text(encoding="utf-8")
            for command_target in PYTHON_COMMAND_RE.findall(text):
                resolved = self._resolve_command_target(command_target)
                with self.subTest(
                    file=path.relative_to(REPO_ROOT).as_posix(),
                    command_target=command_target,
                ):
                    self.assertTrue(resolved.is_file())

    def test_audited_markdown_avoids_absolute_filesystem_paths(self) -> None:
        forbidden_prefixes = ("/Users/", "/private/", "/var/", "/opt/", "/etc/", "/home/")
        for path in MARKDOWN_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.relative_to(REPO_ROOT).as_posix()):
                for prefix in forbidden_prefixes:
                    self.assertNotIn(prefix, text)

    def test_wrapper_allowlist_paths_resolve(self) -> None:
        for wrapper_path in WRAPPER_FILES:
            text = wrapper_path.read_text(encoding="utf-8")
            for script_path in WRAPPER_SCRIPT_RE.findall(text):
                with self.subTest(
                    wrapper=wrapper_path.relative_to(REPO_ROOT).as_posix(),
                    script_path=script_path,
                ):
                    self.assertTrue((REPO_ROOT / script_path).is_file())

    def test_governance_docs_use_canonical_processed_spec_path(self) -> None:
        for path in CANONICAL_SPEC_FILES:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                self.assertNotIn("raw/inbox/SPEC.md", text)
                if "SPEC.md" in text:
                    self.assertIn("raw/processed/SPEC.md", text)

    def _resolve_doc_target(self, source_path: Path, target: str) -> Path:
        if target.startswith("/"):
            return Path(target)
        return (source_path.parent / target).resolve()

    def _resolve_command_target(self, target: str) -> Path:
        if target.startswith("/"):
            return Path(target)
        return (REPO_ROOT / target).resolve()


if __name__ == "__main__":
    unittest.main()
