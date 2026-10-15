from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_accounting import setup

from poc.adapters.outbound.context_service import ContextService
from poc.adapters.outbound.source_cache import SourceCache
from poc.application.context import ContextClassifier
from poc.config import Config
from poc.domain.external import news_record
from poc.domain.factors import entry_foundation, foundation_choices
from poc.domain.primitives import iso

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.at = NOW

    def now(self):
        return self.at


def item(identity, excerpt="Ethereum network upgrade approved"):
    return {
        "item_id": identity,
        "source_kind": "NEWS",
        "title": "Ethereum upgrade " + identity,
        "excerpt": excerpt,
        "source": "news.example",
        "url": "https://news.example/" + identity,
        "published_at": iso(NOW - timedelta(hours=1)),
    }


def choice(label, criteria):
    return {
        "type": "choice",
        "choice": label,
        "probabilities": {key: 1 if key == label else 0 for key in criteria},
    }


class Client:
    def __init__(self, clock):
        self.clock = clock
        self.calls = []
        self.conflict_failure = None
        self.relevance = "DIRECT"

    async def call(self, payload, logical, purpose, deadline):
        self.calls.append(deepcopy(payload))
        self.clock.at += timedelta(seconds=1)
        comparison = "items" in payload["state"]
        if comparison and self.conflict_failure == "budget":
            return {"error_code": "AI_BUDGET_EXHAUSTED"}
        answers = {}
        for key, question in payload["questions"].items():
            labels = {
                "event_timing": "TIMING_UNKNOWN",
                "relevance": self.relevance,
                "relationship": "ASSET_NETWORK",
                "category": "NETWORK",
                "impact_direction": "UNDETERMINED",
                "impact_intensity": "UNDETERMINED",
                "classification_confidence": "MODERATE",
            }
            if comparison:
                cancelled = any("cancelled" in row["excerpt"] for row in payload["state"]["items"])
                label = "CONFLICT" if cancelled else "NO_CONFLICT"
            else:
                label = labels[key]
            answers[key] = choice(label, question["criteria"])
        if comparison and self.conflict_failure == "schema":
            answers.pop(next(iter(answers)))
        return {
            "ai_call_id": "mock-call-" + str(len(self.calls)),
            "response": {"id": "mock-generation", "model": "mock-model", "answers": answers},
        }


def classifier(tmp_path):
    clock = Clock()
    cache = SourceCache(tmp_path / "sources.sqlite3")
    client = Client(clock)
    service = ContextClassifier(Config(), client, cache, clock, "synthetic-key-version")
    return service, client, cache, clock


@pytest.mark.asyncio
async def test_new_peer_only_classifies_new_article_and_one_shared_conflict_batch(tmp_path):
    service, client, cache, clock = classifier(tmp_path)
    evidence = [item(str(index)) for index in range(5)]
    first = await service.classify_news(evidence, "ETH")
    assert len(client.calls) == 6  # Five intrinsic interpretations, one comparison.
    original = deepcopy(first)
    assert all(not call["state"]["peers"] for call in client.calls[:5])
    assert all("factual_conflict" not in call["questions"] for call in client.calls[:5])
    assert len(client.calls[-1]["questions"]) == 5
    assert (await service.classify_news(list(reversed(evidence)), "ETH")) == list(reversed(first))
    assert len(client.calls) == 6

    replacement = [*evidence[:4], item("new")]
    second = await service.classify_news(replacement, "ETH")
    assert len(client.calls) == 8  # One new interpretation plus one shared comparison.
    assert client.calls[-2]["state"]["item"]["item_id"] == "new"
    assert [row["ai_call_id"] for row in second[:4]] == [row["ai_call_id"] for row in first[:4]]
    assert second[0]["conflict_ai_call_id"] != first[0]["conflict_ai_call_id"]
    assert second[0]["classification_id"] != first[0]["classification_id"]
    assert second[0]["semantic_available_at"] == first[0]["semantic_available_at"]
    assert first == original  # No rewrite of a previous factor/snapshot.
    assert cache.classification(second[0]["classification_id"], NOW) is None
    assert cache.classification(second[0]["classification_id"], clock.now()) == second[0]
    assert cache.classification(first[0]["classification_id"], clock.now()) == first[0]

    cache.close()
    cache = SourceCache(tmp_path / "sources.sqlite3")
    restarted = ContextClassifier(Config(), client, cache, clock, "synthetic-key-version")
    assert await restarted.classify_news(replacement, "ETH") == second
    assert len(client.calls) == 8
    clock.at += timedelta(hours=1)
    assert await restarted.classify_news(replacement, "ETH") == second
    assert len(client.calls) == 8
    cache.close()


