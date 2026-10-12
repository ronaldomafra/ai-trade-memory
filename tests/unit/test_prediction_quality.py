from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from poc.config import Config
from poc.domain.prediction import normalize_book, normalize_market, quality, select_markets
from poc.domain.primitives import iso

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
CONDITION = "0x" + "a" * 64


def raw_market():
    return {
        "id": "10",
        "conditionId": CONDITION,
        "question": "Will Ethereum upgrade?",
        "description": "A specific upgrade outcome",
        "outcomes": '["Yes","No"]',
        "clobTokenIds": '["11","12"]',
        "events": [
            {
                "id": "e-1",
                "title": "Will Ethereum upgrade?",
                "description": "A specific upgrade outcome",
            }
        ],
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "liquidityClob": Decimal("10000"),
        "volume24hrClob": Decimal("1000"),
    }


def market(units="REPORTED_USD_V1"):
    return normalize_market(raw_market(), NOW, units)


def book(metadata=None):
    return normalize_book(
        {
            "market": CONDITION,
            "asset_id": "11",
            "timestamp": str(int(NOW.timestamp() * 1000)),
            "bids": [{"price": "0.49", "size": "3000"}, {"price": "0.10", "size": "100000"}],
            "asks": [{"price": "0.51", "size": "3000"}, {"price": "0.90", "size": "100000"}],
        },
        metadata or market(),
        NOW,
    )


def trade():
    return {
        "token_id": "11",
        "condition_id": CONDITION,
        "source_at": iso(NOW - timedelta(minutes=60)),
        "observed_at": iso(NOW),
    }


def test_inclusive_filters_and_depth_band_do_not_count_distant_levels():
    result = quality(market(), book(), trade(), NOW, Config().polymarket)
    assert result["eligible"]
    assert Decimal(result["bid_depth_usd_equivalent"]) == Decimal("1470")
    assert Decimal(result["ask_depth_usd_equivalent"]) == Decimal("1530")
    assert not quality(
        market(), book(), trade(), NOW + timedelta(microseconds=1), Config().polymarket
    )["eligible"]


def test_gamma_updated_metadata_is_not_recent_trade_or_book_and_units_cannot_be_guessed():
    metadata = market(None)
    result = quality(metadata, book(metadata), None, NOW, Config().polymarket)
    assert "GAMMA_METRIC_UNITS_UNVERIFIED" in result["reasons"]
    assert "RECENT_RESULT_TRADE_UNVERIFIED" in result["reasons"]
    result = quality(
        market(),
        book(),
        {**trade(), "source_at": iso(NOW)},
        NOW + timedelta(minutes=76),
        Config().polymarket,
    )
    assert "STALE_LIQUIDITY_REPORTED" in result["reasons"]
    assert "STALE_BOOK" in result["reasons"]


def test_identity_future_and_bad_probability_books_rejected():
    with pytest.raises(ValueError):
        normalize_book({"market": CONDITION, "asset_id": "other"}, market(), NOW)
    with pytest.raises(ValueError):
        normalize_book(
            {
                "market": CONDITION,
                "asset_id": "11",
                "timestamp": str(int((NOW + timedelta(seconds=1)).timestamp() * 1000)),
            },
            market(),
            NOW,
        )


def test_selection_caps_same_occurrence_and_uses_stable_id_tie_break():
    candidates = []
    for identity in ("30", "20", "10"):
        metadata = {**market(), "market_id": identity}
        candidates.append(
            {
                "market": metadata,
                "book": book(metadata),
                "quality": quality(metadata, book(metadata), trade(), NOW, Config().polymarket),
                "relevance": "DIRECT",
                "temporal_relation": "TIMING_UNKNOWN",
            }
        )
    selected = select_markets(candidates, Config().polymarket)
    assert [row["market"]["market_id"] for row in selected] == ["10", "20"]


def test_provider_group_id_alone_never_verifies_occurrence_or_consumes_a_slot():
    raw = raw_market()
    raw["events"] = [{"id": "e-1"}]
    metadata = normalize_market(raw, NOW, "REPORTED_USD_V1")
    assert metadata["provider_event_ids"] == ["e-1"]
    assert metadata["occurrence_id"] is None and metadata["association_status"] == "PENDING"
    assert (
        "OCCURRENCE_ASSOCIATION_PENDING"
        in quality(metadata, book(metadata), trade(), NOW, Config().polymarket)["reasons"]
    )


def test_exact_proposition_association_keeps_full_rules_and_groups_duplicate_event_ids():
    original = market()
    assert original["association_status"] == "VERIFIED_LITERAL_PROPOSITION"
    changed_id = raw_market()
    changed_id["events"][0]["id"] = "another-provider-group"
    assert normalize_market(changed_id, NOW)["occurrence_id"] == original["occurrence_id"]
    evidence = original["association_evidence"]
    assert evidence["rules"] == "A specific upgrade outcome"
    assert evidence["available_at"] == iso(NOW)
    # A mismatch beyond the short decision excerpt must still invalidate the association.
    long_rules = "Rule " * 200 + "Upgrade alpha in October"
    raw = raw_market()
    raw["description"] = long_rules
    raw["events"][0]["description"] = "Rule " * 200 + "Upgrade beta in November"
    mismatched = normalize_market(raw, NOW)
    assert mismatched["association_status"] == "PENDING"
    assert mismatched["association_evidence"]["rules"] == long_rules
    assert mismatched["content_hash"] != original["content_hash"]
