"""Linux service composition and private read-only engine HTTP adapter."""

import asyncio
import os
import signal
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Query

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.catalog import LearningCatalog
from poc.adapters.outbound.context_service import ContextService
from poc.adapters.outbound.datasets import DatasetFiles
from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.market import BinancePublic
from poc.adapters.outbound.news import NewsSources
from poc.adapters.outbound.openrouter import OpenRouterDecisions
from poc.adapters.outbound.polymarket import PolymarketPublic
from poc.adapters.outbound.source_cache import SourceCache
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.ai_policy import JEVPolicy
from poc.application.context import ContextClassifier
from poc.application.engine import LiveEngine
from poc.application.learning import LearningEngine
from poc.application.transfer import TransferEngine
from poc.bootstrap import SystemClock, session_manager
from poc.config import Config, parse_config
from poc.domain.primitives import DomainError, stable_id


class EngineServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # The engine owns SIGINT/SIGTERM; the API must not replace those handlers.
        yield


def engine_api(engine: LiveEngine, database: SessionDatabase) -> FastAPI:
    app = FastAPI(title="Paper engine private API", version="1", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return engine.health()

    @app.get("/v1/session")
    async def state() -> dict[str, Any]:
        snapshot = FileExporter(database).dashboard()
        snapshot["health"] = engine.health()
        return snapshot

    @app.get("/v1/events")
    async def events(
        after_seq: int = Query(default=0, ge=0), limit: int = Query(default=1000, ge=1, le=10000)
    ) -> dict[str, Any]:
        return {"run_id": database.run()["run_id"], "events": database.events(after_seq, limit)}

    return app


async def projection_loop(engine: LiveEngine, database_path: Path) -> None:
    await engine.startup_complete.wait()
    while not engine.stop.is_set():

        def publish() -> None:
            db = SessionDatabase(database_path, create=False)
            try:
                FileExporter(db).publish()
            finally:
                db.close()

        worker = asyncio.create_task(asyncio.to_thread(publish))
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            await worker
            raise
        except Exception as exc:
            engine.error("PROJECTION_FAILED", exc)
        try:
            await asyncio.wait_for(engine.stop.wait(), timeout=60)
        except TimeoutError:
            pass


async def run_service(
    config: Config,
    run_id: str,
    duration_seconds: float | None = None,
    serve: bool = False,
    host: str = "127.0.0.1",
    port: int = 8081,
) -> dict[str, Any]:
    manager = session_manager(config)
    record = manager.restore(run_id)
    saved = parse_config(record["config"])
    if record["market_metadata"]["raw"].get("fixture"):
        raise DomainError("A fixture session cannot be started as a live engine")
    with manager.lease(run_id):
        database = SessionDatabase(record["paths"]["sqlite"], create=False)
        if saved.learning.initial_dataset_path and not DatasetFiles(database).imported():
            database.close()
            raise DomainError("Initial dataset preparation is incomplete; finish preparation first")
        source = BinancePublic(
            intervals=(saved.market.interval, saved.market.trend_interval),
            max_candle_pages=saved.profile_definition.parameters.market.warmup_max_pages_per_interval
            if getattr(saved, "profile_definition", None)
            else 5,
        )
        engine = None
        helpers: list[asyncio.Task] = []
        server = None
        budget = AIBudget(Path(config.app.data_dir) / "operational" / "ai-budget.sqlite3")
        ai_client = OpenRouterDecisions(
            saved.ai, os.environ.get("OPENROUTER_API_KEY"), run_id, budget, SystemClock(), database
        )
        source_cache = SourceCache(
            Path(config.app.data_dir) / "operational" / "source-cache.sqlite3"
        )
        news = NewsSources(os.environ.get("MARKETAUX_API_TOKEN"))
        poly = PolymarketPublic(
            saved.polymarket, source_cache, SystemClock(), os.environ.get("POLYMARKET_PROXY_URL")
        )
        context = ContextService(
            saved,
            record["base_asset"],
            database,
            SystemClock(),
            source_cache,
            news,
            poly,
            ContextClassifier(
                saved, ai_client, source_cache, SystemClock(), ai_client.credential_id
            ),
        )
        catalog = LearningCatalog(Path(config.app.data_dir) / "learning" / "catalog.sqlite3")
        loop = asyncio.get_running_loop()
        installed_signals = []
        try:
            metadata = await source.metadata(record["symbol"])
            if (
                metadata.base_asset != record["base_asset"]
                or metadata.quote_asset != record["quote_asset"]
            ):
                raise DomainError("Current market identity conflicts with persisted session")
            with database.transaction():
                database.event(
                    "MARKET_METADATA_VALIDATED",
                    {
                        "symbol": metadata.symbol,
                        "qty_step": metadata.qty_step,
                        "min_notional_usdt": metadata.min_notional_usdt,
                    },
                    metadata.observed_at,
                    stable_id("metadata", run_id, metadata.observed_at),
                )
            ai_client.reconcile()
            engine = LiveEngine(
                saved,
                metadata,
                database,
                source,
                SystemClock(),
                JEVPolicy(saved, ai_client),
                TransferEngine(saved, LearningEngine(saved, metadata, database), database, catalog),
                context,
            )
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, engine.request_stop)
                    installed_signals.append(sig)
                except NotImplementedError:
                    pass
            helpers.append(
                asyncio.create_task(projection_loop(engine, database.path), name="projection")
            )
            helpers.append(
                asyncio.create_task(
                    context.run(engine.stop, engine.startup_complete), name="external-context"
                )
            )
            if serve:
                server = EngineServer(
                    uvicorn.Config(
                        engine_api(engine, database),
                        host=host,
                        port=port,
                        log_level="warning",
                        access_log=False,
                    )
                )
                helpers.append(asyncio.create_task(server.serve(), name="private-api"))
            await engine.run(duration_seconds)
        finally:
            if engine:
                engine.request_stop()
            if server:
                server.should_exit = True
            for task in helpers:
                if task.get_name() == "private-api":
                    with suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(task), timeout=10)
                if not task.done():
                    task.cancel()
            await asyncio.gather(*helpers, return_exceptions=True)
            for sig in installed_signals:
                with suppress(NotImplementedError):
                    loop.remove_signal_handler(sig)
            await source.close()
            await ai_client.close()
            await news.close()
            await poly.close()
            source_cache.close()
            catalog.close()
            budget.close()
            try:
                FileExporter(database).publish()
                result = {
                    "run_id": run_id,
                    "status": engine.status if engine else "FAILED",
                    "health": engine.health() if engine else None,
                    "audit": database.audit(),
                }
            finally:
                database.close()
        return result


async def backfill(config: Config, run_id: str, days: int) -> dict[str, Any]:
    if not 1 <= days <= 60:
        raise DomainError("Backfill days must be between 1 and 60")
    record = session_manager(config).restore(run_id)
    saved = parse_config(record["config"])
    intervals = (saved.market.interval, saved.market.trend_interval)
    source = BinancePublic(
        intervals=intervals,
        max_candle_pages=saved.profile_definition.parameters.market.warmup_max_pages_per_interval
        if getattr(saved, "profile_definition", None)
        else 5,
    )
    db = SessionDatabase(record["paths"]["sqlite"], create=False)
    inserted = 0
    try:
        for interval in intervals:
            start = datetime.now(UTC) - timedelta(days=days)
            while start < datetime.now(UTC):
                rows = await source.candles(record["symbol"], interval, 999, start_at=start)
                if not rows:
                    break
                with db.transaction():
                    inserted += sum(db.save_candle(row) for row in rows)
                following = rows[-1].close_time_exclusive
                if following <= start:
                    raise DomainError("Backfill pagination made no progress")
                start = following
        FileExporter(db).publish()
        return {"run_id": run_id, "inserted_candles": inserted, "retroactive_trades": False}
    finally:
        await source.close()
        db.close()