@pytest.mark.asyncio
async def test_correction_detects_new_conflict_and_does_not_reinterpret_unchanged_article(tmp_path):
    service, client, cache, clock = classifier(tmp_path)
    evidence = [item("a"), item("b")]
    first = await service.classify_news(evidence, "ETH")
    corrected = [evidence[0], item("b", "Ethereum network upgrade cancelled")]
    second = await service.classify_news(corrected, "ETH")
    assert len(client.calls) == 5
    assert second[0]["ai_call_id"] == first[0]["ai_call_id"]
    assert second[1]["ai_call_id"] != first[1]["ai_call_id"]
    assert all(row["factual_conflict"] == "CONFLICT" for row in second)
    assert all(row["factual_conflict"] == "NO_CONFLICT" for row in first)
    assert second[0]["available_at"] == iso(clock.now())
    factor = {**second[0], "eligible": True, "source_quality": "VERIFIABLE"}
    state = {"news": {"items": [factor]}, "prediction_markets": {"items": []}}
    response = {"answers": {"entry_foundation": choice("FACTOR_0", foundation_choices(state))}}
    assert entry_foundation(state, response) == (False, "ENTRY_DEPENDS_ON_UNRESOLVED_CONFLICT")
    cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["budget", "schema"])
async def test_failed_new_comparison_never_reuses_previous_no_conflict(tmp_path, failure):
    service, client, cache, clock = classifier(tmp_path)
    evidence = [item("a"), item("b")]
    first = await service.classify_news(evidence, "ETH")
    client.conflict_failure = failure
    second = await service.classify_news([evidence[0], item("new")], "ETH")
    assert second[0]["ai_call_id"] == first[0]["ai_call_id"]
    assert all(row["factual_conflict"] == "UNDETERMINED" for row in second)
    assert all(row["conflict_status"] == "UNAVAILABLE" for row in second)
    assert "factual_conflict" not in second[0]["raw_answers"]
    assert first[0]["factual_conflict"] == "NO_CONFLICT"
    calls = len(client.calls)
    client.conflict_failure = None
    same_window = await service.classify_news([evidence[0], item("new")], "ETH")
    assert same_window[0]["factual_conflict"] == "UNDETERMINED"
    assert len(client.calls) == calls
    clock.at += timedelta(minutes=10)
    recovered = await service.classify_news([evidence[0], item("new")], "ETH")
    assert len(client.calls) == calls + 1  # Retry comparison only, no repeated interpretation.
    assert recovered[0]["conflict_status"] == "READY"
    assert recovered[0]["factual_conflict"] == "NO_CONFLICT"
    assert recovered[0]["ai_call_id"] == first[0]["ai_call_id"]
    cache.close()


@pytest.mark.asyncio
async def test_single_article_and_removed_peers_do_not_need_comparison(tmp_path):
    service, client, cache, _ = classifier(tmp_path)
    assert await service.classify_news([], "ETH") == []
    evidence = [item("a"), item("b")]
    await service.classify_news(evidence, "ETH")
    count = len(client.calls)
    result = await service.classify_news(evidence[:1], "ETH")
    assert len(client.calls) == count
    assert not result[0]["peer_evidence_ids"]
    cache.close()


@pytest.mark.asyncio
async def test_semantic_cache_isolates_asset_model_criteria_and_full_content_hash(
    tmp_path, monkeypatch
):
    import poc.domain.factors as factors

    service, client, cache, clock = classifier(tmp_path)
    evidence = [{**item("a"), "content_hash": "original"}]
    await service.classify_news(evidence, "ETH")
    await service.classify_news(evidence, "BTC")
    assert len(client.calls) == 2
    changed_model = Config().model_copy(
        update={"ai": Config().ai.model_copy(update={"model": "typesafe/jev-1.13-next"})}
    )
    another = ContextClassifier(changed_model, client, cache, clock, "synthetic-key-version")
    await another.classify_news(evidence, "ETH")
    assert len(client.calls) == 3
    await service.classify_news([{**evidence[0], "content_hash": "corrected"}], "ETH")
    assert len(client.calls) == 4
    monkeypatch.setattr(factors, "NEWS_CRITERIA_VERSION", "future-fixture-criteria")
    await service.classify_news(evidence, "ETH")
    assert len(client.calls) == 5
    cache.close()


@pytest.mark.asyncio
async def test_clock_rollback_does_not_reuse_future_shared_slot_response(tmp_path):
    service, client, cache, clock = classifier(tmp_path)
    evidence = [item("a")]
    await service.classify_news(evidence, "ETH")
    clock.at = NOW
    result = await service.classify_news(evidence, "ETH")
    assert result[0]["status"] == "PENDING"
    assert result[0]["reason"] == "CLASSIFICATION_NOT_YET_AVAILABLE"
    assert len(client.calls) == 1
    cache.close()


