from dataclasses import dataclass
from typing import Protocol

from poc.domain.features import Features
from poc.domain.models import Action


class TechnicalParameters(Protocol):
    rsi_entry_min: float
    rsi_entry_max: float
    rsi_exit: float
    min_relative_volume: float


@dataclass(frozen=True)
class TechnicalSignal:
    action: Action
    reason: str
    strategy_version: str = "baseline_v1"


def technical_signal(
    features: Features, has_position: bool, parameters: TechnicalParameters, quote_fresh: bool
) -> TechnicalSignal:
    if not features.valid:
        return TechnicalSignal(Action.HOLD, "INVALID_FEATURES")
    if has_position:
        exit_signal = (
            features.ema_short < features.ema_mid
            or features.macd_histogram < 0
            or features.rsi_14 > parameters.rsi_exit
        )
        return TechnicalSignal(
            Action.SELL if exit_signal else Action.HOLD, "STRATEGY_SELL" if exit_signal else "HOLD"
        )
    enter = (
        quote_fresh
        and features.ema_short > features.ema_mid > features.ema_long
        and features.trend_1h == "bullish"
        and features.macd_histogram > 0
        and parameters.rsi_entry_min <= features.rsi_14 <= parameters.rsi_entry_max
        and features.volume_ratio >= parameters.min_relative_volume
    )
    return TechnicalSignal(
        Action.BUY if enter else Action.HOLD, "TECHNICAL_ENTRY" if enter else "HOLD"
    )
