import shutil
from pathlib import Path

import httpx
import pytest
from test_accounting import meta, setup
from test_cycles_engine import Clock, Source

from poc.adapters.inbound.service import engine_api
from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.engine import LiveEngine
from poc.application.sessions import SessionManager
from poc.config import Config


@pytest.mark.asyncio
async def test_private_reads_do_not_trade_and_include_consistent_watermark(tmp_path):
    cfg, _, db, _ = setup(tmp_path)
    clock = Clock()
    engine = LiveEngine(cfg, meta(), db, Source(clock), clock)
    await engine.initialize()
    before = db.audit()["fill_count"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=engine_api(engine, db)), base_url="http://localhost"
    ) as client:
        health = (await client.get("/health")).json()
        snapshot = (await client.get("/v1/session")).json()
        events = (await client.get("/v1/events", params={"after_seq": 0})).json()
        assert health["run_id"] == snapshot["run_id"] == events["run_id"]
        assert snapshot["event_watermark"] == events["events"][-1]["event_seq"]
        assert (await client.get("/v1/events", params={"after_seq": -1})).status_code == 422
    assert db.audit()["fill_count"] == before
    db.close()


def test_volume_mount_remapping_preserves_config_identity_and_money(tmp_path):
    cfg, manager, db, _ = setup(tmp_path / "host")
    saved_hash = manager.restore("run-1")["config_hash"]
    db.close()
    shutil.copytree(tmp_path / "host", tmp_path / "container")
    mounted = Config.model_validate({"app": {"data_dir": str(tmp_path / "container")}})
    record = SessionManager(mounted, SQLiteStorage()).restore("run-1")
    assert record["config_hash"] == saved_hash
    assert record["paths"]["sqlite"].startswith(str(tmp_path / "container"))
    assert record["persisted_paths"]["sqlite"].startswith(str(tmp_path / "host"))
    db2 = SessionDatabase(Path(record["paths"]["sqlite"]), create=False)
    assert all(wallet.cash_usdt == 100 for wallet in db2.wallets())
    assert db2.audit()["ok"]
    db2.close()
