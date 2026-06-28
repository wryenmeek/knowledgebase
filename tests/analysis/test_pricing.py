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
