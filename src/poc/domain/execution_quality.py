"""Decimal execution scenarios use the same pure paper broker as actual simulated fills."""

from dataclasses import replace
from decimal import Decimal

from poc.domain.broker import PaperBroker
from poc.domain.primitives import DomainError
from poc.domain.profiles import parameters


def quality_reason(config, wallet, metadata, quote, now, reference=None):
    p = parameters(config)
    if p is None:
        return None
    if quote is None or not quote.fresh(now, config.app.max_quote_age_seconds):
        return "STALE_QUOTE"
    spread = (quote.ask - quote.bid) / ((quote.ask + quote.bid) / 2) * 100
    if spread > p.execution_quality.max_market_spread_pct:
        return "MARKET_SPREAD_TOO_WIDE"
    if (
        reference is not None
        and abs(quote.ask / reference.ask - 1) * 100 > p.execution_quality.max_entry_price_drift_pct
    ):
        return "ENTRY_PRICE_DRIFT"
    if wallet.has_position:
        return None
    broker = PaperBroker(config.strategy, config.simulation, config.market.min_trade_notional_usdt)
    try:
        entry = broker.buy(wallet, metadata, quote, now, "preview", "preview")
        fill = entry.fill
        outcomes = []
        for percentage in (config.strategy.take_profit_pct, -config.strategy.stop_loss_pct):
            bid = fill.fill_price * (1 + percentage / 100)
            exit_quote = replace(quote, bid=bid, ask=bid)
            exit_trade = broker.sell(
                entry.wallet, exit_quote, now, "preview-exit", "preview", "PREVIEW"
            )
            outcomes.append(exit_trade.fill.realized_pnl_usdt)
    except DomainError:
        return "EXECUTION_SIZE_OR_COST_INVALID"
    gain, loss = outcomes
    if gain <= 0 or loss >= 0:
        return "NONPOSITIVE_NET_TARGET"
    if gain / abs(loss) < Decimal(p.execution_quality.minimum_net_target_to_stop_ratio):
        return "INSUFFICIENT_NET_TARGET_TO_STOP"
    return None
