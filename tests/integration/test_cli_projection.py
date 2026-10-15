import json
from pathlib import Path

import httpx
import pytest
import yaml

from poc.adapters.inbound.cli import main
from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.config import Config


@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
def test_offline_cli_and_projection_reconstruction(tmp_path, monkeypatch, capsys, symbol):
    monkeypatch.setenv("POC_DATA_DIR", str(tmp_path))

    def no_network(*args, **kwargs):
        raise AssertionError("Offline smoke attempted network I/O")

    monkeypatch.setattr(httpx.AsyncClient, "get", no_network)
    cfg = Config.model_validate({"market": {"symbol": symbol}})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg.model_dump(mode="json")))
    assert main(["smoke-offline", "--scope", "accounting", "--config", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["fixture"] and result["network_calls"] == 0
    assert result["audit"]["ok"] and result["audit"]["fill_count"] == 6
    assert all(p["closed_trades"] == 1 for p in result["portfolios"])
    run_id = result["run_id"]
    assert main(["status", "--run-id", run_id]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["fixture"] and state["run_id"] == run_id
    dashboard = Path(result["paths"]["exports"]) / "dashboard-latest.json"
    assert json.loads(dashboard.read_text())["run_id"] == run_id
    logs = list(Path(result["paths"]["logs"]).glob("*/events.jsonl"))
    assert logs
    saved = logs[0].read_text()
    logs[0].write_text(saved + saved)
    db = SessionDatabase(result["paths"]["sqlite"], create=False)
    exporter = FileExporter(db)
    exporter.events(rebuild=True)
    lines = [json.loads(s) for p in logs for s in p.read_text().splitlines()]
    assert len(lines) == len({e["event_id"] for e in lines})
    assert lines[-1]["event_seq"] == state["event_watermark"]
    assert db.audit()["ok"]
    # A torn append must reconstruct from SQLite instead of preserving invalid JSONL.
    with logs[0].open("a") as stream:
        stream.write('{"event_id":"interrupted')
    exporter.events()
    assert all(json.loads(s) for s in logs[0].read_text().splitlines())
    assert len(logs[0].read_text().splitlines()) == len(lines)
    db.close()
    assert main(["validate-data", "--run-id", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]


def test_cli_requires_explicit_session_and_rejects_missing_restore(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("POC_DATA_DIR", str(tmp_path))
    with pytest.raises(SystemExit):
        main(["status"])
    assert main(["status", "--run-id", "missing"]) == 2
    assert "does not exist" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.sqlite3"))


def test_global_budget_cli_only_changes_isolated_operational_policy(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("POC_DATA_DIR", str(tmp_path))

    def no_network(*args, **kwargs):
        raise AssertionError("Budget configuration must never call a provider")

    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)
    assert main(["ai-budget"]) == 0
    assert json.loads(capsys.readouterr().out)["legacy"]["policy"]["cost_limit_enabled"]
    assert main(["ai-budget", "--legacy-global", "--disable-cost-limit"]) == 0
    assert not json.loads(capsys.readouterr().out)["policy"]["cost_limit_enabled"]
    assert (
        main(["ai-budget", "--legacy-global", "--enable-cost-limit", "--daily-limit-usd", "0.15"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["policy"]["cost_limit_enabled"]
    assert result["policy"]["max_observed_cost_usd_per_day"] == "0.15"
    assert result["physical_attempts"] == 0
    assert not (tmp_path / "sessions").exists()
