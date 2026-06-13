"""Friction-signal session_store_sql query templates for the audit improve flow.

Implements `docs/ideas/audit-workspace-improve-flow.md` § Phase 4 — Slice 8c
(issue #204): five friction classes (chronicle_commits, repeated_user_prompts,
repeated_context_loads, hook_bypasses, retry_loops), each emitted as a
read-only template containing a repo-scoped `primary` query, a cross-repo
`broader` query, and a `LIMITED_EVIDENCE` fallback sentinel. The two-pass
execution rule (`run_two_pass`) follows the canonical strategy in
`.github/copilot-instructions.md` § "Two-pass session_store query strategy":
primary → broader-on-zero → limited-evidence-with-telemetry-gap acknowledgment.
Each template's `finding` defaults conform to
`.github/skills/audit-knowledgebase-workspace/schema/finding.schema.json`
(Q4-revised compliance_risk mapping; Q11 cache_strategy = "mtime_first_para").
No repository reads or writes are performed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
import re
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_corpus_cache import CACHE_STRATEGY


LIMITED_EVIDENCE_SENTINEL = "LIMITED_EVIDENCE"
TELEMETRY_GAP_ACKNOWLEDGMENT = (
    "Telemetry gap: session_store returned zero rows for both the repo-scoped "
    "and broader passes. Switch to limited-evidence mode and ground any "
    "recommendations only in observable current-session context."
)
DEFAULT_LIMIT = 50
DEFAULT_DAYS = 7
RETRY_WINDOW_MINUTES = 15
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

FrictionQueryTemplate = dict[str, Any]
QueryRows = Sequence[Mapping[str, Any]]
QueryRunner = Callable[[str], QueryRows]


def chronicle_commits_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for chronicle-improve commit signals."""

    interval = _interval(days)
    repo_literal = _repo_literal(repo)
    # Loose temporal coupling: any matching /chronicle improve prompt within the time window before the commit counts; not a tight cause-effect link.
    primary = f"""
SELECT
  sr.session_id,
  COALESCE(s.repository, '') AS repository,
  sr.ref_value AS commit_sha,
  sr.created_at AS commit_recorded_at,
  MAX(t.timestamp) AS chronicle_prompt_at,
  'chronicle_commits' AS friction_class
FROM session_refs sr
JOIN turns t ON t.session_id = sr.session_id
JOIN sessions s ON s.id = sr.session_id
WHERE s.repository = {repo_literal}
  AND sr.ref_type = 'commit'
  AND sr.created_at > {interval}
  AND t.timestamp > {interval}
  AND t.timestamp <= sr.created_at
  AND COALESCE(t.user_message, '') ILIKE '%/chronicle improve%'
GROUP BY sr.session_id, COALESCE(s.repository, ''), sr.ref_value, sr.created_at
ORDER BY sr.created_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    broader = f"""
SELECT
  sr.session_id,
  COALESCE(s.repository, '') AS repository,
  sr.ref_value AS commit_sha,
  sr.created_at AS commit_recorded_at,
  MAX(t.timestamp) AS chronicle_prompt_at,
  'chronicle_commits' AS friction_class
FROM session_refs sr
JOIN turns t ON t.session_id = sr.session_id
JOIN sessions s ON s.id = sr.session_id
WHERE sr.ref_type = 'commit'
  AND sr.created_at > {interval}
  AND t.timestamp > {interval}
  AND t.timestamp <= sr.created_at
  AND COALESCE(t.user_message, '') ILIKE '%/chronicle improve%'
GROUP BY sr.session_id, COALESCE(s.repository, ''), sr.ref_value, sr.created_at
ORDER BY sr.created_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    return _template(
        "chronicle_commits",
        primary=primary,
        broader=broader,
        source_section="chronicle commits",
        rationale=(
            "Chronicle-improve prompts followed by commits indicate repeated "
            "always-on instruction updates that should route through the audit "
            "skill's locality classifier."
        ),
        proposed_destination="Locality 2",
        compliance_risk="agent-dependent",
        expected_token_efficiency_rank=2,
        suggested_artifact_path=".github/skills/audit-knowledgebase-workspace/SKILL.md",
    )


