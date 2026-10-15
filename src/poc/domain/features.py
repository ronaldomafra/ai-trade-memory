from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from typing import Protocol

from poc.domain.candles import Candle, closed_sequence
from poc.domain.indicators import atr, ema, macd, quantile, rsi
from poc.domain.primitives import DomainError, decimal, iso, utc


class IndicatorParameters(Protocol):
    rsi: int
    ema_short: int
    ema_mid: int
    ema_long: int
    macd_fast: int
    macd_slow: int
    macd_signal: int
    atr: int
    relative_volume_window: int


@dataclass(frozen=True)
class Features:
    valid: bool
    reason: str
    symbol: str
    as_of: datetime
    close: Decimal | None = None
    rsi_14: float | None = None
    ema_short: float | None = None
    ema_mid: float | None = None
    ema_long: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    atr_pct: float | None = None
    volume_ratio: float | None = None
    trend_1h: str = "unknown"
    market_regime: str = "range"
    rsi_bucket: str | None = None
    volume_bucket: str | None = None
    volatility_bucket: str | None = None
    returns_pct: tuple[float, ...] = ()
    feature_version: str = "indicators_v1"

    def __post_init__(self) -> None:
        utc(self.as_of)
        if self.close is not None:
            object.__setattr__(self, "close", decimal(self.close))
        if self.valid:
            values = (
                self.rsi_14,
                self.ema_short,
                self.ema_mid,
                self.ema_long,
                self.macd_line,
                self.macd_signal,
                self.macd_histogram,
                self.atr_pct,
                self.volume_ratio,
            )
            if (
                self.close is None
                or self.close <= 0
                or any(v is None or not isfinite(v) for v in values)
            ):
                raise DomainError("Valid features require complete finite indicator values")
            if not 0 <= self.rsi_14 <= 100 or self.atr_pct < 0 or self.volume_ratio < 0:
                raise DomainError("Invalid indicator range")

    def state(self) -> dict:
        data = asdict(self)
        data["as_of"] = iso(self.as_of)
        data["close"] = str(self.close) if self.close is not None else None
        return data


def rsi_bucket(value: float) -> str:
    return (
        "lt30"
        if value < 30
        else "30_45"
        if value < 45
        else ("45_60" if value < 60 else "60_70" if value < 70 else "ge70")
    )


def volume_bucket(value: float) -> str:
    return "low" if value < 0.8 else "normal" if value <= 1.2 else "high"


class FeatureEngine:
    def __init__(self, parameters: IndicatorParameters, profile=None):
        self.parameters = parameters
        self.profile = profile

    def build(
        self, symbol: str, candles: list[Candle], trend: list[Candle], cutoff: datetime
    ) -> Features:
        try:
            interval = self.profile.market.interval if self.profile else "15m"
            trend_interval = self.profile.market.trend_interval if self.profile else "1h"
            bars = closed_sequence(candles, symbol, interval, cutoff)
            hours = closed_sequence(trend, symbol, trend_interval, cutoff)
            return self._compute(symbol, bars, hours, cutoff)
        except (DomainError, ValueError, OverflowError, ZeroDivisionError) as exc:
            return Features(False, str(exc), symbol, cutoff)

    def _compute(
        self, symbol: str, bars: list[Candle], hours: list[Candle], cutoff: datetime
    ) -> Features:
        p = self.parameters
        if len(bars) < max(
            p.ema_long,
            p.rsi + 1,
            p.macd_slow + p.macd_signal,
            17,
            p.relative_volume_window + 1,
            p.atr + 3,
        ):
            raise DomainError("INSUFFICIENT_WARMUP")
        if len(hours) < p.ema_mid:
            raise DomainError("INSUFFICIENT_1H_WARMUP")
        closes = [float(b.close) for b in bars]
        e_short, e_mid, e_long = (ema(closes, n)[-1] for n in (p.ema_short, p.ema_mid, p.ema_long))
        rsi_value = rsi(closes, p.rsi)[-1]
        line, signal, hist = macd(closes, p.macd_fast, p.macd_slow, p.macd_signal)
        atr_series = atr([float(b.high) for b in bars], [float(b.low) for b in bars], closes, p.atr)
        atr_pcts = [
            100 * a / c if a is not None else None for a, c in zip(atr_series, closes, strict=True)
        ]
        # At most 200 previous closed ATR% observations; the current candle is excluded.
        history = [v for v in atr_pcts[:-1] if v is not None][-200:]
        low, high = quantile(history, 1 / 3), quantile(history, 2 / 3)
        volatility = "low" if atr_pcts[-1] <= low else "medium" if atr_pcts[-1] <= high else "high"
        avg_volume = sum(float(b.volume) for b in bars[-p.relative_volume_window - 1 : -1]) / (
            p.relative_volume_window
        )
        if avg_volume <= 0:
            raise DomainError("ZERO_RELATIVE_VOLUME_DENOMINATOR")
        ratio = float(bars[-1].volume) / avg_volume
        hourly_closes = [float(b.close) for b in hours]
        hshort, hmid = ema(hourly_closes, p.ema_short)[-1], ema(hourly_closes, p.ema_mid)[-1]
        hourly_regime = "bullish" if hshort > hmid else "bearish" if hshort < hmid else "range"
        regime = (
            "bullish"
            if e_short > e_mid > e_long and closes[-1] > e_short
            else ("bearish" if e_short < e_mid < e_long and closes[-1] < e_short else "range")
        )
        values = (
            rsi_value,
            e_short,
            e_mid,
            e_long,
            line[-1],
            signal[-1],
            hist[-1],
            atr_pcts[-1],
            ratio,
        )
        if any(v is None or not isfinite(v) for v in values):
            raise DomainError("INVALID_FEATURES")
        horizons = self.profile.indicators.return_horizons_bars if self.profile else (1, 4, 16)
        result = Features(
            True,
            "VALID",
            symbol,
            cutoff,
            bars[-1].close,
            *values[:4],
            line[-1],
            signal[-1],
            hist[-1],
            atr_pcts[-1],
            ratio,
            hourly_regime,
            regime,
            rsi_bucket(rsi_value),
            volume_bucket(ratio),
            volatility,
            tuple((closes[-1] / closes[-1 - h] - 1) * 100 for h in horizons),
        )
        if self.profile is None:
            return result
        technical = self.profile.strategy.technical
        if technical.entry_rule == "EMA_CROSS":
            setup = ema(closes, p.ema_short)[-2] <= ema(closes, p.ema_mid)[-2] and e_short > e_mid
        elif technical.entry_rule == "PRIOR_HIGH_BREAKOUT":
            n = technical.breakout_lookback_candles
            if len(bars) <= n:
                raise DomainError("INSUFFICIENT_SETUP_HISTORY")
            level = max(b.high for b in bars[-n - 1 : -1])
            setup = bars[-1].close > level * (1 + technical.breakout_buffer_pct / 100)
        else:
            setup = e_short > e_mid > e_long
        return ProfileFeatures(
            **{**asdict(result), "feature_version": "profile_features_v2"},
            decision_interval=self.profile.market.interval,
            trend_interval=self.profile.market.trend_interval,
            trend_direction=hourly_regime,
            rsi_period=p.rsi,
            return_horizons_bars=tuple(horizons),
            structural_entry_setup=setup,
        )


@dataclass(frozen=True)
class ProfileFeatures(Features):
    decision_interval: str = "15m"
    trend_interval: str = "1h"
    trend_direction: str = "unknown"
    rsi_period: int = 14
    return_horizons_bars: tuple[int, ...] = (1, 4, 16)
    structural_entry_setup: bool = False
