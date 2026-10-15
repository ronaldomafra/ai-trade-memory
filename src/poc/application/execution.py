from dataclasses import asdict, dataclass, replace
from datetime import datetime

from poc.application.ports import SessionStore
from poc.config import Config
from poc.domain.broker import PaperBroker
from poc.domain.execution_quality import quality_reason
from poc.domain.models import Action, Fill, MarketMetadata, Quote, Wallet
from poc.domain.primitives import DomainError, stable_id, utc
from poc.domain.profiles import entry_window_open, parameters
from poc.domain.risk import evaluate_risk


@dataclass(frozen=True)
class TradeIntent:
    portfolio_id: str
    action: Action
    request_id: str
    cycle_id: str
    decision_started_at: datetime
    decision_finished_at: datetime
    candle_close_at: datetime | None = None
    decision_id: str | None = None
    record_marks: bool = True
    entries_allowed: bool = True
    hold_reason: str | None = None
    proposed_action: Action | None = None
    entry_reference_quote: Quote | None = None
    forced_exit_reason: str | None = None

    @property
    def fingerprint(self) -> str:
        if self.proposed_action is not None:
            return stable_id(self.portfolio_id, self.action, self.cycle_id, self.proposed_action)
        return stable_id(self.portfolio_id, self.action, self.cycle_id)


@dataclass(frozen=True)
class Execution:
    proposed_action: Action
    approved_action: Action
    executed_action: Action
    reason_code: str
    wallet: Wallet
    fill: Fill | None = None
    duplicate: bool = False


