import copy
from datetime import timedelta
from decimal import Decimal

import pytest
from test_accounting import NOW, config, meta
from test_cycles_engine import FeaturesFixture, current_candle
from test_datasets import synthetic_record_for_schema_tests

from poc.adapters.outbound.catalog import LearningCatalog
from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.sessions import SessionManager
from poc.application.transfer import TransferEngine
from poc.domain.primitives import iso, stable_id


def source_records(prototype, count, anchor=NOW):
    rows = []
    for i in range(count):
        record = copy.deepcopy(prototype)
        core = record["core"]
        at = anchor - timedelta(days=3) + timedelta(minutes=15 * i)
        maturity = at + timedelta(hours=1)
        core["decision_at"] = iso(at + timedelta(seconds=1))
        core["as_of"] = iso(at)
        core["features"]["as_of"] = iso(at)
        core["maturity_time"] = iso(maturity)
        for key, quote_at in (
            ("reference_quote", at + timedelta(seconds=2)),
            ("exit_quote", maturity + timedelta(seconds=1)),
        ):
            core[key]["observed_at"] = iso(quote_at)
            core[key]["received_at"] = iso(quote_at)
            core[key]["quote_id"] = stable_id("synthetic-transfer-test", key, i)
        core.pop("sample_id")
        core["sample_id"] = stable_id("equivalence_v1", core)
        for origin in record["origins"]:
            origin["origin_run_id"] = "synthetic-source"
            origin["decision_id"] = "synthetic-" + str(i) + "-" + origin["portfolio_id"]
            origin["origin_id"] = stable_id(
                "origin", origin["origin_run_id"], origin["decision_id"], 4
            )
            origin["matured_at"] = iso(maturity + timedelta(seconds=2))
            origin["available_at"] = origin["matured_at"]
        rows.append(record)
    return rows


class LocalControl:
    def feedback(self, state, cutoff):
        return {"status": "insufficient_samples", "patterns": [], "source_cutoff_at": iso(cutoff)}

    def mature(self, now):
        return 0

    def register(self):
        return 0


def target(tmp_path, created_at=NOW):
    cfg = config(tmp_path)
    cfg = type(cfg).model_validate({**cfg.model_dump(mode="json"), "market": {"symbol": "ETHUSDT"}})
    from dataclasses import replace

    metadata = replace(meta("ETHUSDT", "ETH"), observed_at=created_at)
    record = SessionManager(cfg, SQLiteStorage()).prepare(
        "target", "trend_15m_v1", metadata, created_at
    )
    db = SessionDatabase(record["paths"]["sqlite"])
    candle = current_candle()

    candle = replace(candle, symbol="ETHUSDT")
    features = FeaturesFixture().build("ETHUSDT", [], [], NOW)
    features = replace(features, volatility_bucket="medium")
    with db.transaction():
        db.start_cycle("cycle", candle, NOW, features.state(), db.wallets())
    state = {"symbol": "ETHUSDT", "portfolio": {"has_position": False}, "market": features.state()}
    return cfg, db, state


@pytest.mark.asyncio
async def test_publication_cutoff_unique_sources_and_shadow_frozen_without_local_counts(tmp_path):
    prototype = await synthetic_record_for_schema_tests(tmp_path / "prototype")
    rows = source_records(prototype, 50)
    catalog = LearningCatalog(tmp_path / "catalog.sqlite3")
    for record in rows:
        for origin in record["origins"]:
            identity = stable_id(
                "catalog-publication", "publisher", record["core"]["sample_id"], origin["origin_id"]
            )
            catalog.publish(identity, record["core"], origin, "publisher", NOW)
            catalog.publish(
                identity, record["core"], origin, "publisher", NOW + timedelta(seconds=1)
            )
    cfg, db, state = target(tmp_path / "target")
    transfer = TransferEngine(cfg, LocalControl(), db, catalog)
    first = transfer.feedback(state, NOW, "cycle")
    assert first["transfer"]["groups"][0]["state"] == "NO_SOURCES"
    assert db.learning_records() == []
    second = transfer.feedback(state, NOW + timedelta(seconds=1), "cycle")
    assert second["status"] == "insufficient_samples"
    assert second["transfer"]["groups"][0]["state"] == "VALIDATING"
    assert second["transfer"]["groups"][0]["source_sample_count"] == 50
    row = db.connection.execute(
        "SELECT p,baseline,source_query_hash FROM transfer_shadows"
    ).fetchone()
    assert Decimal(row["p"]) == Decimal(51) / 52 and row["baseline"] == "0.5"
    transfer.feedback(state, NOW + timedelta(seconds=2), "cycle")
    assert db.connection.execute("SELECT COUNT(*) FROM transfer_shadows").fetchone()[0] == 1
    assert tuple(
        db.connection.execute(
            "SELECT p,baseline,source_query_hash FROM transfer_shadows"
        ).fetchone()
    ) == tuple(row)
    assert db.learning_records() == [] and all(wallet.cash_usdt == 100 for wallet in db.wallets())
    assert db.audit()["ok"]
    db.close()
    catalog.close()


