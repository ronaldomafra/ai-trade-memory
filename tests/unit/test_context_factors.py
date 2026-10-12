from datetime import UTC, datetime

from poc.domain.factors import (
    CLASSES,
    classification_payload,
    classification_result,
    entry_foundation,
    foundation_choices,
)
from poc.domain.primitives import iso

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
