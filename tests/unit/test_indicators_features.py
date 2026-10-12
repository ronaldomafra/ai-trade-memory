from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pandas as pd
import pytest

from poc.config import Config
from poc.domain.candles import Candle
from poc.domain.features import FeatureEngine, Features, rsi_bucket, volume_bucket
from poc.domain.indicators import atr, ema, macd, rsi
from poc.domain.models import Action
from poc.domain.technical import technical_signal

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def candles(interval="15m", count=600, volume=D("10")):
    seconds = 900 if interval == "15m" else 3600
    result = []
    for i in range(count):
        end = NOW - timedelta(seconds=(count - 1 - i) * seconds)
        close = D(1000 + i)
        result.append(
            Candle(
                "ETHUSDT",
                interval,
                end - timedelta(seconds=seconds),
                end,
                close,
                close + 1,
                close - 1,
                close,
                volume,
                NOW,
                "offline_fixture",
            )
        )
    return result


def test_ema_macd_match_independent_pandas_reference():
    closes = [float(i * i % 89 + 100) for i in range(100)]
    source = pd.Series(closes)
    reference = source.ewm(span=20, adjust=False, min_periods=20).mean()
    assert ema(closes, 20)[-1] == pytest.approx(reference.iloc[-1])
    expected_line = (
        source.ewm(span=12, adjust=False, min_periods=12).mean()
        - source.ewm(span=26, adjust=False, min_periods=26).mean()
    )
    expected_signal = expected_line.ewm(span=9, adjust=False, min_periods=9).mean()
    line, signal, histogram = macd(closes, 12, 26, 9)
    assert line[-1] == pytest.approx(expected_line.iloc[-1])
    assert signal[-1] == pytest.approx(expected_signal.iloc[-1])
    assert histogram[-1] == pytest.approx((expected_line - expected_signal).iloc[-1])


def test_wilder_seed_and_flat_zero_cases():
    prices = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.42,
        45.84,
        46.08,
        45.89,
        46.03,
        45.61,
        46.28,
        46.28,
    ]
    assert rsi(prices, 14)[-1] == pytest.approx(70.464135, abs=0.000001)
    assert rsi([10.0] * 30, 14)[-1] == 50
    assert rsi([float(i) for i in range(30)], 14)[-1] == 100
    assert atr([11.0] * 30, [9.0] * 30, [10.0] * 30, 14)[-1] == 2
    assert rsi(prices[:14], 14)[-1] is None


def test_current_volume_and_future_bars_are_excluded():
    bars, hours = candles(), candles("1h", 150)
    bars[-1] = replace(bars[-1], volume=D("20"))
    engine = FeatureEngine(Config().indicators)
    original = engine.build("ETHUSDT", bars, hours, NOW)
    assert original.valid and original.volume_ratio == 2
    future = replace(
        bars[-1],
        open_time=NOW,
        close_time_exclusive=NOW + timedelta(minutes=15),
        available_at=NOW + timedelta(minutes=15),
        volume=D("9999"),
    )
    partial = replace(future, available_at=NOW, is_closed=False)
    assert engine.build("ETHUSDT", bars + [future, partial], hours, NOW).state() == original.state()
    assert engine.build("ETHUSDT", bars, hours[:-1], NOW).valid
    assert not engine.build("ETHUSDT", bars, hours[:40], NOW).valid


def test_gap_unavailable_volume_and_unreceived_history_block_features():
    engine = FeatureEngine(Config().indicators)
    bars, hours = candles(), candles("1h", 150)
    assert engine.build("ETHUSDT", bars[:300] + bars[301:], hours, NOW).reason == "MARKET_DATA_GAP"
    assert not engine.build("ETHUSDT", candles(volume=D("0")), hours, NOW).valid
    unreceived = [replace(b, available_at=NOW + timedelta(seconds=1)) for b in bars]
    assert not engine.build("ETHUSDT", unreceived, hours, NOW).valid


def test_volatility_uses_previous_history_only():
    bars, hours = candles(), candles("1h", 150)
    shocked = replace(bars[-1], high=bars[-1].close + D("1000"), low=bars[-1].close - D("500"))
    result = FeatureEngine(Config().indicators).build("ETHUSDT", bars[:-1] + [shocked], hours, NOW)
    assert result.valid and result.volatility_bucket == "high"


@pytest.mark.parametrize(
    "rsi_value,bucket", [(29.99, "lt30"), (30, "30_45"), (45, "45_60"), (60, "60_70"), (70, "ge70")]
)
def test_bucket_boundaries(rsi_value, bucket):
    assert rsi_bucket(rsi_value) == bucket
    assert volume_bucket(0.8) == volume_bucket(1.2) == "normal"


def test_baseline_requires_all_signals_and_risk_is_external():
    p = Config().strategy.technical
    features = Features(
        True,
        "VALID",
        "ETHUSDT",
        NOW,
        D("3000"),
        60,
        30,
        20,
        10,
        1,
        0.5,
        0.5,
        1,
        1.1,
        "bullish",
        "bullish",
    )
    assert technical_signal(features, False, p, True).action == Action.BUY
    assert technical_signal(features, False, p, False).action == Action.HOLD
    assert (
        technical_signal(replace(features, trend_1h="unknown"), False, p, True).action
        == Action.HOLD
    )
    assert (
        technical_signal(replace(features, macd_histogram=-0.1), True, p, True).action
        == Action.SELL
    )
    assert technical_signal(replace(features, rsi_14=76), True, p, True).action == Action.SELL
    assert technical_signal(replace(features, valid=False), False, p, True).action == Action.HOLD
