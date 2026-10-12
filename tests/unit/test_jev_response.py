from decimal import Decimal

import pytest

from poc.domain.jev import parse_trade_response, trade_payload
from poc.domain.models import Action


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
