"""Tests for audit-workspace friction-signal session_store query templates."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

import pytest

from tests.kb.harnesses import load_module


REPO_ROOT = Path(__file__).resolve().parents[2]
FRICTION_QUERIES_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "logic"
    / "friction_queries.py"
)
FINDING_SCHEMA_PATH = (
    REPO_ROOT
    / ".github"
    / "skills"
    / "audit-knowledgebase-workspace"
    / "schema"
    / "finding.schema.json"
)
REPO = "wryenmeek/knowledgebase"


def _module():
    return load_module("audit_workspace_friction_queries", FRICTION_QUERIES_PATH)


def _templates(module) -> dict[str, dict[str, Any]]:
    return module.all_friction_queries(repo=REPO, days=7)


def test_all_friction_classes_have_two_pass_templates() -> None:
    module = _module()
    templates = _templates(module)

    assert set(templates) == {
        "chronicle_commits",
        "repeated_user_prompts",
        "repeated_context_loads",
        "hook_bypasses",
        "retry_loops",
    }
    for friction_class, template in templates.items():
        assert template["friction_class"] == friction_class, friction_class
        assert "primary" in template, friction_class
        assert "broader" in template, friction_class
        assert template["fallback"] == module.LIMITED_EVIDENCE_SENTINEL, friction_class
        assert "finding" in template, friction_class


def test_sql_templates_follow_session_store_safety_rules() -> None:
    module = _module()
    ilike_exact_match_anchors = {
        "chronicle_commits": ("sr.ref_type = 'commit'",),
        "hook_bypasses": (
            "sr.ref_type = 'commit'",
            "e.type = 'tool.execution_complete'",
            "e.tool_start_name = 'bash'",
        ),
    }

    for friction_class, template in _templates(module).items():
        for pass_name in ("primary", "broader"):
            context = f"{friction_class}/{pass_name}"
            sql = template[pass_name]
            lowered = sql.lower()

            assert "select *" not in lowered, context
            assert lowered.startswith(("select", "with")), context
            assert ";" not in sql, context
            assert (
                re.search(r"\b(insert|update|delete|drop|alter|create)\b", lowered)
                is None
            ), context
            assert "now() - interval '7 days'" in lowered, context
            assert "limit 50" in lowered, context
            if pass_name == "primary":
                assert "s.repository = 'wryenmeek/knowledgebase'" in sql, context
            else:
                assert "s.repository =" not in sql, context
            if " ilike " in lowered:
                for anchor in ilike_exact_match_anchors[friction_class]:
                    assert anchor in lowered, context

    days_30_template = module.retry_loops_query(repo=REPO, days=30)
    assert "now() - INTERVAL '30 days'" in days_30_template["primary"]
    assert "now() - INTERVAL '30 days'" in days_30_template["broader"]


def test_sql_templates_include_friction_specific_predicates() -> None:
    module = _module()
    templates = _templates(module)

    assert "sr.ref_type = 'commit'" in templates["chronicle_commits"]["primary"]
    assert "ILIKE '%/chronicle improve%'" in templates["chronicle_commits"]["primary"]
    assert "HAVING COUNT(*) > 1" in templates["repeated_user_prompts"]["primary"]
    assert (
        "md5(COALESCE(t.user_message, '')) AS prompt_fingerprint"
        in templates["repeated_user_prompts"]["primary"]
    )
    assert (
        "length(COALESCE(t.user_message, '')) AS prompt_length"
        in templates["repeated_user_prompts"]["primary"]
    )
    assert "AS repeated_prompt" not in templates["repeated_user_prompts"]["primary"]
    assert "AS repeated_prompt" not in templates["repeated_user_prompts"]["broader"]
    assert (
        "e.type = 'tool.execution_complete'"
        in templates["repeated_context_loads"]["primary"]
    )
    assert (
        "e.tool_start_name = 'skill'" in templates["repeated_context_loads"]["primary"]
    )
    hook_primary = templates["hook_bypasses"]["primary"]
    assert "ILIKE '%no-verify%'" in hook_primary
    assert hook_primary.index("WITH candidate_commits") < hook_primary.index(
        "ILIKE '%no-verify%'"
    )
    assert hook_primary.index("WHERE sr.ref_type = 'commit'") < hook_primary.index(
        "ILIKE '%no-verify%'"
    )
    assert "tool_complete_success = false" in templates["retry_loops"]["primary"]
    assert "INTERVAL '15 minutes'" in templates["retry_loops"]["primary"]


def test_sql_factories_use_uniform_private_helper_shape() -> None:
    module = _module()

    for helper_name in (
        "_chronicle_commits_sql",
        "_repeated_user_prompts_sql",
        "_repeated_context_loads_sql",
        "_hook_bypasses_sql",
        "_retry_loops_sql",
    ):
        signature = inspect.signature(getattr(module, helper_name))
        assert tuple(signature.parameters) == ("repo_filter", "interval"), helper_name
        for parameter in signature.parameters.values():
            assert parameter.kind == inspect.Parameter.KEYWORD_ONLY, helper_name


def test_sql_templates_parse_under_duckdb_session_store_dialect() -> None:
    if importlib.util.find_spec("duckdb") is None:
        pytest.skip(
            "duckdb package unavailable; SQLite fixture covers semantics, "
            "this smoke test only checks session_store_sql dialect compatibility"
        )

    import duckdb  # type: ignore[import-not-found]

    module = _module()
    db = duckdb.connect(database=":memory:")
    try:
        _create_duckdb_session_store_schema(db)
        for friction_class, template in _templates(module).items():
            for pass_name in ("primary", "broader"):
                db.execute(template[pass_name]).fetchall()
    finally:
        db.close()


def test_primary_query_rows_are_returned_for_each_friction_class() -> None:
    module = _module()
    templates = _templates(module)
    expected_counts = {
        "chronicle_commits": 2,
        "repeated_user_prompts": 1,
        "repeated_context_loads": 1,
        "hook_bypasses": 1,
        "retry_loops": 2,
    }

    for friction_class, template in templates.items():
        query_log: list[str] = []
        db = _build_session_store_fixture(repository=REPO)
        query_runner = _sqlite_query_runner(
            query_log=query_log,
            db=db,
            retry_window_minutes=module.RETRY_WINDOW_MINUTES,
        )

        result = module.run_two_pass(template, query_runner)

        assert result["mode"] == "primary", friction_class
        assert not result["limited_evidence"], friction_class
        assert result["row_count"] == expected_counts[friction_class], friction_class
        assert query_log == [template["primary"]], friction_class
        for row in result["rows"]:
            assert row["repository"] == REPO, friction_class
            assert row["friction_class"] == friction_class
            if friction_class == "chronicle_commits":
                assert row["chronicle_prompt_at"] <= row["commit_recorded_at"]
        if friction_class == "chronicle_commits":
            rows_by_commit = {row["commit_sha"]: row for row in result["rows"]}
            assert (
                rows_by_commit["sha-chronicle-1"]["chronicle_prompt_at"]
                == "2026-06-12 09:10:00"
            )
        if friction_class == "retry_loops":
            rows_by_tool = {row["tool_name"]: row for row in result["rows"]}
            assert rows_by_tool["bash"]["retry_count"] == 1
            assert rows_by_tool["view"]["retry_count"] == 1


def test_broader_query_runs_when_primary_returns_zero_rows() -> None:
    module = _module()
    templates = _templates(module)
    expected_counts = {
        "chronicle_commits": 2,
        "repeated_user_prompts": 1,
        "repeated_context_loads": 1,
        "hook_bypasses": 1,
        "retry_loops": 2,
    }

    for friction_class, template in templates.items():
        query_log: list[str] = []
        db = _build_session_store_fixture(repository="other/repo")
        query_runner = _sqlite_query_runner(
            query_log=query_log,
            db=db,
            retry_window_minutes=module.RETRY_WINDOW_MINUTES,
        )

        result = module.run_two_pass(template, query_runner)

        assert result["mode"] == "broader", friction_class
        assert not result["limited_evidence"], friction_class
        assert result["row_count"] == expected_counts[friction_class], friction_class
        assert query_log == [template["primary"], template["broader"]], friction_class
        for row in result["rows"]:
            assert row["repository"] == "other/repo", friction_class
            assert row["friction_class"] == friction_class
            if friction_class == "chronicle_commits":
                assert row["chronicle_prompt_at"] <= row["commit_recorded_at"]
        if friction_class == "chronicle_commits":
            rows_by_commit = {row["commit_sha"]: row for row in result["rows"]}
            assert (
                rows_by_commit["sha-chronicle-1"]["chronicle_prompt_at"]
                == "2026-06-12 09:10:00"
            )


def test_repeated_prompt_rows_do_not_project_raw_user_message() -> None:
    module = _module()
    template = module.repeated_user_prompts_query(repo=REPO)
    query_log: list[str] = []
    db = _build_session_store_fixture(repository=REPO)

    result = module.run_two_pass(
        template,
        _sqlite_query_runner(
            query_log=query_log,
            db=db,
            retry_window_minutes=module.RETRY_WINDOW_MINUTES,
        ),
    )

    assert result["row_count"] == 1
    row = result["rows"][0]
    assert "repeated_prompt" not in row
    assert row["prompt_length"] == len("Repeat this instruction")
    assert row["prompt_fingerprint"] == hashlib.md5(
        b"Repeat this instruction", usedforsecurity=False
    ).hexdigest()


def test_retry_loop_rows_match_same_tool_request_payload_without_raw_args() -> None:
    module = _module()
    template = module.retry_loops_query(repo=REPO)
    query_log: list[str] = []
    db = _build_session_store_fixture(repository=REPO)

    result = module.run_two_pass(
        template,
        _sqlite_query_runner(
            query_log=query_log,
            db=db,
            retry_window_minutes=module.RETRY_WINDOW_MINUTES,
        ),
    )

    row = next(row for row in result["rows"] if row["tool_name"] == "bash")
    assert row["retry_count"] == 1
    assert "arguments_json" not in row
    assert row["request_length"] == len(
        '{"command": "python3 -m pytest tests/kb/test_x.py"}'
    )
    assert row["request_fingerprint"] == hashlib.md5(
        b'{"command": "python3 -m pytest tests/kb/test_x.py"}',
        usedforsecurity=False,
    ).hexdigest()


def test_retry_loop_window_includes_exact_boundary_and_excludes_after_boundary() -> None:
    module = _module()
    template = module.retry_loops_query(repo=REPO)
    query_log: list[str] = []
    db = _build_session_store_fixture(repository=REPO)

    result = module.run_two_pass(
        template,
        _sqlite_query_runner(
            query_log=query_log,
            db=db,
            retry_window_minutes=module.RETRY_WINDOW_MINUTES,
        ),
    )

    edge_row = next(row for row in result["rows"] if row["tool_name"] == "view")
    assert edge_row["failed_at"] == "2026-06-12 14:00:00"
    assert edge_row["retried_at"] == "2026-06-12 14:15:00"
    assert edge_row["retry_count"] == 1


def test_limited_evidence_fallback_adds_telemetry_gap_acknowledgment() -> None:
    module = _module()

    for friction_class, template in _templates(module).items():
        query_log: list[str] = []

        def query_runner(sql: str, query_log: list[str] = query_log):
            query_log.append(sql)
            return ()

        result = module.run_two_pass(template, query_runner)

        assert result["mode"] == "limited-evidence", friction_class
        assert result["limited_evidence"], friction_class
        assert result["fallback"] == module.LIMITED_EVIDENCE_SENTINEL, friction_class
        assert result["row_count"] == 0, friction_class
        assert result["rows"] == (), friction_class
        assert (
            result["telemetry_gap_acknowledgment"] == module.TELEMETRY_GAP_ACKNOWLEDGMENT
        ), friction_class
        assert query_log == [template["primary"], template["broader"]], friction_class


def test_run_two_pass_rejects_malformed_templates() -> None:
    module = _module()

    with pytest.raises(ValueError):
        module.run_two_pass(
            {"primary": "SELECT 1", "broader": "SELECT 1", "fallback": "bogus"},
            lambda sql: (),
        )
    with pytest.raises(ValueError):
        module.run_two_pass(
            {
                "primary": "",
                "broader": "",
                "fallback": module.LIMITED_EVIDENCE_SENTINEL,
            },
            lambda sql: (),
        )


def test_query_inputs_reject_injection_and_invalid_windows() -> None:
    module = _module()

    for valid_days in (1, 365):
        assert module._validate_days(valid_days) == valid_days

    for factory in (
        module.chronicle_commits_query,
        module.repeated_user_prompts_query,
        module.repeated_context_loads_query,
        module.hook_bypasses_query,
        module.retry_loops_query,
    ):
        with pytest.raises(ValueError):
            factory(repo="wryenmeek/knowledgebase'; DROP TABLE turns; --")
        for invalid_repo in (
            "./knowledgebase",
            "../knowledgebase",
            ".../knowledgebase",
            "wryenmeek/.",
            "wryenmeek/..",
            "wryenmeek/...",
        ):
            with pytest.raises(ValueError):
                factory(repo=invalid_repo)
        for invalid_days in (0, 366, True, 7.5):
            with pytest.raises((TypeError, ValueError)):
                factory(repo=REPO, days=invalid_days)


def test_finding_defaults_match_classifier_schema_required_shape() -> None:
    module = _module()
    schema = json.loads(FINDING_SCHEMA_PATH.read_text(encoding="utf-8"))
    required_keys = set(schema["required"])
    allowed_keys = set(schema["properties"])
    allowed_destinations = set(schema["properties"]["proposed_destination"]["enum"])
    allowed_risks = set(schema["properties"]["compliance_risk"]["enum"])
    allowed_cache_strategies = set(schema["properties"]["cache_strategy"]["enum"])
    repo_path_pattern = re.compile(schema["properties"]["source_file"]["pattern"])

    for friction_class, template in _templates(module).items():
        finding = template["finding"]
        assert required_keys.issubset(finding), friction_class
        assert set(finding).issubset(allowed_keys), friction_class
        assert finding["proposed_destination"] in allowed_destinations, friction_class
        assert finding["compliance_risk"] in allowed_risks, friction_class
        assert finding["cache_strategy"] in allowed_cache_strategies, friction_class
        assert isinstance(finding["expected_token_efficiency_rank"], int), friction_class
        assert finding["expected_token_efficiency_rank"] >= 0, friction_class
        assert repo_path_pattern.search(finding["source_file"]), friction_class
        assert repo_path_pattern.search(finding["suggested_artifact_path"]), friction_class
        for required_key in required_keys:
            value = finding[required_key]
            if isinstance(value, str):
                assert value != "", f"{friction_class}/{required_key}"


def test_sqlite_regexp_extract_rejects_python_only_regex_features() -> None:
    with pytest.raises(AssertionError):
        _sqlite_regexp_extract("aa", r"(?<=a)a", 0)


def _sqlite_query_runner(
    *,
    query_log: list[str],
    db: sqlite3.Connection,
    retry_window_minutes: int,
):
    def query_runner(sql: str):
        query_log.append(sql)
        cursor = db.execute(
            _sqlite_compatible_sql(sql, retry_window_minutes=retry_window_minutes)
        )
        return tuple(dict(row) for row in cursor.fetchall())

    return query_runner


def _sqlite_compatible_sql(sql: str, *, retry_window_minutes: int) -> str:
    converted = re.sub(
        r"now\(\) - INTERVAL '\d+ days'",
        "'2026-06-06 00:00:00'",
        sql,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        rf"f\.failed_at \+ INTERVAL '{retry_window_minutes} minutes'",
        f"datetime(f.failed_at, '+{retry_window_minutes} minutes')",
        converted,
    )
    converted = re.sub(r"\bILIKE\b", "LIKE", converted, flags=re.IGNORECASE)
    return converted


def _create_duckdb_session_store_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, repository TEXT);
        CREATE TABLE turns (session_id TEXT, turn_index INTEGER, user_message TEXT, timestamp TIMESTAMP);
        CREATE TABLE session_refs (session_id TEXT, ref_type TEXT, ref_value TEXT, created_at TIMESTAMP);
        CREATE TABLE events (
          session_id TEXT,
          timestamp TIMESTAMP,
          type TEXT,
          tool_start_name TEXT,
          tool_complete_call_id TEXT,
          tool_complete_success BOOLEAN
        );
        CREATE TABLE tool_requests (session_id TEXT, tool_call_id TEXT, arguments_json TEXT);
        """
    )


