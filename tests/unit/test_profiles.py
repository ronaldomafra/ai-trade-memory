from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from poc.config import Config, parse_config
from poc.domain.candles import INTERVAL_SECONDS, Candle
from poc.domain.features import FeatureEngine
from poc.profile_config import ProfileDefinition, profile_template, resolve_profile


def test_templates_resolve_all_styles_without_changing_legacy_hash():
    original = Config()
    for style, interval, trend in (
        ("SCALPING", "1m", "5m"),
        ("SWING", "4h", "1d"),
        ("DAY_TRADE", "15m", "1h"),
    ):
        profile = ProfileDefinition.model_validate(profile_template(style))
        effective = resolve_profile(profile, original, "SOLUSDT")
        assert effective.market.interval == interval
        assert effective.market.trend_interval == trend
        assert effective.market.symbol == "SOLUSDT"
        assert parse_config(effective.model_dump(mode="json")).hash == effective.hash
    assert parse_config(original.model_dump(mode="json")).hash == original.hash
    assert "schema_version" not in original.model_dump()


def test_profile_rejects_unknown_code_global_overrides_and_inconsistent_intervals():
    data = profile_template("SCALPING")
    for path, value in (("algorithm_version", "exec_python"),):
        invalid = deepcopy(data)
        invalid["parameters"]["strategy"][path] = value
        with pytest.raises(ValidationError):
            ProfileDefinition.model_validate(invalid)


def market_bars(values, interval, at):
    duration = INTERVAL_SECONDS[interval]
    return [
        Candle(
            "BTCUSDT",
            interval,
            at - timedelta(seconds=(len(values) - index) * duration),
            at - timedelta(seconds=(len(values) - index - 1) * duration),
            Decimal(value),
            Decimal(value) + Decimal("0.1"),
            Decimal(value) - Decimal("0.1"),
            Decimal(value),
            Decimal(10),
            at,
            "offline_fixture",
        )
        for index, value in enumerate(values)
    ]


def test_breakout_excludes_current_high_and_future_trend_bars():
    at = datetime(2026, 10, 14, 12, tzinfo=UTC)
    p = ProfileDefinition.model_validate(profile_template("DAY_TRADE")).parameters
    engine = FeatureEngine(p.indicators, p)
    bars = market_bars(["100"] * 599 + ["110"], "15m", at)
    trend = market_bars(["100"] * 600, "1h", at)
    features = engine.build("BTCUSDT", bars, trend, at)
    assert features.valid and features.structural_entry_setup
    assert features.decision_interval == "15m"
    future = market_bars(["99999"], "1h", at + timedelta(hours=1))
    assert engine.build("BTCUSDT", bars, trend + future, at) == features


def test_ema_cross_requires_transition_and_does_not_repeat_above_average():
    at = datetime(2026, 10, 14, 12, tzinfo=UTC)
    p = ProfileDefinition.model_validate(profile_template("SCALPING")).parameters
    engine = FeatureEngine(p.indicators, p)
    values = ["100"] * 569 + ["99"] * 30 + ["105"]
    first = engine.build(
        "BTCUSDT", market_bars(values, "1m", at), market_bars(["100"] * 600, "5m", at), at
    )
    assert first.valid and first.structural_entry_setup
    next_at = at + timedelta(minutes=1)
    following = engine.build(
        "BTCUSDT",
        market_bars(values + ["105"], "1m", next_at),
        market_bars(["100"] * 600, "5m", at),
        next_at,
    )
    assert following.valid and not following.structural_entry_setup
    assert first.state()["return_horizons_bars"] == (1, 3, 15)


def test_runtime_cannot_disagree_with_pinned_profile_parameters():
    profile = ProfileDefinition.model_validate(profile_template("DAY_TRADE"))
    runtime = resolve_profile(profile, Config(), "SOLUSDT").model_dump(mode="json")
    runtime["strategy"]["stop_loss_pct"] = "9"
    with pytest.raises(ValidationError, match="pinned profile"):
        parse_config(runtime)


def test_scalping_accepts_fifteen_second_deadline_and_preserves_old_snapshots():
    original = resolve_profile(
        ProfileDefinition.model_validate(profile_template("SCALPING")), Config(), "ZECUSDT"
    )
    saved = original.model_dump(mode="json")
    revised = deepcopy(saved["profile_definition"])
    revised["profile"]["version"] = 2
    revised["parameters"]["app"]["max_candle_decision_lag_seconds"] = 15
    updated = resolve_profile(ProfileDefinition.model_validate(revised), Config(), "ZECUSDT")
    assert updated.app.max_candle_decision_lag_seconds == 15
    assert updated.ai.timeout_seconds == 6
    assert parse_config(updated.model_dump(mode="json")).hash == updated.hash
    assert parse_config(saved).hash == original.hash
    assert parse_config(saved).app.max_candle_decision_lag_seconds == 8
    revised["parameters"]["app"]["max_candle_decision_lag_seconds"] = 16
    with pytest.raises(ValidationError, match="15s deadline"):
        ProfileDefinition.model_validate(revised)
    revised["parameters"]["app"]["max_candle_decision_lag_seconds"] = 15
    revised["parameters"]["ai"]["timeout_seconds"] = 16
    with pytest.raises(ValidationError, match="AI timeout exceeds candle deadline"):
        ProfileDefinition.model_validate(revised)


def test_profile_rejects_global_paths_bad_horizons_and_oversized_instructions():
    data = profile_template("SCALPING")
    for mutate in (
        lambda p: p["parameters"]["market"].update(trend_interval="1m"),
        lambda p: p["platform_bindings"].update(mode="REAL"),
        lambda p: p["parameters"]["app"].update(data_dir="/tmp/foreign"),
        lambda p: p["parameters"]["learning"].update(primary_horizon_bars=999),
        lambda p: p["parameters"]["ai"].update(max_calls_per_day=0),
        lambda p: p["parameters"]["jev_instructions"].update(objective="x" * 4001),
    ):
        invalid = deepcopy(data)
        mutate(invalid)
        with pytest.raises(ValidationError):
            ProfileDefinition.model_validate(invalid)


def test_per_bot_budget_is_editable_and_legacy_profile_hash_restores_without_added_defaults():
    from poc.domain.primitives import stable_id

    definition = profile_template("SCALPING")
    definition["parameters"]["ai"].update(
        max_calls_per_day=1500, max_observed_cost_usd_per_day="1.00", cost_limit_enabled=False
    )
    profile = ProfileDefinition.model_validate(definition)
    cfg = resolve_profile(profile, Config(), "SOLUSDT")
    assert cfg.ai.budget_scope == "SESSION" and cfg.ai.max_calls_per_day == 1500
    assert not cfg.ai.cost_limit_enabled
    assert cfg.ai.max_observed_cost_usd_per_day == Decimal("1.00")
    assert parse_config(cfg.model_dump(mode="json")).hash == cfg.hash

    legacy = profile_template("SCALPING")
    legacy["parameters"]["ai"].pop("budget_scope")
    legacy["parameters"]["ai"].pop("cost_limit_enabled")
    legacy["platform_bindings"].pop("ai_budget_reference")
    legacy["platform_bindings"].update(
        global_ai_policy_reference="SERVER_GLOBAL_AI_BUDGET", physical_calls_global_ceiling=240
    )
    old_cfg = resolve_profile(ProfileDefinition.model_validate(legacy), Config(), "ETHUSDT")
    raw = old_cfg.model_dump(mode="json")
    assert "cost_limit_enabled" not in raw["ai"] and "budget_scope" not in raw["ai"]
    assert parse_config(raw).hash == stable_id(raw)
