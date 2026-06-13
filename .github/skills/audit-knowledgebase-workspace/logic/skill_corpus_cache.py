"""Skill-corpus cache for audit-workspace classifier prompt inputs.

The cache intentionally stores only each ``SKILL.md`` file's frontmatter and
first post-frontmatter paragraph. Per Decision Q11, invalidation is mtime-only:
touch-only changes re-extract, while content changes that reset mtime can remain
stale until a later chronicle run surfaces the missed redundancy.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.kb.page_template_utils import extract_frontmatter, parse_frontmatter
from scripts.kb.write_utils import check_no_symlink_path, write_text_capturing_previous_safe


CACHE_FILENAME = "skill-corpus.json"
CACHE_STRATEGY = "mtime_first_para"
GOVERNED_CACHE_ROOTS = ("wiki", "raw", "docs")

SkillCorpusEntry = dict[str, object]
SkillCorpus = dict[str, SkillCorpusEntry]


def get_skill_corpus(
    skill_root: str | Path,
    cache_dir: str | Path,
    *,
    force_refresh: bool = False,
) -> SkillCorpus:
    """Return cached frontmatter + first-paragraph entries for direct skill docs.

    ``skill_root`` is expected to be ``.github/skills`` or a test fixture with
    the same shape. Cache JSON is written to ``cache_dir / CACHE_FILENAME`` and
    keyed by each ``SKILL.md`` file's absolute path.
    """

    skill_root_path = Path(skill_root).resolve()
    if not skill_root_path.is_dir():
        raise FileNotFoundError(f"missing skill root: {skill_root_path}")

    cache_dir_path = _validate_cache_dir(skill_root_path, Path(cache_dir))
    cache_path = cache_dir_path / CACHE_FILENAME
    _check_cache_path(cache_dir_path, cache_path)

    cached_entries = {} if force_refresh else _load_cache(cache_path)
    corpus: SkillCorpus = {}
    cache_changed = force_refresh

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


def _cached_entry_is_fresh(entry: Any, *, mtime_ns: int) -> bool:
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("mtime_ns") == mtime_ns
        and entry.get("cache_strategy") == CACHE_STRATEGY
        and isinstance(entry.get("frontmatter"), dict)
        and isinstance(entry.get("first_paragraph"), str)
    )


def _normalize_cached_entry(entry: Any) -> SkillCorpusEntry:
    return {
        "frontmatter": dict(entry["frontmatter"]),
        "first_paragraph": entry["first_paragraph"],
        "mtime_ns": entry["mtime_ns"],
        "cache_strategy": CACHE_STRATEGY,
    }


def _load_cache(cache_path: Path) -> SkillCorpus:
    if not cache_path.exists():
        return {}
    check_no_symlink_path(cache_path)
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}

    cache: SkillCorpus = {}
    for key, value in payload.items():
        if isinstance(key, str) and isinstance(value, dict):
            cache[key] = value
    return cache


def _write_cache(cache_path: Path, corpus: SkillCorpus) -> None:
    serialized = json.dumps(corpus, indent=2, sort_keys=True)
    write_text_capturing_previous_safe(cache_path, f"{serialized}\n")


def _check_cache_path(cache_dir: Path, cache_path: Path) -> None:
    if cache_path.exists() or cache_path.is_symlink():
        check_no_symlink_path(cache_path)
    resolved_parent = cache_path.parent.resolve(strict=False)
    if resolved_parent != cache_dir:
        raise ValueError(f"cache path escapes cache directory: {cache_path}")


def _validate_cache_dir(skill_root: Path, cache_dir: Path) -> Path:
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


def _repo_root_for_skill_root(skill_root: Path) -> Path | None:
    if skill_root.name == "skills" and skill_root.parent.name == ".github":
        return skill_root.parents[1]
    return None


__all__ = [
    "CACHE_FILENAME",
    "CACHE_STRATEGY",
    "SkillCorpus",
    "SkillCorpusEntry",
    "default_cache_dir",
    "get_skill_corpus",
]
