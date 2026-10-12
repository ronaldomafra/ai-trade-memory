import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest
from test_accounting import NOW, meta, quote, setup
from test_cycles_engine import Clock, FeaturesFixture, Source

from poc.application.learning import LearningEngine
from poc.application.orchestrator import CycleCoordinator


class LabelFeatures(FeaturesFixture):
    def build(self, *args):
        return replace(super().build(*args), volatility_bucket="medium")


async def decisions(tmp_path):
    cfg, manager, db, service = setup(tmp_path)
    clock = Clock(NOW + timedelta(seconds=1))
    source = Source(clock)
    bars = await source.candles("BTCUSDT", "15m", 1)
    with db.transaction():
        db.save_candle(bars[-1])
    coordinator = CycleCoordinator(cfg, meta(), db, source, clock, asyncio.Event())
    coordinator.feature_engine = LabelFeatures()
    await coordinator.process(bars[-1])
    return cfg, db, LearningEngine(cfg, meta(), db)


@pytest.mark.asyncio
async def test_three_origin_evaluations_deduplicate_without_financial_mutation(tmp_path):
    cfg, db, learning = await decisions(tmp_path)
    before = [(w.cash_usdt, w.base_qty) for w in db.wallets()]
    assert learning.register() == 6
    maturity = NOW + timedelta(hours=1)
    with db.transaction():
        db.save_quote(quote(maturity - timedelta(seconds=1), bid="110000", ask="110010"))
    assert learning.mature(maturity) == 0
    with db.transaction():
        db.save_quote(quote(maturity + timedelta(seconds=1), bid="110000", ask="110010"))
        db.save_quote(quote(maturity + timedelta(seconds=2), bid="120000", ask="120010"))
    assert learning.mature(maturity + timedelta(seconds=3)) == 3
    records = db.learning_records(maturity + timedelta(seconds=3))
    assert records == []  # strict availability/maturation cutoff
    records = db.learning_records(maturity + timedelta(seconds=4))
    assert len(records) == 1 and len(records[0]["origins"]) == 3
    assert records[0]["core"]["exit_quote"]["bid"] == "110000"
    assert [(w.cash_usdt, w.base_qty) for w in db.wallets()] == before
    assert db.audit()["ok"]
    assert learning.mature(maturity + timedelta(seconds=5)) == 0
    db.close()


@pytest.mark.asyncio
async def test_missing_bid_window_is_unavailable_not_zero_or_future_backfill(tmp_path):
    cfg, db, learning = await decisions(tmp_path)
    learning.register()
    maturity = NOW + timedelta(hours=1)
    assert learning.mature(maturity + timedelta(seconds=89)) == 0
    with db.transaction():
        db.save_quote(quote(maturity + timedelta(seconds=91)))
    assert learning.mature(maturity + timedelta(seconds=92)) == 3
    rows = db.connection.execute("SELECT * FROM decision_outcomes WHERE horizon_bars=4").fetchall()
    assert all(r["status"] == "UNAVAILABLE" and r["return_pct"] is None for r in rows)
    assert all(r["matured_at"] is None and r["evaluated_at"] is not None for r in rows)
    assert db.learning_records() == []
    db.close()
