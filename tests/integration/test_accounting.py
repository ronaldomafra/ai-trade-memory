import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.execution import TradeIntent, TradingService
from poc.application.sessions import SessionManager
from poc.config import Config
from poc.domain.models import Action, MarketMetadata, Quote
from poc.domain.primitives import DomainError

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
A = "BASELINE_TECHNICAL"


def config(tmp_path):
    return Config.model_validate({"app": {"data_dir": str(tmp_path)}})


def meta(symbol="BTCUSDT", base="BTC", step="0.000001"):
    return MarketMetadata(
        symbol, base, "USDT", D(step), D(step), D("10000"), D("5"), None, NOW, {"fixture": True}
    )


def quote(at, bid="100000", ask="100010", symbol="BTCUSDT"):
    return Quote(str(at.timestamp()) + "-" + bid, symbol, D(bid), D(ask), at, at, "offline_fixture")


def setup(tmp_path):
    cfg = config(tmp_path)
    manager = SessionManager(cfg, SQLiteStorage())
    record = manager.prepare("run-1", "trend_15m_v1", meta(), NOW)
    db = SessionDatabase(record["paths"]["sqlite"], create=False)
    return cfg, manager, db, TradingService(cfg, meta(), db)


def intent(action=Action.BUY, key="request-1", cycle="cycle-1", portfolio=A):
    return TradeIntent(portfolio, action, key, cycle, NOW, NOW)


def test_atomic_fill_ledger_event_and_idempotent_restart(tmp_path):
    cfg, manager, db, service = setup(tmp_path)
    q = quote(NOW + timedelta(seconds=1))
    first = service.execute(intent(), q, q.observed_at)
    assert first.fill is not None
    assert first.executed_action == Action.BUY
    second = service.execute(intent(), q, q.observed_at)
    assert second.duplicate
    assert second.fill.fill_id == first.fill.fill_id
    assert db.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 1
    assert (
        db.connection.execute(
            "SELECT COUNT(*) FROM ledger_entries WHERE fill_id IS NOT NULL"
        ).fetchone()[0]
        == 2
    )
    assert db.audit()["ok"]
    cash = db.wallet(A).cash_usdt
    db.close()
    record = manager.restore("run-1")
    db2 = SessionDatabase(record["paths"]["sqlite"], create=False)
    resumed = TradingService(cfg, meta(), db2)
    assert resumed.execute(intent(), q, q.observed_at).duplicate
    assert db2.wallet(A).cash_usdt == cash
    assert db2.audit()["ok"]
    db2.close()


def test_rollback_after_fill_insertion_preserves_all_state(tmp_path):
    _, _, db, service = setup(tmp_path)
    db.connection.execute("""
      CREATE TRIGGER simulate_crash BEFORE INSERT ON ledger_entries
      WHEN NEW.fill_id IS NOT NULL BEGIN SELECT RAISE(ABORT, 'injected crash'); END
    """)
    q = quote(NOW + timedelta(seconds=1))
    with pytest.raises(sqlite3.IntegrityError, match="injected crash"):
        service.execute(intent(), q, q.observed_at)
    assert db.wallet(A).cash_usdt == D("100")
    assert db.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM paper_orders").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM daily_risk_states").fetchone()[0] == 0
    db.connection.execute("DROP TRIGGER simulate_crash")
    assert service.execute(intent(), q, q.observed_at).fill is not None
    assert db.audit()["ok"]
    db.close()


def test_stale_quote_or_predecision_quote_cannot_fill(tmp_path):
    _, _, db, service = setup(tmp_path)
    assert service.execute(intent(), quote(NOW), NOW).reason_code == "QUOTE_NOT_AFTER_DECISION"
    q = quote(NOW + timedelta(seconds=1))
    result = service.execute(intent(key="late"), q, NOW + timedelta(seconds=40))
    assert result.reason_code == "STALE_QUOTE"
    q2 = quote(NOW + timedelta(seconds=91))
    assert (
        service.execute(intent(key="old-candle"), q2, q2.observed_at).reason_code
        == "STALE_DECISION"
    )
    assert db.wallet(A).base_qty == 0
    assert db.audit()["ok"]
    db.close()


def test_risk_latch_fill_and_no_same_cycle_reentry(tmp_path):
    _, _, db, service = setup(tmp_path)
    q = quote(NOW + timedelta(seconds=1))
    service.execute(intent(), q, q.observed_at)
    q2 = quote(NOW + timedelta(seconds=2), bid="60000", ask="60010")
    result = service.execute(intent(Action.HOLD, "risk", "cycle-2"), q2, q2.observed_at)
    assert result.fill.trigger == "STOP_LOSS"
    assert db.wallet(A).base_qty == 0
    assert db.latest_risk(A).guard_triggered_at is not None
    denied = service.execute(intent(key="reenter", cycle="cycle-2"), q2, q2.observed_at)
    assert denied.executed_action == Action.HOLD
    assert db.wallet(A).base_qty == 0
    assert db.audit()["ok"]
    assert db.wallet("JEV_STATIC").cash_usdt == D("100")
    db.close()


