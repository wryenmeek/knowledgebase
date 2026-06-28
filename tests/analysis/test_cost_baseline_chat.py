"""Tests for Chat/OTEL path in ``scripts.analysis.cost_baseline`` (#400, #402).

Covers:
* ``_iter_otel_inferences`` filtering and fail-soft behavior
* ``collect_chat`` aggregation and token handling
* ``ChatBucket.est_cost_usd`` — #402 blended-rate (Option A) and exact-split
  (Option B) implementations
* ``--chat-cache-share`` CLI flag wiring

Synthetic fixture builders are imported from ``_fixtures`` to avoid duplication
with ``test_cost_baseline.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.analysis._fixtures import (
    _otel_inference_event,
    _subagent_completed,
    _write_otel_session,
    _write_session,
)
from scripts.analysis.cost_baseline import (
    ChatBucket,
    collect_chat,
)
from scripts.analysis.pricing import PRICING


# ======================================================================
# P1 tests — _iter_otel_inferences fail-soft contracts
# ======================================================================


def test_iter_otel_inferences_filters_to_inference_operation_details_only(
    tmp_path: Path,
) -> None:
    """Only events with the exact inference event.name are yielded."""
    from scripts.analysis.cost_baseline import _iter_otel_inferences, _epoch_cutoff

    inference_event = _otel_inference_event(model="gpt-5.4", input_tokens=500)
    non_inference = {
        "attributes": {
            "event.name": "some.other.event",
            "gen_ai.request.model": "gpt-5.5",
        }
    }
    _write_otel_session(
        tmp_path, "vscode-otel-test.jsonl", [inference_event, non_inference]
    )

    skipped: dict[str, int] = {"files": 0, "lines": 0}
    results = list(_iter_otel_inferences(tmp_path, _epoch_cutoff(30), skipped))

    assert len(results) == 1
    assert results[0]["gen_ai.request.model"] == "gpt-5.4"
    # Non-inference events are expected (not malformed); skipped count stays 0
    assert skipped["lines"] == 0


def test_iter_otel_inferences_skips_events_with_no_attributes_dict(
    tmp_path: Path,
) -> None:
    """Events missing attributes or with non-dict attributes are silently skipped."""
    from scripts.analysis.cost_baseline import _iter_otel_inferences, _epoch_cutoff

    events = [
        {"no_attributes_key": "here"},
        {"attributes": "a-string-not-a-dict"},
        {"attributes": 42},
        _otel_inference_event(model="claude-sonnet-4.6"),
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    skipped: dict[str, int] = {"files": 0, "lines": 0}
    results = list(_iter_otel_inferences(tmp_path, _epoch_cutoff(30), skipped))

    assert len(results) == 1
    assert results[0]["gen_ai.request.model"] == "claude-sonnet-4.6"
    assert skipped["lines"] == 0  # silently skipped, not malformed JSON


def test_iter_otel_inferences_skips_malformed_json_lines(
    tmp_path: Path,
) -> None:
    """JSON parse errors increment skipped['lines'] and do not abort iteration."""
    from scripts.analysis.cost_baseline import _iter_otel_inferences, _epoch_cutoff

    valid_line = json.dumps(_otel_inference_event())
    content = valid_line + "\n{ not valid json\n" + valid_line + "\n"
    p = tmp_path / "traces" / "vscode-otel-test.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    skipped: dict[str, int] = {"files": 0, "lines": 0}
    results = list(_iter_otel_inferences(tmp_path, _epoch_cutoff(30), skipped))

    assert len(results) == 2
    assert skipped["lines"] == 1


# ======================================================================
# P1 tests — collect_chat aggregation
# ======================================================================


def test_collect_chat_excludes_events_with_missing_or_none_model(
    tmp_path: Path,
) -> None:
    """Events with None or missing gen_ai.request.model are dropped (not '?')."""
    events = [
        _otel_inference_event(model="gpt-5.4"),
        {
            "attributes": {
                "event.name": "gen_ai.client.inference.operation.details",
                # model key absent
            }
        },
        {
            "attributes": {
                "event.name": "gen_ai.client.inference.operation.details",
                "gen_ai.request.model": None,
            }
        },
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    buckets, _ = collect_chat(tmp_path, days=30)

    assert len(buckets) == 1
    assert buckets[0].model == "gpt-5.4"


def test_collect_chat_aggregates_input_output_tokens_per_model(
    tmp_path: Path,
) -> None:
    """Multiple events for the same model are summed into one ChatBucket."""
    events = [
        _otel_inference_event(model="gpt-5.4", input_tokens=1000, output_tokens=100),
        _otel_inference_event(model="gpt-5.4", input_tokens=500, output_tokens=50),
        _otel_inference_event(
            model="claude-sonnet-4.6", input_tokens=2000, output_tokens=200
        ),
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    buckets, _ = collect_chat(tmp_path, days=30)
    by_model = {b.model: b for b in buckets}

    assert by_model["gpt-5.4"].inferences == 2
    assert by_model["gpt-5.4"].input_tokens == 1500
    assert by_model["gpt-5.4"].output_tokens == 150
    assert by_model["claude-sonnet-4.6"].inferences == 1
    assert by_model["claude-sonnet-4.6"].input_tokens == 2000


def test_collect_chat_handles_missing_token_fields_as_zero(
    tmp_path: Path,
) -> None:
    """Events without token fields contribute 0 tokens, not an error."""
    events = [
        {
            "attributes": {
                "event.name": "gen_ai.client.inference.operation.details",
                "gen_ai.request.model": "gpt-5.4",
                # no token fields
            }
        }
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    buckets, _ = collect_chat(tmp_path, days=30)

    assert len(buckets) == 1
    assert buckets[0].input_tokens == 0
    assert buckets[0].output_tokens == 0
    assert buckets[0].est_cost_usd == 0.0


# ======================================================================
# P1 tests — ChatBucket.est_cost_usd (post-#402 behavior)
# ======================================================================


def test_chat_bucket_est_cost_uses_blended_rate_fallback() -> None:
    """#402 Option A: without cached tokens, 70% of input treated as cached.

    Fresh input is billed at cache_write_per_m for Anthropic models (mirrors
    the blended_rate() conservatism; see P2 code-review finding).
    """
    b = ChatBucket(
        model="claude-sonnet-4.6",
        inferences=1,
        input_tokens=1_000_000,
        output_tokens=100_000,
    )
    price = PRICING["claude-sonnet-4.6"]
    # Fresh input uses cache_write_per_m for Anthropic (P2 fix).
    fresh_rate = (
        price.cache_write_per_m
        if price.cache_write_per_m is not None
        else price.input_per_m
    )
    # Default mix: 70% cached, 30% fresh
    expected = (
        0.30 * 1_000_000 * fresh_rate
        + 0.70 * 1_000_000 * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected) < 1e-9


def test_chat_bucket_est_cost_zero_for_unknown_model() -> None:
    """A model absent from PRICING returns 0.0 (not a crash)."""
    b = ChatBucket(
        model="unknown-model-xyz", inferences=1, input_tokens=1000, output_tokens=100
    )
    assert b.est_cost_usd == 0.0


# ======================================================================
# #402 — exact-split (Option B) and blended-rate override
# ======================================================================


def test_chat_bucket_with_cached_input_tokens_uses_exact_split() -> None:
    """#402 Option B: when cached_input_tokens > 0, exact split is applied.

    Fresh input is billed at cache_write_per_m for Anthropic models (P2 fix).
    """
    cached = 700_000
    total_input = 1_000_000
    fresh = total_input - cached

    b = ChatBucket(
        model="claude-sonnet-4.6",
        inferences=1,
        input_tokens=total_input,
        output_tokens=100_000,
        cached_input_tokens=cached,
    )
    price = PRICING["claude-sonnet-4.6"]
    fresh_rate = (
        price.cache_write_per_m
        if price.cache_write_per_m is not None
        else price.input_per_m
    )
    expected = (
        fresh * fresh_rate
        + cached * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected) < 1e-9


def test_chat_bucket_exact_split_cheaper_than_blended_for_anthropic() -> None:
    """Exact split with 70% cached should produce lower cost than 100%-fresh."""
    b_exact = ChatBucket(
        model="claude-opus-4.7",
        inferences=1,
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_input_tokens=700_000,
    )
    # Old (pre-#402) upper-bound: all input at fresh rate
    price = PRICING["claude-opus-4.7"]
    old_cost = (
        1_000_000 * price.input_per_m + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert b_exact.est_cost_usd < old_cost


def test_chat_bucket_falls_back_to_blended_rate_when_cached_tokens_absent() -> None:
    """#402 Option A: cached_input_tokens == 0 → blended-rate fallback (not fresh-only)."""
    b = ChatBucket(
        model="gpt-5.4",
        inferences=1,
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_input_tokens=0,
    )
    price = PRICING["gpt-5.4"]
    cache_frac = 0.70  # default
    expected_blended = (
        (1.0 - cache_frac) * 1_000_000 * price.input_per_m
        + cache_frac * 1_000_000 * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    expected_fresh_only = (
        1_000_000 * price.input_per_m + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected_blended) < 1e-9
    # Must be strictly less than fresh-only (which was the pre-#402 approach)
    assert b.est_cost_usd < expected_fresh_only


def test_chat_cache_share_cli_flag_overrides_default_mix() -> None:
    """#402: chat_cache_share field on ChatBucket overrides the 0.70 default."""
    price = PRICING["gpt-5.4"]

    # cache_share=0.0 → all input at fresh rate (upper bound)
    b_no_cache = ChatBucket(
        model="gpt-5.4",
        inferences=1,
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_input_tokens=0,
        chat_cache_share=0.0,
    )
    expected_no_cache = (
        1_000_000 * price.input_per_m + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b_no_cache.est_cost_usd - expected_no_cache) < 1e-9

    # cache_share=0.9 → 90% of input at cached rate
    b_high_cache = ChatBucket(
        model="gpt-5.4",
        inferences=1,
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_input_tokens=0,
        chat_cache_share=0.90,
    )
    expected_high_cache = (
        0.10 * 1_000_000 * price.input_per_m
        + 0.90 * 1_000_000 * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b_high_cache.est_cost_usd - expected_high_cache) < 1e-9

    # Higher cache share → lower cost (since cached_per_m < input_per_m)
    assert b_high_cache.est_cost_usd < b_no_cache.est_cost_usd


def test_chat_cache_share_wires_through_collect_chat(tmp_path: Path) -> None:
    """--chat-cache-share is plumbed from collect_chat to each ChatBucket."""
    events = [_otel_inference_event(model="gpt-5.4", input_tokens=1_000_000, output_tokens=100_000)]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    # 0% cache → highest cost (all fresh)
    buckets_0, _ = collect_chat(tmp_path, days=30, chat_cache_share=0.0)
    # 90% cache → lowest cost
    buckets_90, _ = collect_chat(tmp_path, days=30, chat_cache_share=0.90)

    assert len(buckets_0) == 1
    assert len(buckets_90) == 1
    assert buckets_0[0].est_cost_usd > buckets_90[0].est_cost_usd


def test_collect_chat_accumulates_otel_cached_input_tokens(tmp_path: Path) -> None:
    """#402 Option B: gen_ai.usage.cache_read_input_tokens is summed per model."""
    events = [
        _otel_inference_event(model="claude-sonnet-4.6", input_tokens=1_000, cached_input_tokens=700),
        _otel_inference_event(model="claude-sonnet-4.6", input_tokens=500, cached_input_tokens=300),
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    buckets, _ = collect_chat(tmp_path, days=30)

    assert len(buckets) == 1
    b = buckets[0]
    assert b.cached_input_tokens == 1000  # 700 + 300
    assert b.input_tokens == 1500
    # Exact split must be used (cached_input_tokens > 0)
    price = PRICING["claude-sonnet-4.6"]
    total_fresh = 1500 - 1000  # 500
    total_output = 100 + 100   # from default _otel_inference_event output_tokens=100
    fresh_rate = (
        price.cache_write_per_m
        if price.cache_write_per_m is not None
        else price.input_per_m
    )
    expected_exact = (
        total_fresh * fresh_rate
        + 1000 * price.cached_per_m
        + total_output * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected_exact) < 1e-9
    # Exact split should be cheaper than all-input-at-fresh-rate (+ output)
    fresh_only = (
        1500 * price.input_per_m + total_output * price.output_per_m
    ) / 1_000_000.0
    assert b.est_cost_usd < fresh_only


# ======================================================================
# #403 — strict-window for OTEL events
# ======================================================================


def test_strict_window_excludes_old_otel_event_timestamps(tmp_path: Path) -> None:
    """--strict-window skips OTEL events with timestamps older than the window."""
    from datetime import datetime, timezone

    old_ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()

    events = [
        {**_otel_inference_event(model="gpt-5.4", input_tokens=1000), "timestamp": old_ts},
        {**_otel_inference_event(model="gpt-5.4", input_tokens=500), "timestamp": fresh_ts},
    ]
    _write_otel_session(tmp_path, "vscode-otel-test.jsonl", events)

    # Default: both events included
    buckets_default, _ = collect_chat(tmp_path, days=30)
    assert len(buckets_default) == 1
    assert buckets_default[0].input_tokens == 1500

    # Strict: only the fresh event included
    buckets_strict, _ = collect_chat(tmp_path, days=30, strict_window=True)
    assert len(buckets_strict) == 1
    assert buckets_strict[0].input_tokens == 500


# ======================================================================
# P2 — cache_write_per_m for Anthropic fresh input
# ======================================================================


def test_chat_bucket_uses_cache_write_per_m_for_anthropic_fresh_input() -> None:
    """P2: Anthropic fresh input is billed at cache_write_per_m, not input_per_m.

    claude-sonnet-4.5 has cache_write_per_m=3.75 and input_per_m=3.00.
    Both Option B paths must use cache_write_per_m for the fresh share.
    """
    price = PRICING["claude-sonnet-4.5"]
    assert price.cache_write_per_m is not None
    assert price.cache_write_per_m != price.input_per_m

    cached = 700_000
    total_input = 1_000_000
    fresh = total_input - cached

    b = ChatBucket(
        model="claude-sonnet-4.5",
        inferences=1,
        input_tokens=total_input,
        output_tokens=100_000,
        cached_input_tokens=cached,
    )
    expected_with_cache_write = (
        fresh * price.cache_write_per_m
        + cached * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    wrong_with_input_per_m = (
        fresh * price.input_per_m
        + cached * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected_with_cache_write) < 1e-9
    assert b.est_cost_usd != wrong_with_input_per_m


def test_chat_bucket_falls_back_to_input_per_m_when_cache_write_per_m_is_none() -> None:
    """P2: When cache_write_per_m is None (OpenAI), fresh input uses input_per_m."""
    price = PRICING["gpt-5.4"]
    assert price.cache_write_per_m is None

    cached = 700_000
    total_input = 1_000_000
    fresh = total_input - cached

    b = ChatBucket(
        model="gpt-5.4",
        inferences=1,
        input_tokens=total_input,
        output_tokens=100_000,
        cached_input_tokens=cached,
    )
    expected = (
        fresh * price.input_per_m
        + cached * price.cached_per_m
        + 100_000 * price.output_per_m
    ) / 1_000_000.0
    assert abs(b.est_cost_usd - expected) < 1e-9


# ======================================================================
# CLI smoke test — --chat-cache-share argparse wiring
# ======================================================================


def test_chat_cache_share_cli_flag_smoke(tmp_path: Path) -> None:
    """--chat-cache-share 0.5 parses and wires through: blended-rate note shows 50%."""
    import io
    from scripts.analysis.cost_baseline import run_cli

    _write_otel_session(
        tmp_path,
        "vscode-otel-test.jsonl",
        [_otel_inference_event(model="gpt-5.4", input_tokens=1000)],
    )
    buf = io.StringIO()
    rc = run_cli(
        ["--home", str(tmp_path), "--days", "30", "--chat-cache-share", "0.5"],
        output_stream=buf,
    )
    assert rc == 0
    assert "50%" in buf.getvalue()
