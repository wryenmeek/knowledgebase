"""Tests for ``scripts.analysis.pricing``: blended rate + cost estimation."""

from __future__ import annotations

import pytest

from scripts.analysis.pricing import (
    ModelPrice,
    PRICING,
    blended_rate,
    estimate_cost_usd,
)


def test_blended_rate_openai_uses_input_when_cache_write_absent() -> None:
    # gpt-5.5: input=5.00, cached=0.50, output=30.00, no cache_write
    # default mix 20/70/10 → 0.2*5.00 + 0.7*0.50 + 0.1*30.00 = 4.35
    assert blended_rate("gpt-5.5") == pytest.approx(4.35)


def test_blended_rate_anthropic_substitutes_cache_write_for_input() -> None:
    # claude-sonnet-4.6: input=3.00, cached=0.30, cache_write=3.75, output=15.00
    # default mix uses cache_write (3.75) for fresh-input share:
    # 0.2*3.75 + 0.7*0.30 + 0.1*15.00 = 2.46
    assert blended_rate("claude-sonnet-4.6") == pytest.approx(2.46)


def test_blended_rate_rejects_shares_that_dont_sum_to_one() -> None:
    with pytest.raises(ValueError, match="must equal 1.0"):
        blended_rate(
            "gpt-5.5",
            input_share=0.5,
            cache_share=0.5,
            output_share=0.5,
        )


def test_blended_rate_accepts_shares_within_floating_point_tolerance() -> None:
    # 1/3 split with rounding — sum is 0.9999999 + epsilon, must accept
    rate = blended_rate(
        "gpt-5.5",
        input_share=0.3333333,
        cache_share=0.3333333,
        output_share=0.3333334,
    )
    assert rate > 0.0  # no exception


def test_blended_rate_returns_zero_for_unknown_model() -> None:
    assert blended_rate("made-up-model-9") == 0.0


@pytest.mark.parametrize(
    "model,tokens,expected",
    [
        ("gpt-5.5", 1_000_000, 4.35),
        ("gpt-5.5", 0, 0.0),
        ("gpt-5.5", 500_000, 2.175),
        ("claude-sonnet-4.6", 2_000_000, 4.92),
    ],
)
def test_estimate_cost_usd_math(model: str, tokens: int, expected: float) -> None:
    assert estimate_cost_usd(model, tokens) == pytest.approx(expected)


def test_estimate_cost_usd_returns_zero_for_unknown_model() -> None:
    assert estimate_cost_usd("does-not-exist", 1_000_000) == 0.0


def test_estimate_cost_usd_question_mark_model_does_not_raise() -> None:
    # "?" is the sentinel for missing model in CLI events; must produce $0
    # rather than crash. Guards the failure-attribution path in the report.
    assert estimate_cost_usd("?", 1_000_000) == 0.0


def test_pricing_table_lookup_is_a_dict_of_modelprice() -> None:
    for model_id, price in PRICING.items():
        assert isinstance(price, ModelPrice), model_id
        assert price.input_per_m >= 0
        assert price.cached_per_m >= 0
        assert price.output_per_m >= 0
        assert price.cache_write_per_m is None or price.cache_write_per_m >= 0


def test_anthropic_models_have_cache_write_set_others_dont() -> None:
    for model_id, price in PRICING.items():
        is_anthropic = model_id.startswith("claude-")
        if is_anthropic:
            assert price.cache_write_per_m is not None, (
                f"{model_id} is Anthropic — must declare cache_write_per_m"
            )
        else:
            assert price.cache_write_per_m is None, (
                f"{model_id} is non-Anthropic — must NOT declare "
                f"cache_write_per_m"
            )


# ---------- Effort-aware blended_rate / estimate_cost_usd ----------


import pytest as _pytest

from scripts.analysis.pricing import (  # noqa: E402
    EFFORT_CAPABLE_MODELS,
    blended_rate as _blended,
    estimate_cost_usd as _estimate,
)


def test_effort_default_equals_no_effort_arg() -> None:
    """Passing effort='default' must not change the result vs. omitting it."""
    base = _blended("gpt-5.4-mini")
    assert _blended("gpt-5.4-mini", effort="default") == base
    assert _blended("gpt-5.4-mini", effort="medium") == base


def test_effort_high_inflates_only_output_share() -> None:
    """effort=high must inflate only the 10% output share (2.5× multiplier)."""
    base = _blended("gpt-5.4-mini")
    high = _blended("gpt-5.4-mini", effort="high")
    # Output share = 10% × $4.50/M × 2.5 = $1.125/M added vs. baseline output
    # baseline output contribution = 10% × $4.50/M = $0.45/M
    # high contribution = 10% × $4.50/M × 2.5 = $1.125/M
    # delta = $0.675/M
    delta = high - base
    assert abs(delta - 0.675) < 0.01, f"expected ≈$0.675/M, got ${delta:.4f}"