@pytest.mark.asyncio
async def test_no_relevant_interpretations_skip_comparison(tmp_path):
    service, client, cache, _ = classifier(tmp_path)
    client.relevance = "NOT_RELEVANT"
    result = await service.classify_news([item("a"), item("b")], "ETH")
    assert all(row["relevance"] == "NOT_RELEVANT" for row in result)
    assert len(client.calls) == 2 and all("item" in call["state"] for call in client.calls)
    cache.close()


@pytest.mark.asyncio
async def test_unknown_pair_relationship_remains_unknown_and_rejects_sole_premise(tmp_path):
    service, client, cache, _ = classifier(tmp_path)
    original = client.call

    async def unknown_comparison(payload, *args):
        response = await original(payload, *args)
        if "items" in payload["state"]:
            response["response"]["answers"] = {
                key: choice("UNDETERMINED", question["criteria"])
                for key, question in payload["questions"].items()
            }
        return response

    client.call = unknown_comparison
    result = await service.classify_news([item("a"), item("b")], "ETH")
    assert all(row["factual_conflict"] == "UNDETERMINED" for row in result)
    factor = {**result[0], "eligible": True, "source_quality": "VERIFIABLE"}
    state = {"news": {"items": [factor]}, "prediction_markets": {"items": []}}
    response = {"answers": {"entry_foundation": choice("FACTOR_0", foundation_choices(state))}}
    assert not entry_foundation(state, response)[0]
    cache.close()


@pytest.mark.asyncio
async def test_news_collection_publishes_comparison_provenance_and_partial_failures(tmp_path):
    cfg, _, db, _ = setup(tmp_path / "session")
    cfg = cfg.model_copy(
        update={"news": cfg.news.model_copy(update={"sources": ["https://news.example/rss"]})}
    )
    service, client, cache, clock = classifier(tmp_path)
    service.config = cfg

    class News:
        token = None
        identities = ["a", "b"]

        async def rss(self, url):
            return {
                "status": "COMPLETE",
                "observed_at": iso(clock.now()),
                "items": [
                    news_record(
                        "Bitcoin upgrade " + identity,
                        "Bitcoin network upgrade approved",
                        "https://news.example/" + identity,
                        "news.example",
                        NOW - timedelta(hours=1),
                        clock.now(),
                        "rss",
                    )
                    for identity in self.identities
                ],
            }

    news = News()
    collector = ContextService(cfg, "BTC", db, clock, cache, news, None, service)
    first = await collector.collect_news()
    assert len(first["items"]) == 2 and len(client.calls) == 3
    assert all(row["conflict_status"] == "READY" for row in first["items"])
    assert first["items"][0]["conflict_classification_id"]
    assert "raw_answers" not in first["items"][0]
    first_at = clock.now()
    with db.transaction():
        db.save_external_context(
            {"news": first, "prediction_markets": {"status": "unavailable", "items": []}}, first_at
        )

    clock.at += timedelta(minutes=10)
    news.identities = ["a", "b", "c"]
    second = await collector.collect_news()
    assert len(second["items"]) == 3 and len(client.calls) == 5
    previous = {row["item_id"]: row for row in first["items"]}
    for row in second["items"]:
        if row["item_id"] in previous:
            assert row["ai_call_id"] == previous[row["item_id"]]["ai_call_id"]
            assert row["valid_until"] == previous[row["item_id"]]["valid_until"]
            assert row["source_observed_at"] == previous[row["item_id"]]["source_observed_at"]

    clock.at += timedelta(minutes=10)
    news.identities = ["a", "b", "c", "d"]
    client.conflict_failure = "budget"
    partial = await collector.collect_news()
    assert partial["status"] == "available" and partial["coverage"] == "PARTIAL"
    assert len(partial["items"]) == 4 and partial["pending_count"] == 4
    assert all(row["factual_conflict"] == "UNDETERMINED" for row in partial["items"])
    assert all(
        row["stage"] == "NEWS_CONFLICT_COMPARISON" for row in partial["classification_failures"]
    )
    with db.transaction():
        db.save_external_context(
            {"news": partial, "prediction_markets": {"status": "unavailable", "items": []}},
            clock.now(),
        )
    assert collector.snapshot(first_at)["news"]["items"] == first["items"]
    assert not collector.snapshot(clock.now() + timedelta(days=2))["news"]["items"]
    cache.close()
    db.close()