def repeated_user_prompts_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for repeated user-prompt signals."""

    interval = _interval(days)
    repo_literal = _repo_literal(repo)
    primary = f"""
SELECT
  t.session_id,
  COALESCE(s.repository, '') AS repository,
  md5(COALESCE(t.user_message, '')) AS prompt_fingerprint,
  length(COALESCE(t.user_message, '')) AS prompt_length,
  COUNT(*) AS repeat_count,
  MIN(t.timestamp) AS first_prompt_at,
  MAX(t.timestamp) AS last_prompt_at,
  'repeated_user_prompts' AS friction_class
FROM turns t
JOIN sessions s ON s.id = t.session_id
WHERE s.repository = {repo_literal}
  AND t.timestamp > {interval}
  AND COALESCE(t.user_message, '') <> ''
GROUP BY t.session_id, COALESCE(s.repository, ''), COALESCE(t.user_message, '')
HAVING COUNT(*) > 1
ORDER BY repeat_count DESC, last_prompt_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    broader = f"""
SELECT
  t.session_id,
  COALESCE(s.repository, '') AS repository,
  md5(COALESCE(t.user_message, '')) AS prompt_fingerprint,
  length(COALESCE(t.user_message, '')) AS prompt_length,
  COUNT(*) AS repeat_count,
  MIN(t.timestamp) AS first_prompt_at,
  MAX(t.timestamp) AS last_prompt_at,
  'repeated_user_prompts' AS friction_class
FROM turns t
JOIN sessions s ON s.id = t.session_id
WHERE t.timestamp > {interval}
  AND COALESCE(t.user_message, '') <> ''
GROUP BY t.session_id, COALESCE(s.repository, ''), COALESCE(t.user_message, '')
HAVING COUNT(*) > 1
ORDER BY repeat_count DESC, last_prompt_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    return _template(
        "repeated_user_prompts",
        primary=primary,
        broader=broader,
        source_section="repeated user prompts",
        rationale=(
            "Identical user prompts repeated in the same session indicate missing "
            "just-in-time guidance or unclear routing."
        ),
        proposed_destination="Locality 3e",
        compliance_risk="agent-dependent",
        expected_token_efficiency_rank=3,
        suggested_artifact_path=".github/hooks/hooks.json",
    )


def repeated_context_loads_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for repeated skill/context load signals."""

    interval = _interval(days)
    repo_literal = _repo_literal(repo)
    skill_expr = _skill_name_expression()
    primary = f"""
SELECT
  e.session_id,
  COALESCE(s.repository, '') AS repository,
  {skill_expr} AS skill_name,
  COUNT(*) AS invocation_count,
  MIN(e.timestamp) AS first_invoked_at,
  MAX(e.timestamp) AS last_invoked_at,
  'repeated_context_loads' AS friction_class
FROM events e
JOIN sessions s ON s.id = e.session_id
JOIN tool_requests tr
  ON tr.session_id = e.session_id
 AND tr.tool_call_id = e.tool_complete_call_id
WHERE s.repository = {repo_literal}
  AND e.type = 'tool.execution_complete'
  AND e.tool_start_name = 'skill'
  AND e.timestamp > {interval}
GROUP BY e.session_id, COALESCE(s.repository, ''), {skill_expr}
HAVING COUNT(*) > 1
ORDER BY invocation_count DESC, last_invoked_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    broader = f"""
SELECT
  e.session_id,
  COALESCE(s.repository, '') AS repository,
  {skill_expr} AS skill_name,
  COUNT(*) AS invocation_count,
  MIN(e.timestamp) AS first_invoked_at,
  MAX(e.timestamp) AS last_invoked_at,
  'repeated_context_loads' AS friction_class
