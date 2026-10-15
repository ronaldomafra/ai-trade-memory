import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest
from test_accounting import NOW, A, config, meta, quote
from test_cycles_engine import Clock, FeaturesFixture, Source

from poc.adapters.outbound.context_service import ContextService
from poc.adapters.outbound.datasets import DatasetFiles, read_dataset
from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.engine import LiveEngine
from poc.application.execution import TradeIntent, TradingService
from poc.application.learning import LearningEngine
from poc.application.orchestrator import CycleCoordinator
from poc.application.sessions import SessionManager
from poc.domain.candles import INTERVAL_SECONDS, Candle
from poc.domain.features import ProfileFeatures
from poc.domain.models import Action, Proposal
from poc.domain.primitives import stable_id
from poc.domain.profiles import age_bars, boundary, entry_window_open, scheduled_exit_due
from poc.profile_config import ProfileDefinition, profile_template, resolve_profile


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["SCALPING", "DAY_TRADE", "SWING"])
async def test_manual_backfill_uses_saved_profile_intervals_without_trading(
    tmp_path, monkeypatch, style
):
    from poc.adapters.inbound import service

    cfg, _, db = prepared(tmp_path, style)
    intervals = (cfg.market.interval, cfg.market.trend_interval)
    seen = []

    class BackfillSource:
        def __init__(self, **kwargs):
            assert kwargs["intervals"] == intervals
            self.closed = False

        async def candles(self, symbol, interval, limit, start_at):
            seen.append(interval)
            # A closed public candle is historical market data, not a new decision.
            at = boundary(datetime.now(UTC), INTERVAL_SECONDS[interval])
            return (
                [
                    Candle(
                        symbol,
                        interval,
                        at - timedelta(seconds=INTERVAL_SECONDS[interval]),
                        at,
                        D("100000"),
                        D("100010"),
                        D("99990"),
                        D("100000"),
                        D("10"),
                        datetime.now(UTC),
                        "offline_fixture",
                    )
                ]
                if seen.count(interval) == 1
                else []
            )

        async def close(self):
            self.closed = True

    source = BackfillSource(intervals=intervals)

    def source_factory(**kwargs):
        assert kwargs["intervals"] == intervals
        return source

    monkeypatch.setattr(service, "BinancePublic", source_factory)
    result = await service.backfill(cfg, "profile-fixture", 1)
    assert result["inserted_candles"] == 2
    assert result["retroactive_trades"] is False and source.closed
    assert set(seen) == set(intervals)
    assert db.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0] == 0
    assert db.audit()["ok"]
    db.close()


def prepared(tmp_path, style="SCALPING"):
    definition = ProfileDefinition.model_validate(profile_template(style))
    cfg = resolve_profile(definition, config(tmp_path), "BTCUSDT")
    manager = SessionManager(cfg, SQLiteStorage())
    record = manager.prepare("profile-fixture", definition.profile.profile_id, meta(), NOW)
    return cfg, manager, SessionDatabase(record["paths"]["sqlite"], create=False)


def candle(cfg, at):
    return Candle(
        "BTCUSDT",
        cfg.market.interval,
        at - timedelta(seconds=INTERVAL_SECONDS[cfg.market.interval]),
        at,
        D("100000"),
        D("100010"),
        D("99990"),
        D("100000"),
        D("10"),
        at,
        "offline_fixture",
    )


class ProfileFeatureFixture(FeaturesFixture):
    def __init__(self, setup=True):
        self.setup = setup

    def build(self, symbol, bars, hours, cutoff):
        base = replace(
            super().build(symbol, bars, hours, cutoff),
            volume_ratio=1.5,
            returns_pct=(0.0, 0.0, 0.0),
        )
        return ProfileFeatures(
            **{
                **asdict(base),
                "feature_version": "profile_features_v2",
                "rsi_bucket": "60_70",
                "volume_bucket": "normal",
                "volatility_bucket": "high",
            },
            structural_entry_setup=self.setup,
            decision_interval="1m",
            trend_interval="5m",
            trend_direction="bullish",
            return_horizons_bars=(1, 3, 15),
        )


