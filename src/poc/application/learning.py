"""Mature observations, deduplicate origins and query memory with an explicit cutoff."""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Protocol

from poc.config import Config
from poc.domain.features import rsi_bucket, volume_bucket
from poc.domain.learning import compatible_group, hold_return, net_entry_return, statistics
from poc.domain.models import MarketMetadata
from poc.domain.primitives import canonical_json, decimal, floor_step, iso, stable_id, utc


def learning_protocol(config: Config) -> str:
    return stable_id(
        "labels_v1",
        "indicators_v1",
        "buckets_v1",
        "public_bid_90s_v1",
        "trend_15m_v1",
        config.indicators.model_dump(mode="json"),
        config.strategy.model_dump(mode="json"),
        config.simulation.model_dump(mode="json"),
    )


class LearningStore(Protocol):
    def mark_learning_registration(self, decision_id: str, status: str, reason: str) -> None: ...
    def transaction(self): ...
    def run(self) -> dict: ...
    def quote(self, quote_id: str): ...
    def observations_to_register(self) -> list[dict]: ...
    def save_pending_outcome(self, record: dict) -> None: ...
    def pending_outcomes(self, now: datetime) -> list[dict]: ...
    def first_maturity_quote(self, symbol: str, maturity: datetime, cutoff: datetime): ...
    def finish_outcome(
        self, outcome: dict, now: datetime, core: dict | None, origin: dict | None, reason: str
    ) -> None: ...
    def learning_records(self, cutoff: datetime | None = None) -> list[dict]: ...


