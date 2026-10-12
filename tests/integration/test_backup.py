from datetime import timedelta
from pathlib import Path

import pytest
from test_accounting import NOW, intent, quote, setup

from poc.adapters.outbound.backup import SessionBackups
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.domain.primitives import DomainError


def test_consistent_backup_restores_ledger_and_rejects_overwrite_or_corruption(tmp_path):
    config, manager, db, service = setup(tmp_path / "source")
    at = NOW + timedelta(seconds=1)
    service.execute(intent(), quote(at), at)
    balances = [(w.cash_usdt, w.base_qty) for w in db.wallets()]
    service_backup = SessionBackups(Path(config.app.data_dir))
    archive = tmp_path / "archive"
    saved = service_backup.create(db, archive, NOW)
    assert saved["run_id"] == "run-1"
    restored_root = tmp_path / "restored"
    restored = SessionBackups(restored_root).restore(archive, "run-1", NOW)
    assert restored["ai_blocked_until_next_utc_day"]
    from decimal import Decimal

    from poc.adapters.outbound.budget import AIBudget

    budget = AIBudget(restored_root / "operational" / "ai-budget.sqlite3")
    assert not budget.reserve("test", "trade", "test", 1, NOW, 240, Decimal(".05"), {})["granted"]
    assert budget.reserve(
        "test", "trade", "test", 1, NOW + timedelta(days=1), 240, Decimal(".05"), {}
    )["granted"]
    budget.close()
    target = SessionDatabase(restored["sqlite"])
    assert [(w.cash_usdt, w.base_qty) for w in target.wallets()] == balances
    assert target.audit()["ok"] and target.audit()["fill_count"] == 1
    assert target.run()["config_hash"] == db.run()["config_hash"]
    target.close()
    with pytest.raises(DomainError):
        SessionBackups(restored_root).restore(archive, "run-1", NOW)
    with (archive / "session.sqlite3").open("ab") as stream:
        stream.write(b"corruption")
    with pytest.raises(DomainError, match="hash"):
        SessionBackups(tmp_path / "bad").restore(archive, "run-1", NOW)
    db.close()
