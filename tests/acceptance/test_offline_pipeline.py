import json
from pathlib import Path

import httpx
import pytest
import yaml

from poc.adapters.inbound.cli import main
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.config import Config


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_full_offline_pipeline_never_uses_network_or_exports_fixture_learning(
    tmp_path, monkeypatch, capsys, symbol
):
    monkeypatch.setenv("POC_DATA_DIR", str(tmp_path))

    async def no_network(*args, **kwargs):
        raise AssertionError("Offline pipeline used a real network transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    cfg = Config.model_validate({"market": {"symbol": symbol}})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg.model_dump(mode="json")))
    assert main(["smoke-offline", "--config", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "V1_OFFLINE_PIPELINE" and result["fixture"]
    assert result["network_calls"] == result["real_provider_attempts"] == 0
    assert (
        result["cycles"]
        == result["duplicate_cycles_skipped"]
        == result["mock_provider_attempts"]
        == 8
    )
    assert result["decisions"] == 24 and result["audit"]["ok"]
    assert result["outcomes"]["MATURED"] > 0 and result["outcomes"]["UNAVAILABLE"] > 0
    assert result["outcomes"].get("PENDING", 0) == 0
    assert result["dataset"]["sample_count"] == 0
    db = SessionDatabase(result["paths"]["sqlite"], readonly=True)
    try:
        assert db.audit()["ok"]
        assert db.connection.execute("SELECT COUNT(*) FROM ai_calls").fetchone()[0] == 8
        assert all(
            row[0] == "typesafe/jev-1.13-offline-fixture"
            for row in db.connection.execute("SELECT actual_model FROM ai_calls")
        )
        assert all(row["core"]["fixture"] for row in db.learning_records())
        assert all(p["initial_usdt"] == "100" for p in result["portfolios"])
        assert Path(result["dataset"]["path"]).is_file()
    finally:
        db.close()