def _build_session_store_fixture(*, repository: str) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.create_function("md5", 1, _sqlite_md5)
    db.create_function("regexp_extract", 3, _sqlite_regexp_extract)
    db.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, repository TEXT);
        CREATE TABLE turns (session_id TEXT, turn_index INTEGER, user_message TEXT, timestamp TEXT);
        CREATE TABLE session_refs (session_id TEXT, ref_type TEXT, ref_value TEXT, created_at TEXT);
        CREATE TABLE events (
          session_id TEXT,
          timestamp TEXT,
          type TEXT,
          tool_start_name TEXT,
          tool_complete_call_id TEXT,
          tool_complete_success BOOLEAN
        );
        CREATE TABLE tool_requests (session_id TEXT, tool_call_id TEXT, arguments_json TEXT);
        """
    )
    _insert_chronicle_rows(db, repository)
    _insert_repeated_prompt_rows(db, repository)
    _insert_repeated_context_rows(db, repository)
    _insert_hook_bypass_rows(db, repository)
    _insert_retry_loop_rows(db, repository)
    return db


def _insert_chronicle_rows(db: sqlite3.Connection, repository: str) -> None:
    db.executemany(
        "INSERT INTO sessions (id, repository) VALUES (?, ?)",
        (
            ("chronicle-1", repository),
            ("chronicle-2", repository),
            ("chronicle-no-match", repository),
        ),
    )
    db.executemany(
        "INSERT INTO turns (session_id, turn_index, user_message, timestamp) VALUES (?, ?, ?, ?)",
        (
            ("chronicle-1", 1, "/chronicle improve", "2026-06-12 09:00:00"),
            (
                "chronicle-1",
                2,
                "Please run /chronicle improve again",
                "2026-06-12 09:10:00",
            ),
            (
                "chronicle-1",
                3,
                "/chronicle improve after commit",
                "2026-06-12 09:45:00",
            ),
            (
                "chronicle-2",
                1,
                "Please run /chronicle improve",
                "2026-06-12 09:05:00",
            ),
            ("chronicle-no-match", 1, "ordinary prompt", "2026-06-12 09:10:00"),
        ),
    )
    db.executemany(
        "INSERT INTO session_refs (session_id, ref_type, ref_value, created_at) VALUES (?, ?, ?, ?)",
        (
            ("chronicle-1", "commit", "sha-chronicle-1", "2026-06-12 09:30:00"),
            ("chronicle-2", "commit", "sha-chronicle-2", "2026-06-12 09:35:00"),
            (
                "chronicle-no-match",
                "commit",
                "sha-chronicle-no-match",
                "2026-06-12 09:40:00",
            ),
        ),
    )


def _insert_repeated_prompt_rows(db: sqlite3.Connection, repository: str) -> None:
    db.execute(
        "INSERT INTO sessions (id, repository) VALUES (?, ?)",
        ("prompt-repeat", repository),
    )
    db.executemany(
        "INSERT INTO turns (session_id, turn_index, user_message, timestamp) VALUES (?, ?, ?, ?)",
        (
            ("prompt-repeat", 1, "Repeat this instruction", "2026-06-12 10:00:00"),
            ("prompt-repeat", 2, "Repeat this instruction", "2026-06-12 10:01:00"),
            ("prompt-repeat", 3, "Unique prompt", "2026-06-12 10:02:00"),
        ),
    )


def _insert_repeated_context_rows(db: sqlite3.Connection, repository: str) -> None:
    db.execute(
        "INSERT INTO sessions (id, repository) VALUES (?, ?)",
        ("context-repeat", repository),
    )
    db.executemany(
        "INSERT INTO events (session_id, timestamp, type, tool_start_name, tool_complete_call_id, tool_complete_success) VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                "context-repeat",
                "2026-06-12 11:00:00",
                "tool.execution_complete",
                "skill",
                "skill-call-1",
                1,
            ),
            (
                "context-repeat",
                "2026-06-12 11:05:00",
                "tool.execution_complete",
                "skill",
                "skill-call-2",
                1,
            ),
            (
                "context-repeat",
                "2026-06-12 11:10:00",
                "tool.execution_complete",
                "bash",
                "bash-call-1",
                1,
            ),
        ),
    )
    db.executemany(
        "INSERT INTO tool_requests (session_id, tool_call_id, arguments_json) VALUES (?, ?, ?)",
        (
            (
                "context-repeat",
                "skill-call-1",
                '{"skill": "audit-knowledgebase-workspace"}',
            ),
            (
                "context-repeat",
                "skill-call-2",
                '{"skill": "audit-knowledgebase-workspace"}',
            ),
            ("context-repeat", "bash-call-1", '{"command": "true"}'),
        ),
    )


def _insert_hook_bypass_rows(db: sqlite3.Connection, repository: str) -> None:
    db.execute(
        "INSERT INTO sessions (id, repository) VALUES (?, ?)",
        ("hook-bypass", repository),
    )
    db.execute(
        "INSERT INTO turns (session_id, turn_index, user_message, timestamp) VALUES (?, ?, ?, ?)",
        ("hook-bypass", 1, "Commit the current changes", "2026-06-12 12:00:00"),
    )
    db.execute(
        "INSERT INTO events (session_id, timestamp, type, tool_start_name, tool_complete_call_id, tool_complete_success) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "hook-bypass",
            "2026-06-12 12:03:00",
            "tool.execution_complete",
            "bash",
            "hook-bypass-call",
            1,
        ),
    )
    db.execute(
        "INSERT INTO tool_requests (session_id, tool_call_id, arguments_json) VALUES (?, ?, ?)",
        (
            "hook-bypass",
            "hook-bypass-call",
            '{"command": "git commit --no-verify"}',
        ),
    )
    db.execute(
        "INSERT INTO session_refs (session_id, ref_type, ref_value, created_at) VALUES (?, ?, ?, ?)",
        ("hook-bypass", "commit", "sha-hook-bypass", "2026-06-12 12:05:00"),
    )


def _insert_retry_loop_rows(db: sqlite3.Connection, repository: str) -> None:
    db.execute(
        "INSERT INTO sessions (id, repository) VALUES (?, ?)",
        ("retry-loop", repository),
    )
    db.executemany(
        "INSERT INTO events (session_id, timestamp, type, tool_start_name, tool_complete_call_id, tool_complete_success) VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                "retry-loop",
                "2026-06-12 13:00:00",
                "tool.execution_complete",
                "bash",
                "bash-failed",
                0,
            ),
            (
                "retry-loop",
                "2026-06-12 13:05:00",
                "tool.execution_complete",
                "bash",
                "bash-retry",
                1,
            ),
            (
                "retry-loop",
                "2026-06-12 13:07:00",
                "tool.execution_complete",
                "bash",
                "bash-unrelated",
                1,
            ),
            (
                "retry-loop",
                "2026-06-12 13:30:00",
                "tool.execution_complete",
                "view",
                "view-late",
                1,
            ),
            (
                "retry-loop",
                "2026-06-12 14:00:00",
                "tool.execution_complete",
                "view",
                "view-failed",
                0,
            ),
            (
                "retry-loop",
                "2026-06-12 14:15:00",
                "tool.execution_complete",
                "view",
                "view-retry-edge",
                1,
            ),
            (
                "retry-loop",
                "2026-06-12 14:15:01",
                "tool.execution_complete",
                "view",
                "view-retry-late",
                1,
            ),
        ),
    )
    db.executemany(
        "INSERT INTO tool_requests (session_id, tool_call_id, arguments_json) VALUES (?, ?, ?)",
        (
            (
                "retry-loop",
                "bash-failed",
                '{"command": "python3 -m pytest tests/kb/test_x.py"}',
            ),
            (
                "retry-loop",
                "bash-retry",
                '{"command": "python3 -m pytest tests/kb/test_x.py"}',
            ),
            ("retry-loop", "bash-unrelated", '{"command": "git status --short"}'),
            ("retry-loop", "view-late", '{"path": "AGENTS.md"}'),
            ("retry-loop", "view-failed", '{"path": "wiki/index.md"}'),
            ("retry-loop", "view-retry-edge", '{"path": "wiki/index.md"}'),
            ("retry-loop", "view-retry-late", '{"path": "wiki/index.md"}'),
        ),
    )


def _sqlite_md5(value: str) -> str:
    # usedforsecurity=False: this fingerprint is a non-cryptographic dedup key,
    # not a security control, so FIPS-restricted Python builds may still use MD5.
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def _sqlite_regexp_extract(value: str, pattern: str, group_index: int) -> str:
    if re.search(r"\(\?([=!<]|P[<=])|\\[1-9]", pattern):
        raise AssertionError(
            "SQLite regexp_extract fixture only accepts DuckDB/RE2-compatible patterns; "
            "use the DuckDB smoke test for dialect-specific coverage"
        )
    match = re.search(pattern, value)
    if match is None:
        return ""
    return match.group(group_index)
