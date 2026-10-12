"""Continuous market supervision; no dependency on a presentation client."""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from poc.application.execution import TradeIntent
from poc.application.market_state import prefer_quote
from poc.application.orchestrator import CycleCoordinator, cycle_identity, holding_bars
from poc.application.ports import (
    Clock,
    ContextPort,
    DecisionPolicy,
    LearningPort,
    MarketPort,
    SessionStore,
)
from poc.config import Config
from poc.domain.candles import Candle, closed_sequence
from poc.domain.models import Action, MarketMetadata, MarketNotice, Quote
from poc.domain.primitives import DomainError, iso, stable_id, utc


class LiveEngine:
    def __init__(
        self,
        config: Config,
        metadata: MarketMetadata,
        store: SessionStore,
        source: MarketPort,
        clock: Clock,
        policy: DecisionPolicy | None = None,
        learning: LearningPort | None = None,
        context: ContextPort | None = None,
    ):
        self.config, self.metadata, self.store = config, metadata, store
        self.source, self.clock = source, clock
        self.stop = asyncio.Event()
        self.coordinator = CycleCoordinator(
            config, metadata, store, source, clock, self.stop, policy, learning, context
        )
        self.latest_quote: Quote | None = None
        self.last_ws_update: int | None = None
        self.ws_connected = False
        self.live_after: datetime | None = None
        self.queue: asyncio.Queue[Candle] = asyncio.Queue(maxsize=8)
        self.history_lock = asyncio.Lock()
        self.recovery_needed = False
        self.status = "STARTING"
        self.last_error: str | None = None
        self.last_cycle_at: datetime | None = None
        self.last_heartbeat: datetime | None = None
        self.last_risk_at: datetime | None = None
        self.last_mark_at: datetime | None = None
        self.last_poll_close: datetime | None = None
        self.clock_status = "UNVERIFIED"
        self.clock_offset_seconds: float | None = None
        self.startup_complete = asyncio.Event()
        self.instance_id = uuid4().hex
        self.event_counter = 0

    def request_stop(self) -> None:
        if self.status != "STOPPED":
            self.status = "STOPPING"
        self.stop.set()

    async def initialize(self) -> None:
        with self.store.transaction():
            self.store.recover_cycles(self.clock.now())
            self.store.set_run_status("STARTING", self.clock.now())
            self._event(
                "SERVICE_STARTED", {"ai_policy_enabled": self.coordinator.policy is not None}
            )
        await self.recover_history()
        try:
            await self.accept_quote(await self.source.quote(self.metadata.symbol), force=True)
        except Exception as exc:
            self.error("STARTUP_QUOTE_UNAVAILABLE", exc)
        self.live_after = self.clock.now()
        self.last_poll_close = self._closed_boundary(self.clock.now())
        self.status = "RUNNING"
        with self.store.transaction():
            self.store.set_run_status("RUNNING", self.clock.now())
        await self.heartbeat()
        self.startup_complete.set()

    async def recover_history(self) -> None:
        async with self.history_lock:
            bars, hours = await asyncio.gather(
                self.source.candles(
                    self.metadata.symbol, "15m", self.config.market.warmup_15m_candles
                ),
                self.source.candles(
                    self.metadata.symbol, "1h", max(200, self.config.indicators.ema_mid + 1)
                ),
            )
            with self.store.transaction():
                for candle in [*bars, *hours]:
                    self.store.save_candle(candle)
                self._event(
                    "MARKET_HISTORY_LOADED",
                    {
                        "bars_15m": len(bars),
                        "bars_1h": len(hours),
                        "retroactive_trades": False,
                    },
                )
            self.recovery_needed = False

    async def accept_quote(self, incoming: Quote, force: bool = False) -> bool:
        if incoming.symbol != self.metadata.symbol or not incoming.fresh(
            self.clock.now(), self.config.app.max_quote_age_seconds
        ):
            return False
        if incoming.update_id is not None:
            if self.last_ws_update is not None and incoming.update_id <= self.last_ws_update:
                return False
            self.last_ws_update = incoming.update_id
        original = self.store.quote(incoming.quote_id)
        if original is not None:
            incoming = original
        preferred = prefer_quote(self.latest_quote, incoming)
        if preferred is self.latest_quote:
            return False
        self.latest_quote = preferred
        now = self.clock.now()
        if force or self.last_risk_at is None or (now - self.last_risk_at).total_seconds() >= 1:
            self.last_risk_at = now
            await self.monitor_risk()
        return True

    async def monitor_risk(self) -> None:
        if self.stop.is_set():
            return
        now = self.clock.now()
        quote = None if self.clock_status == "DRIFT" else self.latest_quote
        cycle_id = self.coordinator.active_cycle_id or stable_id(
            self.store.run()["run_id"],
            self.metadata.symbol,
            "15m",
            iso(self._closed_boundary(now) - timedelta(minutes=15)),
        )
        mark = self.last_mark_at is None or (now - self.last_mark_at).total_seconds() >= 60
        for wallet in self.store.wallets():
            self.coordinator.trading.execute(
                TradeIntent(
                    wallet.portfolio_id,
                    Action.HOLD,
                    "risk-" + (quote.quote_id if quote else iso(now)),
                    cycle_id,
                    now,
                    now,
                    record_marks=mark,
                    hold_reason="RISK_MONITOR",
                ),
                quote,
                now,
                holding_bars(wallet.entry_at, now),
            )
        if mark:
            self.last_mark_at = now
        if self.coordinator.learning:
            self.coordinator.learning.mature(now)

    async def accept_candle(self, candle: Candle) -> bool:
        if candle.symbol != self.metadata.symbol or not candle.is_closed:
            return False
        with self.store.transaction():
            new = self.store.save_candle(candle)
            if new:
                self.store.event(
                    "CANDLE_CLOSED",
                    {
                        "symbol": candle.symbol,
                        "interval": candle.interval,
                        "open_time": iso(candle.open_time),
                        "close_time": iso(candle.close_time_exclusive),
                    },
                    self.clock.now(),
                    stable_id("candle", candle.symbol, candle.interval, iso(candle.open_time)),
                )
        if candle.interval != "15m" or not new or self.live_after is None:
            return False
        if candle.close_time_exclusive <= self.live_after:
            return False
        cycle_id = cycle_identity(self.store.run()["run_id"], candle)
        late = (self.clock.now() - candle.close_time_exclusive).total_seconds() > (
            self.config.app.max_candle_decision_lag_seconds
        )
        if late:
            with self.store.transaction():
                self.store.event(
                    "MISSED_DECISION_WINDOW",
                    {"reason": "LATE_CANDLE"},
                    self.clock.now(),
                    stable_id("late-candle", cycle_id),
                )
            return False
        try:
            self.queue.put_nowait(candle)
            return True
        except asyncio.QueueFull:
            with self.store.transaction():
                self.store.event(
                    "MISSED_DECISION_WINDOW",
                    {"reason": "CYCLE_QUEUE_FULL"},
                    self.clock.now(),
                    stable_id("queue-full", cycle_id),
                )
            return False

    async def stream_loop(self) -> None:
        async for event in self.source.stream(self.metadata.symbol, self.stop):
            if self.stop.is_set():
                break
            try:
                if isinstance(event, Quote):
                    await self.accept_quote(event)
                elif isinstance(event, Candle):
                    await self.accept_candle(event)
                elif isinstance(event, MarketNotice):
                    if event.kind in ("CONNECTED", "DISCONNECTED"):
                        self.ws_connected = event.kind == "CONNECTED"
                    if self.ws_connected and self.live_after is not None:
                        self.recovery_needed = True
                    with self.store.transaction():
                        self._event("MARKET_STREAM_" + event.kind, {"reason": event.reason})
            except Exception as exc:
                self.recovery_needed = True
                self.error("MARKET_STREAM_DATA_REJECTED", exc)

    async def polling_loop(self) -> None:
        while not self.stop.is_set():
            try:
                now = self.clock.now()
                if self.recovery_needed:
                    await self.recover_history()
                if (
                    not self.ws_connected
                    or self.latest_quote is None
                    or not self.latest_quote.fresh(now, self.config.app.max_quote_age_seconds)
                ):
                    await self.accept_quote(
                        await self.source.quote(self.metadata.symbol), force=True
                    )
                boundary = self._closed_boundary(now)
                if self.last_poll_close is None or boundary > self.last_poll_close:
                    bars, hours = await asyncio.gather(
                        self.source.candles(self.metadata.symbol, "15m", 3),
                        self.source.candles(self.metadata.symbol, "1h", 3),
                    )
                    for candle in hours + bars:
                        await self.accept_candle(candle)
                    self.last_poll_close = boundary
                if self.latest_quote is None or not self.latest_quote.fresh(
                    self.clock.now(), self.config.app.max_quote_age_seconds
                ):
                    await self.monitor_risk()
            except Exception as exc:
                self.error("MARKET_POLL_FAILED", exc)
                await self.monitor_risk()
            await self._wait(self.config.app.poll_seconds)

    async def cycle_loop(self) -> None:
        while not self.stop.is_set():
            try:
                candle = await asyncio.wait_for(self.queue.get(), timeout=1)
            except TimeoutError:
                continue
            try:
                try:
                    closed_sequence(
                        self.store.candles(self.metadata.symbol, "15m"),
                        self.metadata.symbol,
                        "15m",
                        self.clock.now(),
                    )
                except DomainError:
                    with self.store.transaction():
                        self._event("MARKET_DATA_GAP", {"interval": "15m"})
                    await self.recover_history()
                hour_boundary = candle.close_time_exclusive.replace(
                    minute=0, second=0, microsecond=0
                )
                hours = self.store.candles(self.metadata.symbol, "1h", 1)
                if not hours or hours[-1].close_time_exclusive < hour_boundary:
                    for hour in await self.source.candles(self.metadata.symbol, "1h", 3):
                        with self.store.transaction():
                            self.store.save_candle(hour)
                if await self.coordinator.process(candle):
                    self.last_cycle_at = self.clock.now()
            except Exception as exc:
                self.recovery_needed = True
                self.error("CYCLE_FAILED", exc)
            finally:
                self.queue.task_done()

    async def heartbeat(self) -> None:
        now = self.clock.now()
        try:
            provider_time = await self.source.server_time()
            self.clock_offset_seconds = (utc(provider_time) - utc(self.clock.now())).total_seconds()
            self.clock_status = "DRIFT" if abs(self.clock_offset_seconds) > 30 else "VERIFIED"
        except Exception:
            if self.clock_status != "DRIFT":
                self.clock_status = "UNVERIFIED"
        self.coordinator.entries_allowed = self.clock_status != "DRIFT"
        self.coordinator.quote_clock_valid = self.clock_status != "DRIFT"
        self.last_heartbeat = now
        with self.store.transaction():
            self.store.runtime_state("engine", self.health())
            self._event("HEARTBEAT", self.health())

    async def heartbeat_loop(self) -> None:
        while not self.stop.is_set():
            try:
                await self.heartbeat()
            except Exception as exc:
                self.error("HEARTBEAT_FAILED", exc)
            await self._wait(60)

    def health(self) -> dict[str, Any]:
        now, quote = self.clock.now(), self.latest_quote
        return {
            "schema_version": 1,
            "run_id": self.store.run()["run_id"],
            "status": self.status,
            "ws_connected": self.ws_connected,
            "last_heartbeat": iso(self.last_heartbeat) if self.last_heartbeat else None,
            "last_cycle_at": iso(self.last_cycle_at) if self.last_cycle_at else None,
            "quote_age_seconds": (now - quote.observed_at).total_seconds() if quote else None,
            "quote_fresh": quote.fresh(now, self.config.app.max_quote_age_seconds)
            if quote
            else False,
            "clock_status": self.clock_status,
            "clock_offset_seconds": self.clock_offset_seconds,
            "last_error": self.last_error,
            "ai_policy_enabled": self.coordinator.policy is not None,
        }

    async def run(self, duration_seconds: float | None = None) -> None:
        tasks = []
        try:
            await self.initialize()
            tasks = [
                asyncio.create_task(coro, name=name)
                for name, coro in (
                    ("market-stream", self.stream_loop()),
                    ("market-poll", self.polling_loop()),
                    ("decision-cycles", self.cycle_loop()),
                    ("heartbeat", self.heartbeat_loop()),
                )
            ]
            waiter = asyncio.create_task(self.stop.wait())
            try:
                done, _ = await asyncio.wait(
                    [waiter, *tasks],
                    timeout=duration_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    if task is not waiter and not self.stop.is_set():
                        self.error(
                            "SERVICE_TASK_STOPPED", task.exception() or RuntimeError("Task ended")
                        )
                        raise DomainError("A required engine task stopped unexpectedly")
            finally:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
        finally:
            self.request_stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.status = "STOPPED"
            self.ws_connected = False
            with self.store.transaction():
                self.store.set_run_status("STOPPED", self.clock.now())
                self.store.runtime_state("engine", self.health())
                self._event("SERVICE_STOPPED", {})
            await self.source.close()

    def error(self, code: str, error: Exception) -> None:
        self.last_error = code + ":" + type(error).__name__
        with self.store.transaction():
            self._event("ERROR", {"code": code, "error_type": type(error).__name__})

    def _event(self, kind: str, data: dict[str, Any]) -> None:
        now = self.clock.now()
        self.event_counter += 1
        self.store.event(kind, data, now, stable_id(kind, self.instance_id, self.event_counter))

    async def _wait(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    @staticmethod
    def _closed_boundary(now: datetime) -> datetime:
        value = utc(now)
        return value.replace(minute=value.minute // 15 * 15, second=0, microsecond=0)