class Policy:
    def __init__(self, action=Action.HOLD):
        self.calls = 0
        self.states = None
        self.action = action

    async def propose(self, cycle_id, states, deadline):
        self.calls += 1
        self.states = states
        return {k: Proposal(self.action, "FIXTURE") for k in states}


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["SCALPING", "DAY_TRADE", "SWING"])
async def test_persisted_context_metadata_does_not_interrupt_profile_cycle(tmp_path, style):
    cfg, _, db = prepared(tmp_path, style)
    clock = Clock(NOW)
    context = ContextService(cfg, "BTC", db, clock, None, None, None, None)
    duration = cfg.strategy.max_holding_candles * INTERVAL_SECONDS[cfg.market.interval]
    factor = {
        "factor_id": "fixture-news",
        "available_at": NOW.isoformat(),
        "source_observed_at": NOW.isoformat(),
        "valid_until": (NOW + timedelta(hours=1)).isoformat(),
        "profile_window_seconds": 999999,
        "event_time": {
            "start": (NOW + timedelta(seconds=duration + 1)).isoformat(),
            "end": (NOW + timedelta(seconds=duration + 1)).isoformat(),
        },
    }
    with db.transaction():
        db.save_external_context(
            {
                "news": {"status": "available", "items": [factor]},
                "prediction_markets": {"status": "unavailable", "items": []},
            },
            NOW,
        )
    stored = db.external_context(NOW)
    assert isinstance(stored["criteria_version"], str)
    assert context.snapshot(NOW - timedelta(microseconds=1))["news"]["items"] == []
    snapshot = context.snapshot(NOW)
    assert snapshot["criteria_version"] == stored["criteria_version"]
    assert snapshot["news"]["items"][0]["profile_window_seconds"] == duration
    assert snapshot["news"]["items"][0]["temporal_relation"] == "BACKGROUND"
    assert db.external_context(NOW) == stored
    assert context.snapshot(NOW + timedelta(hours=2))["news"]["items"] == []
    policy = Policy()
    coordinator = CycleCoordinator(
        cfg, meta(), db, Source(clock), clock, asyncio.Event(), policy, context=context
    )
    coordinator.feature_engine = ProfileFeatureFixture(True)
    assert await coordinator.process(candle(cfg, NOW))
    assert policy.calls == 1
    assert policy.states["JEV_STATIC"]["news"]["items"][0]["factor_id"] == "fixture-news"
    assert db.connection.execute("SELECT status FROM decision_cycles").fetchone()[0] == "COMPLETED"
    assert db.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 3
    assert not await coordinator.process(candle(cfg, NOW))
    assert policy.calls == 1 and db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_filtered_setups_do_not_call_jev_and_cadence_survives_restart(tmp_path):
    cfg, manager, db = prepared(tmp_path)
    clock = Clock()
    policy = Policy()
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event(), policy)
    coordinator.feature_engine = ProfileFeatureFixture(False)
    assert not await coordinator.process(candle(cfg, NOW))
    assert (
        policy.calls == 0
        and db.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    )
    coordinator.feature_engine = ProfileFeatureFixture(True)
    clock.at += timedelta(minutes=1)
    assert await coordinator.process(candle(cfg, NOW + timedelta(minutes=1)))
    assert policy.calls == 1 and db.wallet(A).has_position
    assert policy.states["JEV_STATIC"]["strategy_context"]["interval"] == "1m"
    assert db.audit()["ok"]
    assert not await coordinator.process(candle(cfg, NOW + timedelta(minutes=1)))
    path = db.path
    db.close()
    db = SessionDatabase(path, create=False)
    resumed = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event(), policy)
    resumed.feature_engine = ProfileFeatureFixture(False)
    clock.at = NOW + timedelta(minutes=2)
    assert not await resumed.process(candle(cfg, clock.at))
    assert db.runtime_state("profile_admission")["admitted"] == 1
    # A holds: checkpoint gets admitted after the persisted minimum spacing,
    # despite no new structural setup, and cannot open B/C on that old setup.
    policy.action = Action.BUY
    clock.at = NOW + timedelta(minutes=7)
    assert await resumed.process(candle(cfg, clock.at))
    rows = db.connection.execute(
        "SELECT reason_code FROM decisions WHERE portfolio_id!='BASELINE_TECHNICAL' "
        "ORDER BY rowid DESC LIMIT 2"
    ).fetchall()
    assert all(r[0] == "STRUCTURAL_SETUP_REQUIRED" for r in rows)
    assert db.audit()["ok"]
    db.close()