def test_prepare_idempotence_and_foreign_session_isolation(tmp_path):
    cfg, manager, db, _ = setup(tmp_path)
    record = manager.prepare("run-1", "trend_15m_v1", meta(), NOW)
    assert record["run_id"] == "run-1"
    with pytest.raises(DomainError, match="configuration"):
        different = cfg.model_copy(
            update={"strategy": cfg.strategy.model_copy(update={"max_allocation_pct": D("10")})}
        )
        SessionManager(different, SQLiteStorage()).prepare("run-1", "trend_15m_v1", meta(), NOW)
    eth_cfg = Config.model_validate(
        {"app": {"data_dir": str(tmp_path)}, "market": {"symbol": "ETHUSDT"}}
    )
    other = SessionManager(eth_cfg, SQLiteStorage()).prepare(
        "eth-1", "trend_15m_v1", meta("ETHUSDT", "ETH", "0.0001"), NOW
    )
    assert other["paths"]["sqlite"] != record["paths"]["sqlite"]
    assert db.wallet(A).cash_usdt == D("100")
    with pytest.raises(DomainError):
        manager.restore("missing")
    with pytest.raises(DomainError):
        manager.prepare("../run", "trend_15m_v1", meta(), NOW)
    with pytest.raises(DomainError):
        manager.prepare("other", "scalping", meta(), NOW)
    db.close()


def test_conflicting_intent_key_and_quote_identity_are_rejected(tmp_path):
    _, _, db, service = setup(tmp_path)
    q = quote(NOW + timedelta(seconds=1))
    service.execute(intent(), q, q.observed_at)
    with pytest.raises(DomainError, match="Idempotency"):
        service.execute(intent(Action.SELL), q, q.observed_at)
    with pytest.raises(DomainError, match="quote"):
        altered = Quote(
            q.quote_id, q.symbol, D("90000"), D("90010"), q.observed_at, q.received_at, q.source
        )
        with db.transaction() as unit:
            unit.save_quote(altered)
    db.close()


def test_ledger_is_append_only_and_lock_is_exclusive(tmp_path):
    _, manager, db, _ = setup(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.connection.execute("UPDATE ledger_entries SET amount='300'")
    with manager.lease("run-1"):
        with pytest.raises(DomainError, match="already"):
            with manager.lease("run-1"):
                pass
    db.close()


def test_competing_connections_commit_only_one_fill(tmp_path):
    cfg, manager, db, _ = setup(tmp_path)
    path = manager.restore("run-1")["paths"]["sqlite"]
    db.close()
    q = quote(NOW + timedelta(seconds=1))

    def execute():
        connection = SessionDatabase(path, create=False)
        try:
            return TradingService(cfg, meta(), connection).execute(intent(), q, q.observed_at)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: execute(), range(2)))
    assert sum(not r.duplicate for r in results) == 1
    assert len({r.fill.fill_id for r in results}) == 1
    check = SessionDatabase(path, create=False)
    assert check.audit()["ok"] and check.audit()["fill_count"] == 1
    check.close()


def test_pending_protection_survives_missing_quote_and_restart(tmp_path):
    cfg, manager, db, service = setup(tmp_path)
    q = quote(NOW + timedelta(seconds=1))
    service.execute(intent(), q, q.observed_at)
    risk = service.execute(
        intent(Action.HOLD, "missing-quote", "cycle-2"),
        None,
        NOW + timedelta(seconds=10),
        holding_bars=16,
    )
    assert risk.reason_code == "STALE_QUOTE"
    assert db.latest_risk(A).pending_exit_reason == "MAX_HOLDING"
    assert db.wallet(A).base_qty > 0
    db.close()
    db = SessionDatabase(manager.restore("run-1")["paths"]["sqlite"], create=False)
    service = TradingService(cfg, meta(), db)
    q2 = quote(NOW + timedelta(seconds=11))
    closed = service.execute(intent(Action.HOLD, "restored-risk", "cycle-3"), q2, q2.observed_at)
    assert closed.fill.trigger == "MAX_HOLDING"
    assert db.wallet(A).base_qty == 0
    assert db.latest_risk(A).pending_exit_reason is None
    assert db.audit()["ok"]
    db.close()


def test_delayed_candle_uses_close_time_not_new_model_start(tmp_path):
    _, _, db, service = setup(tmp_path)
    q = quote(NOW + timedelta(seconds=1))
    old_candle = NOW - timedelta(minutes=15)
    delayed = TradeIntent(A, Action.BUY, "delayed-candle", "cycle-old", NOW, NOW, old_candle)
    assert service.execute(delayed, q, q.observed_at).reason_code == "STALE_DECISION"
    assert db.wallet(A).base_qty == 0
    db.close()
