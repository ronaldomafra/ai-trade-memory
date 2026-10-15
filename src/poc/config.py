"""Versioned, immutable configuration with paper-only boundaries."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from poc.domain.primitives import canonical_json, decimal, stable_id

PositiveInt = Annotated[StrictInt, Field(gt=0)]
Money = Annotated[Decimal, BeforeValidator(decimal), Field(ge=0)]
PositiveMoney = Annotated[Decimal, BeforeValidator(decimal), Field(gt=0)]
Percent = Annotated[Decimal, BeforeValidator(decimal), Field(gt=0, le=100)]


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class App(Section):
    mode: Literal["PAPER_ONLY"] = "PAPER_ONLY"
    timezone: Literal["UTC"] = "UTC"
    data_dir: str = "./data"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    instance_name: str = "trade-poc-v1"
    poll_seconds: PositiveInt = 10
    max_candle_decision_lag_seconds: PositiveInt = 90
    max_quote_age_seconds: PositiveInt = 30


class Market(Section):
    provider: Literal["binance_public"] = "binance_public"
    symbol: str = Field(default="BTCUSDT", pattern=r"^[A-Z0-9]{2,30}USDT$")
    quote_asset: Literal["USDT"] = "USDT"
    interval: Literal["15m"] = "15m"
    trend_interval: Literal["1h"] = "1h"
    warmup_15m_candles: Annotated[StrictInt, Field(ge=600)] = 600
    rest_url: Literal["https://data-api.binance.vision"] = "https://data-api.binance.vision"
    min_trade_notional_usdt: PositiveMoney = Decimal("5.00")


class Portfolios(Section):
    initial_usdt: Annotated[Decimal, BeforeValidator(decimal), Field(ge=100, le=100)] = Decimal(
        "100"
    )
    strategies: tuple[str, ...] = ("BASELINE_TECHNICAL", "JEV_STATIC", "JEV_LEARNING")

    @model_validator(mode="after")
    def fixed_experiment(self) -> Self:
        if self.strategies != ("BASELINE_TECHNICAL", "JEV_STATIC", "JEV_LEARNING"):
            raise ValueError("The three independent A/B/C portfolios are required")
        return self


class Technical(Section):
    rsi_entry_min: float = Field(default=45, ge=0, le=100)
    rsi_entry_max: float = Field(default=70, ge=0, le=100)
    rsi_exit: float = Field(default=75, ge=0, le=100)
    min_relative_volume: float = Field(default=1.10, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def order(self) -> Self:
        if not self.rsi_entry_min <= self.rsi_entry_max < self.rsi_exit:
            raise ValueError("RSI entry interval must precede exit threshold")
        return self


class Strategy(Section):
    max_allocation_pct: Percent = Decimal("20.0")
    max_positions: Literal[1] = 1
    stop_loss_pct: Percent = Decimal("1.5")
    take_profit_pct: Percent = Decimal("3.0")
    max_holding_candles: PositiveInt = 16
    daily_loss_guard_pct: Percent = Decimal("5.0")
    action_probability_threshold: float = Field(default=0.65, ge=0, le=1, allow_inf_nan=False)
    action_margin_threshold: float = Field(default=0.10, ge=0, le=1, allow_inf_nan=False)
    technical: Technical = Field(default_factory=Technical)


class Simulation(Section):
    trading_fee_pct_per_side: Money = Decimal("0.10")
    slippage_pct_per_side: Money = Decimal("0.05")
    fill_price_source: Literal["public_book_ticker"] = "public_book_ticker"

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.trading_fee_pct_per_side >= 100 or self.slippage_pct_per_side >= 100:
            raise ValueError("Fee/slippage must be below 100%")
        return self


class Indicators(Section):
    rsi: PositiveInt = 14
    ema_short: PositiveInt = 20
    ema_mid: PositiveInt = 50
    ema_long: PositiveInt = 200
    macd_fast: PositiveInt = 12
    macd_slow: PositiveInt = 26
    macd_signal: PositiveInt = 9
    atr: PositiveInt = 14
    relative_volume_window: PositiveInt = 20

    @model_validator(mode="after")
    def periods(self) -> Self:
        if not self.ema_short < self.ema_mid < self.ema_long or self.macd_fast >= self.macd_slow:
            raise ValueError("Indicator periods are inconsistent")
        return self


class News(Section):
    enabled: bool = True
    api_provider: Literal["marketaux"] = "marketaux"
    api_poll_minutes: PositiveInt = 30
    poll_minutes: PositiveInt = 10
    lookback_hours: Annotated[StrictInt, Field(gt=0, le=24)] = 24
    max_items_per_decision: Annotated[StrictInt, Field(gt=0, le=5)] = 5
    sources: tuple[str, ...] = (
        "https://cointelegraph.com/rss",
        "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    )

    @model_validator(mode="after")
    def public_urls(self) -> Self:
        for source in self.sources:
            parsed = urlsplit(source)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("RSS URLs must use HTTPS without credentials")
        return self


class GlobalAICostLimit(Section):
    """Server-wide operational policy; never added to immutable session config/hash."""

    cost_limit_enabled: StrictBool = True
    max_observed_cost_usd_per_day: PositiveMoney = Decimal("0.05")


class AI(Section):
    provider: Literal["openrouter"] = "openrouter"
    endpoint: Literal["https://openrouter.ai/api/alpha/decisions"] = (
        "https://openrouter.ai/api/alpha/decisions"
    )
    model: Literal["typesafe/jev-1.13"] = "typesafe/jev-1.13"
    timeout_seconds: PositiveInt = 20
    max_retries: Literal[0, 1] = 1
    max_calls_per_day: Annotated[StrictInt, Field(gt=0, le=240)] = 240
    max_observed_cost_usd_per_day: Annotated[
        Decimal, BeforeValidator(decimal), Field(gt=0, le=Decimal("0.05"))
    ] = Decimal("0.05")
    fail_closed: Literal[True] = True
    prompt_version: str = "jev_trade_v1"


class Polymarket(Section):
    enabled: bool = True
    max_tracked_markets: PositiveInt = 10
    max_markets_per_occurrence: PositiveInt = 2
    discovery_page_size: Annotated[StrictInt, Field(gt=0, le=100)] = 100
    discovery_max_requests_per_refresh: PositiveInt = 5
    prices_poll_minutes: PositiveInt = 5
    markets_poll_minutes: PositiveInt = 60
    snapshot_max_age_minutes: PositiveInt = 10
    liquidity_max_age_minutes: PositiveInt = 75
    volume_24h_max_age_minutes: PositiveInt = 75
    max_spread_pp: Money = Decimal("2.0")
    min_liquidity_usd: Money = Decimal("10000")
    min_volume_24h_usd: Money = Decimal("1000")
    max_trade_age_minutes: PositiveInt = 60
    min_depth_per_side_usd: Money = Decimal("1000")
    depth_band_pp: PositiveMoney = Decimal("2.0")

    @model_validator(mode="after")
    def limits(self) -> Self:
        if self.max_markets_per_occurrence > self.max_tracked_markets:
            raise ValueError("Occurrence limit cannot exceed total market limit")
        if self.max_spread_pp > 100 or self.depth_band_pp > 100:
            raise ValueError("Probability bands must be <=100 percentage points")
        return self


class Transfer(Section):
    enabled: bool = True
    policy_version: Literal["transfer_v1"] = "transfer_v1"
    normalizer_version: Literal["relative_features_v1"] = "relative_features_v1"
    min_source_samples: Annotated[StrictInt, Field(ge=50)] = 50
    max_source_samples: Annotated[StrictInt, Field(gt=0, le=200)] = 200
    min_target_validation_samples: Annotated[StrictInt, Field(ge=30)] = 30

    @model_validator(mode="after")
    def sufficient_capacity(self) -> Self:
        if self.max_source_samples < self.min_source_samples:
            raise ValueError("Source capacity is below required sample count")
        return self


class Learning(Section):
    enabled: bool = True
    initial_dataset_path: str | None = None
    evaluation_horizons_bars: tuple[Literal[4, 16], ...] = (4, 16)
    primary_horizon_bars: Literal[4] = 4
    rolling_lookback_days: Literal[60] = 60
    min_exact_pattern_samples: Annotated[StrictInt, Field(ge=30)] = 30
    min_coarse_pattern_samples: Annotated[StrictInt, Field(ge=50)] = 50
    max_memory_items: Annotated[StrictInt, Field(gt=0, le=3)] = 3
    use_only_matured_outcomes: Literal[True] = True
    transfer: Transfer = Field(default_factory=Transfer)

    @model_validator(mode="after")
    def horizons(self) -> Self:
        if self.evaluation_horizons_bars != (4, 16):
            raise ValueError("V1 requires the separate 4/16-bar horizons")
        return self


class Storage(Section):
    sqlite_path: str = "./data/sessions/{run_id}/poc.sqlite3"
    jsonl_dir: str = "./data/sessions/{run_id}/logs"
    export_dir: str = "./data/sessions/{run_id}/exports"
    export_every_closed_candle: Literal[True] = True

    @model_validator(mode="after")
    def session_paths(self) -> Self:
        for value in (self.sqlite_path, self.jsonl_dir, self.export_dir):
            if value.count("{run_id}") != 1 or ".." in Path(value).parts:
                raise ValueError("Storage paths require one run_id and no traversal")
        return self


class Config(Section):
    app: App = Field(default_factory=App)
    market: Market = Field(default_factory=Market)
    portfolios: Portfolios = Field(default_factory=Portfolios)
    strategy: Strategy = Field(default_factory=Strategy)
    simulation: Simulation = Field(default_factory=Simulation)
    indicators: Indicators = Field(default_factory=Indicators)
    news: News = Field(default_factory=News)
    ai: AI = Field(default_factory=AI)
    polymarket: Polymarket = Field(default_factory=Polymarket)
    learning: Learning = Field(default_factory=Learning)
    storage: Storage = Field(default_factory=Storage)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.app.max_candle_decision_lag_seconds > 90 or self.app.max_quote_age_seconds > 30:
            raise ValueError("Freshness/deadline must not be relaxed beyond the V1 contract")
        if self.ai.timeout_seconds > self.app.max_candle_decision_lag_seconds:
            raise ValueError("Inference timeout exceeds decision window")
        if self.market.warmup_15m_candles <= self.indicators.ema_long:
            raise ValueError("Warmup must exceed longest EMA")
        return self

    @property
    def hash(self) -> str:
        return stable_id(self.model_dump(mode="json"))

    def canonical(self) -> str:
        return canonical_json(self.model_dump(mode="json"))


def load_config(path: str | Path) -> Config:
    with Path(path).open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return parse_config(data)


def parse_config(data: dict) -> Config:
    if data.get("schema_version") == 2:
        from poc.profile_config import ProfileConfig

        return ProfileConfig.model_validate(data)
    return Config.model_validate(data)
