"""Skill-corpus cache for audit-workspace classifier prompt inputs.

The cache intentionally stores only each ``SKILL.md`` file's frontmatter and
first prose paragraph. Per Decision Q11, invalidation is mtime-only: touch-only
changes re-extract, while content changes that reset mtime can remain stale
until a later chronicle run surfaces the missed redundancy.

Tracking: issue #202 (slice 8a).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, TypedDict

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.kb.page_template_utils import extract_frontmatter, parse_frontmatter
from scripts.kb.write_utils import check_no_symlink_path, write_text_capturing_previous_safe


CACHE_FILENAME = "skill-corpus.json"
CACHE_STRATEGY = "mtime_first_para"
GOVERNED_CACHE_ROOTS = ("wiki", "raw", "docs")
CACHE_PAYLOAD_STRATEGY_KEY = "cache_strategy"
CACHE_PAYLOAD_ENTRIES_KEY = "entries"
ENTRY_FRONTMATTER_KEY = "frontmatter"
ENTRY_FIRST_PARAGRAPH_KEY = "first_paragraph"
ENTRY_MTIME_NS_KEY = "mtime_ns"


class SkillCorpusEntry(TypedDict):
    """Runtime cache entry returned to classifier callers."""

    frontmatter: dict[str, object]
    first_paragraph: str
    mtime_ns: int
    cache_strategy: str


class _PersistedSkillCorpusEntry(TypedDict):
    frontmatter: dict[str, object]
    first_paragraph: str
    mtime_ns: int


class _SkillCorpusCachePayload(TypedDict):
    cache_strategy: str
    entries: dict[str, _PersistedSkillCorpusEntry]


SkillCorpus = dict[str, SkillCorpusEntry]


def get_skill_corpus(
    skill_root: str | Path,
    cache_dir: str | Path,
    *,
    force_refresh: bool = False,
) -> SkillCorpus:
    """Return cached frontmatter + first prose paragraph entries for direct skill docs.

    ``skill_root`` is expected to be ``.github/skills`` or a test fixture with
    the same shape. Cache JSON is written to ``cache_dir / CACHE_FILENAME`` and
    keyed by each ``SKILL.md`` file's absolute path.
    """

    skill_root_path = Path(skill_root).resolve()
    if not skill_root_path.is_dir():
        raise FileNotFoundError(f"missing skill root: {skill_root_path}")

    cache_dir_path = _validate_cache_dir(skill_root_path, Path(cache_dir))
    cache_path = cache_dir_path / CACHE_FILENAME
    _check_cache_path(cache_path)

    cached_entries, cache_needs_rewrite = ({}, False) if force_refresh else _load_cache(cache_path)
    corpus: SkillCorpus = {}
    cache_changed = force_refresh or cache_needs_rewrite

    for skill_path in _iter_skill_files(skill_root_path):
        stat = skill_path.stat()
        cache_key = str(skill_path)
        cached_entry = cached_entries.get(cache_key)
        if (
            not force_refresh
            and _cached_entry_is_fresh(cached_entry, mtime_ns=stat.st_mtime_ns)
        ):
            corpus[cache_key] = _normalize_cached_entry(cached_entry)
            continue

        corpus[cache_key] = _extract_skill_entry(skill_path, stat.st_mtime_ns)
        cache_changed = True

    if set(cached_entries) != set(corpus):
        cache_changed = True
    if cache_changed:
        _write_cache(cache_path, corpus)

    return corpus


def default_cache_dir() -> Path:
    """Return the audit skill-local deterministic cache directory."""

    return Path(__file__).resolve().parents[1] / ".cache"


def _iter_skill_files(skill_root: Path) -> tuple[Path, ...]:
    skill_files: list[Path] = []
    for skill_path in sorted(skill_root.glob("*/SKILL.md")):
        resolved = skill_path.resolve()
        if not resolved.is_relative_to(skill_root):
            raise ValueError(f"path escape outside skill root: {skill_path}")
        skill_files.append(resolved)
    return tuple(skill_files)


def _extract_skill_entry(skill_path: Path, mtime_ns: int) -> SkillCorpusEntry:
    text = skill_path.read_text(encoding="utf-8")
    frontmatter_text, body = extract_frontmatter(text)
    frontmatter = parse_frontmatter(frontmatter_text) if frontmatter_text is not None else {}
    return {
        "frontmatter": frontmatter,
        "first_paragraph": _extract_first_paragraph(body),
        "mtime_ns": mtime_ns,
        "cache_strategy": CACHE_STRATEGY,
    }


def _extract_first_paragraph(body: str) -> str:
    """Return the first non-heading prose paragraph from a skill body."""

    paragraph_lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not paragraph_lines and not line.strip():
            continue
        if not paragraph_lines and stripped.startswith("#"):
            continue
        if paragraph_lines and not stripped:
            break
        paragraph_lines.append(line)
    return "\n".join(paragraph_lines)


def _cached_entry_is_fresh(entry: SkillCorpusEntry | None, *, mtime_ns: int) -> bool:
    """Return whether a validated cache entry matches current mtime and strategy."""

    if entry is None:
        return False
    return entry["mtime_ns"] == mtime_ns and entry["cache_strategy"] == CACHE_STRATEGY


def _normalize_cached_entry(entry: SkillCorpusEntry) -> SkillCorpusEntry:
    return {
        "frontmatter": dict(entry["frontmatter"]),
        "first_paragraph": entry["first_paragraph"],
        "mtime_ns": entry["mtime_ns"],
        "cache_strategy": entry["cache_strategy"],
    }


def _load_cache(cache_path: Path) -> tuple[SkillCorpus, bool]:
    if not cache_path.exists():
        return {}, False
    check_no_symlink_path(cache_path)
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, True
    if not isinstance(payload, dict):
        return {}, True

    cache_strategy = payload.get(CACHE_PAYLOAD_STRATEGY_KEY)
    entries = payload.get(CACHE_PAYLOAD_ENTRIES_KEY)
    if isinstance(cache_strategy, str) and isinstance(entries, dict):
        return _coerce_cache_entries(entries, cache_strategy=cache_strategy), False
    return _coerce_legacy_cache_entries(payload), True


def _write_cache(cache_path: Path, corpus: SkillCorpus) -> None:
    payload: _SkillCorpusCachePayload = {
        "cache_strategy": CACHE_STRATEGY,
        "entries": {
            cache_key: _persisted_cache_entry(entry) for cache_key, entry in corpus.items()
        },
    }
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    write_text_capturing_previous_safe(cache_path, f"{serialized}\n")


def _check_cache_path(cache_path: Path) -> None:
    """Reject symlinked cache path components before cache read/write."""

    if cache_path.exists() or cache_path.is_symlink():
        check_no_symlink_path(cache_path)


def _validate_cache_dir(skill_root: Path, cache_dir: Path) -> Path:
    """Resolve cache_dir to the skill-local path outside governed roots."""

    requested_cache_dir = cache_dir if cache_dir.is_absolute() else Path.cwd() / cache_dir
    check_no_symlink_path(requested_cache_dir)
    resolved_cache_dir = requested_cache_dir.resolve(strict=False)

    repo_root = _repo_root_for_skill_root(skill_root)
    if repo_root is None:
        return resolved_cache_dir
    for governed_root in GOVERNED_CACHE_ROOTS:
        if resolved_cache_dir.is_relative_to(repo_root / governed_root):
            raise ValueError(
                f"cache directory must not be under governed path: {resolved_cache_dir}"
            )
    allowed_cache_dir = skill_root / "audit-knowledgebase-workspace" / ".cache"
    check_no_symlink_path(allowed_cache_dir)
    if resolved_cache_dir != allowed_cache_dir.resolve(strict=False):
        raise ValueError(f"cache directory must be skill-local: {allowed_cache_dir}")
    return resolved_cache_dir


def _coerce_cache_entries(entries: dict[Any, Any], *, cache_strategy: str) -> SkillCorpus:
    if cache_strategy != CACHE_STRATEGY:
        return {}

    cache: SkillCorpus = {}
    for key, value in entries.items():
        entry = _coerce_cache_entry(value, cache_strategy=cache_strategy)
        if isinstance(key, str) and entry is not None:
            cache[key] = entry
    return cache


def _coerce_legacy_cache_entries(payload: dict[Any, Any]) -> SkillCorpus:
    cache: SkillCorpus = {}
    for key, value in payload.items():
        entry = _coerce_cache_entry(value, cache_strategy=None)
        if isinstance(key, str) and entry is not None:
            cache[key] = entry
    return cache


def _coerce_cache_entry(value: Any, *, cache_strategy: str | None) -> SkillCorpusEntry | None:
    if not isinstance(value, dict):
        return None

    resolved_cache_strategy = (
        cache_strategy
        if cache_strategy is not None
        else value.get(CACHE_PAYLOAD_STRATEGY_KEY)
    )
    frontmatter = value.get(ENTRY_FRONTMATTER_KEY)
    first_paragraph = value.get(ENTRY_FIRST_PARAGRAPH_KEY)
    mtime_ns = value.get(ENTRY_MTIME_NS_KEY)
    if (
        resolved_cache_strategy != CACHE_STRATEGY
        or not isinstance(frontmatter, dict)
        or not isinstance(first_paragraph, str)
        or not isinstance(mtime_ns, int)
        or isinstance(mtime_ns, bool)
    ):
        return None
    return {
        "frontmatter": dict(frontmatter),
        "first_paragraph": first_paragraph,
        "mtime_ns": mtime_ns,
        "cache_strategy": resolved_cache_strategy,
    }


def _persisted_cache_entry(entry: SkillCorpusEntry) -> _PersistedSkillCorpusEntry:
    return {
        "frontmatter": dict(entry["frontmatter"]),
        "first_paragraph": entry["first_paragraph"],
        "mtime_ns": entry["mtime_ns"],
    }


def _repo_root_for_skill_root(skill_root: Path) -> Path | None:
    if skill_root.name == "skills" and skill_root.parent.name == ".github":
        return skill_root.parents[1]
    return None


__all__ = [
    "CACHE_FILENAME",
    "CACHE_PAYLOAD_ENTRIES_KEY",
    "CACHE_PAYLOAD_STRATEGY_KEY",
    "CACHE_STRATEGY",
    "ENTRY_FIRST_PARAGRAPH_KEY",
    "ENTRY_FRONTMATTER_KEY",
    "ENTRY_MTIME_NS_KEY",
    "SkillCorpus",
    "SkillCorpusEntry",
    "default_cache_dir",
    "get_skill_corpus",
]
