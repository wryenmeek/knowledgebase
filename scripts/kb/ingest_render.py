"""Pure rendering helpers for source ingest: SourceRef construction and page content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import os
import subprocess

from scripts.kb.sourceref import validate_sourceref

__all__ = [
    "PROVISIONAL_GIT_SHA",
    "SourceProvenance",
    "build_source_ref",
    "build_provisional_source_provenance",
    "render_source_page",
    "escape_quotes",
    "resolve_ingest_git_sha",
]

PROVISIONAL_GIT_SHA = "0" * 40
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def resolve_ingest_git_sha(repo_root: Path) -> tuple[str, str]:
    """Return ``(sha, kind)`` for the current ingest context.

    Resolution order:
    1. ``GITHUB_SHA`` environment variable (CI commits) → ``ci_commit_sha``
    2. ``git rev-parse HEAD`` in *repo_root* → ``head_sha``
    3. Fallback: ``PROVISIONAL_GIT_SHA`` → ``placeholder``

    Always returns a valid 40-hex SHA string.
    """
    env_sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    if _SHA_RE.match(env_sha):
        return env_sha, "ci_commit_sha"

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            head_sha = result.stdout.strip().lower()
            if _SHA_RE.match(head_sha):
                return head_sha, "head_sha"
    except OSError:
        pass

    return PROVISIONAL_GIT_SHA, "placeholder"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Structured provenance status for machine-readable ingest outputs."""

    status: str
    authoritative: bool
    review_mode: str
    reconciliation: str
    git_sha: str
    git_sha_kind: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "authoritative": self.authoritative,
            "review_mode": self.review_mode,
            "reconciliation": self.reconciliation,
            "git_sha": self.git_sha,
            "git_sha_kind": self.git_sha_kind,
        }


def build_source_ref(
    repo_root: Path,
    processed_relative: str,
    checksum: str,
    git_sha: str = PROVISIONAL_GIT_SHA,
) -> str:
    """Build and validate a provisional SourceRef for an ingested artifact."""
    repo_name = re.sub(r"[^A-Za-z0-9_.-]", "-", repo_root.name) or "repo"
    source_ref = (
        f"repo://local/{repo_name}/{processed_relative}@{git_sha}"
        f"#asset?sha256={checksum}"
    )
    validate_sourceref(source_ref)
    return source_ref


def build_provisional_source_provenance(
    git_sha: str = PROVISIONAL_GIT_SHA,
    git_sha_kind: str = "placeholder",
) -> SourceProvenance:
    """Return a ``SourceProvenance`` with the given (or placeholder) git SHA."""
    return SourceProvenance(
        status="provisional",
        authoritative=False,
        review_mode="authoritative_review_required",
        reconciliation="commit_bound_pending",
        git_sha=git_sha,
        git_sha_kind=git_sha_kind,
    )
    """Return a ``SourceProvenance`` with placeholder (provisional) values."""
    return SourceProvenance(
        status="provisional",
        authoritative=False,
        review_mode="authoritative_review_required",
        reconciliation="commit_bound_pending",
        git_sha=PROVISIONAL_GIT_SHA,
        git_sha_kind="placeholder",
    )


def render_source_page(
    *,
    source_relative: str,
    processed_relative: str,
    source_ref: str,
    provenance: SourceProvenance,
    source_bytes: bytes,
    checksum: str,
) -> str:
    """Render the wiki/sources markdown page for an ingested source."""
    title_token = Path(source_relative).stem.replace("_", " ").replace("-", " ").strip()
    normalized_title = (
        " ".join(title_token.split()).title() or Path(source_relative).name
    )
    page_title = f"Source: {normalized_title}"

    lines = [
        "---",
        "type: source",
        f'title: "{escape_quotes(page_title)}"',
        "status: active",
        "sources:",
        f'  - "{escape_quotes(source_ref)}"',
        "open_questions: []",
        "confidence: 5",
        "sensitivity: internal",
        'updated_at: "1970-01-01T00:00:00Z"',
        "tags:",
        "  - source",
        "---",
        "",
        f"# {page_title}",
        "",
        f"- inbox_path: `{source_relative}`",
        f"- processed_path: `{processed_relative}`",
        f"- sourceref: `{source_ref}`",
        f"- provenance_status: `{provenance.status}`",
        f"- provenance_authoritative: `{str(provenance.authoritative).lower()}`",
        f"- provenance_review_mode: `{provenance.review_mode}`",
        f"- provenance_reconciliation: `{provenance.reconciliation}`",
        f"- provenance_git_sha_kind: `{provenance.git_sha_kind}`",
        f"- checksum_sha256: `{checksum}`",
        f"- bytes: {len(source_bytes)}",
        "",
    ]
    return "\n".join(lines)


def escape_quotes(value: str) -> str:
    """Escape backslashes and double-quotes for embedding in YAML string values."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
