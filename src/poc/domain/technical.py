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
            (
                getattr(parameters, "exit_on_ema_reversal", True)
                and features.ema_short < features.ema_mid
            )
            or (getattr(parameters, "exit_on_negative_macd", True) and features.macd_histogram < 0)
            or (
                getattr(parameters, "rsi_exit_enabled", True)
                and features.rsi_14 > parameters.rsi_exit
            )
        )
        return TechnicalSignal(
            Action.SELL if exit_signal else Action.HOLD, "STRATEGY_SELL" if exit_signal else "HOLD"
        )
    enter = (
        quote_fresh
        and (
            not hasattr(parameters, "entry_rule")
            or getattr(features, "structural_entry_setup", False)
        )
        and (
            not getattr(parameters, "require_ema_alignment", True)
            or features.ema_short > features.ema_mid > features.ema_long
        )
        and (
            not getattr(parameters, "require_trend_bullish", True) or features.trend_1h == "bullish"
        )
        and (not getattr(parameters, "require_positive_macd", True) or features.macd_histogram > 0)
        and parameters.rsi_entry_min <= features.rsi_14 <= parameters.rsi_entry_max
        and features.volume_ratio >= parameters.min_relative_volume
    )
    return TechnicalSignal(
        Action.BUY if enter else Action.HOLD, "TECHNICAL_ENTRY" if enter else "HOLD"
    )
