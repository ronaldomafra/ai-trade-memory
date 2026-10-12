from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from poc.domain.primitives import DomainError, decimal, utc


class Action(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PortfolioKind(StrEnum):
    TECHNICAL = "BASELINE_TECHNICAL"
    STATIC = "JEV_STATIC"
    LEARNING = "JEV_LEARNING"


def checked_money(instance: Any, fields: tuple[str, ...]) -> None:
    for name in fields:
        value = getattr(instance, name)
        if value is not None:
            object.__setattr__(instance, name, decimal(value))


@dataclass(frozen=True)
class MarketMetadata:
    symbol: str
    base_asset: str
    quote_asset: str
    qty_step: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional_usdt: Decimal
    max_notional_usdt: Decimal | None
    observed_at: datetime
    raw: dict[str, Any]

    def __post_init__(self) -> None:
        checked_money(
            self, ("qty_step", "min_qty", "max_qty", "min_notional_usdt", "max_notional_usdt")
        )
        if (
            self.quote_asset != "USDT"
            or not self.base_asset
            or self.symbol != self.base_asset + self.quote_asset
            or self.qty_step <= 0
            or self.min_qty < 0
            or self.max_qty <= 0
            or self.max_qty < self.min_qty
            or self.min_notional_usdt < 0
            or (
                self.max_notional_usdt is not None
                and self.max_notional_usdt < self.min_notional_usdt
            )
        ):
            raise DomainError("Invalid Spot USDT metadata or quantity filters")
        utc(self.observed_at)

    def validate_buy(self, qty: Decimal, gross: Decimal, internal_min: Decimal) -> None:
        if not self.min_qty <= qty <= self.max_qty or qty <= 0 or qty % self.qty_step != 0:
            raise DomainError("QUANTITY_FILTER")
        if gross < max(self.min_notional_usdt, internal_min):
            raise DomainError("MIN_NOTIONAL")
        if self.max_notional_usdt is not None and gross > self.max_notional_usdt:
            raise DomainError("MAX_NOTIONAL")


@dataclass(frozen=True)
class Quote:
    quote_id: str
    symbol: str
    bid: Decimal
    ask: Decimal
    observed_at: datetime
    received_at: datetime
    source: str
    event_at: datetime | None = None
    request_started_at: datetime | None = None
    update_id: int | None = None
    bid_qty: Decimal | None = None
    ask_qty: Decimal | None = None

    def __post_init__(self) -> None:
        checked_money(self, ("bid", "ask", "bid_qty", "ask_qty"))
        if not self.quote_id or self.bid <= 0 or self.ask < self.bid:
            raise DomainError("Invalid bid/ask")
        if utc(self.observed_at) > utc(self.received_at):
            raise DomainError("Observation cannot follow receipt")
        if self.event_at is not None and utc(self.event_at) > utc(self.received_at):
            raise DomainError("Future quote event")
        if self.request_started_at is not None and utc(self.request_started_at) > utc(
            self.received_at
        ):
            raise DomainError("Invalid quote request timing")
        if any(v is not None and v <= 0 for v in (self.bid_qty, self.ask_qty)):
            raise DomainError("Quote has no executable public quantity")

    def fresh(self, now: datetime, max_age_seconds: int) -> bool:
        age = (utc(now) - utc(self.observed_at)).total_seconds()
        return 0 <= age <= max_age_seconds and utc(self.received_at) <= utc(now)


@dataclass(frozen=True)
class Wallet:
    portfolio_id: str
    strategy_type: str
    initial_usdt: Decimal
    cash_usdt: Decimal
    base_qty: Decimal = Decimal("0")
    base_cost_basis_usdt: Decimal = Decimal("0")
    realized_pnl_usdt: Decimal = Decimal("0")
    entry_fill_price: Decimal | None = None
    entry_at: datetime | None = None
    peak_equity_usdt: Decimal = Decimal("100")
    max_drawdown_pct: Decimal = Decimal("0")
    last_exit_cycle_id: str | None = None
    version: int = 0

    def __post_init__(self) -> None:
        checked_money(
            self,
            (
                "initial_usdt",
                "cash_usdt",
                "base_qty",
                "base_cost_basis_usdt",
                "realized_pnl_usdt",
                "entry_fill_price",
                "peak_equity_usdt",
                "max_drawdown_pct",
            ),
        )
        if (
            self.initial_usdt <= 0
            or min(self.cash_usdt, self.base_qty, self.base_cost_basis_usdt) < 0
        ):
            raise DomainError("Negative balance or invalid initial capital")
        if self.base_qty == 0 and self.base_cost_basis_usdt != 0:
            raise DomainError("Flat portfolio cannot retain cost basis")
        if self.base_qty > 0 and (
            self.entry_fill_price is None or self.entry_fill_price <= 0 or self.entry_at is None
        ):
            raise DomainError("Holding portfolio requires entry state")
        if self.entry_at is not None:
            utc(self.entry_at)

    @property
    def has_position(self) -> bool:
        return self.base_qty > 0

    def equity(self, bid: Decimal) -> Decimal:
        return self.cash_usdt + self.base_qty * bid


@dataclass(frozen=True)
class DailyRiskState:
    portfolio_id: str
    day_utc: str
    day_start_equity_usdt: Decimal | None
    baseline_observed_at: datetime | None
    baseline_quote_id: str | None
    guard_triggered_at: datetime | None = None
    trigger_equity_usdt: Decimal | None = None
    trigger_quote_id: str | None = None
    blocked_until_utc: datetime | None = None
    pending_exit_reason: str | None = None

    def __post_init__(self) -> None:
        checked_money(self, ("day_start_equity_usdt", "trigger_equity_usdt"))
        if self.day_start_equity_usdt is not None and self.day_start_equity_usdt <= 0:
            raise DomainError("Daily reference must be positive")
        for value in (self.baseline_observed_at, self.guard_triggered_at, self.blocked_until_utc):
            if value is not None:
                utc(value)


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    portfolio_id: str
    quote_id: str
    filled_at: datetime
    side: Action
    qty_base: Decimal
    fill_price: Decimal
    gross_usdt: Decimal
    fee_usdt: Decimal
    net_cash_delta_usdt: Decimal
    slippage_pct: Decimal
    realized_pnl_usdt: Decimal | None
    trigger: str
    cycle_id: str
    idempotency_key: str
    observed_bid: Decimal
    observed_ask: Decimal

    def __post_init__(self) -> None:
        checked_money(
            self,
            (
                "qty_base",
                "fill_price",
                "gross_usdt",
                "fee_usdt",
                "net_cash_delta_usdt",
                "slippage_pct",
                "realized_pnl_usdt",
                "observed_bid",
                "observed_ask",
            ),
        )
        if self.qty_base <= 0 or self.fill_price <= 0 or self.gross_usdt <= 0 or self.fee_usdt < 0:
            raise DomainError("Invalid fill values")
        if self.observed_bid <= 0 or self.observed_ask < self.observed_bid:
            raise DomainError("Invalid fill quote")
        utc(self.filled_at)


@dataclass(frozen=True)
class TradeResult:
    wallet: Wallet
    fill: Fill


@dataclass(frozen=True)
class MarketNotice:
    kind: str
    occurred_at: datetime
    reason: str | None = None


@dataclass(frozen=True)
class Proposal:
    action: Action
    reason: str
    probabilities: dict[str, float | Decimal] | None = None
    confidence: float | Decimal | None = None
    ai_call_id: str | None = None
    feedback: dict[str, Any] | None = None
    evidence: dict[str, Any] | None = None
    proposed_action: Action | None = None
