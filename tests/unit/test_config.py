from decimal import Decimal

import pytest
import yaml
from pydantic import ValidationError

from poc.config import Config, load_config
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