def test_effort_xhigh_doubles_high_delta() -> None:
    """xhigh (5×) should be roughly double the high (2.5×) output share delta."""
    base = _blended("gpt-5.5")
    high_delta = _blended("gpt-5.5", effort="high") - base
    xhigh_delta = _blended("gpt-5.5", effort="xhigh") - base
    # Ratio of (5.0-1.0)/(2.5-1.0) = 4/1.5 ≈ 2.67
    ratio = xhigh_delta / high_delta
    assert 2.5 < ratio < 2.9, f"expected ratio ~2.67, got {ratio:.2f}"


def test_effort_ignored_on_non_effort_models() -> None:
    """Sonnet/Haiku don't expose effort; passing it must be a no-op."""
    assert _blended("claude-sonnet-4.6") == _blended("claude-sonnet-4.6", effort="high")
    assert _blended("claude-haiku-4.5") == _blended("claude-haiku-4.5", effort="xhigh")


def test_effort_capable_set_matches_docs() -> None:
    """Pin the effort-capable model set against the documented list."""
    expected = {
        "claude-opus-4.6",
        "claude-opus-4.7",
        "gpt-5-mini",
        "gpt-5.3-codex",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.5",
    }
    assert set(EFFORT_CAPABLE_MODELS) == expected


def test_unknown_effort_value_falls_back_to_baseline() -> None:
    """An unknown effort string must not crash; treat as baseline."""
    assert _blended("gpt-5.4-mini", effort="bogus") == _blended("gpt-5.4-mini")


def test_estimate_cost_usd_passes_effort_through() -> None:
    """estimate_cost_usd must respect the effort param."""
    base = _estimate("gpt-5.4-mini", 1_000_000)
    high = _estimate("gpt-5.4-mini", 1_000_000, effort="high")
    assert high > base
    assert abs((high - base) - 0.675) < 0.01


def test_max_effort_only_meaningful_for_models_supporting_it() -> None:
    """effort=max should inflate opus-4.7 output but be a no-op on haiku."""
    opus_max = _blended("claude-opus-4.7", effort="max")
    opus_base = _blended("claude-opus-4.7")
    assert opus_max > opus_base
    # haiku ignores
    assert _blended("claude-haiku-4.5", effort="max") == _blended("claude-haiku-4.5")


def test_low_effort_reduces_output_share() -> None:
    """effort=low (0.7×) should produce a lower blended rate than default."""
    base = _blended("gpt-5.4-mini")
    low = _blended("gpt-5.4-mini", effort="low")
    assert low < base


# ---------- Reviewer remediation: subset invariant, falsy effort, case ----


def test_effort_capable_models_subset_of_pricing() -> None:
    """A model in EFFORT_CAPABLE_MODELS but missing from PRICING would
    silently zero its blended_rate while keeping the multiplier set,
    causing recommendations against a $0 baseline. Pin the invariant.
    """
    from scripts.analysis.pricing import PRICING
    missing = EFFORT_CAPABLE_MODELS - set(PRICING.keys())
    assert missing == set(), f"effort-capable models missing from PRICING: {missing}"


@_pytest.mark.parametrize("effort_value", [None, "", 0, False, [], {}])
def test_blended_rate_treats_falsy_and_non_string_effort_safely(effort_value) -> None:
    """blended_rate must not crash on falsy/non-string effort values.

    Type hint says ``str`` but Python doesn't enforce; defensive behavior
    is "fall back to baseline" via _EFFORT_OUTPUT_MULTIPLIER.get default.
    """
    rate = _blended("gpt-5.4-mini", effort=effort_value)  # type: ignore[arg-type]
    assert rate == _blended("gpt-5.4-mini")  # equals baseline


def test_blended_rate_case_sensitive_in_pricing_module() -> None:
    """pricing.blended_rate does NOT lowercase — callers must normalize first.

    Pinning current behavior: a 'HIGH' string at the pricing layer is
    treated as unknown and falls back to baseline. The normalization
    contract lives in cost_baseline._normalize_effort, not in pricing.
    """
    assert _blended("gpt-5.5", effort="HIGH") == _blended("gpt-5.5")
    # Lowercase 'high' produces the inflated rate
    assert _blended("gpt-5.5", effort="high") > _blended("gpt-5.5")


# ---------- Long-context tier selection ----------

LONG_CONTEXT_MODELS = [
    # (model, threshold, lc_input_per_m, lc_output_per_m)
    ("gpt-5.4", 272_000, 5.00, 22.50),
    ("gpt-5.5", 272_000, 10.00, 45.00),
    ("gemini-3.1-pro", 200_000, 4.00, 18.00),
]


def test_estimate_cost_usd_default_tier_when_input_tokens_omitted() -> None:
    """Omitting input_tokens_for_threshold must yield the Default-tier rate."""
    # gpt-5.5 Default blended rate: 0.2*5.00 + 0.7*0.50 + 0.1*30.00 = 4.35/M
    expected = 4.35 * 100_000 / 1_000_000
    assert _estimate("gpt-5.5", 100_000) == pytest.approx(expected)


