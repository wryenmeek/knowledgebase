"""Tests for ``scripts.analysis.cost_baseline``: aggregation + heuristics."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts.analysis.cost_baseline import (
    AgentBucket,
    REASON_CODE_MISSING_COPILOT_HOME,
    _cheapest_candidate,
    build_report,
    collect_cli,
)
from scripts._optional_surface_common import (
    REASON_CODE_INVALID_INPUT,
    STATUS_FAIL,
    STATUS_PASS,
)


# ---------- Synthetic-fixture builders ----------


def _write_session(home: Path, session_id: str, events: list[dict]) -> Path:
    sess_dir = home / "session-state" / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    p = sess_dir / "events.jsonl"
    p.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    return p


def _subagent_completed(
    agent: str = "general-purpose",
    model: str = "gpt-5.5",
    tokens: int = 1_000_000,
    tool_calls: int = 5,
    duration_ms: int = 60_000,
) -> dict:
    return {
        "type": "subagent.completed",
        "data": {
            "agentName": agent,
            "model": model,
            "totalTokens": tokens,
            "totalToolCalls": tool_calls,
            "durationMs": duration_ms,
        },
    }


def _session_shutdown(nano_aiu: int) -> dict:
    return {
        "type": "session.shutdown",
        "data": {"totalNanoAiu": nano_aiu},
    }


# ---------- collect_cli aggregation ----------


def test_collect_cli_aggregates_per_agent_per_model_bucket(
    tmp_path: Path,
) -> None:
    _write_session(
        tmp_path,
        "sess-a",
        [
            _subagent_completed(model="gpt-5.5", tokens=100),
            _subagent_completed(model="gpt-5.5", tokens=200),
            _subagent_completed(model="claude-sonnet-4.6", tokens=50),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    by_key = {(b.agent, b.model): b for b in buckets}
    assert by_key[("general-purpose", "gpt-5.5")].invocations == 2
    assert by_key[("general-purpose", "gpt-5.5")].total_tokens == 300
    assert by_key[("general-purpose", "claude-sonnet-4.6")].invocations == 1
    assert by_key[("general-purpose", "claude-sonnet-4.6")].total_tokens == 50


def test_collect_cli_session_dedup_across_multiple_events(
    tmp_path: Path,
) -> None:
    _write_session(
        tmp_path,
        "sess-x",
        [
            _subagent_completed(),
            _subagent_completed(),
            _subagent_completed(),
            _subagent_completed(),
            _subagent_completed(),
            _session_shutdown(1_000_000),
        ],
    )
    _, session_count, _, _, _ = collect_cli(tmp_path, days=30)
    assert session_count == 1


def test_collect_cli_sums_actual_nano_aiu_from_shutdown_events(
    tmp_path: Path,
) -> None:
    _write_session(tmp_path, "a", [_session_shutdown(1_000_000_000)])
    _write_session(tmp_path, "b", [_session_shutdown(2_500_000_000)])
    _, _, actual_nano, _, _ = collect_cli(tmp_path, days=30)
    assert actual_nano == 3_500_000_000


# ---------- Failure heuristic ----------


def test_failure_heuristic_quota_exceeded_dispatch_counted_as_failure(
    tmp_path: Path,
) -> None:
    # 0 tokens AND 0 tool calls AND <5s duration → upstream model failure
    _write_session(
        tmp_path,
        "s",
        [_subagent_completed(tokens=0, tool_calls=0, duration_ms=1500)],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.failures == 1
    assert bucket.failure_rate == 1.0


def test_failure_heuristic_successful_dispatch_not_counted(
    tmp_path: Path,
) -> None:
    # >0 tool calls → success, regardless of token count
    _write_session(
        tmp_path,
        "s",
        [_subagent_completed(tokens=0, tool_calls=3, duration_ms=500)],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.failures == 0


def test_failure_heuristic_long_timeout_not_counted(tmp_path: Path) -> None:
    # ≥5s duration → not a quota failure (slow upstream is legitimate)
    _write_session(
        tmp_path,
        "s",
        [_subagent_completed(tokens=0, tool_calls=0, duration_ms=6000)],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.failures == 0


def test_failure_heuristic_token_returning_dispatch_not_counted(
    tmp_path: Path,
) -> None:
    # >0 tokens → success, regardless of tool count
    _write_session(
        tmp_path,
        "s",
        [_subagent_completed(tokens=500, tool_calls=0, duration_ms=1000)],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.failures == 0


# ---------- Fail-soft contracts ----------


def test_collect_cli_handles_totaltokens_none_as_zero(tmp_path: Path) -> None:
    _write_session(
        tmp_path,
        "s",
        [
            {
                "type": "subagent.completed",
                "data": {
                    "agentName": "general-purpose",
                    "model": "gpt-5.5",
                    "totalTokens": None,
                    "totalToolCalls": 1,
                    "durationMs": 1000,
                },
            }
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.total_tokens == 0


def test_collect_cli_handles_missing_data_key(tmp_path: Path) -> None:
    """Missing ``data`` key is treated as malformed telemetry and skipped.

    Previously this produced a bucket with ``agent="?"`` / ``model="?"`` which
    inflated invocation counts from schema drift. Skipping is more correct.
    """
    _write_session(tmp_path, "s", [{"type": "subagent.completed"}])
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets == ()


@pytest.mark.parametrize("model_value", [None, "", "missing"])
def test_collect_cli_handles_model_none_or_missing(
    tmp_path: Path, model_value: object
) -> None:
    data = {"agentName": "x", "totalTokens": 1, "totalToolCalls": 1}
    if model_value != "missing":
        data["model"] = model_value
    _write_session(
        tmp_path, "s", [{"type": "subagent.completed", "data": data}]
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.model == "?"


def test_collect_cli_skips_malformed_json_lines(tmp_path: Path) -> None:
    sess_dir = tmp_path / "session-state" / "s"
    sess_dir.mkdir(parents=True)
    p = sess_dir / "events.jsonl"
    p.write_text(
        json.dumps(_subagent_completed(tokens=100))
        + "\n{ not json\n"
        + json.dumps(_subagent_completed(tokens=200))
        + "\n",
        encoding="utf-8",
    )
    buckets, _, _, skipped, _ = collect_cli(tmp_path, days=30)
    bucket = next(iter(buckets))
    assert bucket.invocations == 2
    assert bucket.total_tokens == 300
    assert skipped["lines"] == 1


def test_collect_cli_skips_sessions_older_than_cutoff(tmp_path: Path) -> None:
    fresh_path = _write_session(
        tmp_path, "fresh", [_subagent_completed(tokens=100)]
    )
    old_path = _write_session(
        tmp_path, "old", [_subagent_completed(tokens=200)]
    )
    # Backdate the old session 60 days
    old_t = time.time() - 60 * 86400
    os.utime(old_path, (old_t, old_t))
    buckets, sessions_seen, _, _, _ = collect_cli(tmp_path, days=30)
    assert sessions_seen == 1
    bucket = next(iter(buckets))
    assert bucket.total_tokens == 100


# ---------- _cheapest_candidate ----------


def test_cheapest_candidate_versatile_picks_haiku_over_gpt55() -> None:
    # Headline finding driver: general-purpose on gpt-5.5 → cheapest versatile
    assert _cheapest_candidate("versatile", "gpt-5.5") == "claude-haiku-4.5"


def test_cheapest_candidate_returns_none_when_current_model_unpriced() -> None:
    # Defensive guard: don't recommend a swap based on $0 baseline
    assert _cheapest_candidate("versatile", "not-in-pricing-table") is None


# ---------- build_report fail-closed semantics ----------


def test_build_report_fails_closed_on_missing_home(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    report = build_report(home=missing, days=30, include_chat=False)
    assert report.status == STATUS_FAIL
    assert report.reason_code == REASON_CODE_MISSING_COPILOT_HOME


def test_build_report_fails_closed_on_negative_days(tmp_path: Path) -> None:
    report = build_report(home=tmp_path, days=-5, include_chat=False)
    assert report.status == STATUS_FAIL
    assert report.reason_code == REASON_CODE_INVALID_INPUT


def test_build_report_succeeds_on_empty_but_valid_home(tmp_path: Path) -> None:
    report = build_report(home=tmp_path, days=1, include_chat=False)
    assert report.status == STATUS_PASS
    assert report.sessions_analyzed == 0
    assert report.cli_buckets == ()


# ---------- Defensive guards: non-dict JSON, schema drift, bool/int ----------


def test_collect_cli_skips_non_dict_json_lines(tmp_path: Path) -> None:
    """A line that parses to ``null``/list/string must not abort iteration.

    Regression: a bare ``null`` or ``[]`` in events.jsonl previously raised
    ``AttributeError`` in ``collect_cli`` on ``.get()``. The streaming reader
    now filters to dicts and treats the rest as malformed (skipped/lines++).
    """
    sess_dir = tmp_path / "session-state" / "sess-nondict"
    sess_dir.mkdir(parents=True)
    valid = json.dumps(_subagent_completed())
    payload = "\n".join([
        "null",
        "[1,2,3]",
        '"a string"',
        "42",
        valid,
    ])
    (sess_dir / "events.jsonl").write_text(payload + "\n", encoding="utf-8")
    buckets, sessions, _, skipped, _ = collect_cli(tmp_path, days=30)
    assert sessions == 1
    assert len(buckets) == 1
    # 4 non-dict lines should be counted as skipped lines (alongside the
    # 1 valid line that produced the bucket).
    assert skipped["lines"] == 4


def test_collect_cli_skips_event_with_non_dict_data_field(tmp_path: Path) -> None:
    """``event["data"]`` arriving as a string or list must not crash."""
    sess_dir = tmp_path / "session-state" / "sess-baddata"
    sess_dir.mkdir(parents=True)
    bad_subagent = {"type": "subagent.completed", "data": "this should be a dict"}
    bad_shutdown = {"type": "session.shutdown", "data": [1, 2, 3]}
    valid = _subagent_completed()
    (sess_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in [bad_subagent, bad_shutdown, valid]) + "\n",
        encoding="utf-8",
    )
    buckets, sessions, nano, _, _ = collect_cli(tmp_path, days=30)
    # Only the valid event contributes a bucket; the bad ones are silently
    # skipped (they parsed as JSON dicts but had malformed ``data`` payloads).
    assert sessions == 1
    assert len(buckets) == 1
    assert nano == 0.0


def test_collect_cli_coerces_string_tokens_to_zero(tmp_path: Path) -> None:
    """Telemetry numeric drift: a stringified ``totalTokens`` must not crash."""
    sess_dir = tmp_path / "session-state" / "sess-drift"
    sess_dir.mkdir(parents=True)
    drifted = {
        "type": "subagent.completed",
        "data": {
            "agentName": "general-purpose",
            "model": "gpt-5.5",
            "totalTokens": "not-a-number",
            "totalToolCalls": None,
            "durationMs": [1, 2],
        },
    }
    (sess_dir / "events.jsonl").write_text(json.dumps(drifted) + "\n", encoding="utf-8")
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert len(buckets) == 1
    b = buckets[0]
    assert b.total_tokens == 0
    assert b.total_duration_ms == 0
    # 0 tokens + 0 tool calls + 0 duration triggers the failure heuristic
    assert b.failures == 1


def test_build_report_rejects_bool_days() -> None:
    """``isinstance(True, int)`` is True; bool must be explicitly rejected.

    Regression: ``--days True`` (or any bool slipped past argparse via the
    Python API) would bypass ``days < 1`` because ``True == 1``. The guard
    now treats bool as invalid input.
    """
    report = build_report(home=Path("/tmp"), days=True, include_chat=False)  # type: ignore[arg-type]
    assert report.status == STATUS_FAIL
    assert report.reason_code == REASON_CODE_INVALID_INPUT
    report2 = build_report(home=Path("/tmp"), days=False, include_chat=False)  # type: ignore[arg-type]
    assert report2.status == STATUS_FAIL
    assert report2.reason_code == REASON_CODE_INVALID_INPUT


def test_collect_cli_ignores_bool_nano_aiu(tmp_path: Path) -> None:
    """``isinstance(True, (int, float))`` is True; bool must be filtered.

    Regression: a ``totalNanoAiu: true`` in malformed telemetry would have
    contributed 1.0 to actual_nano_aiu and inflated the cost baseline.
    """
    sess_dir = tmp_path / "session-state" / "sess-boolnano"
    sess_dir.mkdir(parents=True)
    drifted = {"type": "session.shutdown", "data": {"totalNanoAiu": True}}
    valid = _session_shutdown(nano_aiu=5_000_000_000)
    (sess_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in [drifted, valid]) + "\n",
        encoding="utf-8",
    )
    _, _, nano, _, _ = collect_cli(tmp_path, days=30)
    # Only the valid 5e9 should contribute; the bool True must be filtered.
    assert nano == 5_000_000_000.0
