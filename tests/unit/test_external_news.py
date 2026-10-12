from datetime import UTC, datetime, timedelta

import pytest

from poc.domain.external import canonical_url, clean_text, news_record, relevant_candidates

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def test_sanitization_excludes_scripts_controls_and_limits_context():
    assert clean_text("<p>Ethereum</p><script>secret</script>\x00update", 200) == "Ethereum update"
    assert len(clean_text("a" * 1000, 80)) == 80
    assert (
        canonical_url("https://site.example/story?utm_source=x&id=2#fragment")
        == "https://site.example/story?id=2"
    )
    with pytest.raises(ValueError):
        canonical_url("javascript:alert(1)")


def test_news_first_seen_never_becomes_publication_time_and_asset_selection_is_explicit():
    item = news_record(
        "Ethereum upgrade",
        "Network change",
        "https://site.example/a",
        "site.example",
        NOW - timedelta(hours=1),
        NOW,
        "rss",
    )
    assert item["first_seen_at"] != item["published_at"]
    assert relevant_candidates([item], "ETH", NOW)
    assert not relevant_candidates([item], "BTC", NOW)
    assert not relevant_candidates([item], "ETH", NOW - timedelta(seconds=1))
    assert not relevant_candidates([item], "ETH", NOW + timedelta(hours=25))


def test_macro_is_only_a_candidate_not_automatic_btc_relevance_for_other_asset():
    item = news_record(
        "Fed rate decision",
        "Federal Reserve rates",
        "https://site.example/b",
        "site.example",
        NOW,
        NOW,
        "rss",
    )
    selected = relevant_candidates([item], "SOL", NOW)
    assert selected[0]["candidate_reason"] == "MACRO_REQUIRES_ASSET_CLASSIFICATION"


def test_configured_news_window_excludes_older_items_and_expires_empty_scope():
    from poc.domain.external import context_at

    item = news_record(
        "Ethereum upgrade",
        "Network change",
        "https://site.example/a",
        "site.example",
        NOW - timedelta(hours=3),
        NOW,
        "rss",
    )
    assert relevant_candidates([item], "ETH", NOW)
    assert not relevant_candidates([item], "ETH", NOW, lookback_hours=2)
    context = {
        "news": {
            "status": "no_relevant_items",
            "items": [],
            "absence_verified_in_scope": True,
            "scope": {"lookback_hours": 2},
            "sources": {"rss": {"status": "COMPLETE", "observed_at": NOW.isoformat()}},
        },
        "prediction_markets": {"status": "unavailable", "items": []},
    }
    assert context_at(context, NOW + timedelta(hours=2))["news"]["absence_verified_in_scope"]
    later = context_at(context, NOW + timedelta(hours=2, microseconds=1))["news"]
    assert later["status"] == "unavailable" and not later["absence_verified_in_scope"]
