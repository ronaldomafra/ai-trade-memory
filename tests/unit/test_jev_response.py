from copy import deepcopy
from decimal import Decimal

import pytest

from poc.domain.jev import parse_trade_response, trade_payload
from poc.domain.models import Action
from poc.domain.primitives import canonical_json


def response(choice="buy", probabilities=None, confidence=".81"):
    return {
        "id": "physical-1",
        "model": "typesafe/jev-1.13-test",
        "answers": {
            "action": {
                "type": "choice",
                "choice": choice,
                "confidence": Decimal(confidence),
                "probabilities": probabilities
                or {"buy": Decimal(".74"), "sell": Decimal(".06"), "hold": Decimal(".20")},
            },
            "adverse_news_risk": {"type": "noul", "noul": Decimal(".08")},
        },
        "usage": {"input_tokens": 500, "output_tokens": 20, "cost": Decimal(".000021")},
    }


def test_choice_probability_and_raw_confidence_are_separate():
    proposal = parse_trade_response(response(), 0.65, 0.10, "call")
    assert proposal.action == Action.BUY
    assert proposal.confidence == Decimal(".81")
    assert proposal.probabilities["buy"] == Decimal(".74")
    assert proposal.ai_call_id == "call"


@pytest.mark.parametrize(
    "data",
    [
        response(
            probabilities={"buy": Decimal(".64"), "sell": Decimal(".06"), "hold": Decimal(".30")}
        ),
        response(
            probabilities={"buy": Decimal(".66"), "sell": Decimal(".60"), "hold": Decimal(".10")}
        ),
        response(probabilities={"buy": Decimal("NaN"), "sell": 0, "hold": 0}),
        {"answers": {}},
        response(choice="not-an-action"),
    ],
)
def test_invalid_or_low_probability_fails_closed(data):
    assert parse_trade_response(data, 0.65, 0.10, "call").action == Action.HOLD


def test_hold_is_not_replaced_by_highest_alternative():
    assert parse_trade_response(response(choice="hold"), 0.65, 0.10, "call").action == Action.HOLD


def test_questions_generalize_to_actual_asset_and_state_size_is_bounded():
    payload = trade_payload({"symbol": "ETHUSDT", "base_asset": "ETH"}, "typesafe/jev-1.13")
    assert "BTC" not in str(payload)
    assert payload["state"]["task"]
    with pytest.raises(ValueError):
        trade_payload({"news": {"items": ["x" * 100000]}}, "typesafe/jev-1.13")


def test_trade_context_summarizes_rejected_markets_without_losing_selected_evidence():
    factor = {
        "factor_id": "selected-factor",
        "eligible": True,
        "relevance": "DIRECT",
        "factual_conflict": "CONFLICT",
        "classification_confidence": "LOW",
        "source_quality": "PARTIAL",
        "available_at": "2026-10-13T15:00:00Z",
        "valid_until": "2026-10-13T15:10:00Z",
        "occurrence_id": "same-event",
        "evidence": {"title": "Synthetic contested claim", "excerpt": "Short evidence"},
    }
    pending = [
        {
            "market_id": str(i),
            "reasons": ["GAMMA_METRIC_UNITS_UNVERIFIED", "OCCURRENCE_ASSOCIATION_PENDING"],
        }
        for i in range(500)
    ]
    state = {
        "symbol": "ETHUSDT",
        "base_asset": "ETH",
        "news": {
            "status": "unavailable",
            "items": [],
            "absence_verified_in_scope": False,
            "classification_failures": [
                {"item_id": str(i), "reason": "AI_CIRCUIT_OPEN"} for i in range(5)
            ],
        },
        "prediction_markets": {
            "status": "available",
            "items": [factor],
            "pending": pending,
            "candidate_count": 500,
            "coverage": "PARTIAL",
            "absence_verified_in_scope": False,
            "discovery": {"status": "PARTIAL", "complete": False, "markets": pending},
            "raw_audit": "x" * 100000,
        },
    }
    original = deepcopy(state)
    assert len(canonical_json(state).encode()) > 30000
    payload = trade_payload(state, "typesafe/jev-1.13")
    assert len(canonical_json(payload).encode()) < 6000
    poly = payload["state"]["prediction_markets"]
    assert poly["items"] == [factor]
    assert poly["pending_count"] == 500
    assert poly["diagnostic_counts"] == {
        "GAMMA_METRIC_UNITS_UNVERIFIED": 500,
        "OCCURRENCE_ASSOCIATION_PENDING": 500,
    }
    assert "pending" not in poly and "raw_audit" not in poly
    assert "markets" not in poly["discovery"]
    assert not poly["absence_verified_in_scope"] and poly["coverage"] == "PARTIAL"
    assert payload["state"]["news"]["diagnostic_counts"] == {"AI_CIRCUIT_OPEN": 5}
    assert "FACTOR_0" in payload["questions"]["entry_foundation"]["criteria"]
    assert state == original  # Audit snapshot and local risk gates retain the full evidence.


def test_stage_receipts_stay_in_audit_without_inflating_trade_context_or_losing_conflict():
    from copy import deepcopy

    from poc.domain.jev import trade_payload

    factor = {
        "factor_id": "selected-factor",
        "eligible": True,
        "relevance": "DIRECT",
        "factual_conflict": "CONFLICT",
        "conflict_status": "READY",
        "available_at": "2026-10-14T12:00:00Z",
        "valid_until": "2026-10-15T12:00:00Z",
        "evidence": {"title": "Ethereum upgrade cancelled"},
        "semantic_classification_id": "semantic-receipt",
        "semantic_available_at": "2026-10-14T11:00:00Z",
        "conflict_criteria_version": "news_conflicts_v1",
        "conflict_classification_id": "comparison-receipt",
        "conflict_ai_call_id": "physical-call-id",
        "conflict_available_at": "2026-10-14T12:00:00Z",
        "peer_evidence_ids": ["other-article"],
    }
    state = {"news": {"status": "available", "items": [factor]}}
    original = deepcopy(state)
    payload = trade_payload(state, "typesafe/jev-1.13")
    projected = payload["state"]["news"]["items"][0]
    assert projected["factor_id"] == "selected-factor"
    assert projected["factual_conflict"] == "CONFLICT" and projected["conflict_status"] == "READY"
    assert projected["available_at"] == factor["available_at"]
    assert projected["valid_until"] == factor["valid_until"]
    assert projected["evidence"] == factor["evidence"]
    assert "comparison-receipt" not in str(payload)
    assert "FACTOR_0" in payload["questions"]["entry_foundation"]["criteria"]
    assert state == original
