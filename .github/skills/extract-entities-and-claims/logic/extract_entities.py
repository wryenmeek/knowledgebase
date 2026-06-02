"""
Extract entities and concepts from a wiki source page using GitHub Models API.

Read-only — no wiki writes. Outputs a JSON extraction bundle for downstream synthesis.
Self-correcting: feeds schema validation errors back to the LLM for up to 3 total attempts.
On persistent failure writes an empty bundle with `soft_skipped: true`.

GitHub token is read from the ``SYNTHESIS_GITHUB_TOKEN`` environment variable
(fallback: ``GITHUB_TOKEN``).  Do not pass it as a CLI argument.

CLI usage:
    python3 extract_entities.py \\
        --source-page wiki/sources/my-source.md \\
        --wiki-root wiki \\
        --output /tmp/extraction-bundle.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # repo root

from scripts.kb.page_template_utils import (
    extract_frontmatter,
    extract_sources_from_frontmatter,
    extract_yaml_list,
    parse_frontmatter,
)

_MAX_ATTEMPTS = 3
_GITHUB_MODELS_ENDPOINT = "https://models.inference.ai.azure.com"
_MODEL_ID = "gpt-4o-mini"
_REQUIRED_ITEM_KEYS = frozenset(
    {"title", "aliases", "summary", "evidence", "tags", "open_questions"}
)
_ALLOWED_ENDPOINT_HOSTS = frozenset({"models.inference.ai.azure.com"})


def _validate_endpoint(endpoint: str) -> bool:
    """Return True only if endpoint uses HTTPS and an allowed hostname."""
    try:
        parsed = urlparse(endpoint)
        return parsed.scheme == "https" and parsed.hostname in _ALLOWED_ENDPOINT_HOSTS
    except Exception:
        return False


def _resolve_repo_path_from_sourceref(source_ref: str) -> str | None:
    """Extract the repo-relative path segment from a canonical SourceRef."""
    if not source_ref:
        return None
    # repo://<owner>/<repo>/<path>@<git_sha>#...
    match = re.match(r"^repo://[^/]+/[^/]+/(?P<path>[^@]+)@", source_ref)
    if not match:
        return None
    path_part = (match.group("path") or "").strip()
    return path_part or None


def _load_primary_source_text(
    *,
    repo_root: Path,
    source_ref: str,
    fallback_text: str,
) -> str:
    """Prefer raw source text referenced by SourceRef; fallback to source-page body."""
    source_path_part = _resolve_repo_path_from_sourceref(source_ref)
    if not source_path_part:
        return fallback_text
    candidate = (repo_root / source_path_part).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        print(
            f"warning: source_ref path escapes repo root; falling back to source page body: {source_ref}",
            file=sys.stderr,
        )
        return fallback_text
    if not candidate.is_file():
        return fallback_text
    try:
        text = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"warning: failed reading source_ref path '{source_path_part}': {exc}; falling back to source page body.",
            file=sys.stderr,
        )
        return fallback_text
    return text if text.strip() else fallback_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract entities and concepts from a source page."
    )
    parser.add_argument(
        "--source-page",
        required=True,
        help="Repo-relative path to wiki/sources/<slug>.md",
    )
    parser.add_argument("--wiki-root", default="wiki", help="Wiki root directory")
    parser.add_argument("--output", required=True, help="Output JSON bundle path")
    parser.add_argument(
        "--endpoint",
        default=_GITHUB_MODELS_ENDPOINT,
        help="GitHub Models API base URL (must be an allowed hostname)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Existing-page scanning
# ---------------------------------------------------------------------------


def scan_existing_pages(wiki_root: Path, namespace: str) -> list[dict[str, Any]]:
    """Return a list of ``{title, aliases, path}`` for all pages in a namespace."""
    ns_dir = wiki_root / namespace
    if not ns_dir.is_dir():
        return []
    results = []
    for page_path in sorted(ns_dir.glob("*.md")):
        try:
            content = page_path.read_text(encoding="utf-8")
            fm_str, _ = extract_frontmatter(content)
            if fm_str is None:
                continue
            fm = parse_frontmatter(fm_str)
            title = fm.get("title", "").strip().strip('"').strip("'")
            aliases = extract_yaml_list(fm_str, "aliases")
            results.append({"title": title, "aliases": aliases, "path": str(page_path)})
        except Exception as exc:
            print(
                f"warning: scan_existing_pages: failed to parse {page_path}: {exc}",
                file=sys.stderr,
            )
    return results


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(
    source_title: str,
    source_body: str,
    existing_entities: list[dict[str, Any]],
    existing_concepts: list[dict[str, Any]],
    validation_errors: list[str] | None = None,
) -> str:
    def _page_line(p: dict[str, Any]) -> str:
        aliases_str = ", ".join(p["aliases"]) if p.get("aliases") else "no aliases"
        return f"  - {p['title']} ({aliases_str})"

    entity_list = (
        "\n".join(_page_line(e) for e in existing_entities[:30]) or "  (none)"
    )
    concept_list = (
        "\n".join(_page_line(c) for c in existing_concepts[:30]) or "  (none)"
    )

    error_section = ""
    if validation_errors:
        error_section = (
            "\n\n## CORRECTION REQUIRED\n"
            "Your previous response failed validation. Fix these errors:\n"
            + "\n".join(f"  - {e}" for e in validation_errors)
        )

    MAX_BODY_LEN = 3500
    if len(source_body) > MAX_BODY_LEN:
        body_excerpt = source_body[:MAX_BODY_LEN] + "\n\n[... content truncated at 3500 chars ...]\n"
    else:
        body_excerpt = source_body

    return f"""You are a knowledge extraction assistant. Extract named entities and concepts from the following wiki source page.

