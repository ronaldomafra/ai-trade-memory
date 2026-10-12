"""Explicit offline pipeline scenario. Fixtures never start live engines or enter real learning."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.datasets import DatasetFiles, read_dataset
from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.openrouter import OpenRouterDecisions
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.ai_policy import JEVPolicy
from poc.application.execution import TradeIntent
from poc.application.learning import LearningEngine
from poc.application.orchestrator import CycleCoordinator, holding_bars
from poc.application.sessions import SessionManager
from poc.config import Config
from poc.domain.candles import Candle
from poc.domain.models import Action, MarketMetadata, Quote
from poc.domain.primitives import DomainError, iso, stable_id


class FixtureClock:
    def __init__(self, at: datetime):
        self.at = at

    def now(self) -> datetime:
        return self.at


class FixtureMarket:
    """Deterministic observed fixture feed, used only by smoke-offline."""

    def __init__(self, metadata: MarketMetadata, clock: FixtureClock, base_price: Decimal):
        self.metadata, self.clock, self.base = metadata, clock, base_price
        self.origin = clock.now()
        self.quote_count = 0

    def price(self, at: datetime) -> Decimal:
        index = int((at - self.origin).total_seconds()) // 900
        wave = ("0", ".0012", "-.0004", ".0008", "-.0003", ".0011", "-.0005", ".0006")
        return self.base * (1 + Decimal(index) * Decimal(".00015") + Decimal(wave[index % 8]))

    def candle(self, close_at: datetime, interval: str) -> Candle:
        seconds = 900 if interval == "15m" else 3600
        opened = close_at - timedelta(seconds=seconds)
        start, end = self.price(opened), self.price(close_at)
        return Candle(
            self.metadata.symbol,
            interval,
            opened,
            close_at,
            start,
            max(start, end) * Decimal("1.001"),
            min(start, end) * Decimal(".999"),
            end,
            Decimal("200") if int(close_at.timestamp()) // 900 % 4 == 0 else Decimal("100"),
            close_at,
            "offline_pipeline_fixture",
        )

    async def quote(self, symbol: str) -> Quote:
        if symbol != self.metadata.symbol:
            raise DomainError("Smoke quote identity mismatch")
        self.clock.at += timedelta(milliseconds=10)
        self.quote_count += 1
        bid = self.price(self.clock.now())
        return Quote(
            stable_id("pipeline-quote", self.quote_count, iso(self.clock.now())),
            symbol,
            bid,
            bid * Decimal("1.0001"),
            self.clock.now(),
            self.clock.now(),
            "offline_pipeline_fixture",
        )


class FixtureEmptyContext:
    def snapshot(self, cutoff: datetime) -> dict:
        return {
            "news": {
                "status": "no_relevant_items",
                "items": [],
                "absence_verified_in_scope": True,
                "fixture": True,
            },
            "prediction_markets": {"status": "unavailable", "items": [], "fixture": True},
        }


async def smoke_pipeline(config: Config, manager: SessionManager) -> dict:
    fixtures = {"BTCUSDT": ("BTC", "100000", ".000001"), "ETHUSDT": ("ETH", "3000", ".0001")}
    if config.market.symbol not in fixtures:
        raise DomainError("Offline pipeline provides identified BTC/ETH fixtures only")
    data = config.model_dump(mode="json")
    data["learning"]["initial_dataset_path"] = None
    config = Config.model_validate(data)
    manager = SessionManager(config, manager.storage)
    base, price, step = fixtures[config.market.symbol]
    real_now = datetime.now(UTC)
    beginning = datetime.fromtimestamp(int(real_now.timestamp()) // 3600 * 3600, UTC) - timedelta(
        days=1
    )
    clock = FixtureClock(beginning)
    metadata = MarketMetadata(
        config.market.symbol,
        base,
        "USDT",
        Decimal(step),
        Decimal(step),
        Decimal("10000"),
        Decimal("5"),
        None,
        beginning,
        {"fixture": True, "fixture_id": "v1_pipeline_smoke"},
    )
    run_id = "smoke-v1-" + uuid4().hex[:16]
    record = manager.prepare(run_id, "trend_15m_v1", metadata, beginning)
    path = Path(record["paths"]["sqlite"])
    db = SessionDatabase(path)
    budget = AIBudget(path.parent / "fixture-operational" / "ai-budget.sqlite3")
    source = FixtureMarket(metadata, clock, Decimal(price))
    mock_requests = []

    async def response(request: httpx.Request) -> httpx.Response:
        if (
            str(request.url) != "https://openrouter.ai/api/alpha/decisions"
            or request.method != "POST"
        ):
            raise DomainError("Smoke attempted an unexpected provider route")
        payload = json.loads(request.content)
        mock_requests.append(payload)
        action = "buy" if len(mock_requests) == 1 else "sell" if len(mock_requests) == 4 else "hold"
        foundation = "TECHNICAL_INDEPENDENT" if action == "buy" else "INSUFFICIENT"
        criteria = payload["questions"]["entry_foundation"]["criteria"]
        clock.at += timedelta(milliseconds=5)
        return httpx.Response(
            200,
            json={
                "id": "fixture-generation-" + str(len(mock_requests)),
                "model": "typesafe/jev-1.13-offline-fixture",
                "fixture": True,
                "answers": {
                    "action": {
                        "type": "choice",
                        "choice": action,
                        "probabilities": {
                            key: ".90" if key == action else ".05"
                            for key in ("buy", "sell", "hold")
                        },
                        "confidence": ".80",
                    },
                    "adverse_news_risk": {"type": "noul", "noul": ".20"},
                    "entry_foundation": {
                        "type": "choice",
                        "choice": foundation,
                        "probabilities": {
                            key: "1" if key == foundation else "0" for key in criteria
                        },
                    },
                },
                "usage": {"cost": "0", "prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(response))
    client = OpenRouterDecisions(config.ai, "offline-fixture-key", run_id, budget, clock, db, http)
    learning = LearningEngine(config, metadata, db)
    coordinator = CycleCoordinator(
        config,
        metadata,
        db,
        source,
        clock,
        asyncio.Event(),
        JEVPolicy(config, client),
        learning,
        FixtureEmptyContext(),
    )
    try:
        with db.transaction():
            for interval, seconds, count in (("15m", 900, 500), ("1h", 3600, 300)):
                for index in range(count):
                    db.save_candle(
                        source.candle(
                            beginning - timedelta(seconds=(count - index - 1) * seconds), interval
                        )
                    )
        duplicate_cycles_skipped = 0
        for index in range(1, 25):
            closed = beginning + timedelta(minutes=index * 15)
            clock.at = closed + timedelta(milliseconds=1)
            candle = source.candle(closed, "15m")
            with db.transaction():
                db.save_candle(candle)
                if index % 4 == 0:
                    db.save_candle(source.candle(closed, "1h"))
            if index <= 8:
                if not await coordinator.process(candle):
                    raise DomainError("Offline cycle was not processed")
                if await coordinator.process(candle):
                    raise DomainError("Duplicate offline cycle was processed")
                duplicate_cycles_skipped += 1
            if index != 12:  # One explicit missing maturity bid exercises UNAVAILABLE.
                at = clock.now()
                quote = await source.quote(metadata.symbol)
                for wallet in db.wallets():
                    coordinator.trading.execute(
                        TradeIntent(
                            wallet.portfolio_id,
                            Action.HOLD,
                            f"fixture-risk-{index}-{wallet.portfolio_id}",
                            f"fixture-risk-{index}",
                            at,
                            at,
                            record_marks=True,
                        ),
                        quote,
                        clock.now(),
                        holding_bars(wallet.entry_at, clock.now()),
                    )
            learning.mature(clock.now())
        export_path = path.parent / "fixture-learning.jsonl"
        exported = DatasetFiles(db).export(export_path, clock.now())
        validated = read_dataset(export_path, real_now)
        if exported["sample_count"] or validated["records"]:
            raise DomainError("Fixture examples escaped into reusable learning export")
        report = FileExporter(db).publish()
        audit = db.audit()
        counts = {
            row[0]: row[1]
            for row in db.connection.execute(
                "SELECT status,COUNT(*) FROM decision_outcomes GROUP BY status"
            )
        }
        if not audit["ok"] or not counts.get("MATURED") or counts.get("PENDING"):
            raise DomainError("Offline pipeline accounting or maturity failed")
        return {
            "scope": "V1_OFFLINE_PIPELINE",
            "fixture": True,
            "network_calls": 0,
            "run_id": run_id,
            "paths": record["paths"],
            "audit": audit,
            "cycles": 8,
            "duplicate_cycles_skipped": duplicate_cycles_skipped,
            "decisions": db.connection.execute("SELECT COUNT(*) FROM decisions").fetchone()[0],
            "mock_provider_attempts": len(mock_requests),
            "real_provider_attempts": 0,
            "outcomes": counts,
            "portfolios": report["portfolios"],
            "dataset": {**exported, "path": str(export_path)},
            "learning_note": (
                "Fixture observations mature but are excluded "
                "from operational memory/catalog/datasets."
            ),
            "cost_note": (
                "All provider responses/costs are mocked; no real inference or billing validated."
            ),
        }
    finally:
        await http.aclose()
        budget.close()
        db.close()
