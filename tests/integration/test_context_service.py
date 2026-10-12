from datetime import timedelta

import pytest
from test_accounting import NOW, meta, setup
from test_cycles_engine import Clock, FeaturesFixture, Source

from poc.adapters.outbound.context_service import ContextService
from poc.adapters.outbound.source_cache import SourceCache
from poc.application.context import ContextClassifier
from poc.application.orchestrator import CycleCoordinator
from poc.domain.external import news_record
from poc.domain.factors import CLASSES
from poc.domain.jev import parse_trade_response
from poc.domain.models import PortfolioKind
from poc.domain.prediction import normalize_book, normalize_market


def prediction_market(units="REPORTED_USD_V1"):
    return normalize_market(
        {
            "id": "10",
            "conditionId": "0x" + "a" * 64,
            "question": "Will Ethereum upgrade?",
            "description": "Upgrade alpha in October",
            "outcomes": ["Yes", "No"],
            "clobTokenIds": ["11", "12"],
            "active": True,
            "closed": False,
            "enableOrderBook": True,
            "liquidityClob": "10000",
            "volume24hrClob": "1000",
            "events": [
                {
                    "id": "event",
                    "title": "Will Ethereum upgrade?",
                    "description": "Upgrade alpha in October",
                }
            ],
        },
        NOW,
        units,
    )


def prediction_book(metadata):
    return normalize_book(
        {
            "market": metadata["condition_id"],
            "asset_id": metadata["token_id"],
            "timestamp": str(int(NOW.timestamp() * 1000)),
            "bids": [{"price": "0.49", "size": "3000"}],
            "asks": [{"price": "0.51", "size": "3000"}],
        },
        metadata,
        NOW,
    )


class Client:
    def __init__(self):
        self.calls = 0

    async def call(self, *args):
        self.calls += 1
        labels = {
            "event_timing": "TIMING_UNKNOWN",
            "relevance": "DIRECT",
            "relationship": "ASSET_NETWORK",
            "category": "NETWORK",
            "impact_direction": "UNDETERMINED",
            "impact_intensity": "UNDETERMINED",
            "classification_confidence": "MODERATE",
            "factual_conflict": "NO_CONFLICT",
        }
        response = {
            "id": "mock-gen",
            "model": "typesafe/jev-1.13-fixture",
            "answers": {
                key: {
                    "type": "choice",
                    "choice": labels[key],
                    "probabilities": {value: 1 if value == labels[key] else 0 for value in choices},
                }
                for key, choices in CLASSES.items()
            },
        }
        return {"ai_call_id": "mock-call", "response": response}


class News:
    token = None

    def __init__(self):
        self.calls = 0

    async def rss(self, url):
        self.calls += 1
        return {
            "status": "COMPLETE",
            "complete": True,
            "observed_at": NOW.isoformat(),
            "items": [
                news_record(
                    "Bitcoin network upgrade",
                    "Network change",
                    "https://news.example/one",
                    "news.example",
                    NOW - timedelta(hours=1),
                    NOW,
                    "rss",
                )
            ],
        }


@pytest.mark.asyncio
async def test_classification_reuse_version_cutoff_and_compact_snapshot(tmp_path):
    cfg, _, db, _ = setup(tmp_path / "session")
    cache = SourceCache(tmp_path / "sources.sqlite3")
    clock = Clock(NOW)
    client = Client()
    classifier = ContextClassifier(cfg, client, cache, clock, "fixture-credential-version")
    news = News()
    service = ContextService(cfg, "BTC", db, clock, cache, news, None, classifier)
    first = await service.collect_news()
    assert first["status"] == "available" and len(first["items"]) == 1
    assert client.calls == 1
    assert "raw_answers" not in first["items"][0]
    with db.transaction():
        db.save_external_context(
            {"news": first, "prediction_markets": {"status": "unavailable", "items": []}}, NOW
        )
    assert service.snapshot(NOW - timedelta(microseconds=1))["news"]["status"] == "unavailable"
    second = await service.collect_news()
    assert second["items"] == first["items"] and client.calls == 1
    assert news.calls == len(cfg.news.sources)
    expired = service.snapshot(NOW + timedelta(days=2))["news"]
    assert expired["status"] == "unavailable" and not expired["items"]
    assert not expired["absence_verified_in_scope"]
    cache.close()
    db.close()