## Source: {source_title}

{body_excerpt}

## Already-indexed entities (skip any whose title or alias matches exactly):
{entity_list}

## Already-indexed concepts (skip any whose title or alias matches exactly):
{concept_list}

## Instructions
Return ONLY valid JSON matching this exact schema. No prose, no markdown fences, no comments.

{{
  "entities": [
    {{
      "title": "<canonical entity name: person, organization, program, or policy>",
      "aliases": ["<alternate name>"],
      "summary": "<1-3 sentence neutral description>",
      "evidence": "<quote or paraphrase from the source that supports this entity>",
      "tags": ["<lowercase-tag>"],
      "open_questions": ["<unresolved question if any, else empty list>"]
    }}
  ],
  "concepts": [
    {{
      "title": "<singular durable concept label: recurring idea, category, or definition>",
      "aliases": [],
      "summary": "<1-3 sentence neutral description>",
      "evidence": "<quote or paraphrase from the source>",
      "tags": ["<lowercase-tag>"],
      "open_questions": []
    }}
  ]
}}

Rules:
- Include only entities/concepts clearly supported by the source text.
- Skip any whose title or an alias exactly matches an already-indexed entry above.
- Entities: real-world subjects (people, orgs, programs, policies). Concepts: durable ideas/patterns.
- Use singular labels, not questions or source-specific headings.
- Return empty arrays when no new entries are found.
- All JSON must be syntactically valid.{error_section}"""


# ---------------------------------------------------------------------------
# GitHub Models API call
# ---------------------------------------------------------------------------


def _call_models_api(
    prompt: str,
    github_token: str,
    endpoint: str,
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "model": _MODEL_ID,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
    ).encode("utf-8")

    req = request.Request(
        f"{endpoint.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_extraction_from_response(api_response: dict[str, Any]) -> dict[str, Any]:
    choices = api_response.get("choices") or []
    if not choices:
        raise ValueError("API response contained no choices")
    content: str = choices[0].get("message", {}).get("content", "") or ""
    # Strip accidental markdown fences
    content = re.sub(r"```(?:json)?\s*", "", content).strip()
    content = re.sub(r"```\s*$", "", content).strip()
    return json.loads(content)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_extraction_bundle(bundle: Any) -> list[str]:
    """Return a list of schema violations (empty list = valid)."""
    errors: list[str] = []
    if not isinstance(bundle, dict):
        return ["root value must be a JSON object"]
    for key in ("entities", "concepts"):
        if key not in bundle:
            errors.append(f"missing required key '{key}'")
        elif not isinstance(bundle[key], list):
            errors.append(f"'{key}' must be a JSON array")
        else:
            for i, item in enumerate(bundle[key]):
                if not isinstance(item, dict):
                    errors.append(f"'{key}[{i}]' must be a JSON object")
                    continue
                for rk in _REQUIRED_ITEM_KEYS:
                    if rk not in item:
                        errors.append(f"'{key}[{i}]' missing required key '{rk}'")
                if not isinstance(item.get("title", ""), str):
                    errors.append(f"'{key}[{i}].title' must be a string")
                if not isinstance(item.get("aliases", []), list):
                    errors.append(f"'{key}[{i}].aliases' must be a list")
                if not isinstance(item.get("tags", []), list):
                    errors.append(f"'{key}[{i}].tags' must be a list")
                if not isinstance(item.get("open_questions", []), list):
                    errors.append(f"'{key}[{i}].open_questions' must be a list")
    return errors


# ---------------------------------------------------------------------------
# Main extraction logic
# ---------------------------------------------------------------------------


def run(
    source_page_path: str,
    wiki_root: str,
    github_token: str,
    output_path: str,
    endpoint: str = _GITHUB_MODELS_ENDPOINT,
    *,
    repo_root: Path | None = None,
) -> int:
    """Run extraction; returns 0 on success (including soft-skip), 1 on hard error."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[4]

    # Use env fallback when token not supplied directly (callers may pass "").
    if not github_token:
        github_token = (
            os.environ.get("SYNTHESIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        )

    # Endpoint hostname must be in the allowlist — prevent token exfiltration.
    if not _validate_endpoint(endpoint):
        print(
            f"error: endpoint hostname not allowed: {endpoint!r}",
            file=sys.stderr,
        )
        return 1

    wiki_root_path = repo_root / wiki_root
    source_path = (repo_root / source_page_path).resolve()

    # Boundary check — source page must be inside repo root.
    try:
        source_path.relative_to(repo_root.resolve())
    except ValueError:
        print(
            f"error: source page path escapes repo root: {source_page_path}",
            file=sys.stderr,
        )
        return 1

    if not source_path.exists():
        print(
            f"error: source page not found: {source_page_path}", file=sys.stderr
        )
        return 1

    source_content = source_path.read_text(encoding="utf-8")
    fm_str, body = extract_frontmatter(source_content)
    if fm_str is None:
        fm_str, body = "", source_content

    fm = parse_frontmatter(fm_str)
    source_title = fm.get("title", source_path.stem).strip().strip('"').strip("'")
    sources = extract_sources_from_frontmatter(fm_str)
    source_ref = sources[0] if sources else ""
    source_body_for_extraction = _load_primary_source_text(
        repo_root=repo_root,
        source_ref=source_ref,
        fallback_text=body,
    )

    existing_entities = scan_existing_pages(wiki_root_path, "entities")
    existing_concepts = scan_existing_pages(wiki_root_path, "concepts")

    extraction: dict[str, Any] | None = None
    last_errors: list[str] | None = None

    for attempt in range(_MAX_ATTEMPTS):
        prompt = _build_prompt(
            source_title=source_title,
            source_body=source_body_for_extraction,
            existing_entities=existing_entities,
            existing_concepts=existing_concepts,
            validation_errors=last_errors,
        )
        try:
            api_response = _call_models_api(prompt, github_token, endpoint)
            bundle = _parse_extraction_from_response(api_response)
        except (urllib_error.URLError, json.JSONDecodeError, ValueError, KeyError) as exc:
            last_errors = [f"attempt {attempt + 1} API/parse error: {exc}"]
            print(
                f"warning: extraction attempt {attempt + 1} failed: {exc}",
                file=sys.stderr,
            )
            continue

        errors = validate_extraction_bundle(bundle)
        if not errors:
            extraction = bundle
            break
        last_errors = errors
        print(
            f"warning: extraction attempt {attempt + 1} schema errors: {errors}",
            file=sys.stderr,
        )

    soft_skipped = extraction is None
    if soft_skipped:
        print(
            "warning: synthesis soft-skipped — all attempts produced invalid output",
            file=sys.stderr,
        )
        extraction = {"entities": [], "concepts": []}

    extraction["source_ref"] = source_ref
    extraction["source_page"] = source_page_path
    extraction["soft_skipped"] = soft_skipped

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(extraction, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def main() -> int:
    args = _parse_args()
    return run(
        source_page_path=args.source_page,
        wiki_root=args.wiki_root,
        github_token="",
        output_path=args.output,
        endpoint=args.endpoint,
    )


if __name__ == "__main__":
    sys.exit(main())
