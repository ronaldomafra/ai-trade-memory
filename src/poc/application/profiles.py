"""Profile lifecycle and immutable resolution, independent of storage/HTTP/TUI."""

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from poc.config import Config
from poc.domain.learning import net_entry_return
from poc.domain.primitives import DomainError
from poc.profile_config import (
    ProfileDefinition,
    profile_template,
    resolve_profile,
    with_session_budget,
)


class ProfileRepositoryPort(Protocol):
    def list_profiles(self) -> list[dict]: ...
    def profile(self, profile_id: str, version: int | None = None) -> dict | None: ...
    def register_profile(
        self, definition: dict, digest: str, actor: str, now: datetime
    ) -> dict: ...
    def transition_profile(
        self, profile_id: str, version: int, status: str, actor: str, now: datetime
    ) -> dict: ...


class ProfileService:
    def __init__(self, repository: ProfileRepositoryPort, server: Config):
        self.repository, self.server = repository, server

    def template(self, style: str) -> dict:
        return {
            "definition": profile_template(style),
            "parameter_schema": ProfileDefinition.model_json_schema(),
            "capabilities": ["profiles_v2", "ema_cross_long_v1", "breakout_long_v1", "baseline_v1"],
        }

    def validate(self, definition: dict) -> dict:
        p = ProfileDefinition.model_validate(with_session_budget(definition))
        if p.profile.profile_id == "trend_15m_v1":
            raise DomainError("The legacy profile is protected; use a new profile_id")
        effective = resolve_profile(p, self.server, p.session_defaults.symbol)
        parameters = p.parameters
        fee = parameters.simulation.trading_fee_pct_per_side / 100
        slip = parameters.simulation.slippage_pct_per_side / 100
        price = Decimal(100)
        target = net_entry_return(
            price, price * (1 + slip) * (1 + parameters.strategy.take_profit_pct / 100), fee, slip
        )
        stop = net_entry_return(
            price, price * (1 + slip) * (1 - parameters.strategy.stop_loss_pct / 100), fee, slip
        )
        if (
            target <= 0
            or stop >= 0
            or target / abs(stop) < parameters.execution_quality.minimum_net_target_to_stop_ratio
        ):
            raise DomainError(
                "Even the zero-spread execution scenario fails the configured net target/stop gate"
            )
        from poc.domain.candles import INTERVAL_SECONDS

        return {
            "valid": True,
            "definition": p.model_dump(mode="json"),
            "profile_hash": p.hash,
            "preview": {
                "mode": "PAPER_ONLY",
                "interval": effective.market.interval,
                "trend_interval": effective.market.trend_interval,
                "maximum_holding_seconds": parameters.strategy.max_holding_candles
                * INTERVAL_SECONDS[effective.market.interval],
                "horizon_seconds": [
                    h * INTERVAL_SECONDS[effective.market.interval]
                    for h in effective.learning.evaluation_horizons_bars
                ],
                "maximum_cycles_per_day_utc": parameters.opportunities.max_cycles_per_day_utc,
                "trade_calls_before_retries_and_classifications": [
                    parameters.opportunities.max_cycles_per_day_utc,
                    2 * parameters.opportunities.max_cycles_per_day_utc,
                ],
                "ai_budget": {
                    "scope": "SESSION",
                    "max_calls_per_day": p.parameters.ai.max_calls_per_day,
                    "cost_limit_enabled": p.parameters.ai.cost_limit_enabled,
                    "max_observed_cost_usd_per_day": str(
                        p.parameters.ai.max_observed_cost_usd_per_day
                    ),
                },
                "zero_spread_net_target_pct": str(target),
                "zero_spread_net_stop_pct": str(stop),
                "zero_spread_net_target_to_stop_ratio": str(target / abs(stop)),
                "note": "Experimental parameters; public metadata and execution gates "
                "are checked before use. Publication does not start a bot.",
            },
        }

    def register(self, definition: dict, actor: str, now: datetime) -> dict:
        valid = self.validate(definition)
        if valid["definition"]["profile"]["lifecycle_status"] != "DRAFT":
            raise DomainError("Register DRAFT first; publishing is a separate audited operation")
        return self.repository.register_profile(
            valid["definition"], valid["profile_hash"], actor, now
        )

    def transition(
        self, profile_id: str, version: int, action: str, actor: str, now: datetime
    ) -> dict:
        record = self.repository.profile(profile_id, version)
        if record is None:
            raise DomainError("Profile version not found")
        if action == "publish":
            self.validate(record["definition"])
            status = "READY_FOR_PAPER"
        elif action == "archive":
            status = "ARCHIVED"
        else:
            raise DomainError("Unknown profile lifecycle operation")
        return self.repository.transition_profile(profile_id, version, status, actor, now)

    def resolve(
        self, profile_id: str, version: int | None = None
    ) -> tuple[ProfileDefinition, dict]:
        record = self.repository.profile(profile_id, version)
        if record is None or record["status"] != "READY_FOR_PAPER":
            raise DomainError("Choose a published profile revision")
        profile = ProfileDefinition.model_validate(record["definition"])
        if profile.hash != record["profile_hash"]:
            raise DomainError("Profile integrity check failed")
        return profile, record