FROM events e
JOIN sessions s ON s.id = e.session_id
JOIN tool_requests tr
  ON tr.session_id = e.session_id
 AND tr.tool_call_id = e.tool_complete_call_id
WHERE e.type = 'tool.execution_complete'
  AND e.tool_start_name = 'skill'
  AND e.timestamp > {interval}
GROUP BY e.session_id, COALESCE(s.repository, ''), {skill_expr}
HAVING COUNT(*) > 1
ORDER BY invocation_count DESC, last_invoked_at DESC
LIMIT {DEFAULT_LIMIT}
"""
    return _template(
        "repeated_context_loads",
        primary=primary,
        broader=broader,
        source_section="repeated context loads",
        rationale=(
            "Repeated invocations of the same skill in one session indicate "
            "context reentry friction that may need narrower routing or cached "
            "handoff guidance."
        ),
        proposed_destination="Locality 2",
        compliance_risk="agent-dependent",
        expected_token_efficiency_rank=2,
        suggested_artifact_path=".github/skills/audit-knowledgebase-workspace/SKILL.md",
    )


def hook_bypasses_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for hook-bypass commit signals."""

    interval = _interval(days)
    repo_literal = _repo_literal(repo)
    primary = _hook_bypass_sql(repo_filter=f"s.repository = {repo_literal}", interval=interval)
    broader = _hook_bypass_sql(repo_filter=None, interval=interval)
    return _template(
        "hook_bypasses",
        primary=primary,
        broader=broader,
        source_section="hook bypasses",
        rationale=(
            "Commit sessions mentioning hook bypasses indicate guardrail friction "
            "that should be made deterministic or clarified at the hook boundary."
        ),
        proposed_destination="Locality 3d",
        compliance_risk="deterministic",
        expected_token_efficiency_rank=1,
        suggested_artifact_path=".pre-commit-config.yaml",
    )


def retry_loops_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for failed-tool retry-loop signals."""

    interval = _interval(days)
    repo_literal = _repo_literal(repo)
    primary = _retry_loop_sql(repo_filter=f"s.repository = {repo_literal}", interval=interval)
    broader = _retry_loop_sql(repo_filter=None, interval=interval)
    return _template(
        "retry_loops",
        primary=primary,
        broader=broader,
        source_section="retry loops",
        rationale=(
            "Failed tool executions followed by near-term reinvocations indicate "
            "missing diagnostics or recovery guidance that should move closer to "
            "the failing tool boundary."
        ),
        proposed_destination="Locality 3a",
        compliance_risk="deterministic",
        expected_token_efficiency_rank=1,
        suggested_artifact_path=".github/hooks/hooks.json",
    )


def all_friction_queries(*, repo: str, days: int = DEFAULT_DAYS) -> dict[str, FrictionQueryTemplate]:
    """Return every friction-class template keyed by class name."""

    templates = (
        chronicle_commits_query(repo=repo, days=days),
        repeated_user_prompts_query(repo=repo, days=days),
        repeated_context_loads_query(repo=repo, days=days),
        hook_bypasses_query(repo=repo, days=days),
        retry_loops_query(repo=repo, days=days),
    )
    return {template["friction_class"]: template for template in templates}


def run_two_pass(template: Mapping[str, Any], query_runner: QueryRunner) -> dict[str, Any]:
    """Execute primary then broader SQL, falling back to limited-evidence mode."""

    primary_sql = _required_sql(template, "primary")
    broader_sql = _required_sql(template, "broader")
    fallback = template.get("fallback")
    if fallback != LIMITED_EVIDENCE_SENTINEL:
        raise ValueError("template fallback must be LIMITED_EVIDENCE")

    primary_rows = tuple(query_runner(primary_sql))
    if primary_rows:
        return _query_result("primary", primary_sql, primary_rows)

    broader_rows = tuple(query_runner(broader_sql))
    if broader_rows:
        return _query_result("broader", broader_sql, broader_rows)

    return {
        "mode": "limited-evidence",
        "sql": None,
        "fallback": LIMITED_EVIDENCE_SENTINEL,
        "limited_evidence": True,
        "telemetry_gap_acknowledgment": TELEMETRY_GAP_ACKNOWLEDGMENT,
        "rows": (),
        "row_count": 0,
    }


def _query_result(mode: str, sql: str, rows: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    return {
        "mode": mode,
        "sql": sql,
        "fallback": None,
        "limited_evidence": False,
        "telemetry_gap_acknowledgment": None,
        "rows": rows,
        "row_count": len(rows),
    }


def _template(
    friction_class: str,
    *,
    primary: str,
    broader: str,
    source_section: str,
    rationale: str,
    proposed_destination: str,
    compliance_risk: str,
    expected_token_efficiency_rank: int,
    suggested_artifact_path: str,
) -> FrictionQueryTemplate:
    return {
        "friction_class": friction_class,
        "primary": _normalize_sql(primary),
        "broader": _normalize_sql(broader),
        "fallback": LIMITED_EVIDENCE_SENTINEL,
        "finding": {
            "source_file": ".github/copilot-instructions.md",
            "source_section": f"session_store:{source_section}",
            "proposed_destination": proposed_destination,
            "rationale": rationale,
            "compliance_risk": compliance_risk,
            "expected_token_efficiency_rank": expected_token_efficiency_rank,
            "cache_strategy": CACHE_STRATEGY,
            "suggested_artifact_path": suggested_artifact_path,
        },
    }


def _hook_bypass_sql(*, repo_filter: str | None, interval: str) -> str:
    repo_clause = f"  AND {repo_filter}\n" if repo_filter is not None else ""
    turn_predicate = _hook_bypass_predicate("COALESCE(t.user_message, '')")
    tool_predicate = _hook_bypass_predicate("COALESCE(tr.arguments_json, '')")
    return f"""
