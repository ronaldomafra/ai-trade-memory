"""Periodic source collection and immutable context publication, independent of price risk."""

import asyncio
from datetime import datetime, timedelta

from poc.adapters.outbound.news import NewsSources
from poc.adapters.outbound.polymarket import PolymarketPublic
from poc.adapters.outbound.source_cache import SourceCache
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.context import ContextClassifier
from poc.application.ports import Clock
from poc.config import Config
from poc.domain.event_time import temporal_relation
from poc.domain.external import context_at, relevant_candidates
from poc.domain.prediction import metadata_quality, probability_changes, quality, select_markets
from poc.domain.primitives import iso, stable_id, utc


def semantic_news(item: dict) -> dict:
    return {
        "item_id": item["item_id"],
        "source_kind": "NEWS",
        "title": item["title"],
        "excerpt": item["summary"][:360],
        "url": item["url"],
        "source": item["source"],
        "published_at": item["published_at"],
    }


def compact_factor(
    result: dict, item: dict, expires: datetime, window_seconds: int = 16 * 900
) -> dict:
    fields = (
        "factor_id",
        "item_id",
        "relevance",
        "relationship",
        "category",
        "impact_direction",
        "impact_intensity",
        "classification_confidence",
        "factual_conflict",
        "available_at",
        "ai_call_id",
        "classification_id",
        "criteria_version",
    )
    return {
        **{key: result[key] for key in fields},
        "event_time": result.get("event_time"),
        "profile_window_seconds": window_seconds,
        "eligible": True,
        "source_quality": "VERIFIABLE",
        "valid_until": iso(expires),
        "temporal_relation": "TIMING_UNKNOWN",
        "justification": result["justification"][:220],
        "evidence": {
            "title": item["title"][:200],
            "excerpt": item["summary"][:240],
            "source": item["source"],
            "url": item["url"],
            "published_at": item["published_at"],
        },
        "source_observed_at": item.get("version_available_at", item["first_seen_at"]),
        "temporal_limitation": (
            "Publication/resolution time is not necessarily impact occurrence time."
        ),
    }


