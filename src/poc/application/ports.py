"""Application-facing contracts; implementations are composed in bootstrap."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from poc.domain.candles import Candle
from poc.domain.models import (
    DailyRiskState,
    MarketMetadata,
    MarketNotice,
    Proposal,
    Quote,
    TradeResult,
    Wallet,
)


class TradingUnitOfWork(Protocol):
    def wallet(self, portfolio_id: str) -> Wallet: ...
    def latest_risk(self, portfolio_id: str) -> DailyRiskState | None: ...
    def save_risk(self, state: DailyRiskState) -> None: ...
    def save_quote(self, quote: Quote) -> bool: ...
    def command(self, key: str) -> dict[str, Any] | None: ...
    def record_trade(self, trade: TradeResult, fingerprint: str) -> None: ...
    def reject(
        self,
        portfolio_id: str,
        action: str,
        key: str,
        fingerprint: str,
        cycle_id: str,
        reason: str,
        now: datetime,
    ) -> None: ...
    def mark(self, wallet: Wallet, quote: Quote, now: datetime, persist: bool = True) -> Wallet: ...
    def complete_decision(
        self,
        decision_id: str,
        proposed: str,
        approved: str,
        executed: str,
        reason: str,
        quote_id: str | None,
        order_id: str | None = None,
    ) -> None: ...
    def event(
        self,
        event_type: str,
        data: dict[str, Any],
        now: datetime,
        identity: str,
        portfolio_id: str | None = None,
        cycle_id: str | None = None,
    ) -> None: ...


class SessionStore(TradingUnitOfWork, Protocol):
    def save_ai_call(self, row: dict) -> None: ...
    def transaction(self) -> AbstractContextManager[TradingUnitOfWork]: ...
    def create_session(
        self, record: dict[str, Any], initial_usdt: str, strategies: tuple[str, ...], now: datetime
    ) -> None: ...
    def run(self) -> dict[str, Any] | None: ...
    def close(self) -> None: ...
    def wallets(self) -> list[Wallet]: ...
    def save_candle(self, candle: Candle) -> bool: ...
    def candles(self, symbol: str, interval: str, limit: int = 1000) -> list[Candle]: ...
    def last_exit_at(self, portfolio_id: str) -> datetime | None: ...
    def quote(self, quote_id: str) -> Quote | None: ...
    def start_cycle(
        self,
        cycle_id: str,
        candle: Candle,
        started_at: datetime,
        features: dict[str, Any],
        wallets: list[Wallet],
    ) -> bool: ...
    def finish_cycle(self, cycle_id: str, now: datetime, status: str = "COMPLETED") -> None: ...
    def recover_cycles(self, now: datetime) -> int: ...
    def set_run_status(self, status: str, now: datetime) -> None: ...
    def cycle(self, cycle_id: str) -> dict[str, Any] | None: ...
    def save_proposal(
        self,
        cycle_id: str,
        wallet: Wallet,
        proposal: Proposal,
        started_at: datetime,
        finished_at: datetime,
        state: dict[str, Any],
    ) -> str: ...
    def runtime_state(
        self, name: str, value: dict[str, Any] | None = None
    ) -> dict[str, Any] | None: ...


class StorageFactory(Protocol):
    def open(self, path: Path, create: bool = False) -> SessionStore: ...
    def lease(self, path: Path) -> AbstractContextManager[None]: ...
    def prepare_initial_learning(self, store: SessionStore, path: Path, now: datetime) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class PublicMetadataPort(Protocol):
    async def metadata(self, symbol: str) -> MarketMetadata: ...


class MarketPort(PublicMetadataPort, Protocol):
    async def quote(self, symbol: str) -> Quote: ...
    async def candles(
        self, symbol: str, interval: str, limit: int = 600, start_at: datetime | None = None
    ) -> list[Candle]: ...
    def stream(
        self, symbol: str, stop: asyncio.Event
    ) -> AsyncIterator[Quote | Candle | MarketNotice]: ...
    async def server_time(self) -> datetime: ...
    async def close(self) -> None: ...


class DecisionPolicy(Protocol):
    async def propose(
        self, cycle_id: str, states: dict[str, dict[str, Any]], deadline: datetime
    ) -> dict[str, Proposal]: ...


class LearningPort(Protocol):
    def mature(self, now: datetime) -> int: ...
    def register(self) -> int: ...
    def feedback(
        self, state: dict[str, Any], cutoff: datetime, cycle_id: str | None = None
    ) -> dict: ...


class ContextPort(Protocol):
    def snapshot(self, cutoff: datetime) -> dict: ...