def test_estimate_cost_usd_default_tier_when_threshold_not_exceeded() -> None:
    """input_tokens_for_threshold below threshold → Default tier rates."""
    # gpt-5.4 threshold is 272K; 200K does NOT exceed it
    default_rate = blended_rate("gpt-5.4")
    cost_default = default_rate * 1_000_000 / 1_000_000
    cost_below = _estimate("gpt-5.4", 1_000_000, input_tokens_for_threshold=200_000)
    assert cost_below == pytest.approx(cost_default)


@pytest.mark.parametrize("model,threshold,lc_in,lc_out", LONG_CONTEXT_MODELS)
def test_estimate_cost_usd_long_context_tier_when_threshold_exceeded(
    model: str, threshold: int, lc_in: float, lc_out: float
) -> None:
    """input_tokens_for_threshold above threshold → long-context rates used."""
    over_threshold = threshold + 1
    # Expected blended rate using long-context rates (default 20/70/10 mix).
    price = PRICING[model]
    lc_rate = (
        0.20 * lc_in
        + 0.70 * price.cached_per_m
        + 0.10 * lc_out
    )
    expected_cost = lc_rate * 1_000_000 / 1_000_000
    actual = _estimate(model, 1_000_000, input_tokens_for_threshold=over_threshold)
    assert actual == pytest.approx(expected_cost)


def test_estimate_cost_usd_default_tier_for_model_without_threshold() -> None:
    """Passing input_tokens_for_threshold for a model with no threshold → Default tier, no error."""
    # claude-sonnet-4.5 has no input_threshold_tokens; must silently use Default
    default = _estimate("claude-sonnet-4.5", 1_000_000)
    with_param = _estimate(
        "claude-sonnet-4.5", 1_000_000, input_tokens_for_threshold=500_000
    )
    assert with_param == pytest.approx(default)


def test_pricing_table_has_long_context_fields_for_known_long_context_models() -> None:
    """gpt-5.4, gpt-5.5, gemini-3.1-pro must have all three long-context fields set."""
    expected_thresholds = {
        "gpt-5.4": 272_000,
        "gpt-5.5": 272_000,
        "gemini-3.1-pro": 200_000,
    }
    for model, threshold in expected_thresholds.items():
        price = PRICING[model]
        assert price.long_context_input_per_m is not None, (
            f"{model}: long_context_input_per_m must be set"
        )
        assert price.long_context_output_per_m is not None, (
            f"{model}: long_context_output_per_m must be set"
        )
        assert price.input_threshold_tokens == threshold, (
            f"{model}: expected threshold {threshold}, got {price.input_threshold_tokens}"
        )


def test_long_context_rates_strictly_greater_than_default_rates() -> None:
    """Long-context input and output rates must exceed Default-tier rates."""
    for model, *_ in LONG_CONTEXT_MODELS:
        price = PRICING[model]
        assert price.long_context_input_per_m > price.input_per_m, (  # type: ignore[operator]
            f"{model}: long_context_input_per_m should exceed input_per_m"
        )
        assert price.long_context_output_per_m > price.output_per_m, (  # type: ignore[operator]
            f"{model}: long_context_output_per_m should exceed output_per_m"
        )


# ---------- Long-context share-sum validation ----------


@pytest.mark.parametrize(
    "input_share,cache_share,output_share",
    [
        (0.50, 0.70, 0.10),        # sum = 1.30 — clearly over
        (0.10, 0.70, 0.10),        # sum = 0.90 — clearly under
        (0.20 + 2e-6, 0.70, 0.10), # sum = 1.0 + 2e-6 — just over 1e-6 tolerance
    ],
)
def test_estimate_cost_usd_long_context_rejects_non_unit_share_sum(
    input_share: float, cache_share: float, output_share: float
) -> None:
    """Long-context branch must reject share sums that deviate more than 1e-6 from 1.0."""
    # gpt-5.5 threshold = 272K; pass over-threshold to activate the LC path
    with pytest.raises(ValueError):
        _estimate(
            "gpt-5.5",
            1_000_000,
            input_tokens_for_threshold=300_000,
            input_share=input_share,
            cache_share=cache_share,
            output_share=output_share,
        )


def test_estimate_cost_usd_long_context_accepts_unit_share_sum_within_tolerance() -> None:
    """Long-context branch must accept share sums within 1e-6 of 1.0."""
    # Exact split: 0.20 + 0.70 + 0.10 = 1.0
    cost_exact = _estimate(
        "gpt-5.5",
        1_000_000,
        input_tokens_for_threshold=300_000,
        input_share=0.20,
        cache_share=0.70,
        output_share=0.10,
    )
    assert cost_exact > 0.0

    # Within-tolerance split: 0.2000005 + 0.6999995 + 0.10 = 1.0 (difference = 0 < 1e-6)
    cost_near = _estimate(
        "gpt-5.5",
        1_000_000,
        input_tokens_for_threshold=300_000,
        input_share=0.2000005,
        cache_share=0.6999995,
        output_share=0.10,
    )
    assert cost_near > 0.0