@pytest.mark.asyncio
async def test_active_then_suspended_with_frozen_scores_and_local_priority(tmp_path):
    from dataclasses import replace

    prototype = await synthetic_record_for_schema_tests(tmp_path / "prototype")
    records = source_records(prototype, 50, anchor=NOW - timedelta(days=27))
    catalog = LearningCatalog(tmp_path / "catalog.sqlite3")
    published = NOW - timedelta(days=25)
    for record in records:
        origin = record["origins"][0]
        identity = stable_id(
            "catalog-publication", "publisher", record["core"]["sample_id"], origin["origin_id"]
        )
        catalog.publish(identity, record["core"], origin, "publisher", published)
    cfg, db, state = target(tmp_path / "target", created_at=NOW - timedelta(days=16))
    local = LocalControl()
    transfer = TransferEngine(cfg, local, db, catalog)
    for i in range(30):
        at = NOW - timedelta(days=15) + timedelta(hours=12 * i)
        cycle = "prospective-fixture-" + str(i)
        candle = replace(
            current_candle(),
            symbol="ETHUSDT",
            open_time=at - timedelta(minutes=15),
            close_time_exclusive=at,
            available_at=at,
        )
        frame = {**state, "market": {**state["market"], "as_of": iso(at)}}
        with db.transaction():
            db.start_cycle(cycle, candle, at, frame["market"], db.wallets())
        forecast = transfer.feedback(frame, at + timedelta(seconds=1), cycle)
        assert forecast["transfer"]["groups"][0]["state"] == "VALIDATING"
        with db.transaction():
            db.connection.execute(
                "UPDATE transfer_shadows SET status='SCORED',matured_at=?,y=1,return_pct='1' "
                "WHERE cycle_id=?",
                (iso(at + timedelta(hours=1)), cycle),
            )
    active = transfer.feedback(state, NOW)
    assert active["transfer"]["groups"][0]["state"] == "ACTIVE"
    assert active["patterns"][0]["source_scope"] == "TRANSFERRED"
    assert active["patterns"][0]["validation"]["sample_count"] == 30
    original_p = [row[0] for row in db.connection.execute("SELECT p FROM transfer_shadows")]

    class LocalReady(LocalControl):
        def feedback(self, state, cutoff):
            return {
                "status": "available",
                "patterns": [
                    {
                        "source_scope": "LOCAL",
                        "position_context": "flat",
                        "label_kind": "ENTRY_LONG_NET_RETURN",
                        "horizon_bars": 4,
                        "market_regime": "bullish",
                        "smoothed_win_rate": 0.5,
                    }
                ],
            }

    composed = TransferEngine(cfg, LocalReady(), db, catalog).feedback(state, NOW)
    assert len(composed["patterns"]) == 1 and composed["patterns"][0]["source_scope"] == "LOCAL"
    for i in range(30):
        at = NOW + timedelta(hours=12 * i)
        cycle = "future-negative-fixture-" + str(i)
        candle = replace(
            current_candle(),
            symbol="ETHUSDT",
            open_time=at - timedelta(minutes=15),
            close_time_exclusive=at,
            available_at=at,
        )
        frame = {**state, "market": {**state["market"], "as_of": iso(at)}}
        with db.transaction():
            db.start_cycle(cycle, candle, at, frame["market"], db.wallets())
        transfer.feedback(frame, at + timedelta(seconds=1), cycle)
        with db.transaction():
            db.connection.execute(
                "UPDATE transfer_shadows SET status='SCORED',matured_at=?,y=0,return_pct='-1' "
                "WHERE cycle_id=?",
                (iso(at + timedelta(hours=1)), cycle),
            )
    suspended = transfer.feedback(state, NOW + timedelta(days=15))
    assert suspended["transfer"]["groups"][0]["state"] == "SUSPENDED"
    assert not suspended["patterns"]
    assert [
        row[0] for row in db.connection.execute("SELECT p FROM transfer_shadows LIMIT 30")
    ] == original_p
    assert db.learning_records() == [] and db.audit()["ok"]
    original_sources = catalog.sources

    def unavailable(*args):
        raise OSError("synthetic catalog outage")

    catalog.sources = unavailable
    failed = transfer.feedback(state, NOW + timedelta(days=15, seconds=1))
    assert not failed["patterns"] and failed["transfer"]["groups"][0]["state"] == "UNAVAILABLE"
    assert all(
        row[0] == "UNAVAILABLE"
        for row in db.connection.execute("SELECT state FROM transfer_states")
    )
    catalog.sources = original_sources
    db.close()
    catalog.close()


@pytest.mark.asyncio
async def test_outbox_replay_after_catalog_commit_does_not_duplicate(tmp_path):
    prototype = await synthetic_record_for_schema_tests(tmp_path / "prototype")
    records = source_records(prototype, 1)
    cfg, db, state = target(tmp_path / "target")
    at = NOW - timedelta(seconds=1)
    with db.transaction():
        for origin in records[0]["origins"]:
            db.save_learning_record(records[0]["core"], origin, at)
    catalog = LearningCatalog(tmp_path / "catalog.sqlite3")
    transfer = TransferEngine(cfg, LocalControl(), db, catalog)
    original = db.acknowledge_publication

    def crash(*args):
        raise RuntimeError("crash after catalog commit")

    db.acknowledge_publication = crash
    with pytest.raises(RuntimeError):
        transfer.publish(NOW)
    assert catalog.connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
    db.acknowledge_publication = original
    assert transfer.publish(NOW + timedelta(seconds=1)) == 3
    assert catalog.connection.execute("SELECT COUNT(*) FROM examples").fetchone()[0] == 1
    assert catalog.connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 3
    assert transfer.publish(NOW + timedelta(seconds=2)) == 0
    catalog.close()
    rebuilt = LearningCatalog(tmp_path / "rebuilt-catalog.sqlite3")
    recovered = TransferEngine(cfg, LocalControl(), db, rebuilt)
    assert recovered.publish(NOW + timedelta(seconds=3)) == 3
    assert (
        rebuilt.sources("ETHUSDT", records[0]["core"]["protocol_hash"], NOW + timedelta(seconds=3))
        == []
    )
    assert (
        len(
            rebuilt.sources(
                "ETHUSDT", records[0]["core"]["protocol_hash"], NOW + timedelta(seconds=4)
            )
        )
        == 1
    )
    rebuilt.close()
    db.close()