WITH candidate_commits AS (
  SELECT
    sr.session_id,
    COALESCE(s.repository, '') AS repository,
    sr.ref_value AS commit_sha,
    sr.created_at AS commit_recorded_at
  FROM session_refs sr
  JOIN sessions s ON s.id = sr.session_id
  WHERE sr.ref_type = 'commit'
    AND sr.created_at > {interval}
{repo_clause}),
bypass_mentions AS (
  SELECT
    c.session_id,
    c.repository,
    c.commit_sha,
    c.commit_recorded_at,
    t.timestamp AS bypass_mentioned_at
  FROM candidate_commits c
  JOIN turns t ON t.session_id = c.session_id
  WHERE t.timestamp > {interval}
    AND t.timestamp <= c.commit_recorded_at
    AND ({turn_predicate})
  UNION ALL
  SELECT
    c.session_id,
    c.repository,
    c.commit_sha,
    c.commit_recorded_at,
    e.timestamp AS bypass_mentioned_at
  FROM candidate_commits c
  JOIN events e ON e.session_id = c.session_id
  JOIN tool_requests tr
    ON tr.session_id = e.session_id
   AND tr.tool_call_id = e.tool_complete_call_id
  WHERE e.type = 'tool.execution_complete'
    AND e.tool_start_name = 'bash'
    AND e.timestamp > {interval}
    AND e.timestamp <= c.commit_recorded_at
    AND ({tool_predicate})
)
SELECT
  session_id,
  repository,
  commit_sha,
  commit_recorded_at,
  MAX(b.bypass_mentioned_at) AS bypass_mentioned_at,
  'hook_bypasses' AS friction_class
FROM bypass_mentions b
GROUP BY session_id, repository, commit_sha, commit_recorded_at
ORDER BY commit_recorded_at DESC
LIMIT {DEFAULT_LIMIT}
"""


def _retry_loop_sql(*, repo_filter: str | None, interval: str) -> str:
    repo_clause = f"  AND {repo_filter}\n" if repo_filter is not None else ""
    return f"""
