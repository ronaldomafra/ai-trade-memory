from datetime import UTC, datetime, timedelta

import pytest

from poc.domain.event_time import occurrence_candidates, temporal_relation, timing_choices
from poc.domain.external import context_at
from poc.domain.factors import CLASSES, classification_payload, classification_result
from poc.domain.primitives import iso

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def item():
    return {
        "item_id": "scheduled-fixture",
        "title": "Ethereum upgrade",
        "excerpt": "The upgrade is scheduled for 2026-10-12T14:00:00Z.",
        "source_kind": "NEWS",
        "published_at": iso(NOW),
        "resolution_deadline": "2027-01-01T00:00:00Z",
    }


def test_dates_only_in_metadata_and_unspecified_timezone_are_not_occurrences():
    assert not occurrence_candidates({"published_at": iso(NOW), "resolution_deadline": iso(NOW)})
    assert not occurrence_candidates({"excerpt": "At 2026-10-12T14:00:00 without a timezone"})
    assert not occurrence_candidates({"excerpt": "At 2026-19-80T14:00:00Z"})
    choices = timing_choices(item())
    assert "SOURCE_TIME_0" in choices and "2027-01-01" not in str(choices)


def test_evidence_chosen_by_semantic_question_is_preserved_separately_from_confidence():
    evidence = item()
    payload = classification_payload(evidence, [], "ETHUSDT", "ETH", "typesafe/jev-1.13")
    answers = {}
    for key, question in payload["questions"].items():
        labels = {
            "event_timing": "SOURCE_TIME_0",
            "relevance": "DIRECT",
            "relationship": "ASSET_NETWORK",
        }
        chosen = labels.get(key, next(iter(CLASSES[key])))
        answers[key] = {
            "type": "choice",
            "choice": chosen,
            "probabilities": {
                option: 1 if option == chosen else 0 for option in question["criteria"]
            },
            "confidence": 0.5,
        }
    result = classification_result(
        {"id": "fixture", "model": "fixture", "answers": answers},
        evidence,
        [],
        "fixture-call",
        iso(NOW),
    )
    assert result["event_time"]["start"] == "2026-10-12T14:00:00.000000Z"
    assert "upgrade" in result["event_time"]["evidence_quote"]
    assert result["raw_answers"]["event_timing"]["raw_confidence"] == 0.5
    assert temporal_relation(result, NOW) == "IN_WINDOW"
    assert temporal_relation(result, NOW + timedelta(hours=3)) == "BACKGROUND"


@pytest.mark.parametrize(
    "offset, expected", [(0, "IN_WINDOW"), (4, "IN_WINDOW"), (5, "BACKGROUND"), (-1, "BACKGROUND")]
)
def test_window_boundaries_and_configured_horizon(offset, expected):
    stamp = iso(NOW + timedelta(hours=offset))
    factor = {"event_time": {"start": stamp, "end": stamp}, "profile_window_seconds": 4 * 3600}
    assert temporal_relation(factor, NOW) == expected
    if offset == 4:
        assert (
            temporal_relation({**factor, "profile_window_seconds": 2 * 3600}, NOW) == "BACKGROUND"
        )


def test_unknown_interval_and_clock_reclassification_do_not_rewrite_previous_context():
    stamp = iso(NOW + timedelta(hours=1))
    factor = {
        "event_time": {"start": stamp, "end": stamp},
        "available_at": iso(NOW),
        "source_observed_at": iso(NOW),
        "valid_until": iso(NOW + timedelta(days=1)),
        "temporal_relation": "TIMING_UNKNOWN",
    }
    context = {
        "news": {"status": "available", "items": [factor]},
        "prediction_markets": {"status": "unavailable", "items": []},
    }
    early = context_at(context, NOW)
    late = context_at(context, NOW + timedelta(hours=2))
    assert early["news"]["items"][0]["temporal_relation"] == "IN_WINDOW"
    assert late["news"]["items"][0]["temporal_relation"] == "BACKGROUND"
    assert factor["temporal_relation"] == "TIMING_UNKNOWN"
    assert early["news"]["items"][0]["temporal_relation"] == "IN_WINDOW"
    broad = {
        "event_time": {"start": iso(NOW - timedelta(days=1)), "end": iso(NOW + timedelta(days=1))}
    }
    assert temporal_relation(broad, NOW) == "TIMING_UNKNOWN"
