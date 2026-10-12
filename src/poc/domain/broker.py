"""Pure paper fill calculations. Nothing here can send an exchange order."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Protocol

from poc.domain.models import Action, Fill, MarketMetadata, Quote, TradeResult, Wallet
from poc.domain.primitives import DomainError, floor_step, stable_id


class Allocation(Protocol):
    max_allocation_pct: Decimal


class Costs(Protocol):
    trading_fee_pct_per_side: Decimal
    slippage_pct_per_side: Decimal


class PaperBroker:
    def __init__(self, allocation: Allocation, costs: Costs, minimum_notional: Decimal):
        self.allocation = allocation
        self.costs = costs
        self.minimum_notional = minimum_notional

    def buy(
        self,
        wallet: Wallet,
        metadata: MarketMetadata,
        quote: Quote,
        now: datetime,
        idempotency_key: str,
        cycle_id: str,
        trigger: str = "STRATEGY_BUY",
    ) -> TradeResult:
        if wallet.has_position:
            raise DomainError("ALREADY_IN_POSITION")
        if metadata.symbol != quote.symbol:
            raise DomainError("Quote symbol differs from session symbol")
        if wallet.last_exit_cycle_id == cycle_id:
            raise DomainError("CLOSED_IN_SAME_CYCLE")
        with localcontext() as ctx:
            ctx.prec = 50
            fee_ratio = self.costs.trading_fee_pct_per_side / 100
            slip_ratio = self.costs.slippage_pct_per_side / 100
            budget = min(
                wallet.cash_usdt,
                wallet.equity(quote.bid) * self.allocation.max_allocation_pct / 100,
            )
            price = quote.ask * (1 + slip_ratio)
            qty = floor_step(budget / (1 + fee_ratio) / price, metadata.qty_step)
            gross = qty * price
            fee = gross * fee_ratio
            debit = gross + fee
            metadata.validate_buy(qty, gross, self.minimum_notional)
            if debit > budget or debit > wallet.cash_usdt:
                raise DomainError("INSUFFICIENT_BALANCE")
            updated = replace(
                wallet,
                cash_usdt=wallet.cash_usdt - debit,
                base_qty=qty,
                base_cost_basis_usdt=debit,
                entry_fill_price=price,
                entry_at=now,
                version=wallet.version + 1,
            )
            fill = self._fill(
                wallet,
                quote,
                now,
                idempotency_key,
                cycle_id,
                Action.BUY,
                qty,
                price,
                gross,
                fee,
                -debit,
                None,
                trigger,
            )
            return TradeResult(updated, fill)

    def sell(
        self,
        wallet: Wallet,
        quote: Quote,
        now: datetime,
        idempotency_key: str,
        cycle_id: str,
        trigger: str,
    ) -> TradeResult:
        if not wallet.has_position:
            raise DomainError("NO_POSITION")
        with localcontext() as ctx:
            ctx.prec = 50
            price = quote.bid * (1 - self.costs.slippage_pct_per_side / 100)
            gross = wallet.base_qty * price
            fee = gross * self.costs.trading_fee_pct_per_side / 100
            proceeds = gross - fee
            pnl = proceeds - wallet.base_cost_basis_usdt
            fill = self._fill(
                wallet,
                quote,
                now,
                idempotency_key,
                cycle_id,
                Action.SELL,
                wallet.base_qty,
                price,
                gross,
                fee,
                proceeds,
                pnl,
                trigger,
            )
            updated = replace(
                wallet,
                cash_usdt=wallet.cash_usdt + proceeds,
                base_qty=Decimal(0),
                base_cost_basis_usdt=Decimal(0),
                realized_pnl_usdt=wallet.realized_pnl_usdt + pnl,
                entry_fill_price=None,
                entry_at=None,
                last_exit_cycle_id=cycle_id,
                version=wallet.version + 1,
            )
            return TradeResult(updated, fill)

    def _fill(
        self,
        wallet: Wallet,
        quote: Quote,
        now: datetime,
        key: str,
        cycle: str,
        side: Action,
        qty: Decimal,
        price: Decimal,
        gross: Decimal,
        fee: Decimal,
        cash_delta: Decimal,
        pnl: Decimal | None,
        trigger: str,
    ) -> Fill:
        return Fill(
            stable_id("fill", key),
            stable_id("order", key),
            wallet.portfolio_id,
            quote.quote_id,
            now,
            side,
            qty,
            price,
            gross,
            fee,
            cash_delta,
            self.costs.slippage_pct_per_side,
            pnl,
            trigger,
            cycle,
            key,
            quote.bid,
            quote.ask,
        )
