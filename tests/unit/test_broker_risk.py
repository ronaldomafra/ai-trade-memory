from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from poc.config import Config
from poc.domain.broker import PaperBroker
from poc.domain.models import Action, MarketMetadata, Quote, Wallet
from poc.domain.primitives import DomainError
from poc.domain.risk import evaluate_risk

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def metadata(symbol="BTCUSDT", base="BTC", step="0.000001"):
    return MarketMetadata(
        symbol, base, "USDT", D(step), D(step), D("10000"), D("5"), None, NOW, {"fixture": True}
    )


def quote(bid="100000", ask="100010", at=NOW, symbol="BTCUSDT"):
    return Quote(
        "quote-" + str(at.timestamp()) + "-" + bid,
        symbol,
        D(bid),
        D(ask),
        at,
        at,
        "offline_fixture",
    )


def wallet():
    return Wallet("BASELINE_TECHNICAL", "BASELINE_TECHNICAL", D("100"), D("100"))


def buy(price="100010"):
    cfg = Config()
    return PaperBroker(cfg.strategy, cfg.simulation, cfg.market.min_trade_notional_usdt).buy(
        wallet(), metadata(), quote(ask=price), NOW, "buy-1", "cycle-1"
    )


def test_buy_budget_includes_fee_and_round_trip_reconciles():
    broker = PaperBroker(Config().strategy, Config().simulation, D("5"))
    result = buy()
    assert -result.fill.net_cash_delta_usdt <= D("20")
    assert result.fill.fill_price == D("100010") * D("1.0005")
    assert result.wallet.cash_usdt + result.wallet.base_cost_basis_usdt == D("100")
    assert result.wallet.base_qty % D("0.000001") == 0
    sold = broker.sell(
        result.wallet, quote(bid="103100", ask="103110"), NOW, "sell-1", "cycle-2", "STRATEGY_SELL"
    )
    assert sold.wallet.base_qty == sold.wallet.base_cost_basis_usdt == 0
    assert sold.wallet.cash_usdt == D("100") + sold.wallet.realized_pnl_usdt
    assert (
        sold.fill.realized_pnl_usdt
        == sold.fill.net_cash_delta_usdt - result.wallet.base_cost_basis_usdt
    )


def test_eth_quantity_is_quantized_to_its_own_non_power_of_ten_step():
    broker = PaperBroker(Config().strategy, Config().simulation, D("5"))
    meta = metadata("ETHUSDT", "ETH", "0.005")
    result = broker.buy(
        wallet(), meta, quote("3000", "3001", symbol="ETHUSDT"), NOW, "eth-buy", "cycle-1"
    )
    assert result.wallet.base_qty == D("0.005")
    assert -result.fill.net_cash_delta_usdt <= D("20")


def test_wrong_symbol_or_insufficient_minimum_cannot_open_position():
    broker = PaperBroker(Config().strategy, Config().simulation, D("5"))
    with pytest.raises(DomainError, match="symbol"):
        broker.buy(wallet(), metadata(), quote(symbol="ETHUSDT"), NOW, "buy", "cycle")
    meta = metadata(step="0.01")
    with pytest.raises(DomainError):
        broker.buy(wallet(), meta, quote(), NOW, "buy", "cycle")


def test_sell_flat_and_buy_holding_do_not_create_new_money():
    broker = PaperBroker(Config().strategy, Config().simulation, D("5"))
    with pytest.raises(DomainError, match="NO_POSITION"):
        broker.sell(wallet(), quote(), NOW, "sell", "cycle", "STRATEGY_SELL")
    with pytest.raises(DomainError, match="ALREADY_IN_POSITION"):
        broker.buy(buy().wallet, metadata(), quote(), NOW, "buy", "cycle")


def test_stop_guard_take_duration_precedence_and_guard_latch():
    cfg = Config()
    holding = buy().wallet
    start = evaluate_risk(holding, None, quote(), NOW, 0, cfg.strategy)
    assert start.state.day_start_equity_usdt is not None
    falling = quote("60000", "60001", NOW + timedelta(seconds=1))
    risk = evaluate_risk(holding, start.state, falling, falling.observed_at, 16, cfg.strategy)
    assert risk.exit_reason == "STOP_LOSS"
    assert risk.state.guard_triggered_at is not None
    assert risk.block_buy
    recovery = evaluate_risk(
        holding,
        risk.state,
        quote(at=NOW + timedelta(seconds=2)),
        NOW + timedelta(seconds=2),
        0,
        cfg.strategy,
    )
    assert recovery.block_buy
    # Once protection is pending, a price recovery must not cancel the exit.
    assert recovery.exit_reason == "STOP_LOSS"


def test_guard_boundary_and_flat_portfolio():
    cfg = Config()
    w = wallet()
    ref = evaluate_risk(w, None, None, NOW, 0, cfg.strategy).state
    below = Wallet(w.portfolio_id, w.strategy_type, D("100"), D("95.001"))
    exact = Wallet(w.portfolio_id, w.strategy_type, D("100"), D("95"))
    assert not evaluate_risk(below, ref, None, NOW, 0, cfg.strategy).block_buy
    assert evaluate_risk(exact, ref, None, NOW, 0, cfg.strategy).block_buy
    assert evaluate_risk(exact, ref, None, NOW, 0, cfg.strategy).exit_reason is None


def test_rollover_retains_pending_exit_without_manufacturing_baseline():
    cfg = Config()
    holding = buy().wallet
    ref = evaluate_risk(holding, None, quote(), NOW, 0, cfg.strategy).state
    crash = quote("60000", "60001", NOW + timedelta(seconds=1))
    triggered = evaluate_risk(holding, ref, crash, crash.observed_at, 0, cfg.strategy).state
    tomorrow = NOW + timedelta(days=1)
    rolled = evaluate_risk(holding, triggered, None, tomorrow, 0, cfg.strategy)
    assert rolled.state.day_start_equity_usdt is None
    assert rolled.state.pending_exit_reason == "STOP_LOSS"
    assert rolled.block_buy
    assert triggered.day_start_equity_usdt == ref.day_start_equity_usdt


def test_take_and_duration():
    cfg = Config()
    holding = buy().wallet
    high = quote("104000", "104010")
    risk = evaluate_risk(holding, None, high, NOW, 16, cfg.strategy)
    assert risk.exit_reason == "TAKE_PROFIT"
    assert evaluate_risk(holding, None, quote(), NOW, 16, cfg.strategy).exit_reason == "MAX_HOLDING"


def test_quote_freshness_boundaries_and_future():
    q = quote()
    assert q.fresh(NOW + timedelta(seconds=30), 30)
    assert not q.fresh(NOW + timedelta(seconds=30, microseconds=1), 30)
    assert not q.fresh(NOW - timedelta(seconds=1), 30)
    with pytest.raises(DomainError):
        quote("100", "99")


def test_financial_dataclasses_reject_float():
    with pytest.raises(DomainError):
        Wallet("A", "BASELINE_TECHNICAL", D("100"), 100.0)
    assert Action.BUY.value == "BUY"
