import sqlite3

import pytest
from test_control_api import cleanup, fixture


@pytest.mark.asyncio
async def test_remote_view_connection_rejects_ledger_and_schema_writes(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        response = await client.post(
            "/v1/sessions",
            json={"profile_id": "trend_15m_v1", "symbol": "BTCUSDT", "run_id": "readonly"},
            headers={"Idempotency-Key": "prepare-readonly"},
        )
        assert response.status_code == 201
        db = app.state.views.database("readonly", readonly=True)
        try:
            version = db.connection.execute("PRAGMA user_version").fetchone()[0]
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                db.connection.execute("UPDATE portfolios SET cash_usdt='999'")
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                db.connection.execute("PRAGMA user_version=1")
            assert db.connection.execute("PRAGMA user_version").fetchone()[0] == version
            assert all(str(wallet.cash_usdt) == "100" for wallet in db.wallets())
        finally:
            db.close()
    finally:
        await cleanup(items)
