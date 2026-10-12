from datetime import timedelta

from test_accounting import NOW, A, intent, quote, setup

from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.execution import TradingService


def test_audit_uses_one_read_snapshot_while_another_connection_commits_a_fill(
    tmp_path, monkeypatch
):
    cfg, manager, reader, trading = setup(tmp_path)
    writer = SessionDatabase(reader.path)
    service = TradingService(cfg, trading.metadata, writer)
    original = reader.wallets

    def wallets_before_concurrent_commit():
        wallets = original()
        service.execute(intent(), quote(NOW + timedelta(seconds=1)), NOW + timedelta(seconds=1))
        return wallets

    try:
        monkeypatch.setattr(reader, "wallets", wallets_before_concurrent_commit)
        audit = reader.audit()
        assert audit["ok"] and audit["fill_count"] == 0
        assert not reader.connection.in_transaction
        monkeypatch.setattr(reader, "wallets", original)
        assert reader.wallet(A).cash_usdt < 100
        assert reader.audit()["ok"] and reader.audit()["fill_count"] == 1
        # Joining an existing read transaction must not close its snapshot.
        reader.connection.execute("BEGIN")
        assert reader.audit()["ok"] and reader.connection.in_transaction
        reader.connection.rollback()
    finally:
        writer.close()
        reader.close()