@pytest.mark.asyncio
async def test_low_confidence_keeps_original_buy_proposal_but_never_executes_it(tmp_path):
    import asyncio

    cfg, _, db, _ = setup(tmp_path)
    clock = Clock(NOW + timedelta(seconds=1))
    source = Source(clock)

    class Policy:
        async def propose(self, cycle, states, deadline):
            data = {
                "id": "mock-gen",
                "model": "typesafe/jev-1.13-fixture",
                "answers": {
                    "action": {
                        "type": "choice",
                        "choice": "buy",
                        "probabilities": {"buy": 0.64, "sell": 0.06, "hold": 0.30},
                    },
                    "adverse_news_risk": {"type": "noul", "noul": 0.08},
                },
            }
            return {key: parse_trade_response(data, 0.65, 0.1, "mock-call") for key in states}

    coordinator = CycleCoordinator(cfg, meta(), db, source, clock, asyncio.Event(), Policy())
    coordinator.feature_engine = FeaturesFixture()
    bars = await source.candles("BTCUSDT", "15m", 1)
    with db.transaction():
        db.save_candle(bars[-1])
    await coordinator.process(bars[-1])
    row = db.connection.execute(
        "SELECT proposed_action,approved_action,executed_action,reason_code "
        "FROM decisions WHERE portfolio_id=?",
        (PortfolioKind.STATIC,),
    ).fetchone()
    assert tuple(row) == ("BUY", "HOLD", "HOLD", "LOW_CONFIDENCE")
    assert not db.wallet(PortfolioKind.STATIC).has_position
    assert db.audit()["ok"]
    db.close()


@pytest.mark.asyncio
async def test_prediction_quality_precedes_total_cap_and_composition_changes_only_on_revision(
    tmp_path,
):
    cfg, _, db, _ = setup(tmp_path / "session")
    cfg = cfg.model_copy(
        update={
            "polymarket": cfg.polymarket.model_copy(
                update={"max_tracked_markets": 2, "max_markets_per_occurrence": 2}
            )
        }
    )
    clock = Clock(NOW)
    cache = SourceCache(tmp_path / "sources.sqlite3")
    classifier = ContextClassifier(cfg, Client(), cache, clock, "synthetic-key-version")

    class Poly:
        def __init__(self):
            self.book_calls = []
            self.fixed_bad_books = True

        async def discover(self, base):
            return {
                "complete": True,
                "observed_at": NOW.isoformat(),
                "markets": [
                    {
                        **prediction_market(),
                        "market_id": str(i),
                        "occurrence_id": "verified-" + str(i),
                    }
                    for i in range(12)
                ],
            }

        async def book(self, metadata):
            self.book_calls.append(metadata["market_id"])
            value = prediction_book(metadata)
            return (
                {**value, "spread_pp": "3"}
                if (self.fixed_bad_books and int(metadata["market_id"]) < 10)
                else value
            )

        async def recent_trade(self, metadata):
            return {
                "condition_id": metadata["condition_id"],
                "token_id": metadata["token_id"],
                "observed_at": clock.now().isoformat(),
                "source_at": clock.now().isoformat(),
            }

    poly = Poly()
    service = ContextService(cfg, "ETH", db, clock, cache, None, poly, classifier)
    first = await service.collect_prediction_markets()
    assert {item["market_id"] for item in first["items"]} == {"10", "11"}
    assert len(poly.book_calls) == 12
    assert first["candidate_count"] == 12
    selection = db.runtime_state("prediction_selection")
    assert selection["selected_market_ids"] == ["10", "11"]
    assert selection["excluded"][0]["reasons"] == ["SPREAD_TOO_WIDE"]
    poly.fixed_bad_books = False
    clock.at += timedelta(minutes=5)
    await service.collect_prediction_markets()
    assert len(poly.book_calls) == 14  # Only the two tracked IDs, until the hourly revision.
    assert {row["market_id"] for row in service.selected} == {"10", "11"}
    cache.close()
    db.close()


@pytest.mark.asyncio
async def test_unverified_prediction_metadata_does_not_spend_book_trade_or_jev_calls(tmp_path):
    cfg, _, db, _ = setup(tmp_path / "session")
    cache = SourceCache(tmp_path / "sources.sqlite3")
    clock = Clock(NOW)
    client = Client()

    class Poly:
        async def discover(self, base):
            return {"complete": True, "markets": [prediction_market(None)]}

        async def book(self, metadata):
            pytest.fail("Unverified monetary metadata should fail before public book requests")

        async def recent_trade(self, metadata):
            pytest.fail("Unverified metadata should fail before public trade requests")

    service = ContextService(
        cfg,
        "ETH",
        db,
        clock,
        cache,
        None,
        Poly(),
        ContextClassifier(cfg, client, cache, clock, "synthetic-key-version"),
    )
    result = await service.collect_prediction_markets()
    assert not result["items"] and not result["absence_verified_in_scope"]
    assert result["pending"][0]["reasons"] == ["GAMMA_METRIC_UNITS_UNVERIFIED"]
    assert client.calls == 0 and not service.selected
    cache.close()
    db.close()
