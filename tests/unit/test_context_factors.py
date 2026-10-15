from datetime import UTC, datetime

import pytest

from poc.domain.factors import (
    CLASSES,
    classification_payload,
    classification_result,
    entry_foundation,
    foundation_choices,
    news_conflict_payload,
    news_conflict_result,
)
from poc.domain.primitives import DomainError, iso

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
EVIDENCE = {
    "item_id": "one",
    "title": "Ethereum upgrade",
    "excerpt": "Network change",
    "source_kind": "NEWS",
    "source": "news.example",
    "url": "https://news.example/one",
    "published_at": iso(NOW),
}


def answer(choice, criteria):
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": {k: 1 if k == choice else 0 for k in criteria},
        "confidence": 0.8,
    }


def classification(relevance="DIRECT", relationship="ASSET_NETWORK"):
    labels = {
        "event_timing": "TIMING_UNKNOWN",
        "relevance": relevance,
        "relationship": relationship,
        "category": "NETWORK",
        "impact_direction": "UNDETERMINED",
        "impact_intensity": "UNDETERMINED",
        "classification_confidence": "MODERATE",
        "factual_conflict": "NO_CONFLICT",
    }
    return {
        "id": "mock-gen",
        "model": "typesafe/jev-1.13-fixture",
        "answers": {key: answer(labels[key], choices) for key, choices in CLASSES.items()},
    }


def state(factor=None, absent=False):
    return {
        "market": {
            "valid": True,
            "rsi_14": 60,
            "ema_short": 100,
            "ema_mid": 90,
            "ema_long": 80,
            "macd_histogram": 1,
            "atr_pct": 0.5,
            "volume_ratio": 1.2,
        },
        "news": {
            "status": "available" if factor else "no_relevant_items" if absent else "unavailable",
            "items": [factor] if factor else [],
            "absence_verified_in_scope": absent,
        },
        "prediction_markets": {"status": "unavailable", "items": []},
    }


def foundation_response(s, choice):
    return {"answers": {"entry_foundation": answer(choice, foundation_choices(s))}}


def test_semantic_unknown_impact_not_neutral_and_unknown_relation_not_promoted():
    result = classification_result(classification(), EVIDENCE, [], "call", iso(NOW))
    assert (
        result["impact_direction"] == "UNDETERMINED"
        and result["classification_confidence"] == "MODERATE"
    )
    assert result["raw_answers"]["relevance"]["raw_confidence"] == 0.8
    unknown = classification_result(
        classification(relationship="UNDETERMINED"), EVIDENCE, [], "call", iso(NOW)
    )
    assert unknown["relevance"] == "UNDETERMINED"
    assert "historical_feedback" not in str(
        classification_payload(EVIDENCE, [], "ETHUSDT", "ETH", "typesafe/jev-1.13")
    )


def test_external_failure_not_empty_and_verifiable_empty_allows_technical_foundation():
    unavailable = state()
    assert not entry_foundation(
        unavailable, foundation_response(unavailable, "TECHNICAL_INDEPENDENT")
    )[0]
    empty = state(absent=True)
    assert entry_foundation(empty, foundation_response(empty, "TECHNICAL_INDEPENDENT"))[0]


def test_conflict_or_low_confidence_cannot_be_sole_premise_but_independent_facts_can():
    factor = {
        "factor_id": "factor-one",
        "eligible": True,
        "relevance": "DIRECT",
        "source_quality": "VERIFIABLE",
        "classification_confidence": "MODERATE",
        "factual_conflict": "CONFLICT",
    }
    s = state(factor)
    assert (
        entry_foundation(s, foundation_response(s, "FACTOR_0"))[1]
        == "ENTRY_DEPENDS_ON_UNRESOLVED_CONFLICT"
    )
    assert entry_foundation(s, foundation_response(s, "TECHNICAL_INDEPENDENT"))[0]
    factor["factual_conflict"] = "NO_CONFLICT"
    factor["classification_confidence"] = "LOW"
    assert (
        entry_foundation(s, foundation_response(s, "FACTOR_0"))[1]
        == "ENTRY_DEPENDS_ON_UNVERIFIABLE_PREMISE"
    )
    factor["classification_confidence"] = "HIGH"
    assert entry_foundation(s, foundation_response(s, "FACTOR_0"))[0]
    assert not entry_foundation(s, {"answers": {}})[0]


def test_shared_conflict_payload_is_canonical_bounded_and_strictly_validated():
    items = [EVIDENCE, {**EVIDENCE, "item_id": "two"}]
    payload = news_conflict_payload(items, "ETHUSDT", "ETH", "typesafe/jev-1.13")
    assert payload == news_conflict_payload(
        list(reversed(items)), "ETHUSDT", "ETH", "typesafe/jev-1.13"
    )
    assert set(payload["questions"]) == {"conflict_0", "conflict_1"}
    response = {
        "id": "mock-gen",
        "model": "mock-model",
        "answers": {
            key: answer("NO_CONFLICT", CLASSES["factual_conflict"]) for key in payload["questions"]
        },
    }
    result = news_conflict_result(response, items, "mock-call", iso(NOW))
    assert set(result["checks"]) == {"one", "two"}
    response["answers"]["conflict_0"]["probabilities"] = {"NO_CONFLICT": 1}
    with pytest.raises(DomainError, match="Invalid structured semantic"):
        news_conflict_result(response, items, "mock-call", iso(NOW))
    for invalid in (
        [],
        items[:1],
        [EVIDENCE, EVIDENCE],
        [{**EVIDENCE, "item_id": str(i)} for i in range(6)],
    ):
        with pytest.raises(DomainError):
            news_conflict_payload(invalid, "ETHUSDT", "ETH", "typesafe/jev-1.13")
    with pytest.raises(DomainError, match="exceeds 16 KB"):
        news_conflict_payload(
            [{**row, "excerpt": "x" * 16000} for row in items],
            "ETHUSDT",
            "ETH",
            "typesafe/jev-1.13",
        )


def test_news_split_preserves_existing_polymarket_questionnaire_and_version():
    evidence = {**EVIDENCE, "source_kind": "PREDICTION_EXPECTATION"}
    payload = classification_payload(evidence, [], "ETHUSDT", "ETH", "typesafe/jev-1.13")
    assert payload["state"]["criteria_version"] == "external_factors_v2"
    assert "factual_conflict" in payload["questions"]
    result = classification_result(classification(), evidence, [], "mock-call", iso(NOW))
    assert result["criteria_version"] == "external_factors_v2"
    assert result["raw_answers"]["factual_conflict"]["choice"] == "NO_CONFLICT"
