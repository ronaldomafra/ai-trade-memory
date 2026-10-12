from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from poc.domain.models import checked_money
from poc.domain.primitives import DomainError, utc

INTERVAL_SECONDS = {"15m": 900, "1h": 3600}


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    open_time: datetime
    close_time_exclusive: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    available_at: datetime
    source: str
    is_closed: bool = True

    def __post_init__(self) -> None:
        checked_money(self, ("open", "high", "low", "close", "volume"))
        if self.interval not in INTERVAL_SECONDS:
            raise DomainError("Unsupported profile candle interval")
        if utc(self.close_time_exclusive) != utc(self.open_time) + timedelta(
            seconds=INTERVAL_SECONDS[self.interval]
        ):
            raise DomainError("Invalid candle window")
        if (
            min(self.open, self.low, self.high, self.close) <= 0
            or self.volume < 0
            or self.low > min(self.open, self.close)
            or self.high < max(self.open, self.close)
            or self.low > self.high
        ):
            raise DomainError("Invalid OHLCV")
        if self.is_closed and utc(self.available_at) < utc(self.close_time_exclusive):
            raise DomainError("Closed candle was not yet available")


def closed_sequence(
    candles: list[Candle], symbol: str, interval: str, cutoff: datetime
) -> list[Candle]:
    selected = {}
    for candle in candles:
        if (
            candle.symbol == symbol
            and candle.interval == interval
            and candle.is_closed
            and utc(candle.close_time_exclusive) <= utc(cutoff)
            and utc(candle.available_at) <= utc(cutoff)
        ):
            key = utc(candle.open_time)
            if key in selected and selected[key] != candle:
                raise DomainError("Conflicting candle identity")
            selected[key] = candle
    rows = [selected[k] for k in sorted(selected)]
    for previous, current in zip(rows, rows[1:], strict=False):
        if utc(previous.close_time_exclusive) != utc(current.open_time):
            raise DomainError("MARKET_DATA_GAP")
    return rows