def test_execution_drift_spread_cost_and_elapsed_holding_are_enforced(tmp_path):
    cfg, _, db = prepared(tmp_path)
    service = TradingService(cfg, meta(), db)
    reference = quote(NOW)

    def intent(key):
        return TradeIntent(A, Action.BUY, key, key, NOW, NOW, NOW, entry_reference_quote=reference)

    drift = quote(NOW + timedelta(seconds=1), bid="100040", ask="100050")
    assert (
        service.execute(intent("drift"), drift, drift.observed_at).reason_code
        == "ENTRY_PRICE_DRIFT"
    )
    wide = quote(NOW + timedelta(seconds=1), bid="99000", ask="100010")
    assert (
        service.execute(intent("spread"), wide, wide.observed_at).reason_code
        == "MARKET_SPREAD_TOO_WIDE"
    )
    q = quote(NOW + timedelta(seconds=1))
    assert service.execute(intent("valid"), q, q.observed_at).fill
    assert age_bars(cfg, NOW + timedelta(seconds=59), NOW + timedelta(minutes=1, seconds=1)) == 0
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_daily_flatten_pending_survives_midnight_and_does_not_require_ai(tmp_path):
    cfg, _, db = prepared(tmp_path)
    service = TradingService(cfg, meta(), db)
    at = NOW.replace(hour=23, minute=54)
    reference = quote(at)
    q = quote(at + timedelta(seconds=1))
    opened = service.execute(
        TradeIntent(A, Action.BUY, "entry", "entry", at, at, at, entry_reference_quote=reference),
        q,
        q.observed_at,
    )
    assert opened.fill
    clock = Clock(at.replace(minute=59, second=31))
    engine = LiveEngine(cfg, meta(), db, Source(clock), clock)
    await engine.monitor_risk()  # Missing quote: durable pending, never invented fill.
    assert db.latest_risk(A).pending_exit_reason == "SESSION_WINDOW_CLOSED"
    clock.at = clock.at + timedelta(minutes=2)
    engine.latest_quote = quote(clock.at)
    await engine.monitor_risk()
    assert not db.wallet(A).has_position
    await engine.monitor_risk()
    assert (
        db.connection.execute("SELECT COUNT(*) FROM paper_fills WHERE side='SELL'").fetchone()[0]
        == 1
    )
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_profile_labels_have_real_durations_and_dataset_v2_roundtrips(tmp_path):
    cfg, _, db = prepared(tmp_path)
    # Synthetic fixture data, isolated from all operational databases and providers.
    clock = Clock()
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())
    coordinator.feature_engine = ProfileFeatureFixture(False)
    # EVERY_CLOSED_CANDLE allows an observation without a structural entry.
    definition = cfg.profile_definition.model_dump(mode="json")
    definition["parameters"]["opportunities"]["mode"] = "EVERY_CLOSED_CANDLE"
    cfg = resolve_profile(ProfileDefinition.model_validate(definition), config(tmp_path), "BTCUSDT")
    coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())
    coordinator.feature_engine = ProfileFeatureFixture(False)
    assert await coordinator.process(candle(cfg, NOW))
    learning = LearningEngine(cfg, meta(), db)
    assert learning.register() == 6
    rows = db.connection.execute(
        "SELECT DISTINCT horizon_bars,maturity_time FROM decision_outcomes ORDER BY horizon_bars"
    ).fetchall()
    assert rows[0][1].startswith("2026-10-12T12:03:")
    assert rows[1][1].startswith("2026-10-12T12:15:")
    clock.at = NOW + timedelta(minutes=3, seconds=1)
    with db.transaction():
        db.save_quote(replace(quote(clock.at, bid="100500", ask="100510"), source="binance_rest"))
    assert learning.mature(clock.at) == 3
    assert len(db.learning_records()) == 1
    clock.at = NOW + timedelta(minutes=15, seconds=11)
    assert learning.mature(clock.at) == 3
    assert (
        db.connection.execute(
            "SELECT COUNT(*) FROM decision_outcomes WHERE status='UNAVAILABLE'"
        ).fetchone()[0]
        == 3
    )
    record = db.learning_records()[0]
    assert record["core"]["interval_seconds"] == 60
    assert record["core"]["label_version"] == "profile_labels_v2"
    assert record["core"]["fixture"] is True
    # Exporting fixtures never promotes them into reusable live learning.
    exported = DatasetFiles(db).export(tmp_path / "profile.jsonl", clock.at)
    assert exported["sample_count"] == 0
    assert read_dataset(tmp_path / "profile.jsonl", clock.at)["records"] == []
    # Synthetic, non-operational records exercise the reusable V2 wire schema.
    synthetic = db.learning_records()[0]
    core = synthetic["core"]
    core["fixture"] = False
    for name in ("reference_quote", "exit_quote"):
        core[name]["source"] = "binance_rest"
    core.pop("sample_id")
    core["sample_id"] = stable_id("profile_equivalence_v2", core)
    # A second temporary database provides an import/export boundary without
    # changing the original fixture identity in learning_examples.
    target_cfg, _, target = prepared(tmp_path / "target")
    with target.transaction():
        for origin in synthetic["origins"]:
            target.save_learning_record(core, origin, clock.at)
    output = DatasetFiles(target).export(tmp_path / "v2.jsonl", clock.at + timedelta(seconds=1))
    assert output["sample_count"] == 1
    data = read_dataset(tmp_path / "v2.jsonl", clock.at + timedelta(seconds=2))
    assert data["header"]["schema_version"] == 2
    assert data["records"][0]["core"]["interval_seconds"] == 60
    target.close()
    assert db.audit()["ok"]
    db.close()


