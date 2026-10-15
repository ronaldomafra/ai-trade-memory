"""One persistent cycle per closed candle; risk monitoring remains independent."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta

from poc.application.execution import TradeIntent, TradingService
from poc.application.ports import (
    Clock,
    ContextPort,
    DecisionPolicy,
    LearningPort,
    MarketPort,
    SessionStore,
)
from poc.config import Config
from poc.domain.candles import Candle
from poc.domain.execution_quality import quality_reason
from poc.domain.features import FeatureEngine
from poc.domain.models import Action, MarketMetadata, PortfolioKind, Proposal
from poc.domain.primitives import iso, stable_id, utc
from poc.domain.profiles import (
    age_bars,
    entry_window_open,
    parameters,
    seconds,
    strategy_context,
    structural_setup,
)
from poc.domain.technical import technical_signal


def cycle_identity(run_id: str, candle: Candle) -> str:
    return stable_id(run_id, candle.symbol, candle.interval, iso(candle.open_time))


def holding_bars(entry_at: datetime | None, now: datetime) -> int:
    if entry_at is None:
        return 0
    return max(0, int(utc(now).timestamp()) // 900 - int(utc(entry_at).timestamp()) // 900)


class CycleCoordinator:
    def __init__(
        self,
        config: Config,
        metadata: MarketMetadata,
        store: SessionStore,
        source: MarketPort,
        clock: Clock,
        stop: asyncio.Event,
        policy: DecisionPolicy | None = None,
        learning: LearningPort | None = None,
        context: ContextPort | None = None,
    ):
        self.config, self.metadata, self.store = config, metadata, store
        self.source, self.clock, self.stop, self.policy = source, clock, stop, policy
        self.learning = learning
        self.context = context
        self.profile = parameters(config)
        self.feature_engine = FeatureEngine(config.indicators, self.profile)
        self.trading = TradingService(config, metadata, store)
        self.active_cycle_id: str | None = None
        self.lock = asyncio.Lock()
        self.entries_allowed = True
        self.quote_clock_valid = True

    async def process(self, candle: Candle) -> bool:
        if (
            not candle.is_closed
            or candle.interval != self.config.market.interval
            or candle.symbol != self.metadata.symbol
        ):
            return False
        async with self.lock:
            cycle_id = cycle_identity(self.store.run()["run_id"], candle)
            if self.store.cycle(cycle_id) is not None:
                return False
            started = self.clock.now()
            if self.learning:
                self.learning.mature(started)
            if utc(candle.close_time_exclusive) > utc(started):
                return False
            features = self.feature_engine.build(
                candle.symbol,
                self.store.candles(
                    candle.symbol,
                    self.config.market.interval,
                    self.config.market.warmup_15m_candles,
                ),
                self.store.candles(
                    candle.symbol,
                    self.config.market.trend_interval,
                    self.profile.market.warmup_candles.trend if self.profile else 1000,
                ),
                started,
            )
            wallets = self.store.wallets()
            reference_quote = None
            if self.profile:
                admitted, reason = self._candidate(features, wallets, started)
                if admitted:
                    try:
                        reference_quote = await self.source.quote(candle.symbol)
                        flat = next((w for w in wallets if not w.has_position), wallets[0])
                        reason = quality_reason(
                            self.config, flat, self.metadata, reference_quote, self.clock.now()
                        )
                        if any(w.has_position for w in wallets):
                            reason = None  # Checkpoints must not depend on entry cost viability.
                        admitted = reason is None
                    except Exception:
                        admitted, reason = False, "REFERENCE_QUOTE_UNAVAILABLE"
                with self.store.transaction():
                    if not self._admit(cycle_id, started, admitted, reason):
                        return False
                    if reference_quote:
                        self.store.save_quote(reference_quote)
                started = self.clock.now()
            with self.store.transaction():
                if not self.store.start_cycle(cycle_id, candle, started, features.state(), wallets):
                    return False
                self.store.event(
                    "FEATURES_READY",
                    {"valid": features.valid, "reason": features.reason},
                    started,
                    stable_id("features", cycle_id),
                    cycle_id=cycle_id,
                )
            self.active_cycle_id = cycle_id
            try:
                states = {
                    wallet.portfolio_id: {
                        "symbol": candle.symbol,
                        "base_asset": self.metadata.base_asset,
                        "quote_asset": self.metadata.quote_asset,
                        "interval": self.config.market.interval,
                        "as_of_utc": iso(started),
                        "portfolio": {
                            "has_position": wallet.has_position,
                            "cash_usdt": str(wallet.cash_usdt),
                            "base_qty": str(wallet.base_qty),
                            "base_cost_basis_usdt": str(wallet.base_cost_basis_usdt),
                            "entry_fill_price": str(wallet.entry_fill_price)
                            if wallet.entry_fill_price
                            else None,
                            "position_age_candles": age_bars(self.config, wallet.entry_at, started),
                        },
                        "market": features.state(),
                        "news": {"status": "unavailable", "items": []},
                        "prediction_markets": {"status": "unavailable", "items": []},
                        "historical_feedback": {"status": "disabled"},
                    }
                    for wallet in wallets
                }
                if self.profile:
                    for wallet in wallets:
                        state = states[wallet.portfolio_id]
                        state["strategy_context"] = strategy_context(self.config, features, started)
                        state["strategy_context"]["reference_quote"] = (
                            {
                                "quote_id": reference_quote.quote_id,
                                "ask": str(reference_quote.ask),
                                "bid": str(reference_quote.bid),
                                "observed_at": iso(reference_quote.observed_at),
                            }
                            if reference_quote
                            else None
                        )
                        state["strategy_context"]["position_remaining_seconds"] = (
                            max(
                                0,
                                self.config.strategy.max_holding_candles * seconds(self.config)
                                - int((started - wallet.entry_at).total_seconds()),
                            )
                            if wallet.entry_at
                            else None
                        )
                if self.learning:
                    key = PortfolioKind.LEARNING
                    states[key]["historical_feedback"] = self.learning.feedback(
                        states[key], started, cycle_id
                    )
                if self.context:
                    context = self.context.snapshot(started)
                    for key in (PortfolioKind.STATIC, PortfolioKind.LEARNING):
                        states[key]["news"] = context["news"]
                        states[key]["prediction_markets"] = context["prediction_markets"]
                deadline = candle.close_time_exclusive + timedelta(
                    seconds=self.config.app.max_candle_decision_lag_seconds
                )
                elapsed = utc(started) > utc(deadline)
                technical = technical_signal(
                    features, wallets[0].has_position, self.config.strategy.technical, True
                )
                proposals: dict[str, Proposal] = {
                    PortfolioKind.TECHNICAL: Proposal(technical.action, technical.reason),
                    PortfolioKind.STATIC: Proposal(Action.HOLD, "AI_NOT_CONFIGURED"),
                    PortfolioKind.LEARNING: Proposal(Action.HOLD, "AI_NOT_CONFIGURED"),
                }
                if not features.valid or elapsed:
                    reason = "STALE_DECISION" if elapsed else "INVALID_FEATURES"
                    proposals = {w.portfolio_id: Proposal(Action.HOLD, reason) for w in wallets}
                    if elapsed:
                        with self.store.transaction():
                            self.store.event(
                                "MISSED_DECISION_WINDOW",
                                {"reason": reason},
                                started,
                                stable_id("missed", cycle_id),
                                cycle_id=cycle_id,
                            )
                elif self.policy is not None and not self.stop.is_set():
                    ai_states = {
                        key: value
                        for key, value in states.items()
                        if key != PortfolioKind.TECHNICAL
                    }
                    try:
                        replies = await asyncio.wait_for(
                            self.policy.propose(cycle_id, ai_states, deadline),
                            timeout=max(
                                0.001, (utc(deadline) - utc(self.clock.now())).total_seconds()
                            ),
                        )
                        for key in ai_states:
                            proposals[key] = replies.get(
                                key, Proposal(Action.HOLD, "INVALID_AI_RESPONSE")
                            )
                    except TimeoutError:
                        for key in ai_states:
                            proposals[key] = Proposal(Action.HOLD, "AI_TIMEOUT")
                    except Exception as exc:
                        for key in ai_states:
                            proposals[key] = Proposal(Action.HOLD, "AI_FAILURE")
                        self._error("AI_FAILURE", exc, cycle_id)
                # Until E05 supplies eligible factors or a verified empty query scope,
                # unavailable sources cannot substantiate a new AI entry.
                for wallet in wallets:
                    if self.profile and proposals[wallet.portfolio_id].action == Action.BUY:
                        reject = None
                        if not structural_setup(features):
                            reject = "STRUCTURAL_SETUP_REQUIRED"
                        elif not entry_window_open(self.config, self.clock.now()):
                            reject = "ENTRY_WINDOW_CLOSED"
                        if reject:
                            proposal = proposals[wallet.portfolio_id]
                            proposals[wallet.portfolio_id] = replace(
                                proposal,
                                proposed_action=proposal.proposed_action or proposal.action,
                                action=Action.HOLD,
                                reason=reject,
                            )
                    if wallet.portfolio_id != PortfolioKind.TECHNICAL and not wallet.has_position:
                        key = wallet.portfolio_id
                        if proposals[key].action == Action.BUY and all(
                            states[key][source]["status"] == "unavailable"
                            for source in ("news", "prediction_markets")
                        ):
                            proposals[key] = replace(
                                proposals[key],
                                proposed_action=proposals[key].proposed_action
                                or proposals[key].action,
                                action=Action.HOLD,
                                reason="EXTERNAL_CONTEXT_UNAVAILABLE",
                            )
                finished = self.clock.now()
                if self.stop.is_set():
                    proposals = {
                        w.portfolio_id: Proposal(Action.HOLD, "SERVICE_STOPPING") for w in wallets
                    }
                quote = None
                if not self.stop.is_set() and self.quote_clock_valid:
                    try:
                        quote = await self.source.quote(candle.symbol)
                    except Exception as exc:
                        self._error("QUOTE_FETCH_FAILED", exc, cycle_id)
                for wallet in wallets:
                    proposal = proposals[wallet.portfolio_id]
                    with self.store.transaction():
                        decision_id = self.store.save_proposal(
                            cycle_id,
                            wallet,
                            proposal,
                            started,
                            finished,
                            states[wallet.portfolio_id],
                        )
                    if self.stop.is_set():
                        with self.store.transaction():
                            self.store.complete_decision(
                                decision_id, "HOLD", "HOLD", "HOLD", "SERVICE_STOPPING", None
                            )
                        continue
                    intent = TradeIntent(
                        wallet.portfolio_id,
                        proposal.action,
                        "decision-" + decision_id,
                        cycle_id,
                        started,
                        finished,
                        candle.close_time_exclusive,
                        decision_id,
                        entries_allowed=self.entries_allowed,
                        hold_reason=proposal.reason if proposal.action == Action.HOLD else None,
                        proposed_action=proposal.proposed_action,
                        entry_reference_quote=reference_quote,
                    )
                    self.trading.execute(
                        intent,
                        quote,
                        self.clock.now(),
                        age_bars(
                            self.config,
                            self.store.wallet(wallet.portfolio_id).entry_at,
                            self.clock.now(),
                        ),
                    )
                with self.store.transaction():
                    self.store.finish_cycle(cycle_id, self.clock.now())
                if self.learning:
                    self.learning.register()
                return True
            except BaseException:
                with self.store.transaction():
                    self.store.finish_cycle(cycle_id, self.clock.now(), "INTERRUPTED")
                raise
            finally:
                self.active_cycle_id = None

    def _candidate(self, features, wallets, now):
        if not features.valid:
            return False, "INVALID_FEATURES"
        if any(w.has_position for w in wallets):
            return True, None
        if not self.entries_allowed or not entry_window_open(self.config, now):
            return False, "ENTRY_WINDOW_CLOSED"
        opportunity = self.profile.opportunities
        if opportunity.mode == "LOCAL_SETUP_OR_POSITION_CHECKPOINT" and not (
            structural_setup(features)
            and opportunity.candidate_rsi_min <= features.rsi_14 <= opportunity.candidate_rsi_max
            and features.volume_ratio >= opportunity.candidate_min_relative_volume
        ):
            return False, "LOCAL_SETUP_FILTERED"
        return True, None

    def _admit(self, cycle_id, now, eligible, reason):
        previous = self.store.runtime_state("profile_admission") or {}
        if previous.get("last_candle_id") == cycle_id:
            return False
        day = utc(now).date().isoformat()
        state = (
            previous
            if previous.get("day_utc") == day
            else {
                "day_utc": day,
                "admitted": 0,
                "filtered": 0,
                "last_admitted_at": previous.get("last_admitted_at"),
            }
        )
        p = self.profile.opportunities
        if (
            state.get("last_admitted_at")
            and (utc(now) - utc(state["last_admitted_at"])).total_seconds()
            < p.minimum_cycle_spacing_seconds
        ):
            eligible, reason = False, "CYCLE_SPACING_LIMIT"
        if state["admitted"] >= p.max_cycles_per_day_utc:
            eligible, reason = False, "DAILY_CYCLE_LIMIT"
        state = {**state, "last_candle_id": cycle_id}
        if eligible:
            state["admitted"] += 1
            state["last_admitted_at"] = iso(now)
        else:
            state["filtered"] += 1
        self.store.runtime_state("profile_admission", state)
        self.store.event(
            "OPPORTUNITY_ADMITTED" if eligible else "OPPORTUNITY_FILTERED",
            {"reason": reason, **state},
            now,
            stable_id("admission", cycle_id),
        )
        return eligible

    def _error(self, code: str, error: Exception, cycle_id: str) -> None:
        with self.store.transaction():
            self.store.event(
                "ERROR",
                {"code": code, "error_type": type(error).__name__},
                self.clock.now(),
                stable_id("error", cycle_id, code),
                cycle_id=cycle_id,
            )