class LearningEngine:
    def __init__(self, config: Config, metadata: MarketMetadata, store: LearningStore):
        self.config, self.metadata, self.store = config, metadata, store
        self.protocol = learning_protocol(config)

    def _skip(self, decision_id: str, reason: str) -> None:
        with self.store.transaction():
            self.store.mark_learning_registration(decision_id, "INELIGIBLE", reason)

    def register(self) -> int:
        count = 0
        for decision in self.store.observations_to_register():
            state = decision["state"]
            market = state.get("market", {})
            if (
                not market.get("valid")
                or not decision["decision_price_quote_id"]
                or market.get("volatility_bucket") not in ("low", "medium", "high")
                or (
                    utc(decision["decision_at"]) - utc(decision["candle_close_time"])
                ).total_seconds()
                > self.config.app.max_candle_decision_lag_seconds
            ):
                self._skip(decision["decision_id"], "INVALID_FEATURES_OR_REFERENCE")
                continue
            quote = self.store.quote(decision["decision_price_quote_id"])
            at = utc(decision["decision_at"])
            if (
                not quote
                or utc(quote.observed_at) <= at
                or not quote.fresh(utc(quote.received_at), self.config.app.max_quote_age_seconds)
            ):
                self._skip(decision["decision_id"], "INVALID_REFERENCE_QUOTE")
                continue
            holding = state["portfolio"]["has_position"]
            if decision["approved_action"] not in (
                ("SELL", "HOLD") if holding else ("BUY", "HOLD")
            ):
                self._skip(decision["decision_id"], "INVALID_POSITION_ACTION")
                continue
            position = "holding" if holding else "flat"
            kind = "HOLD_VS_SELL_RETURN" if holding else "ENTRY_LONG_NET_RETURN"
            fee = self.config.simulation.trading_fee_pct_per_side / 100
            slippage = self.config.simulation.slippage_pct_per_side / 100
            portfolio = state["portfolio"]
            if holding:
                quantity = decimal(portfolio["base_qty"])
                budget = None
            else:
                cash = decimal(portfolio["cash_usdt"])
                budget = cash * self.config.strategy.max_allocation_pct / 100
                quantity = floor_step(
                    budget / (1 + fee) / (quote.ask * (1 + slippage)), self.metadata.qty_step
                )
                notional = quantity * quote.ask * (1 + slippage)
                if (
                    quantity < self.metadata.min_qty
                    or quantity > self.metadata.max_qty
                    or notional
                    < max(
                        self.metadata.min_notional_usdt, self.config.market.min_trade_notional_usdt
                    )
                    or (
                        self.metadata.max_notional_usdt is not None
                        and notional > self.metadata.max_notional_usdt
                    )
                ):
                    self._skip(decision["decision_id"], "HYPOTHETICAL_SIZE_TOO_SMALL")
                    continue
            if quantity <= 0:
                self._skip(decision["decision_id"], "NO_QUANTITY")
                continue
            with self.store.transaction():
                for horizon in self.config.learning.evaluation_horizons_bars:
                    maturity = at.replace(
                        minute=at.minute // 15 * 15, second=0, microsecond=0
                    ) + timedelta(minutes=15 * horizon)
                    reference = {
                        "symbol": self.metadata.symbol,
                        "base_asset": self.metadata.base_asset,
                        "quote_asset": self.metadata.quote_asset,
                        "profile_id": "trend_15m_v1",
                        "profile_version": "1",
                        "interval": "15m",
                        "protocol_hash": self.protocol,
                        "feature_version": market.get(
                            "version", market.get("feature_version", "features_v1")
                        ),
                        "label_version": "labels_v1",
                        "equivalence_version": "equivalence_v1",
                        "position_context": position,
                        "label_kind": kind,
                        "horizon_bars": horizon,
                        "decision_at": iso(at),
                        "as_of": state["as_of_utc"],
                        "maturity_time": iso(maturity),
                        "features": market,
                        "market_regime": market["market_regime"],
                        "rsi_bucket": rsi_bucket(market["rsi_14"]),
                        "volume_bucket": volume_bucket(market["volume_ratio"]),
                        "volatility_bucket": market.get(
                            "volatility_bucket", market.get("volatility_regime", "unknown")
                        ),
                        "reference_quote": asdict(quote),
                        "quantity": str(quantity),
                        "reference_budget_usdt": str(budget) if budget is not None else None,
                        "fee_fraction": str(fee),
                        "slippage_fraction": str(slippage),
                        "fixture": bool(self.store.run()["market_metadata"]["raw"].get("fixture")),
                    }
                    self.store.save_pending_outcome(
                        {
                            "outcome_id": stable_id("outcome", decision["decision_id"], horizon),
                            "decision_id": decision["decision_id"],
                            "horizon_bars": horizon,
                            "label_kind": kind,
                            "maturity_time": iso(maturity),
                            "reference_json": canonical_json(reference),
                        }
                    )
                    count += 1
                self.store.mark_learning_registration(
                    decision["decision_id"], "REGISTERED", "PENDING_HORIZONS"
                )
        return count

    def mature(self, now: datetime) -> int:
        self.register()
        completed = 0
        for outcome in self.store.pending_outcomes(now):
            reference = outcome["reference"]
            maturity = utc(outcome["maturity_time"])
            quote = self.store.first_maturity_quote(reference["symbol"], maturity, now)
            if quote is None and utc(now) < maturity + timedelta(seconds=90):
                continue
            core, origin = None, None
            if quote:
                current = reference["reference_quote"]
                fee, slip = (
                    decimal(reference["fee_fraction"]),
                    decimal(reference["slippage_fraction"]),
                )
                result = (
                    net_entry_return(decimal(current["ask"]), quote.bid, fee, slip)
                    if outcome["label_kind"] == "ENTRY_LONG_NET_RETURN"
                    else hold_return(decimal(current["bid"]), quote.bid, fee, slip)
                )
                # The economic example excludes source identity; all eligible origins are retained.
                core = {**reference, "exit_quote": asdict(quote), "return_pct": str(result)}
                core["sample_id"] = stable_id("equivalence_v1", core)
                origin = {
                    "origin_id": stable_id(
                        "origin",
                        self.store.run()["run_id"],
                        outcome["decision_id"],
                        outcome["horizon_bars"],
                    ),
                    "origin_run_id": self.store.run()["run_id"],
                    "decision_id": outcome["decision_id"],
                    "portfolio_id": outcome["portfolio_id"],
                    "matured_at": iso(now),
                    "available_at": iso(now),
                    "code_version": self.store.run()["code_version"],
                    "config_hash": self.store.run()["config_hash"],
                    "template_version": self.store.run()["template_version"],
                    "protocol_parameters": {
                        "indicators": self.config.indicators.model_dump(mode="json"),
                        "strategy": self.config.strategy.model_dump(mode="json"),
                        "simulation": self.config.simulation.model_dump(mode="json"),
                    },
                }
            with self.store.transaction():
                self.store.finish_outcome(
                    outcome, now, core, origin, "MATURED" if quote else "NO_BID_IN_90S_WINDOW"
                )
            completed += 1
        return completed

    def feedback(
        self, state: dict[str, Any], cutoff: datetime, cycle_id: str | None = None
    ) -> dict:
        base = {
            "learning_version": "memory_v1",
            "source_cutoff_at": iso(cutoff),
            "primary_horizon_bars": 4,
            "patterns": [],
        }
        if not self.config.learning.enabled:
            return {**base, "status": "disabled"}
        holding = state["portfolio"]["has_position"]
        market = state["market"]
        context = {
            "symbol": state["symbol"],
            "position_context": "holding" if holding else "flat",
            "label_kind": "HOLD_VS_SELL_RETURN" if holding else "ENTRY_LONG_NET_RETURN",
            "market_regime": market.get("market_regime"),
            "rsi_bucket": rsi_bucket(market["rsi_14"])
            if market.get("rsi_14") is not None
            else None,
            "volume_bucket": volume_bucket(market["volume_ratio"])
            if market.get("volume_ratio") is not None
            else None,
            "volatility_bucket": market.get(
                "volatility_bucket", market.get("volatility_regime", "unknown")
            ),
        }
        records = self.store.learning_records(cutoff)
        after = utc(cutoff) - timedelta(days=60)
        eligible = [
            row
            for row in records
            if row["core"]["protocol_hash"] == self.protocol
            and not row["core"]["fixture"]
            and after <= utc(row["core"]["decision_at"]) < utc(cutoff)
        ]
        for horizon in self.config.learning.evaluation_horizons_bars:
            required = {**context, "horizon_bars": horizon}
            coarse = [
                row
                for row in eligible
                if compatible_group(row["core"], required)
                and row["core"]["market_regime"] == required["market_regime"]
            ]
            exact = [
                row
                for row in coarse
                if all(
                    row["core"][key] == required[key]
                    for key in ("rsi_bucket", "volume_bucket", "volatility_bucket")
                )
            ]
            level, rows = (
                ("exact", exact)
                if len(exact) >= self.config.learning.min_exact_pattern_samples
                else ("regime", coarse)
            )
            minimum = (
                self.config.learning.min_exact_pattern_samples
                if level == "exact"
                else self.config.learning.min_coarse_pattern_samples
            )
            if len(rows) < minimum:
                continue
            summary = statistics([decimal(row["core"]["return_pct"]) for row in rows])
            source_hash = stable_id(sorted(row["core"]["sample_id"] for row in rows))
            key = {**required}
            if level == "regime":
                for field in ("rsi_bucket", "volume_bucket", "volatility_bucket"):
                    key.pop(field)
            base["patterns"].append(
                {
                    **summary,
                    **key,
                    "source_scope": "LOCAL",
                    "run_id": self.store.run()["run_id"],
                    "aggregation_level": level,
                    "pattern_version": "memory_v1",
                    "pattern_id": stable_id(self.store.run()["run_id"], key, level),
                    "source_query_hash": source_hash,
                    "source_cutoff_at": iso(cutoff),
                    "data_window_start": min(row["core"]["decision_at"] for row in rows),
                    "data_window_end": max(row["core"]["decision_at"] for row in rows),
                    "min_matured_at": min(o["matured_at"] for row in rows for o in row["origins"]),
                    "max_matured_at": max(o["matured_at"] for row in rows for o in row["origins"]),
                }
            )
        base["patterns"] = base["patterns"][: self.config.learning.max_memory_items]
        return {**base, "status": "available" if base["patterns"] else "insufficient_samples"}
