"""Pure rendering helpers for source ingest: SourceRef construction and page content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.kb.sourceref import validate_sourceref


_PROVISIONAL_GIT_SHA = "0" * 40


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


def _build_source_ref(repo_root: Path, processed_relative: str, checksum: str) -> str:
    """Build and validate a provisional SourceRef for an ingested artifact."""
    repo_name = re.sub(r"[^A-Za-z0-9_.-]", "-", repo_root.name) or "repo"
    source_ref = (
        f"repo://local/{repo_name}/{processed_relative}@{_PROVISIONAL_GIT_SHA}"
        f"#asset?sha256={checksum}"
    )
    validate_sourceref(source_ref)
    return source_ref


def _build_provisional_source_provenance() -> SourceProvenance:
    """Return a ``SourceProvenance`` with placeholder (provisional) values."""
    return SourceProvenance(
        status="provisional",
        authoritative=False,
        review_mode="authoritative_review_required",
        reconciliation="commit_bound_pending",
        git_sha=_PROVISIONAL_GIT_SHA,
        git_sha_kind="placeholder",
    )


def _render_source_page(
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
    normalized_title = " ".join(title_token.split()).title() or Path(source_relative).name
    page_title = f"Source: {normalized_title}"

    lines = [
        "---",
        "type: source",
        f'title: "{_escape_quotes(page_title)}"',
        "status: active",
        "sources:",
        f'  - "{_escape_quotes(source_ref)}"',
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


def _escape_quotes(value: str) -> str:
    """Escape backslashes and double-quotes for embedding in YAML string values."""
    return value.replace("\\", "\\\\").replace('"', '\\"')