class ContextService:
    def __init__(
        self,
        config: Config,
        base_asset: str,
        store: SessionDatabase,
        clock: Clock,
        cache: SourceCache,
        news: NewsSources,
        poly: PolymarketPublic,
        classifier: ContextClassifier,
    ):
        self.config, self.base, self.store, self.clock = config, base_asset, store, clock
        self.cache, self.news, self.poly, self.classifier = cache, news, poly, classifier
        self.source_states = (store.runtime_state("external_sources") or {}).get("sources", {})
        self.markets = []
        self.selected = []
        self.selection_pending = []
        self.candidate_count = 0
        self.last_news_revision = None
        self.last_poly_revision = None
        self.last_prices = None

    async def collect_news(self) -> dict:
        tasks = []
        if self.news.token:
            tasks.append(
                (
                    "marketaux",
                    {"base_asset": self.base, "lookback_hours": self.config.news.lookback_hours},
                    self.config.news.api_poll_minutes * 60,
                    lambda: self.news.marketaux(self.base, self.config.news.lookback_hours),
                )
            )
        else:
            self.source_states["marketaux"] = {
                "status": "UNAVAILABLE",
                "reason": "MARKETAUX_TOKEN_NOT_CONFIGURED",
                "items": [],
            }
        for url in self.config.news.sources:
            tasks.append(
                (
                    "rss",
                    {"url": url},
                    self.config.news.poll_minutes * 60,
                    lambda url=url: self.news.rss(url),
                )
            )
        changed = False
        for provider, scope, seconds, collect in tasks:
            source_id = provider + "-" + stable_id(scope)[:16]
            slot = self.cache.reserve(provider, scope, self.clock.now(), seconds)
            if slot["granted"]:
                try:
                    result = await collect()
                except Exception as error:
                    result = {"status": "UNAVAILABLE", "reason": type(error).__name__, "items": []}
                self.cache.finish(slot["request_id"], result, self.clock.now())
            else:
                result = slot.get("cached")
                if result is None:
                    result = {"status": "UNAVAILABLE", "reason": slot["reason"], "items": []}
            if self.source_states.get(source_id) != result:
                changed = True
            self.source_states[source_id] = result
            for item in result.get("items", []):
                self.cache.save_item(item)
        if not changed:
            return self.snapshot(self.clock.now())["news"]
        cutoff = self.clock.now()
        candidates = relevant_candidates(
            self.cache.items(cutoff), self.base, cutoff, self.config.news.lookback_hours
        )
        # First five candidate slots are explicit, with truncation recorded.
        # Never convert a limited/unclassified query into absence of relevant news.
        selected = candidates[: self.config.news.max_items_per_decision]
        evidence = [semantic_news(item) for item in selected]
        factors = []
        pending = 0
        classification_failures = []
        classified_not_relevant = 0
        for item, semantic in zip(selected, evidence, strict=True):
            peers = [peer for peer in evidence if peer["item_id"] != semantic["item_id"]]
            result = await self.classifier.classify(semantic, peers, self.base)
            if result["status"] != "READY" or result.get("relevance") == "UNDETERMINED":
                pending += 1
                classification_failures.append(
                    {
                        "item_id": item["item_id"],
                        "status": result["status"],
                        "reason": result.get("reason", "UNDETERMINED_ASSET_RELATIONSHIP"),
                        "ai_call_id": result.get("ai_call_id"),
                    }
                )
                continue
            if result["relevance"] == "NOT_RELEVANT":
                classified_not_relevant += 1
                continue
            expires = utc(item["published_at"]) + timedelta(hours=self.config.news.lookback_hours)
            if utc(expires) >= utc(self.clock.now()):
                factors.append(
                    compact_factor(
                        result, item, expires, self.config.strategy.max_holding_candles * 900
                    )
                )
        sources = {
            key: {k: v for k, v in state.items() if k not in ("items", "quota_headers")}
            for key, state in self.source_states.items()
            if not key.startswith("poly")
        }
        valid_scopes = [
            state
            for state in sources.values()
            if state.get("status") == "COMPLETE"
            and state.get("observed_at")
            and cutoff - timedelta(hours=self.config.news.lookback_hours)
            <= utc(state["observed_at"])
            <= cutoff
        ]
        truncated = len(candidates) > len(selected)
        absent = bool(valid_scopes) and not factors and pending == 0 and not truncated
        return {
            "status": "available" if factors else "no_relevant_items" if absent else "unavailable",
            "items": factors,
            "absence_verified_in_scope": absent,
            "sources": sources,
            "coverage": "PARTIAL"
            if pending or truncated or any(s.get("status") != "COMPLETE" for s in sources.values())
            else "COMPLETE_IN_CONFIGURED_SCOPES",
            "candidate_count": len(candidates),
            "classified_not_relevant": classified_not_relevant,
            "pending_count": pending,
            "classification_failures": classification_failures,
            "truncated": truncated,
            "scope": {
                "base_asset": self.base,
                "aliases_and_macro_candidates_only": True,
                "lookback_hours": self.config.news.lookback_hours,
            },
            "absence_limitation": (
                "Only completed collected feed/query scopes; not global news coverage."
            ),
        }

    async def collect_prediction_markets(self) -> dict:
        now = self.clock.now()
        revision = int(now.timestamp()) // (self.config.polymarket.markets_poll_minutes * 60)
        review_selection = revision != self.last_poly_revision
        to_evaluate = self.selected
        if review_selection:
            discovery = await self.poly.discover(self.base)
            self.source_states["poly-discovery"] = discovery
            self.markets = discovery["markets"]
            # Only publicly stated asset/macro themes are classification candidates.
            candidates = []
            for market in self.markets:
                pseudo = {
                    "item_id": market["market_id"],
                    "title": market["question"],
                    "summary": market["description"],
                    "first_seen_at": market["observed_at"],
                    "published_at": market["observed_at"],
                }
                if relevant_candidates([pseudo], self.base, now):
                    candidates.append(market)
            # Candidate observations do not consume tracked slots. Apply all mandatory
            # filters and semantic priority before the final market/occurrence caps.
            to_evaluate = sorted(candidates, key=lambda market: market["market_id"])
            self.candidate_count = len(to_evaluate)
        summaries = []
        pending = [] if review_selection else list(self.selection_pending)
        candidates = []
        excluded = []
        for market in to_evaluate:
            metadata_reasons = metadata_quality(market, self.clock.now(), self.config.polymarket)
            if metadata_reasons:
                pending.append({"market_id": market["market_id"], "reasons": metadata_reasons})
                continue
            try:
                book, trade = await asyncio.gather(
                    self.poly.book(market), self.poly.recent_trade(market)
                )
                assessment = quality(market, book, trade, self.clock.now(), self.config.polymarket)
            except Exception as error:
                pending.append({"market_id": market["market_id"], "reason": type(error).__name__})
                continue
            if not assessment["eligible"]:
                pending.append({"market_id": market["market_id"], "reasons": assessment["reasons"]})
                continue
            item = {
                "item_id": market["market_id"],
                "source_kind": "PREDICTION_EXPECTATION",
                "title": market["question"],
                "excerpt": market["description"],
                "content_version": market["content_hash"],
                "outcome": market["outcome"],
                "resolution_deadline": market["end_date"],
                "source": "Polymarket",
                "url": market["url"],
            }
            result = await self.classifier.classify(item, [], self.base)
            if result["status"] != "READY" or result.get("relevance") == "UNDETERMINED":
                pending.append(
                    {"market_id": market["market_id"], "reason": "SEMANTIC_CLASSIFICATION_PENDING"}
                )
                continue
            if result["relevance"] == "NOT_RELEVANT":
                excluded.append(
                    {
                        "market_id": market["market_id"],
                        "reasons": ["NOT_RELEVANT"],
                        "classification_id": result["classification_id"],
                    }
                )
                continue
            candidates.append(
                {
                    "market": market,
                    "book": book,
                    "trade": trade,
                    "quality": assessment,
                    "relevance": result["relevance"],
                    "temporal_relation": temporal_relation(
                        {
                            **result,
                            "profile_window_seconds": self.config.strategy.max_holding_candles
                            * 900,
                        },
                        self.clock.now(),
                    ),
                    "classification": result,
                }
            )
        chosen = (
            select_markets(candidates, self.config.polymarket) if review_selection else candidates
        )
        if review_selection:
            chosen_ids = {row["market"]["market_id"] for row in chosen}
            excluded.extend(
                {
                    "market_id": row["market"]["market_id"],
                    "reasons": ["PRIORITY_OR_MARKET_OCCURRENCE_CAP"],
                    "classification_id": row["classification"]["classification_id"],
                }
                for row in candidates
                if row["market"]["market_id"] not in chosen_ids
            )
            self.selected = [row["market"] for row in chosen]
            self.selection_pending = list(pending)
            self.last_poly_revision = revision
            with self.store.transaction():
                self.store.runtime_state(
                    "prediction_selection",
                    {
                        "version": "poly_selection_v2",
                        "reviewed_at": iso(self.clock.now()),
                        "revision": revision,
                        "base_asset": self.base,
                        "candidate_count": self.candidate_count,
                        "selected_market_ids": [row["market_id"] for row in self.selected],
                        "selected": [
                            {
                                "market_id": row["market"]["market_id"],
                                "occurrence_id": row["market"]["occurrence_id"],
                                "relevance": row["relevance"],
                                "temporal_relation": row["temporal_relation"],
                                "book_observed_at": row["book"]["observed_at"],
                                "spread_pp": row["book"]["spread_pp"],
                                "quality": row["quality"],
                                "classification_id": row["classification"]["classification_id"],
                            }
                            for row in chosen
                        ],
                        "excluded": pending + excluded,
                        "limits": (
                            "Observed candidates are bounded by discovery; "
                            "pending IDs consume no slots."
                        ),
                    },
                )
        for candidate in chosen:
            market, book, result = (
                candidate["market"],
                candidate["book"],
                candidate["classification"],
            )
            news_like = {
                "title": market["question"],
                "summary": market["description"],
                "source": "Polymarket",
                "url": market["url"],
                "published_at": market["observed_at"],
                "first_seen_at": market["observed_at"],
            }
            expires = min(
                utc(book["observed_at"])
                + timedelta(minutes=self.config.polymarket.snapshot_max_age_minutes),
                utc(market["liquidity_observed_at"])
                + timedelta(minutes=self.config.polymarket.liquidity_max_age_minutes),
                utc(market["volume_observed_at"])
                + timedelta(minutes=self.config.polymarket.volume_24h_max_age_minutes),
            )
            factor = compact_factor(
                result, news_like, expires, self.config.strategy.max_holding_candles * 900
            )
            factor.update(
                {
                    "source_kind": "PREDICTION_EXPECTATION",
                    "market_id": market["market_id"],
                    "question": market["question"],
                    "outcome": market["outcome"],
                    "end_date": market["end_date"],
                    "implied_probability": book["midpoint"],
                    "price_source": "CLOB_MIDPOINT",
                    "probability_changes": probability_changes(
                        book,
                        self.cache.history(
                            "poly_book",
                            {
                                "condition_id": market["condition_id"],
                                "token_id": market["token_id"],
                            },
                            self.clock.now(),
                        ),
                        self.clock.now(),
                        self.config.polymarket,
                    ),
                    "spread_pp": book["spread_pp"],
                    "quality": candidate["quality"],
                    "occurrence_id": market["occurrence_id"],
                }
            )
            summaries.append(factor)
        discovery = self.source_states.get("poly-discovery", {})
        absent = discovery.get("complete") is True and not self.selected and not pending
        return {
            "status": "available"
            if summaries
            else "no_relevant_items"
            if absent
            else "unavailable",
            "items": summaries,
            "absence_verified_in_scope": absent,
            "pending": pending,
            "candidate_count": self.candidate_count,
            "tracked_market_count": len(self.selected),
            "selection_revision": self.last_poly_revision,
            "coverage": "COMPLETE_IN_CONFIGURED_SCOPE" if absent else "PARTIAL",
            "discovery": {key: value for key, value in discovery.items() if key != "markets"},
            "limitation": (
                "Expectation conditioned on question/outcome/deadline; not factual confirmation."
            ),
        }

    def snapshot(self, cutoff: datetime) -> dict:
        return context_at(self.store.external_context(cutoff), cutoff)

    async def run(self, stop: asyncio.Event, startup: asyncio.Event) -> None:
        await startup.wait()
        news_state = self.snapshot(self.clock.now())["news"]
        poly_state = self.snapshot(self.clock.now())["prediction_markets"]
        while not stop.is_set():
            try:
                if self.config.news.enabled:
                    news_state = await self.collect_news()
                with self.store.transaction():
                    self.store.save_external_context(
                        {"news": news_state, "prediction_markets": poly_state}, self.clock.now()
                    )
                if stop.is_set():
                    break
                prices = int(self.clock.now().timestamp()) // (
                    self.config.polymarket.prices_poll_minutes * 60
                )
                if self.config.polymarket.enabled and prices != self.last_prices:
                    poly_state = await self.collect_prediction_markets()
                    self.last_prices = prices
                with self.store.transaction():
                    self.store.runtime_state("external_sources", {"sources": self.source_states})
                    self.store.save_external_context(
                        {"news": news_state, "prediction_markets": poly_state}, self.clock.now()
                    )
            except Exception as error:
                with self.store.transaction():
                    self.store.event(
                        "EXTERNAL_CONTEXT_ERROR",
                        {"error_type": type(error).__name__},
                        self.clock.now(),
                        stable_id("context-error", iso(self.clock.now())),
                    )
            try:
                await asyncio.wait_for(stop.wait(), timeout=10)
            except TimeoutError:
                pass
