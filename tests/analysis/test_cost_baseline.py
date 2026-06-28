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


# ---------- Effort capture (session default + per-call override) ----------


def _session_start(reasoning_effort: str = "default") -> dict:
    return {
        "type": "session.start",
        "data": {
            "sessionId": "test-session",
            "version": 1,
            "reasoningEffort": reasoning_effort,
            "contextTier": "default",
        },
    }


def _task_tool_start(
    tool_call_id: str,
    agent_type: str = "general-purpose",
    reasoning_effort: str | None = None,
) -> dict:
    args: dict[str, object] = {
        "agent_type": agent_type,
        "description": "test",
        "name": "t",
        "prompt": "p",
    }
    if reasoning_effort is not None:
        args["reasoning_effort"] = reasoning_effort
    return {
        "type": "tool.execution_start",
        "data": {
            "toolCallId": tool_call_id,
            "toolName": "task",
            "arguments": args,
        },
    }


def _subagent_with_id(
    tool_call_id: str,
    agent: str = "general-purpose",
    model: str = "claude-sonnet-4.6",
) -> dict:
    e = _subagent_completed(agent=agent, model=model)
    e["data"]["toolCallId"] = tool_call_id
    return e


def test_bucket_inherits_session_default_effort(tmp_path: Path) -> None:
    """When no per-call override is present, bucket gets session.start effort."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="high"),
            _subagent_with_id("tc-1"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert len(buckets) == 1
    assert buckets[0].effort == "high"


def test_per_call_override_beats_session_default(tmp_path: Path) -> None:
    """task tool arguments.reasoning_effort overrides session.start.reasoningEffort."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="medium"),
            _task_tool_start("tc-A", reasoning_effort="xhigh"),
            _subagent_with_id("tc-A"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "xhigh"


def test_default_effort_when_no_session_start(tmp_path: Path) -> None:
    """Missing session.start → 'default' (the canonical sentinel)."""
    _write_session(tmp_path, "sess", [_subagent_with_id("tc-x")])
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "default"


def test_unknown_effort_value_normalizes_to_default(tmp_path: Path) -> None:
    """Garbled effort value in telemetry must not produce a non-canonical bucket key."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="UNKNOWN_VALUE"),
            _subagent_with_id("tc-y"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "default"


def test_buckets_split_by_effort(tmp_path: Path) -> None:
    """Same (agent, model) at different effort levels = separate buckets."""
    _write_session(
        tmp_path,
        "s1",
        [
            _session_start(reasoning_effort="medium"),
            _subagent_with_id("tc-1"),
        ],
    )
    _write_session(
        tmp_path,
        "s2",
        [
            _session_start(reasoning_effort="high"),
            _subagent_with_id("tc-2"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    keys = sorted((b.agent, b.model, b.effort) for b in buckets)
    assert keys == [
        ("general-purpose", "claude-sonnet-4.6", "high"),
        ("general-purpose", "claude-sonnet-4.6", "medium"),
    ]


def test_per_call_override_only_affects_matched_dispatch(tmp_path: Path) -> None:
    """toolCallId-keyed override must not leak across dispatches."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="medium"),
            _task_tool_start("tc-OVR", reasoning_effort="xhigh"),
            _subagent_with_id("tc-OVR"),
            _subagent_with_id("tc-OTHER"),  # no override → session default
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    by_effort = {b.effort: b for b in buckets}
    assert "xhigh" in by_effort
    assert "medium" in by_effort
    assert by_effort["xhigh"].invocations == 1
    assert by_effort["medium"].invocations == 1


# ---------- Reviewer remediation: cross-session isolation, explicit-default
# override, SavingsRow effort, failure-attribution after split,
# defensive guards (per code-review / test-engineer / security-auditor) ----


from scripts.analysis.cost_baseline import _build_savings, AgentBucket
from scripts.analysis.pricing import EFFORT_CAPABLE_MODELS


# P0 (test-eng): effort-aware downgrade-candidate flip


def test_cheapest_candidate_flips_to_downgrade_when_effort_inflates_current() -> None:
    """Headline payoff of the (agent, model, effort) split.

    gpt-5.4 at default is cheaper than every powerful candidate (so no
    swap), but at effort=high the 2.5× output multiplier pushes it past
    claude-sonnet-4.6's fixed rate — sonnet then becomes a downgrade
    candidate. This is the user-visible flip the bucket-key change enables.
    """
    assert (
        _cheapest_candidate("powerful", "gpt-5.4", current_effort="default") is None
    )
    assert (
        _cheapest_candidate("powerful", "gpt-5.4", current_effort="high")
        == "claude-sonnet-4.6"
    )


# P1-a (test-eng): cross-session toolCallId isolation


def test_per_call_override_does_not_leak_across_sessions(tmp_path: Path) -> None:
    """A toolCallId reused across sessions must keep effort separate.

    Regression guard: a refactor that hoists per_call_effort out of the
    per-session loop would silently cross-contaminate.
    """
    _write_session(
        tmp_path,
        "s1",
        [
            _session_start(reasoning_effort="medium"),
            _task_tool_start("shared-id", reasoning_effort="xhigh"),
            _subagent_with_id("shared-id"),
        ],
    )
    _write_session(
        tmp_path,
        "s2",
        [
            _session_start(reasoning_effort="medium"),
            _subagent_with_id("shared-id"),  # NO per-task override here
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    by_effort = {b.effort: b for b in buckets}
    assert by_effort["xhigh"].invocations == 1
    assert by_effort["medium"].invocations == 1


# P2 (code-rev): explicit reasoning_effort="default" overrides session high


def test_explicit_default_override_steps_down_session_default(tmp_path: Path) -> None:
    """An explicit per-task reasoning_effort='default' must defeat session high.

    Previously the `if eff != "default"` filter silently discarded the
    explicit step-down. Now any presence of the key (including 'default')
    is recorded as an override.
    """
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="xhigh"),
            _task_tool_start("tc-step-down", reasoning_effort="default"),
            _subagent_with_id("tc-step-down"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "default"


# P2 (test-eng): _build_savings coverage


def test_build_savings_omits_row_when_no_cheaper_candidate() -> None:
    """A bucket whose current model is already cheapest produces no row."""
    bucket = AgentBucket(
        agent="documentation-engineer",
        model="claude-haiku-4.5",  # cheapest versatile candidate
        effort="default",
        invocations=1,
        total_tokens=1_000_000,
        total_duration_ms=1000,
        failures=0,
        sessions_count=1,
    )
    rows = _build_savings((bucket,))
    assert rows == ()


def test_build_savings_emits_row_with_effort_when_swap_available() -> None:
    """A bucket with a known-cheaper alt produces a SavingsRow that carries
    the bucket's effort field so the consumer can distinguish swap-model
    recommendations from drop-effort alternatives.
    """
    bucket = AgentBucket(
        agent="documentation-engineer",
        model="claude-opus-4.7",
        effort="xhigh",
        invocations=1,
        total_tokens=1_000_000,
        total_duration_ms=1000,
        failures=0,
        sessions_count=1,
    )
    rows = _build_savings((bucket,))
    assert len(rows) == 1
    assert rows[0].current_effort == "xhigh"
    assert rows[0].current_model == "claude-opus-4.7"
    assert rows[0].savings_usd > 0


# P2 (test-eng): failure attribution after bucket-key split


def test_failures_attribute_to_current_effort_bucket(tmp_path: Path) -> None:
    """A failed subagent.completed under session xhigh must NOT phantom-create
    a separate 'default'-effort bucket — failures land in the active-effort
    bucket like successes do.
    """
    failed = {
        "type": "subagent.completed",
        "data": {
            "toolCallId": "tc-fail",
            "agentName": "general-purpose",
            "model": "gpt-5.5",
            "totalTokens": 0,
            "totalToolCalls": 0,
            "durationMs": 1500,  # < 5000ms threshold
        },
    }
    _write_session(
        tmp_path,
        "sess",
        [_session_start(reasoning_effort="xhigh"), failed],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert len(buckets) == 1
    assert buckets[0].effort == "xhigh"
    assert buckets[0].failures == 1


# P2 (sec-aud): _normalize_effort length guard


def test_normalize_effort_rejects_oversize_string() -> None:
    """Multi-MB strings must short-circuit before .lower() materializes a copy."""
    from scripts.analysis.cost_baseline import _normalize_effort

    long_value = "x" * 1_000_000
    assert _normalize_effort(long_value) == "default"
    # A length-32 input is allowed (boundary), even if it normalizes to default
    assert _normalize_effort("a" * 32) == "default"
    # 33 chars is rejected
    assert _normalize_effort("a" * 33) == "default"


# P3 (code-rev): empty-string toolCallId guard


def test_empty_string_tool_call_id_is_rejected(tmp_path: Path) -> None:
    """A tool.execution_start with toolCallId='' must not become a wildcard key."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="medium"),
            _task_tool_start("", reasoning_effort="xhigh"),  # invalid id
            _subagent_with_id("real-tc"),  # falls through to session default
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    # The bucket must inherit session 'medium', not the rogue '' override.
    assert buckets[0].effort == "medium"


# P3 (test-eng): non-string toolCallId on subagent.completed


def test_subagent_completed_with_none_tool_call_id(tmp_path: Path) -> None:
    """A subagent.completed without a toolCallId falls back to session default."""
    e = _subagent_completed()
    e["data"].pop("toolCallId", None)  # ensure absent
    _write_session(
        tmp_path,
        "sess",
        [_session_start(reasoning_effort="high"), e],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "high"


# P3 (test-eng): per-call override with unknown effort value
# Currently the override-side normalizes "BOGUS" → "default" and records it
# (because the new contract records the override regardless of value). This
# is correct: the user explicitly stepped down to default for this dispatch.


def test_unknown_effort_in_override_records_default(tmp_path: Path) -> None:
    """An unknown effort value in a per-call override normalizes to default."""
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="xhigh"),
            _task_tool_start("tc-x", reasoning_effort="BOGUS"),
            _subagent_with_id("tc-x"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    # BOGUS normalizes to default — the override is recorded and bucket
    # inherits default, NOT the xhigh session default.
    assert buckets[0].effort == "default"


# P3 (code-rev): AgentBucket default-value pin


def test_agent_bucket_effort_defaults_to_default_string() -> None:
    """Pinning the dataclass default — guards a future field reorder regression."""
    b = AgentBucket(
        agent="x",
        model="claude-haiku-4.5",
        invocations=1,
        total_tokens=0,
        total_duration_ms=0,
        failures=0,
        sessions_count=1,
    )
    assert b.effort == "default"


# P3 (code-rev): multiple session.start → last-wins (matches updated docstring)


def test_multiple_session_start_events_last_one_wins(tmp_path: Path) -> None:
    """Real sessions resume across restarts and emit multiple session.start
    events; the last one reflects the active configuration.
    """
    _write_session(
        tmp_path,
        "sess",
        [
            _session_start(reasoning_effort="medium"),
            _session_start(reasoning_effort="xhigh"),
            _subagent_with_id("tc-1"),
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert buckets[0].effort == "xhigh"


# ======================================================================
# P1 tests (#400) — collect_cli / _cheapest_candidate gaps
# ======================================================================


def test_collect_cli_handles_agent_none_or_missing_as_question_mark(
    tmp_path: Path,
) -> None:
    """agentName=None and absent agentName both map to '?'."""
    _write_session(
        tmp_path,
        "s-none",
        [
            {
                "type": "subagent.completed",
                "data": {
                    "agentName": None,
                    "model": "gpt-5.5",
                    "totalTokens": 100,
                    "totalToolCalls": 1,
                    "durationMs": 1000,
                },
            }
        ],
    )
    _write_session(
        tmp_path,
        "s-missing",
        [
            {
                "type": "subagent.completed",
                "data": {
                    "model": "gpt-5.5",
                    "totalTokens": 200,
                    "totalToolCalls": 1,
                    "durationMs": 1000,
                },
            }
        ],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert all(b.agent == "?" for b in buckets)


def test_iter_session_events_skips_unreadable_files(tmp_path: Path) -> None:
    """An events.jsonl that is actually a directory raises OSError on open → skipped."""
    from scripts.analysis.cost_baseline import _iter_session_events, _epoch_cutoff

    # Make events.jsonl a directory — stat() succeeds but open() raises IsADirectoryError
    sess_dir = tmp_path / "session-state" / "sess-dir"
    (sess_dir / "events.jsonl").mkdir(parents=True)

    skipped: dict[str, int] = {"files": 0, "lines": 0}
    events = list(_iter_session_events(tmp_path, _epoch_cutoff(30), skipped))

    assert events == []
    assert skipped["files"] >= 1


def test_cheapest_candidate_lightweight_picks_gpt5_4_nano_over_gpt55() -> None:
    """gpt-5.4-nano is the cheapest lightweight candidate; returned over gpt-5.5."""
    result = _cheapest_candidate("lightweight", "gpt-5.5")
    assert result == "gpt-5.4-nano"


def test_cheapest_candidate_skips_current_model_from_pool() -> None:
    """Current model is excluded from the candidate set even when it is in the pool."""
    # claude-haiku-4.5 is in LIGHTWEIGHT_CANDIDATES; gpt-5.4-nano should be returned
    result = _cheapest_candidate("lightweight", "claude-haiku-4.5")
    assert result is not None
    assert result != "claude-haiku-4.5"


def test_cheapest_candidate_unknown_workload_class_falls_back_to_versatile() -> None:
    """An unknown workload class falls back to the VERSATILE_CANDIDATES pool."""
    result_unknown = _cheapest_candidate("nonexistent-class", "gpt-5.5")
    result_versatile = _cheapest_candidate("versatile", "gpt-5.5")
    assert result_unknown == result_versatile


def test_cheapest_candidate_returns_none_when_no_pool_member_is_cheaper() -> None:
    """When the current model is already the cheapest in the pool, None is returned."""
    # gpt-5.4-nano is the cheapest lightweight model; no cheaper alternative exists
    result = _cheapest_candidate("lightweight", "gpt-5.4-nano")
    assert result is None


# ======================================================================
# P2 tests (#400) — integration / render / pricing-freshness
# ======================================================================


def test_main_smoke_writes_expected_section_headers(tmp_path: Path) -> None:
    """Integration: run_cli writes the three expected section headers."""
    import io
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    _write_session(tmp_path, "sess", [_subagent_completed()])
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--skip-chat"],
        output_stream=buf,
    )
    output = buf.getvalue()
    assert rc == 0
    assert "## CLI sub-agent baseline" in output
    assert "## Savings projection" in output
    assert "## Experimentation priority" in output


def test_main_skip_chat_flag_omits_chat_section(tmp_path: Path) -> None:
    """--skip-chat suppresses the VS Code Copilot Chat section."""
    import io
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--skip-chat"],
        output_stream=buf,
    )
    assert rc == 0
    assert "VS Code Copilot Chat" not in buf.getvalue()


def test_main_empty_home_does_not_crash(tmp_path: Path) -> None:
    """Missing home directory → STATUS_FAIL with REASON_CODE_MISSING_COPILOT_HOME."""
    import io
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    missing = tmp_path / "does-not-exist"
    rc = run_cli(["--home", str(missing), "--days", "30"], output_stream=buf)
    assert rc == 1
    assert REASON_CODE_MISSING_COPILOT_HOME in buf.getvalue()


def test_pricing_freshness_warning_emitted_when_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale PRICING_RETRIEVED date triggers the WARNING line in text output."""
    import io
    import scripts.analysis.cost_baseline as cb
    from datetime import date

    monkeypatch.setattr(cb, "PRICING_RETRIEVED", date(2020, 1, 1))
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--skip-chat"],
        output_stream=buf,
    )
    assert rc == 0
    assert "WARNING" in buf.getvalue()


def test_pricing_freshness_no_warning_when_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A current PRICING_RETRIEVED date emits no WARNING line."""
    import io
    import scripts.analysis.cost_baseline as cb
    from datetime import date

    monkeypatch.setattr(cb, "PRICING_RETRIEVED", date.today())
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--skip-chat"],
        output_stream=buf,
    )
    assert rc == 0
    assert "WARNING" not in buf.getvalue()


def test_render_baseline_table_sorts_by_cost_descending(tmp_path: Path) -> None:
    """build_report emits cli_buckets sorted by est_cost_usd descending."""
    _write_session(
        tmp_path,
        "s-cheap",
        [_subagent_completed(model="claude-haiku-4.5", tokens=100_000)],
    )
    _write_session(
        tmp_path,
        "s-expensive",
        [_subagent_completed(model="gpt-5.5", tokens=10_000_000)],
    )
    report = build_report(home=tmp_path, days=30, include_chat=False)
    costs = [b.est_cost_usd for b in report.cli_buckets]
    assert costs == sorted(costs, reverse=True)


def test_render_savings_table_total_equals_sum_of_per_row_savings() -> None:
    """_render_savings_table TOTAL line equals sum of per-row savings."""
    from scripts.analysis.cost_baseline import _render_savings_table, SavingsRow

    rows = (
        SavingsRow(
            agent="a",
            current_model="gpt-5.5",
            current_effort="default",
            current_cost_usd=10.0,
            alt_model="claude-haiku-4.5",
            alt_cost_usd=2.0,
            savings_usd=8.0,
            reduction_pct=80.0,
        ),
        SavingsRow(
            agent="b",
            current_model="gpt-5.5",
            current_effort="default",
            current_cost_usd=5.0,
            alt_model="claude-haiku-4.5",
            alt_cost_usd=1.0,
            savings_usd=4.0,
            reduction_pct=80.0,
        ),
    )
    table = _render_savings_table(rows)
    expected_total = sum(r.savings_usd for r in rows)
    assert f"{expected_total:.2f}" in table
    assert "TOTAL" in table


def test_render_savings_table_omits_rows_with_zero_or_negative_savings(
    tmp_path: Path,
) -> None:
    """An agent already on the cheapest model produces no SavingsRow."""
    # claude-haiku-4.5 is cheapest in versatile/lightweight pools
    _write_session(
        tmp_path,
        "s",
        [_subagent_completed(model="claude-haiku-4.5", tokens=1_000_000)],
    )
    report = build_report(home=tmp_path, days=30, include_chat=False)
    assert report.savings == ()


def test_render_priority_list_caps_at_top_n(tmp_path: Path) -> None:
    """_build_priority respects the top_n cap."""
    for i in range(5):
        _write_session(
            tmp_path,
            f"s{i}",
            [_subagent_completed(agent=f"agent-{i}", tokens=1_000_000)],
        )
    report = build_report(home=tmp_path, days=30, top_n=3, include_chat=False)
    assert len(report.priority) == 3


# ======================================================================
# P3 tests (#400) — schema / invariant guards
# ======================================================================


def test_agent_class_maps_only_to_known_workload_classes() -> None:
    """Every entry in AGENT_CLASS must map to a recognised workload class."""
    from scripts.analysis.cost_baseline import AGENT_CLASS

    valid_classes = {"lightweight", "versatile", "powerful"}
    for agent, cls in AGENT_CLASS.items():
        assert cls in valid_classes, (
            f"agent {agent!r} mapped to unknown class {cls!r}"
        )


def test_candidate_pool_models_are_in_pricing_table() -> None:
    """Every model in the workload-class candidate pools must be in PRICING."""
    from scripts.analysis.pricing import (
        LIGHTWEIGHT_CANDIDATES,
        POWERFUL_CANDIDATES,
        PRICING,
        VERSATILE_CANDIDATES,
    )

    for model in (
        *LIGHTWEIGHT_CANDIDATES,
        *VERSATILE_CANDIDATES,
        *POWERFUL_CANDIDATES,
    ):
        assert model in PRICING, (
            f"{model!r} in a candidate pool but absent from PRICING table"
        )


def test_agent_bucket_failure_rate_handles_zero_invocations() -> None:
    """failure_rate must not divide by zero when invocations == 0."""
    b = AgentBucket(
        agent="x",
        model="claude-haiku-4.5",
        invocations=0,
        total_tokens=0,
        total_duration_ms=0,
        failures=0,
        sessions_count=0,
    )
    assert b.failure_rate == 0.0


def test_main_json_format_flag_emits_valid_json(tmp_path: Path) -> None:
    """--format json produces parseable JSON with expected top-level keys."""
    import io
    from scripts.analysis.cost_baseline import run_cli

    buf = io.StringIO()
    _write_session(tmp_path, "s", [_subagent_completed()])
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--format", "json", "--skip-chat"],
        output_stream=buf,
    )
    assert rc == 0
    doc = json.loads(buf.getvalue())
    assert doc["status"] == STATUS_PASS
    assert "cli_buckets" in doc
    assert "chat_buckets" in doc


# ======================================================================
# #403 — --strict-window per-event timestamp filtering
# ======================================================================


def test_strict_window_excludes_old_event_timestamps_when_mtime_is_fresh(
    tmp_path: Path,
) -> None:
    """mtime=fresh + old event timestamps → strict mode excludes all events."""
    from datetime import datetime, timezone

    old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    _write_session(
        tmp_path,
        "sess",
        [
            {**_subagent_completed(tokens=500), "timestamp": old_ts},
            {**_subagent_completed(tokens=200), "timestamp": old_ts},
        ],
    )

    # Default mode: both events included (file mtime is fresh)
    buckets_default, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert len(buckets_default) == 1
    assert buckets_default[0].total_tokens == 700

    # Strict mode: old-timestamp events filtered out
    buckets_strict, _, _, _, _ = collect_cli(tmp_path, days=30, strict_window=True)
    assert len(buckets_strict) == 0


def test_default_window_includes_old_event_timestamps_when_mtime_is_fresh(
    tmp_path: Path,
) -> None:
    """Without --strict-window, old event timestamps don't block inclusion."""
    from datetime import datetime, timezone

    old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    _write_session(
        tmp_path,
        "sess",
        [{**_subagent_completed(tokens=300), "timestamp": old_ts}],
    )
    buckets, _, _, _, _ = collect_cli(tmp_path, days=30)
    assert len(buckets) == 1
    assert buckets[0].total_tokens == 300

