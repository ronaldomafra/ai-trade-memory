from decimal import Decimal

import pytest

from poc.domain.learning import compatible_group, hold_return, net_entry_return, statistics


def test_labels_account_for_both_fees_and_slippage_and_families_are_separate():
    value = net_entry_return(Decimal("100"), Decimal("100"), Decimal(".001"), Decimal(".0005"))
    assert value < 0
    assert hold_return(
        Decimal("100"), Decimal("110"), Decimal(".001"), Decimal(".0005")
    ) == Decimal("10")
    assert not compatible_group(
        {
            "symbol": "BTCUSDT",
            "position_context": "flat",
            "label_kind": "ENTRY_LONG_NET_RETURN",
            "horizon_bars": 4,
        },
        {
            "symbol": "BTCUSDT",
            "position_context": "holding",
            "label_kind": "HOLD_VS_SELL_RETURN",
            "horizon_bars": 4,
        },
    )


def test_statistics_preserve_neutrals_and_explain_dependence():
    values = [Decimal("1"), Decimal("-1"), Decimal("0"), Decimal("0")]
    result = statistics(values)
    assert result["sample_count"] == 4
    assert result["wins"] == 1 and result["losses"] == 1 and result["breakevens"] == 2
    assert result["smoothed_win_rate"] == 0.5
    assert result["net_win_rate"] == 0.25
    assert result["uncertainty"]["non_neutral_count"] == 2
    assert result["uncertainty"]["independence_assumed"] is True
    assert result["temporal_dependence_warning"]


def test_zero_prices_or_nonfinite_results_rejected():
    with pytest.raises(ValueError):
        net_entry_return(Decimal("0"), Decimal("100"), Decimal(".001"), Decimal(".0005"))
    with pytest.raises(ValueError):
        statistics([Decimal("NaN")])
