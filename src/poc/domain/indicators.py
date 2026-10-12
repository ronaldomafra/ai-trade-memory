"""Deterministic EMA and Wilder indicators, with explicit warmup and flat RSI."""

from math import isfinite


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0 or any(not isfinite(v) for v in values):
        raise ValueError("Invalid EMA input")
    result = []
    previous = None
    alpha = 2 / (period + 1)
    for index, value in enumerate(values):
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        result.append(previous if index + 1 >= period else None)
    return result


def rsi(values: list[float], period: int) -> list[float | None]:
    if period <= 0 or any(not isfinite(v) for v in values):
        raise ValueError("Invalid RSI input")
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    deltas = [b - a for a, b in zip(values, values[1:], strict=False)]
    gain = sum(max(d, 0) for d in deltas[:period]) / period
    loss = sum(max(-d, 0) for d in deltas[:period]) / period
    for index in range(period, len(values)):
        if index > period:
            delta = deltas[index - 1]
            gain = (gain * (period - 1) + max(delta, 0)) / period
            loss = (loss * (period - 1) + max(-delta, 0)) / period
        # Explicit flat-series convention: 50, neither overbought nor oversold.
        result[index] = (
            50.0 if gain == loss == 0 else (100.0 if loss == 0 else 100 - 100 / (1 + gain / loss))
        )
    return result


def atr(high: list[float], low: list[float], close: list[float], period: int) -> list[float | None]:
    if period <= 0 or not len(high) == len(low) == len(close):
        raise ValueError("Invalid ATR input")
    if any(not isfinite(v) for values in (high, low, close) for v in values):
        raise ValueError("Nonfinite ATR input")
    result: list[float | None] = [None] * len(close)
    if len(close) < period:
        return result
    ranges = [
        max(h - low_value, abs(h - close[i - 1]), abs(low_value - close[i - 1]))
        if i
        else h - low_value
        for i, (h, low_value) in enumerate(zip(high, low, strict=True))
    ]
    current = sum(ranges[:period]) / period
    result[period - 1] = current
    for i in range(period, len(close)):
        current = (current * (period - 1) + ranges[i]) / period
        result[i] = current
    return result


def macd(
    values: list[float], fast: int, slow: int, signal: int
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    fast_ema, slow_ema = ema(values, fast), ema(values, slow)
    line = [
        a - b if a is not None and b is not None else None
        for a, b in zip(fast_ema, slow_ema, strict=True)
    ]
    available = [v for v in line if v is not None]
    computed = iter(ema(available, signal))
    signal_line = [next(computed) if v is not None else None for v in line]
    histogram = [
        a - b if a is not None and b is not None else None
        for a, b in zip(line, signal_line, strict=True)
    ]
    return line, signal_line, histogram


def quantile(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("Invalid quantile input")
    ordered = sorted(values)
    location = (len(ordered) - 1) * probability
    left = int(location)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (location - left)
