from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from poc.bootstrap import configuration
from poc.config import Config, GlobalAICostLimit, load_config
from poc.domain.primitives import DomainError, decimal, floor_step


def test_default_template_matches_spec():
    cfg = load_config("config/default.yaml")
    assert cfg.portfolios.initial_usdt == Decimal("100")
    assert cfg.simulation.trading_fee_pct_per_side == Decimal("0.10")
    assert cfg.strategy.max_allocation_pct == Decimal("20")
    assert cfg.ai.max_calls_per_day == 240
    assert cfg.ai.max_observed_cost_usd_per_day == Decimal("0.05")
    assert cfg.learning.evaluation_horizons_bars == (4, 16)
    assert cfg.hash == Config.model_validate_json(cfg.canonical()).hash


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", True, 0.10])
def test_global_cost_limit_requires_positive_finite_decimal_string(amount):
    with pytest.raises(ValidationError):
        GlobalAICostLimit(max_observed_cost_usd_per_day=amount)


def test_global_cost_policy_is_separate_from_session_config_and_not_capped_at_five_cents():
    before = Config().hash
    assert GlobalAICostLimit(
        max_observed_cost_usd_per_day="1.00"
    ).max_observed_cost_usd_per_day == Decimal("1.00")
    assert not GlobalAICostLimit(cost_limit_enabled=False).cost_limit_enabled
    with pytest.raises(ValidationError):
        GlobalAICostLimit(cost_limit_enabled="false")
    assert "cost_limit_enabled" not in Config().ai.model_dump()
    assert Config().hash == before


@pytest.mark.parametrize("value", [0.1, True, "NaN", "Infinity", "-Infinity", "bad"])
def test_financial_values_cannot_be_float_or_nonfinite(value):
    with pytest.raises(DomainError):
        decimal(value)


@pytest.mark.parametrize(
    "update",
    [
        {"app": {"mode": "LIVE"}},
        {"market": {"interval": "1m"}},
        {"market": {"rest_url": "https://api.binance.com/api/v3/order"}},
        {"portfolios": {"initial_usdt": "300"}},
        {"ai": {"endpoint": "https://openrouter.ai/api/v1/chat/completions"}},
        {"ai": {"max_calls_per_day": 480}},
        {"ai": {"max_observed_cost_usd_per_day": "0.10"}},
        {"ai": {"max_retries": 2}},
        {"simulation": {"trading_fee_pct_per_side": 0.1}},
        {"storage": {"sqlite_path": "../other/{run_id}/db"}},
        {"strategy": {"unknown": 1}},
        {"learning": {"use_only_matured_outcomes": False}},
        {"learning": {"transfer": {"min_source_samples": 49}}},
        {"polymarket": {"discovery_page_size": 101}},
        {"indicators": {"ema_short": 200, "ema_long": 20}},
    ],
)
def test_invalid_config_rejected(update):
    with pytest.raises(ValidationError):
        Config.model_validate(update)


def test_immutable_and_generic_symbol(tmp_path):
    cfg = Config.model_validate({"market": {"symbol": "ETHUSDT"}})
    with pytest.raises(ValidationError):
        cfg.market.symbol = "BTCUSDT"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg.model_dump(mode="json")))
    assert load_config(path).hash == cfg.hash
    assert floor_step(Decimal("1.237"), Decimal("0.005")) == Decimal("1.235")


def test_provider_file_overrides_stale_shell_but_data_directory_remains_explicit(
    tmp_path, monkeypatch
):
    path = Path("config/default.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    for key in ("OPENROUTER_API_KEY", "MARKETAUX_API_TOKEN", "POLYMARKET_PROXY_URL"):
        monkeypatch.setenv(key, "stale-shell-value")
    monkeypatch.delenv("POC_ENV_FILE", raising=False)
    monkeypatch.setenv("POC_DATA_DIR", "/explicit/data")
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=synthetic-file-key\n"
        "MARKETAUX_API_TOKEN=synthetic-news-key\nPOLYMARKET_PROXY_URL=\nPOC_DATA_DIR=./other\n"
    )
    cfg = configuration(path)
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "synthetic-file-key"
    assert os.environ["MARKETAUX_API_TOKEN"] == "synthetic-news-key"
    assert os.environ["POLYMARKET_PROXY_URL"] == ""
    assert cfg.app.data_dir == "/explicit/data"


def test_control_reads_explicit_credentials_file_without_using_stale_export(tmp_path, monkeypatch):
    path = Path("config/default.yaml").resolve()
    secret_file = tmp_path / "mounted.env"
    secret_file.write_text("OPENROUTER_API_KEY=synthetic-mounted-key\n")
    monkeypatch.setenv("POC_ENV_FILE", str(secret_file))
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-stale-key")
    configuration(path)
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "synthetic-mounted-key"
    secret_file.unlink()
    with pytest.raises(DomainError, match="Credentials file"):
        configuration(path)