WITH failed_tools AS (
  SELECT
    e.session_id,
    COALESCE(s.repository, '') AS repository,
    e.tool_start_name AS tool_name,
    e.timestamp AS failed_at,
    COALESCE(tr.arguments_json, '') AS arguments_json
  FROM events e
  JOIN sessions s ON s.id = e.session_id
  JOIN tool_requests tr
    ON tr.session_id = e.session_id
   AND tr.tool_call_id = e.tool_complete_call_id
  WHERE e.type = 'tool.execution_complete'
    AND e.tool_complete_success = false
    AND e.tool_start_name IS NOT NULL
    AND e.timestamp > {interval}
{repo_clause}),
retry_matches AS (
  SELECT
    f.session_id,
    f.repository,
    f.tool_name,
    f.failed_at,
    md5(f.arguments_json) AS request_fingerprint,
    length(f.arguments_json) AS request_length,
    MIN(r.timestamp) AS retried_at,
    COUNT(*) AS retry_count
  FROM failed_tools f
  JOIN events r
    ON r.session_id = f.session_id
   AND r.type = 'tool.execution_complete'
   AND r.tool_start_name = f.tool_name
   AND r.timestamp > f.failed_at
   AND r.timestamp <= f.failed_at + INTERVAL '{RETRY_WINDOW_MINUTES} minutes'
   AND r.timestamp > {interval}
  JOIN tool_requests rr
    ON rr.session_id = r.session_id
   AND rr.tool_call_id = r.tool_complete_call_id
   AND COALESCE(rr.arguments_json, '') = f.arguments_json
  GROUP BY f.session_id, f.repository, f.tool_name, f.failed_at, f.arguments_json
)
SELECT
  session_id,
  repository,
  tool_name,
  failed_at,
  request_fingerprint,
  request_length,
  retried_at,
  retry_count,
  'retry_loops' AS friction_class
FROM retry_matches
ORDER BY retry_count DESC, retried_at DESC
LIMIT {DEFAULT_LIMIT}
"""


def _required_sql(template: Mapping[str, Any], key: str) -> str:
    value = template.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"template missing SQL string: {key}")
    return value


def _normalize_sql(sql: str) -> str:
    return "\n".join(line.rstrip() for line in sql.strip().splitlines())


def _interval(days: int) -> str:
    validated_days = _validate_days(days)
    return f"now() - INTERVAL '{validated_days} days'"


def _validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int):
        raise TypeError("days must be an integer")
    if days < 1 or days > 365:
        raise ValueError("days must be between 1 and 365")
    return days


def _repo_literal(repo: str) -> str:
    if not _REPO_PATTERN.fullmatch(repo):
        raise ValueError("repo must be in owner/name form")
    return f"'{repo}'"


def _skill_name_expression() -> str:
    """Heuristic JSON key extraction; assumes well-formed skill names without escaped quotes."""

    return (
        "COALESCE(NULLIF(regexp_extract(COALESCE(tr.arguments_json, ''), "
        """'"skill"\\s*:\\s*"([^"]+)"', 1), ''), 'unknown')"""
    )


def _hook_bypass_predicate(subject: str) -> str:
    return "\n  OR ".join(
        (
            f"{subject} ILIKE '%no-verify%'",
            f"{subject} ILIKE '%hook bypass%'",
            f"{subject} ILIKE '%skip pre-commit%'",
        )
    )


__all__ = [
    "DEFAULT_DAYS",
    "DEFAULT_LIMIT",
    "FrictionQueryTemplate",
    "LIMITED_EVIDENCE_SENTINEL",
    "QueryRunner",
    "RETRY_WINDOW_MINUTES",
    "TELEMETRY_GAP_ACKNOWLEDGMENT",
    "all_friction_queries",
    "chronicle_commits_query",
    "hook_bypasses_query",
    "repeated_context_loads_query",
    "repeated_user_prompts_query",
    "retry_loops_query",
    "run_two_pass",
]
