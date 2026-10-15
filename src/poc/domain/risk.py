"""UTC daily latch and forced exit precedence, independent of the decision model."""

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Protocol

from poc.domain.models import DailyRiskState, Quote, Wallet
from poc.domain.primitives import next_utc_day, utc

EXIT_PRECEDENCE = (
    "STOP_LOSS",
    "DAILY_RISK_GUARD",
    "TAKE_PROFIT",
    "MAX_HOLDING",
    "SESSION_WINDOW_CLOSED",
    "STRATEGY_SELL",
)


class RiskParameters(Protocol):
    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    max_holding_candles: int
    daily_loss_guard_pct: Decimal


@dataclass(frozen=True)
class RiskEvaluation:
    state: DailyRiskState
    exit_reason: str | None
    block_buy: bool
    events: tuple[str, ...]


def evaluate_risk(
    wallet: Wallet,
    previous: DailyRiskState | None,
    quote: Quote | None,
    now: datetime,
    holding_bars: int,
    parameters: RiskParameters,
    max_quote_age_seconds: int = 30,
) -> RiskEvaluation:
    now = utc(now)
    day = now.date().isoformat()
    valid_quote = quote is not None and quote.fresh(now, max_quote_age_seconds)
    events = []
    rollover = previous is not None and previous.day_utc != day
    if previous is None or rollover:
        state = DailyRiskState(
            wallet.portfolio_id,
            day,
            None,
            None,
            None,
            pending_exit_reason=previous.pending_exit_reason if previous else None,
        )
        if rollover and previous.guard_triggered_at:
            events.append("DAILY_RISK_GUARD_RESET")
    else:
        state = previous
    with localcontext() as ctx:
        ctx.prec = 50
        equity = (
            wallet.equity(quote.bid)
            if valid_quote
            else (wallet.cash_usdt if not wallet.has_position else None)
        )
        if state.day_start_equity_usdt is None and equity is not None and equity > 0:
            state = replace(
                state,
                day_start_equity_usdt=equity,
                baseline_observed_at=now,
                baseline_quote_id=quote.quote_id if valid_quote else None,
            )
            events.append("DAILY_RISK_BASELINE_SET")
        if state.day_start_equity_usdt is not None and equity is not None:
            loss = max(
                Decimal(0),
                (state.day_start_equity_usdt - equity) / state.day_start_equity_usdt * 100,
            )
            if loss >= parameters.daily_loss_guard_pct and state.guard_triggered_at is None:
                state = replace(
                    state,
                    guard_triggered_at=now,
                    trigger_equity_usdt=equity,
                    trigger_quote_id=quote.quote_id if valid_quote else None,
                    blocked_until_utc=next_utc_day(now),
                )
                events.append("DAILY_RISK_GUARD_TRIGGERED")
        reasons = []
        if wallet.has_position:
            if state.pending_exit_reason:
                reasons.append(state.pending_exit_reason)
            if state.guard_triggered_at:
                reasons.append("DAILY_RISK_GUARD")
            if valid_quote:
                stop = wallet.entry_fill_price * (1 - parameters.stop_loss_pct / 100)
                take = wallet.entry_fill_price * (1 + parameters.take_profit_pct / 100)
                if quote.bid <= stop:
                    reasons.append("STOP_LOSS")
                if quote.bid >= take:
                    reasons.append("TAKE_PROFIT")
            if holding_bars >= parameters.max_holding_candles:
                reasons.append("MAX_HOLDING")
        reason = next((r for r in EXIT_PRECEDENCE if r in reasons), None)
        if reason:
            state = replace(state, pending_exit_reason=reason)
        blocked = (
            state.day_start_equity_usdt is None
            or state.guard_triggered_at is not None
            or state.pending_exit_reason is not None
        )
        return RiskEvaluation(state, reason, blocked, tuple(events))
