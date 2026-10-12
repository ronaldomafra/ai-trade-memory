import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest
from test_accounting import NOW, A, intent, meta, quote, setup

from poc.application.engine import LiveEngine
from poc.application.orchestrator import CycleCoordinator, cycle_identity
from poc.domain.candles import Candle
from poc.domain.features import Features
from poc.domain.models import Action, Proposal


class Clock:
    def __init__(self, at=NOW):
        self.at = at

    def now(self):
        return self.at


class Source:
    def __init__(self, clock):
        self.clock = clock
        self.closed = False

    async def quote(self, symbol):
        self.clock.at += timedelta(milliseconds=10)
        return quote(self.clock.at, symbol=symbol)

    async def candles(self, symbol, interval, limit=600, start_at=None):
        seconds = 900 if interval == "15m" else 3600
        return [
            Candle(
                symbol,
                interval,
                NOW - timedelta(seconds=(limit - i) * seconds),
                NOW - timedelta(seconds=(limit - i - 1) * seconds),
                D("100000"),
                D("100010"),
                D("99990"),
                D("100000"),
                D("10"),
                self.clock.now(),
                "offline_fixture",
            )
            for i in range(limit)
        ]

    async def server_time(self):
        return self.clock.now()

    async def close(self):
        self.closed = True

    async def stream(self, symbol, stop):
        while not stop.is_set():
            await asyncio.sleep(0.01)
            yield await self.quote(symbol)


class FeaturesFixture:
    def build(self, symbol, bars, hours, cutoff):
        return Features(
            True,
            "VALID",
            symbol,
            cutoff,
            D("100000"),
            60,
            90000,
            80000,
            70000,
            3,
            2,
            1,
            0.5,
            1.2,
            "bullish",
            "bullish",
        )


def current_candle():
    return Candle(
        "BTCUSDT",
        "15m",
        NOW - timedelta(minutes=15),
        NOW,
        D("100000"),
        D("100010"),
        D("99990"),
        D("100000"),
        D("10"),
        NOW,
        "offline_fixture",
    )


@pytest.mark.asyncio
async def test_closed_cycle_is_unique_and_decision_fill_are_linked(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock = Clock()
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())
    coordinator.feature_engine = FeaturesFixture()
    candle = current_candle()
    with db.transaction():
        db.save_candle(candle)
    assert await coordinator.process(candle)
    assert not await coordinator.process(candle)
    assert db.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
    assert db.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 1
    assert (
        db.connection.execute(
            "SELECT COUNT(*) FROM paper_orders WHERE decision_id IS NOT NULL"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.connection.execute(
            "SELECT reason_code FROM decisions WHERE portfolio_id='JEV_STATIC'"
        ).fetchone()[0]
        == "AI_NOT_CONFIGURED"
    )
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_risk_runs_while_policy_is_waiting_and_prevents_reentry(tmp_path):
    cfg, _, db, trading = setup(tmp_path)
    clock = Clock(NOW + timedelta(seconds=1))
    q = quote(clock.now())
    for wallet in db.wallets():
        trading.execute(intent(portfolio=wallet.portfolio_id), q, clock.now())
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingPolicy:
        async def propose(self, cycle_id, states, deadline):
            entered.set()
            await release.wait()
            return {key: Proposal(Action.BUY, "SYNTHETIC_TEST") for key in states}

    engine = LiveEngine(cfg, meta(), db, Source(clock), clock, WaitingPolicy())
    engine.coordinator.feature_engine = FeaturesFixture()
    task = asyncio.create_task(engine.coordinator.process(current_candle()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    clock.at += timedelta(seconds=1)
    falling = quote(clock.now(), "60000", "60010")
    await engine.accept_quote(falling, force=True)
    assert all(not wallet.has_position for wallet in db.wallets())
    release.set()
    assert await task
    assert all(not wallet.has_position for wallet in db.wallets())
    assert db.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 6
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_restart_marks_interrupted_cycle_without_replaying(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock = Clock()
    candle = current_candle()
    cycle_id = cycle_identity("run-1", candle)
    with db.transaction():
        db.save_candle(candle)
        db.start_cycle(
            cycle_id,
            candle,
            NOW,
            FeaturesFixture().build(candle.symbol, [], [], NOW).state(),
            db.wallets(),
        )
    with db.transaction():
        assert db.recover_cycles(NOW + timedelta(seconds=1)) == 1
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())
    assert not await coordinator.process(candle)
    assert db.cycle(cycle_id)["status"] == "INTERRUPTED"
    assert db.audit()["fill_count"] == 0
    db.close()


@pytest.mark.asyncio
async def test_financial_commit_rolls_back_if_decision_link_cannot_be_saved(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock = Clock()
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())
    coordinator.feature_engine = FeaturesFixture()
    db.connection.execute("""
       CREATE TRIGGER decision_crash BEFORE UPDATE ON decisions
       BEGIN SELECT RAISE(ABORT,'decision link crash'); END
    """)
    with pytest.raises(Exception, match="decision link crash"):
        await coordinator.process(current_candle())
    assert db.wallet(A).cash_usdt == 100
    assert db.audit()["fill_count"] == 0
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_startup_backfill_and_old_candles_do_not_trade(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock = Clock(NOW + timedelta(seconds=1))
    source = Source(clock)
    engine = LiveEngine(cfg, meta(), db, source, clock)
    await engine.initialize()
    assert not await engine.accept_candle(current_candle())
    assert db.audit()["fill_count"] == 0
    clock.at = NOW + timedelta(minutes=15)
    next_bar = replace(
        current_candle(), open_time=NOW, close_time_exclusive=clock.now(), available_at=clock.now()
    )
    assert await engine.accept_candle(next_bar)
    assert not await engine.accept_candle(next_bar)
    assert engine.queue.qsize() == 1
    db.close()


@pytest.mark.asyncio
async def test_engine_stops_with_persisted_state_and_source_closed(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock, source = Clock(), None
    source = Source(clock)
    engine = LiveEngine(cfg, meta(), db, source, clock)
    await engine.run(duration_seconds=0.03)
    assert source.closed and engine.status == "STOPPED"
    assert db.run()["status"] == "STOPPED"
    assert db.runtime_state("engine")["status"] == "STOPPED"
    assert db.audit()["ok"]
    db.close()
