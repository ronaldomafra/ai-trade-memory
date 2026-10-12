"""Counterfactual labels and transparent statistics, never wallet mutations."""

import math
import statistics as stat
from decimal import Decimal

from poc.domain.primitives import DomainError, decimal


def net_entry_return(ask: Decimal, bid: Decimal, fee: Decimal, slippage: Decimal) -> Decimal:
    if ask <= 0 or bid <= 0 or not 0 <= fee < 1 or not 0 <= slippage < 1:
        raise DomainError("Invalid hypothetical prices or costs")
    return (bid * (1 - slippage) * (1 - fee) / (ask * (1 + slippage) * (1 + fee)) - 1) * 100


def hold_return(now_bid: Decimal, later_bid: Decimal, fee: Decimal, slippage: Decimal) -> Decimal:
    if now_bid <= 0 or later_bid <= 0 or not 0 <= fee < 1 or not 0 <= slippage < 1:
        raise DomainError("Invalid hypothetical liquidation")
    return (
        later_bid * (1 - slippage) * (1 - fee) / (now_bid * (1 - slippage) * (1 - fee)) - 1
    ) * 100


def compatible_group(sample: dict, context: dict) -> bool:
    return all(
        sample.get(key) == context.get(key)
        for key in ("symbol", "position_context", "label_kind", "horizon_bars")
    )


def statistics(returns: list[Decimal]) -> dict:
    values = [decimal(v) for v in returns]
    if not values:
        raise DomainError("No matured observations")
    wins = sum(v > 0 for v in values)
    losses = sum(v < 0 for v in values)
    non_neutral = wins + losses
    z = 1.959963984540054
    if non_neutral:
        p = wins / non_neutral
        denominator = 1 + z * z / non_neutral
        center = (p + z * z / (2 * non_neutral)) / denominator
        half = z * math.sqrt(p * (1 - p) / non_neutral + z * z / (4 * non_neutral**2)) / denominator
        interval = [max(0, center - half), min(1, center + half)]
    else:
        interval = None
    return {
        "sample_count": len(values),
        "wins": wins,
        "losses": losses,
        "breakevens": len(values) - non_neutral,
        "net_win_rate": wins / len(values),
        "smoothed_win_rate": (wins + 1) / (non_neutral + 2),
        "mean_net_return_pct": str(stat.mean(values)),
        "median_net_return_pct": str(stat.median(values)),
        "std_net_return_pct": str(stat.stdev(values)) if len(values) > 1 else "0",
        "uncertainty": {
            "method": "Wilson95",
            "interval": interval,
            "non_neutral_count": non_neutral,
            "independence_assumed": True,
        },
        "temporal_dependence_warning": (
            "Unique examples can have overlapping horizons; independent sample size "
            "and nominal coverage are not established."
        ),
    }
