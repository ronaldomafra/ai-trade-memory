from datetime import timedelta

import pytest
from test_accounting import NOW, config, meta, quote
from test_outcomes import decisions

from poc.adapters.outbound.datasets import DatasetFiles, read_dataset
from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.application.sessions import SessionManager
from poc.domain.primitives import DomainError, stable_id


async def synthetic_record_for_schema_tests(tmp_path):
    # A wholly synthetic provenance fixture, confined to pytest's temporary directory.
    cfg, db, learning = await decisions(tmp_path)
    learning.register()
    at = NOW + timedelta(hours=1, seconds=1)
    with db.transaction():
        db.save_quote(quote(at, bid="110000", ask="110010"))
    learning.mature(at)
    record = db.learning_records()[0]
    db.close()
    record["core"]["fixture"] = False
    for key in ("reference_quote", "exit_quote"):
        record["core"][key]["source"] = "binance_rest"
    record["core"].pop("sample_id")
    record["core"]["sample_id"] = stable_id("equivalence_v1", record["core"])
    return record


def new_database(root, run="target", symbol="BTCUSDT"):
    cfg = config(root)
    if symbol != "BTCUSDT":
        cfg = type(cfg).model_validate(
            {**cfg.model_dump(mode="json"), "market": {"symbol": symbol}}
        )
    m = meta(symbol=symbol, base=symbol[:-4])
    session = SessionManager(cfg, SQLiteStorage()).prepare(run, "trend_15m_v1", m, NOW)
    return cfg, SessionDatabase(session["paths"]["sqlite"])


@pytest.mark.asyncio
async def test_accumulated_roundtrip_provenance_availability_and_finances(tmp_path):
    record = await synthetic_record_for_schema_tests(tmp_path / "fixture")
    cfg, db = new_database(tmp_path / "source", "source")
    imported_at = NOW + timedelta(hours=2)
    with db.transaction():
        for origin in record["origins"]:
            db.save_learning_record(record["core"], origin, imported_at)
    first = tmp_path / "r001.jsonl"
    export_at = imported_at + timedelta(seconds=1)
    exported = DatasetFiles(db).export(first, export_at)
    assert exported["sample_count"] == 1
    with pytest.raises(FileExistsError):
        DatasetFiles(db).export(first, export_at)
    db.close()
    _, target = new_database(tmp_path / "target", symbol="ETHUSDT")
    now = export_at + timedelta(hours=1)
    imported = DatasetFiles(target).import_path(first, now)
    assert not imported["idempotent"]
    assert DatasetFiles(target).import_path(first, now)["idempotent"]
    assert target.learning_records(now) == []
    records = target.learning_records(now + timedelta(microseconds=1))
    assert records[0]["core"] == record["core"]
    assert len(records[0]["origins"]) == 3
    assert all(wallet.cash_usdt == 100 and not wallet.has_position for wallet in target.wallets())
    second = tmp_path / "r002.jsonl"
    DatasetFiles(target).export(second, now + timedelta(seconds=1))
    data = read_dataset(second, now + timedelta(seconds=2))
    assert data["header"]["predecessors"][0]["dataset_id"] == exported["dataset_id"]
    assert data["records"][0]["core"]["sample_id"] == record["core"]["sample_id"]
    assert target.audit()["ok"]
    target.close()


@pytest.mark.asyncio
async def test_corruption_future_and_fixture_rejected_without_partial_import(tmp_path):
    record = await synthetic_record_for_schema_tests(tmp_path / "fixture")
    _, db = new_database(tmp_path / "source", "source")
    now = NOW + timedelta(hours=2)
    with db.transaction():
        for origin in record["origins"]:
            db.save_learning_record(record["core"], origin, now)
    path = tmp_path / "version.jsonl"
    DatasetFiles(db).export(path, now + timedelta(seconds=1))
    with pytest.raises(DomainError, match="cutoff"):
        read_dataset(path, now)
    path.write_bytes(path.read_bytes().replace(b"110000", b"120000"))
    with pytest.raises(DomainError, match="integrity"):
        read_dataset(path, now + timedelta(seconds=2))
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_initial_configuration_import_restore_does_not_reread_altered_file(tmp_path):
    record = await synthetic_record_for_schema_tests(tmp_path / "fixture")
    _, source = new_database(tmp_path / "source", "source")
    now = NOW + timedelta(hours=2)
    with source.transaction():
        for origin in record["origins"]:
            source.save_learning_record(record["core"], origin, now)
    path = tmp_path / "initial.jsonl"
    DatasetFiles(source).export(path, now + timedelta(seconds=1))
    source.close()
    cfg = config(tmp_path / "new")
    cfg = type(cfg).model_validate(
        {**cfg.model_dump(mode="json"), "learning": {"initial_dataset_path": str(path)}}
    )
    manager = SessionManager(cfg, SQLiteStorage())
    prepared = manager.prepare("initial", "trend_15m_v1", meta(), now + timedelta(seconds=2))
    database = SessionDatabase(prepared["paths"]["sqlite"])
    assert len(database.learning_records()) == 1
    database.close()
    path.write_text("altered file, never re-read on restore")
    manager.restore("initial")
    manager.prepare("initial", "trend_15m_v1", meta(), now + timedelta(seconds=3))
    database = SessionDatabase(prepared["paths"]["sqlite"])
    assert len(database.learning_records()) == 1 and database.audit()["ok"]
    database.close()


@pytest.mark.asyncio
async def test_import_rollback_is_not_partially_usable(tmp_path):
    record = await synthetic_record_for_schema_tests(tmp_path / "fixture")
    _, db = new_database(tmp_path / "target")
    now = NOW + timedelta(hours=2)
    db.connection.execute(
        "CREATE TRIGGER injected_failure BEFORE INSERT ON learning_origins "
        "BEGIN SELECT RAISE(ABORT,'crash'); END"
    )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        DatasetFiles(db).install(
            {
                "header": {"dataset_id": "synthetic-test"},
                "records": [record],
                "file_hash": "synthetic-test",
            },
            now,
        )
    assert db.learning_records() == []
    assert db.connection.execute("SELECT COUNT(*) FROM learning_examples").fetchone()[0] == 0
    assert db.connection.execute("SELECT COUNT(*) FROM dataset_imports").fetchone()[0] == 0
    assert db.audit()["ok"]
    db.close()