class TradingService:
    def __init__(self, config: Config, metadata: MarketMetadata, store: SessionStore):
        self.config = config
        self.metadata = metadata
        self.store = store
        self.broker = PaperBroker(
            config.strategy, config.simulation, config.market.min_trade_notional_usdt
        )

    def execute(
        self, intent: TradeIntent, quote: Quote | None, now: datetime, holding_bars: int = 0
    ) -> Execution:
        now = utc(now)
        key = stable_id(intent.portfolio_id, intent.request_id)
        proposed = intent.proposed_action or intent.action
        with self.store.transaction() as unit:
            wallet = unit.wallet(intent.portfolio_id)
            previous = unit.command(key)
            if previous:
                if previous["fingerprint"] != intent.fingerprint:
                    raise DomainError("Idempotency key used for a conflicting intent")
                if intent.decision_id and previous.get("decision_id") != intent.decision_id:
                    raise DomainError("Idempotency key linked to a conflicting decision")
                fill = previous["fill"]
                actual = fill.side if fill else Action.HOLD
                return Execution(proposed, actual, actual, previous["reason"], wallet, fill, True)
            matching = quote is not None and quote.symbol == self.metadata.symbol
            fresh = matching and quote.fresh(now, self.config.app.max_quote_age_seconds)
            if matching:
                unit.save_quote(quote)
            risk = evaluate_risk(
                wallet,
                unit.latest_risk(wallet.portfolio_id),
                quote if fresh else None,
                now,
                holding_bars,
                self.config.strategy,
                self.config.app.max_quote_age_seconds,
            )
            if intent.forced_exit_reason and wallet.has_position and not risk.exit_reason:
                risk = replace(
                    risk,
                    state=replace(risk.state, pending_exit_reason=intent.forced_exit_reason),
                    exit_reason=intent.forced_exit_reason,
                    block_buy=True,
                )
            unit.save_risk(risk.state)
            for kind in risk.events:
                unit.event(
                    kind,
                    asdict(risk.state),
                    now,
                    stable_id(kind, wallet.portfolio_id, risk.state.day_utc),
                    wallet.portfolio_id,
                    intent.cycle_id,
                )
            action = Action.SELL if risk.exit_reason else intent.action
            trigger = risk.exit_reason or (
                "STRATEGY_BUY" if action == Action.BUY else "STRATEGY_SELL"
            )
            reason = intent.hold_reason or "HOLD"
            if action != Action.HOLD:
                reason = self._gate(
                    intent, wallet, quote, now, fresh, risk.block_buy, risk.exit_reason is not None
                )
                if reason == "APPROVED":
                    try:
                        trade = (
                            self.broker.buy(
                                wallet, self.metadata, quote, now, key, intent.cycle_id, trigger
                            )
                            if action == Action.BUY
                            else self.broker.sell(wallet, quote, now, key, intent.cycle_id, trigger)
                        )
                    except DomainError as exc:
                        reason = str(exc)
                    else:
                        unit.record_trade(trade, intent.fingerprint)
                        if action == Action.SELL:
                            unit.save_risk(replace(risk.state, pending_exit_reason=None))
                        if intent.decision_id:
                            unit.complete_decision(
                                intent.decision_id,
                                proposed.value,
                                action.value,
                                action.value,
                                trigger,
                                quote.quote_id,
                                trade.fill.order_id,
                            )
                        marked = unit.mark(trade.wallet, quote, now)
                        return Execution(proposed, action, action, trigger, marked, trade.fill)
                unit.reject(
                    wallet.portfolio_id,
                    action.value,
                    key,
                    intent.fingerprint,
                    intent.cycle_id,
                    reason,
                    now,
                )
            if fresh:
                wallet = unit.mark(wallet, quote, now, persist=intent.record_marks)
            if intent.decision_id:
                unit.complete_decision(
                    intent.decision_id,
                    proposed.value,
                    "HOLD",
                    "HOLD",
                    reason,
                    quote.quote_id if fresh else None,
                    stable_id("order", key) if action != Action.HOLD else None,
                )
            return Execution(proposed, Action.HOLD, Action.HOLD, reason, wallet)

    def _gate(
        self,
        intent: TradeIntent,
        wallet: Wallet,
        quote: Quote | None,
        now: datetime,
        fresh: bool,
        blocked: bool,
        forced: bool,
    ) -> str:
        if quote is not None and quote.symbol != self.metadata.symbol:
            return "INVALID_SYMBOL"
        if not fresh:
            return "STALE_QUOTE"
        if not forced:
            started, finished = utc(intent.decision_started_at), utc(intent.decision_finished_at)
            if started > finished or finished > now:
                return "INVALID_DECISION_TIME"
            if utc(quote.observed_at) <= finished:
                return "QUOTE_NOT_AFTER_DECISION"
            deadline_origin = utc(intent.candle_close_at) if intent.candle_close_at else started
            if deadline_origin > started:
                return "INVALID_DECISION_TIME"
            if intent.action == Action.BUY and (now - deadline_origin).total_seconds() > (
                self.config.app.max_candle_decision_lag_seconds
            ):
                return "STALE_DECISION"
        if intent.action == Action.BUY and not forced:
            if not intent.entries_allowed:
                return "ENTRIES_DISABLED"
            if blocked:
                return "DAILY_RISK_BLOCKED"
            if wallet.last_exit_cycle_id == intent.cycle_id:
                return "CLOSED_IN_SAME_CYCLE"
            p = parameters(self.config)
            if p:
                if not entry_window_open(self.config, now):
                    return "ENTRY_WINDOW_CLOSED"
                if any(
                    (
                        self.store.latest_risk(w.portfolio_id)
                        and self.store.latest_risk(w.portfolio_id).pending_exit_reason
                    )
                    for w in self.store.wallets()
                ):
                    return "SESSION_EXIT_PENDING"
                if wallet.entry_at is not None:
                    return "ALREADY_IN_POSITION"
                previous_exit = self.store.last_exit_at(wallet.portfolio_id)
                from poc.domain.profiles import seconds

                if previous_exit and (
                    now - previous_exit
                ).total_seconds() < p.strategy.reentry_cooldown_candles * seconds(self.config):
                    return "REENTRY_COOLDOWN"
                if intent.entry_reference_quote is None:
                    return "ENTRY_REFERENCE_UNAVAILABLE"
                reason = quality_reason(
                    self.config, wallet, self.metadata, quote, now, intent.entry_reference_quote
                )
                if reason:
                    return reason
        return "APPROVED"