@pytest.mark.parametrize(
    "style,seconds_per_bar", [("SCALPING", 60), ("DAY_TRADE", 900), ("SWING", 14400)]
)
def test_utc_windows_and_profile_restore_are_stable(tmp_path, style, seconds_per_bar):
    cfg, manager, db = prepared(tmp_path, style)
    assert cfg.market.interval in INTERVAL_SECONDS
    assert INTERVAL_SECONDS[cfg.market.interval] == seconds_per_bar
    assert manager.restore("profile-fixture")["config_hash"] == cfg.hash
    if style != "SWING":
        assert not entry_window_open(cfg, NOW.replace(hour=23, minute=59))
        assert scheduled_exit_due(cfg, NOW, NOW + timedelta(days=1))
    else:
        assert entry_window_open(cfg, NOW.replace(hour=23, minute=59))
        assert not scheduled_exit_due(cfg, NOW, NOW + timedelta(days=1))
    db.close()


@pytest.mark.asyncio
async def test_generic_engine_warmup_and_real_features_use_selected_intervals(tmp_path):
    cfg, _, db = prepared(tmp_path)
    clock = Clock()

    class IntervalSource(Source):
        async def candles(self, symbol, interval, limit=600, start_at=None):
            end = boundary(self.clock.now(), INTERVAL_SECONDS[interval])
            duration = INTERVAL_SECONDS[interval]
            return [
                Candle(
                    symbol,
                    interval,
                    end - timedelta(seconds=(limit - n) * duration),
                    end - timedelta(seconds=(limit - n - 1) * duration),
                    D("100000"),
                    D("100010"),
                    D("99990"),
                    D("100000"),
                    D("10"),
                    self.clock.now(),
                    "offline_fixture",
                )
                for n in range(limit)
            ]

    source = IntervalSource(clock)
    engine = LiveEngine(cfg, meta(), db, source, clock)
    await engine.initialize()
    assert len(db.candles("BTCUSDT", "1m")) == 600
    assert len(db.candles("BTCUSDT", "5m")) == 600
    assert not db.candles("BTCUSDT", "15m")
    clock.at = NOW + timedelta(minutes=1)
    new = candle(cfg, clock.at)
    assert await engine.accept_candle(new)
    assert engine.coordinator.feature_engine.build(
        "BTCUSDT", db.candles("BTCUSDT", "1m"), db.candles("BTCUSDT", "5m"), clock.at
    ).valid
    assert not await engine.coordinator.process(new)  # Flat market has no new EMA cross.
    assert db.runtime_state("profile_admission")["filtered"] == 1
    assert db.audit()["ok"]
    await source.close()
    db.close()
