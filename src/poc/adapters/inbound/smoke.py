"""Explicit synthetic scenario for the offline accounting smoke, never live data."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.execution import TradeIntent, TradingService
from poc.application.sessions import SessionManager
from poc.config import Config
from poc.domain.models import Action, MarketMetadata, Quote
from poc.domain.primitives import DomainError


def smoke_offline(config: Config, manager: SessionManager) -> dict:
    prices = {"BTCUSDT": ("BTC", "100000", "0.000001"), "ETHUSDT": ("ETH", "3000", "0.0001")}
    if config.market.symbol not in prices:
        raise DomainError("Offline smoke has explicitly identified BTC/ETH fixtures only")
    base, price, step = prices[config.market.symbol]
    now = datetime.now(UTC)
    metadata = MarketMetadata(
        config.market.symbol,
        base,
        "USDT",
        Decimal(step),
        Decimal(step),
        Decimal("10000"),
        Decimal("5"),
        None,
        now,
        {"fixture": True, "fixture_id": "accounting_smoke_v1"},
    )
    run_id = "smoke-" + uuid4().hex[:16]
    record = manager.prepare(run_id, "trend_15m_v1", metadata, now)
    db = SessionDatabase(Path(record["paths"]["sqlite"]), create=False)
    try:
        service = TradingService(config, metadata, db)
        buy_at, sell_at = now + timedelta(seconds=1), now + timedelta(seconds=3)
        bid = Decimal(price)
        buy_quote = Quote(
            "smoke-buy",
            metadata.symbol,
            bid,
            bid * Decimal("1.0001"),
            buy_at,
            buy_at,
            "offline_fixture",
        )
        sell_quote = Quote(
            "smoke-sell",
            metadata.symbol,
            bid * Decimal("1.02"),
            bid * Decimal("1.0201"),
            sell_at,
            sell_at,
            "offline_fixture",
        )
        for wallet in db.wallets():
            service.execute(
                TradeIntent(wallet.portfolio_id, Action.BUY, "buy", "cycle-buy", now, now),
                buy_quote,
                buy_at,
            )
            service.execute(
                TradeIntent(wallet.portfolio_id, Action.SELL, "sell", "cycle-sell", buy_at, buy_at),
                sell_quote,
                sell_at,
            )
        report = FileExporter(db).publish()
        audit = db.audit()
        if not audit["ok"]:
            raise DomainError("Smoke accounting failed")
        return {
            "scope": "E01_ACCOUNTING",
            "fixture": True,
            "network_calls": 0,
            "run_id": run_id,
            "paths": record["paths"],
            "audit": audit,
            "portfolios": report["portfolios"],
        }
    finally:
        db.close()
