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
_REPO_PATTERN = re.compile(r"^(?!\.+/)(?![^/]+/\.+$)[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

FrictionQueryTemplate = dict[str, Any]
QueryRows = Sequence[Mapping[str, Any]]
QueryRunner = Callable[[str, tuple[Any, ...]], QueryRows]


def chronicle_commits_query(*, repo: str, days: int = DEFAULT_DAYS) -> FrictionQueryTemplate:
    """Return two-pass queries for chronicle-improve commit signals."""

    _repo_literal(repo)
    interval = _interval(days)
    primary, primary_params = _chronicle_commits_sql(repo=repo, interval=interval)
    broader, broader_params = _chronicle_commits_sql(repo=None, interval=interval)
    return _template(
        "chronicle_commits",
        primary=primary,
        primary_params=primary_params,
        broader=broader,
        broader_params=broader_params,
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

    _repo_literal(repo)
    interval = _interval(days)
    primary, primary_params = _repeated_user_prompts_sql(repo=repo, interval=interval)
    broader, broader_params = _repeated_user_prompts_sql(repo=None, interval=interval)
    return _template(
        "repeated_user_prompts",
        primary=primary,
        primary_params=primary_params,
        broader=broader,
        broader_params=broader_params,
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

    _repo_literal(repo)
    interval = _interval(days)
    primary, primary_params = _repeated_context_loads_sql(repo=repo, interval=interval)
    broader, broader_params = _repeated_context_loads_sql(repo=None, interval=interval)
    return _template(
        "repeated_context_loads",
        primary=primary,
        primary_params=primary_params,
        broader=broader,
        broader_params=broader_params,
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

    _repo_literal(repo)
    interval = _interval(days)
    primary, primary_params = _hook_bypasses_sql(repo=repo, interval=interval)
    broader, broader_params = _hook_bypasses_sql(repo=None, interval=interval)
    return _template(
        "hook_bypasses",
        primary=primary,
        primary_params=primary_params,
        broader=broader,
        broader_params=broader_params,
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

    _repo_literal(repo)
    interval = _interval(days)
    primary, primary_params = _retry_loops_sql(repo=repo, interval=interval)
    broader, broader_params = _retry_loops_sql(repo=None, interval=interval)
    return _template(
        "retry_loops",
        primary=primary,
        primary_params=primary_params,
        broader=broader,
        broader_params=broader_params,
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
    primary_params = template["primary_params"]
    broader_sql = _required_sql(template, "broader")
    broader_params = template["broader_params"]
    fallback = template.get("fallback")
    if fallback != LIMITED_EVIDENCE_SENTINEL:
        raise ValueError("template fallback must be LIMITED_EVIDENCE")

    primary_rows = tuple(query_runner(primary_sql, primary_params))
    if primary_rows:
        return _query_result("primary", primary_sql, primary_rows)

    broader_rows = tuple(query_runner(broader_sql, broader_params))
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
    primary_params: tuple[Any, ...],
    broader: str,
    broader_params: tuple[Any, ...],
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
        "primary_params": primary_params,
        "broader": _normalize_sql(broader),
        "broader_params": broader_params,
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


def _chronicle_commits_sql(*, repo: str | None, interval: str) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    repo_clause = ""
    if repo is not None:
        repo_clause = "  AND s.repository = ?\n"
        params.append(repo)
    # Loose temporal coupling: any matching /chronicle improve prompt within the
    # time window before the commit counts; not a tight cause-effect link.
    sql = (
        "\n"
        "SELECT\n"
        "  sr.session_id,\n"
        "  COALESCE(s.repository, '') AS repository,\n"
        "  sr.ref_value AS commit_sha,\n"
        "  sr.created_at AS commit_recorded_at,\n"
        "  MAX(t.timestamp) AS chronicle_prompt_at,\n"
        "  'chronicle_commits' AS friction_class\n"
        "FROM session_refs sr\n"
        "JOIN turns t ON t.session_id = sr.session_id\n"
        "JOIN sessions s ON s.id = sr.session_id\n"
        "WHERE sr.ref_type = 'commit'\n"
        "  AND sr.created_at > __INTERVAL__\n"
        "  AND t.timestamp > __INTERVAL__\n"
        "  AND t.timestamp <= sr.created_at\n"
        "  AND COALESCE(t.user_message, '') ILIKE '%/chronicle improve%'\n"
        "__REPO_CLAUSE__"
        "GROUP BY sr.session_id, COALESCE(s.repository, ''), sr.ref_value, sr.created_at\n"
        "ORDER BY sr.created_at DESC\n"
        "LIMIT __DEFAULT_LIMIT__\n"
    )
    sql = sql.replace("__INTERVAL__", interval)
    sql = sql.replace("__REPO_CLAUSE__", repo_clause)
    sql = sql.replace("__DEFAULT_LIMIT__", str(DEFAULT_LIMIT))
    return sql, tuple(params)


def _repeated_user_prompts_sql(*, repo: str | None, interval: str) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    repo_clause = ""
    if repo is not None:
        repo_clause = "  AND s.repository = ?\n"
        params.append(repo)
    sql = (
        "\n"
        "SELECT\n"
        "  t.session_id,\n"
        "  COALESCE(s.repository, '') AS repository,\n"
        "  md5(COALESCE(t.user_message, '')) AS prompt_fingerprint,\n"
        "  length(COALESCE(t.user_message, '')) AS prompt_length,\n"
        "  COUNT(*) AS repeat_count,\n"
        "  MIN(t.timestamp) AS first_prompt_at,\n"
        "  MAX(t.timestamp) AS last_prompt_at,\n"
        "  'repeated_user_prompts' AS friction_class\n"
        "FROM turns t\n"
        "JOIN sessions s ON s.id = t.session_id\n"
        "WHERE t.timestamp > __INTERVAL__\n"
        "  AND COALESCE(t.user_message, '') <> ''\n"
        "__REPO_CLAUSE__"
        "GROUP BY t.session_id, COALESCE(s.repository, ''), COALESCE(t.user_message, '')\n"
        "HAVING COUNT(*) > 1\n"
        "ORDER BY repeat_count DESC, last_prompt_at DESC\n"
        "LIMIT __DEFAULT_LIMIT__\n"
    )
    sql = sql.replace("__INTERVAL__", interval)
    sql = sql.replace("__REPO_CLAUSE__", repo_clause)
    sql = sql.replace("__DEFAULT_LIMIT__", str(DEFAULT_LIMIT))
    return sql, tuple(params)


def _repeated_context_loads_sql(*, repo: str | None, interval: str) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    repo_clause = ""
    if repo is not None:
        repo_clause = "  AND s.repository = ?\n"
        params.append(repo)
    skill_expr = _skill_name_expression()
    sql = (
        "\n"
        "SELECT\n"
        "  e.session_id,\n"
        "  COALESCE(s.repository, '') AS repository,\n"
        "  __SKILL_EXPR__ AS skill_name,\n"
        "  COUNT(*) AS invocation_count,\n"
        "  MIN(e.timestamp) AS first_invoked_at,\n"
        "  MAX(e.timestamp) AS last_invoked_at,\n"
        "  'repeated_context_loads' AS friction_class\n"
        "FROM events e\n"
        "JOIN sessions s ON s.id = e.session_id\n"
        "JOIN tool_requests tr\n"
        "  ON tr.session_id = e.session_id\n"
        " AND tr.tool_call_id = e.tool_complete_call_id\n"
        "WHERE e.type = 'tool.execution_complete'\n"
        "  AND e.tool_start_name = 'skill'\n"
        "  AND e.timestamp > __INTERVAL__\n"
        "__REPO_CLAUSE__"
        "GROUP BY e.session_id, COALESCE(s.repository, ''), __SKILL_EXPR__\n"
        "HAVING COUNT(*) > 1\n"
        "ORDER BY invocation_count DESC, last_invoked_at DESC\n"
        "LIMIT __DEFAULT_LIMIT__\n"
    )
    sql = sql.replace("__INTERVAL__", interval)
    sql = sql.replace("__REPO_CLAUSE__", repo_clause)
    sql = sql.replace("__SKILL_EXPR__", skill_expr)
    sql = sql.replace("__DEFAULT_LIMIT__", str(DEFAULT_LIMIT))
    return sql, tuple(params)


def _hook_bypasses_sql(*, repo: str | None, interval: str) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    repo_clause = ""
    if repo is not None:
        repo_clause = "  AND s.repository = ?\n"
        params.append(repo)
    turn_predicate = _hook_bypass_predicate("COALESCE(t.user_message, '')")
    tool_predicate = _hook_bypass_predicate("COALESCE(tr.arguments_json, '')")
    sql = (
        "\n"
        "WITH candidate_commits AS (\n"
        "  SELECT\n"
        "    sr.session_id,\n"
        "    COALESCE(s.repository, '') AS repository,\n"
        "    sr.ref_value AS commit_sha,\n"
        "    sr.created_at AS commit_recorded_at\n"
        "  FROM session_refs sr\n"
        "  JOIN sessions s ON s.id = sr.session_id\n"
        "  WHERE sr.ref_type = 'commit'\n"
        "    AND sr.created_at > __INTERVAL__\n"
        "__REPO_CLAUSE__"
        "),\n"
        "bypass_mentions AS (\n"
        "  SELECT\n"
        "    c.session_id,\n"
        "    c.repository,\n"
        "    c.commit_sha,\n"
        "    c.commit_recorded_at,\n"
        "    t.timestamp AS bypass_mentioned_at\n"
        "  FROM candidate_commits c\n"
        "  JOIN turns t ON t.session_id = c.session_id\n"
        "  WHERE t.timestamp > __INTERVAL__\n"
        "    AND t.timestamp <= c.commit_recorded_at\n"
        "    AND (__TURN_PREDICATE__)\n"
        "  UNION ALL\n"
        "  SELECT\n"
        "    c.session_id,\n"
        "    c.repository,\n"
        "    c.commit_sha,\n"
        "    c.commit_recorded_at,\n"
        "    e.timestamp AS bypass_mentioned_at\n"
        "  FROM candidate_commits c\n"
        "  JOIN events e ON e.session_id = c.session_id\n"
        "  JOIN tool_requests tr\n"
        "    ON tr.session_id = e.session_id\n"
        "   AND tr.tool_call_id = e.tool_complete_call_id\n"
        "  WHERE e.type = 'tool.execution_complete'\n"
        "    AND e.tool_start_name = 'bash'\n"
        "    AND e.timestamp > __INTERVAL__\n"
        "    AND e.timestamp <= c.commit_recorded_at\n"
        "    AND (__TOOL_PREDICATE__)\n"
        ")\n"
        "SELECT\n"
        "  session_id,\n"
        "  repository,\n"
        "  commit_sha,\n"
        "  commit_recorded_at,\n"
        "  MAX(b.bypass_mentioned_at) AS bypass_mentioned_at,\n"
        "  'hook_bypasses' AS friction_class\n"
        "FROM bypass_mentions b\n"
        "GROUP BY session_id, repository, commit_sha, commit_recorded_at\n"
        "ORDER BY commit_recorded_at DESC\n"
        "LIMIT __DEFAULT_LIMIT__\n"
    )
    sql = sql.replace("__INTERVAL__", interval)
    sql = sql.replace("__REPO_CLAUSE__", repo_clause)
    sql = sql.replace("__TURN_PREDICATE__", turn_predicate)
    sql = sql.replace("__TOOL_PREDICATE__", tool_predicate)
    sql = sql.replace("__DEFAULT_LIMIT__", str(DEFAULT_LIMIT))
    return sql, tuple(params)


def _retry_loops_sql(*, repo: str | None, interval: str) -> tuple[str, tuple[Any, ...]]:
    params: list[Any] = []
    repo_clause = ""
    if repo is not None:
        repo_clause = "  AND s.repository = ?\n"
        params.append(repo)
    sql = (
        "\n"
        "WITH failed_tools AS (\n"
        "  SELECT\n"
        "    e.session_id,\n"
        "    COALESCE(s.repository, '') AS repository,\n"
        "    e.tool_start_name AS tool_name,\n"
        "    e.timestamp AS failed_at,\n"
        "    COALESCE(tr.arguments_json, '') AS arguments_json\n"
        "  FROM events e\n"
        "  JOIN sessions s ON s.id = e.session_id\n"
        "  JOIN tool_requests tr\n"
        "    ON tr.session_id = e.session_id\n"
        "   AND tr.tool_call_id = e.tool_complete_call_id\n"
        "  WHERE e.type = 'tool.execution_complete'\n"
        "    AND e.tool_complete_success = false\n"
        "    AND e.tool_start_name IS NOT NULL\n"
        "    AND e.timestamp > __INTERVAL__\n"
        "__REPO_CLAUSE__"
        "),\n"
        "retry_matches AS (\n"
        "  SELECT\n"
        "    f.session_id,\n"
        "    f.repository,\n"
        "    f.tool_name,\n"
        "    f.failed_at,\n"
        "    md5(f.arguments_json) AS request_fingerprint,\n"
        "    length(f.arguments_json) AS request_length,\n"
        "    MIN(r.timestamp) AS retried_at,\n"
        "    COUNT(*) AS retry_count\n"
        "  FROM failed_tools f\n"
        "  JOIN events r\n"
        "    ON r.session_id = f.session_id\n"
        "   AND r.type = 'tool.execution_complete'\n"
        "   AND r.tool_start_name = f.tool_name\n"
        "   AND r.timestamp > f.failed_at\n"
        "   AND r.timestamp <= f.failed_at + INTERVAL '__RETRY_WINDOW_MINUTES__ minutes'\n"
        "   AND r.timestamp > __INTERVAL__\n"
        "  JOIN tool_requests rr\n"
        "    ON rr.session_id = r.session_id\n"
        "   AND rr.tool_call_id = r.tool_complete_call_id\n"
        "   AND COALESCE(rr.arguments_json, '') = f.arguments_json\n"
        "  GROUP BY f.session_id, f.repository, f.tool_name, f.failed_at, f.arguments_json\n"
        ")\n"
        "SELECT\n"
        "  session_id,\n"
        "  repository,\n"
        "  tool_name,\n"
        "  failed_at,\n"
        "  request_fingerprint,\n"
        "  request_length,\n"
        "  retried_at,\n"
        "  retry_count,\n"
        "  'retry_loops' AS friction_class\n"
        "FROM retry_matches\n"
        "ORDER BY retry_count DESC, retried_at DESC\n"
        "LIMIT __DEFAULT_LIMIT__\n"
    )
    sql = sql.replace("__INTERVAL__", interval)
    sql = sql.replace("__REPO_CLAUSE__", repo_clause)
    sql = sql.replace("__RETRY_WINDOW_MINUTES__", str(RETRY_WINDOW_MINUTES))
    sql = sql.replace("__DEFAULT_LIMIT__", str(DEFAULT_LIMIT))
    return sql, tuple(params)



def _required_sql(template: Mapping[str, Any], key: str) -> str:
    value = template.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"template missing SQL string: {key}")
    return value


def _normalize_sql(sql: str) -> str:
    """Normalize generated SQL without hiding its executable first token.

    session_store_sql accepts a single read-only statement. Keep templates free
    of leading comments/newlines so the normalized string visibly begins with
    SELECT or WITH for safety tests and operator inspection.
    """

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

def _repo_literal(repo: str) -> str:
    if not _REPO_PATTERN.fullmatch(repo):
        raise ValueError("repo must be in owner/name form")
    return f"'{repo}'"
