import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from test_accounting import NOW, config, meta
from test_cycles_engine import Clock, FeaturesFixture, Source, current_candle

from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.learning import LearningEngine
from poc.application.orchestrator import CycleCoordinator
from poc.application.sessions import SessionManager
from poc.config import parse_config
from poc.domain.primitives import stable_id


@pytest.mark.asyncio
async def test_upgrade_v6_preserves_legacy_hashes_fills_ledger_and_pending_outcomes(
    tmp_path, monkeypatch
):
    glob = Path.glob

    def before_profiles(path, pattern):
        return (item for item in glob(path, pattern) if item.name != "007_profile_horizons.sql")

    cfg = config(tmp_path)
    manager = SessionManager(cfg, SQLiteStorage())
    with monkeypatch.context() as local:
        local.setattr(Path, "glob", before_profiles)
        saved = manager.prepare("legacy", "trend_15m_v1", meta(), NOW)
        db = SessionDatabase(saved["paths"]["sqlite"], create=False)
        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 6
        clock = Clock()
        coordinator = CycleCoordinator(cfg, meta(), db, Source(clock), clock, asyncio.Event())

        class MatureFeatures(FeaturesFixture):
            def build(self, *args):
                return replace(super().build(*args), volatility_bucket="high")

        coordinator.feature_engine = MatureFeatures()
        assert await coordinator.process(current_candle())
        learning = LearningEngine(cfg, meta(), db)
        assert learning.register() == 6
        tables = ("runs", "decisions", "paper_fills", "ledger_entries", "decision_outcomes")
        hashes = {
            t: stable_id(
                [tuple(r) for r in db.connection.execute("SELECT * FROM " + t + " ORDER BY rowid")]
            )
            for t in tables
        }
        db.close()
    db = SessionDatabase(saved["paths"]["sqlite"], create=False)
    assert db.connection.execute("PRAGMA user_version").fetchone()[0] == 7
    assert db.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert not db.connection.execute("PRAGMA foreign_key_check").fetchall()
    assert db.audit()["ok"]
    for table in tables:
        assert (
            stable_id(
                [
                    tuple(r)
                    for r in db.connection.execute("SELECT * FROM " + table + " ORDER BY rowid")
                ]
            )
            == hashes[table]
        )
    db.close()
    restored = manager.restore("legacy")
    assert restored["config_hash"] == saved["config_hash"] == cfg.hash
    assert parse_config(restored["config"]).hash == cfg.hash
