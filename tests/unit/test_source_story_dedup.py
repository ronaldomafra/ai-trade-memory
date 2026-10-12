from datetime import UTC, datetime, timedelta

from poc.adapters.outbound.source_cache import SourceCache
from poc.domain.external import news_record

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def story(url, provider, seen, published=NOW):
    return news_record(
        "Bitcoin network upgrade", "New feature", url, "Publisher", published, seen, provider
    )


def test_title_source_publication_groups_alias_urls_preserving_provenance_and_cutoff(tmp_path):
    cache = SourceCache(tmp_path / "sources.sqlite3")
    try:
        first = story("https://news.example/one", "rss", NOW)
        second = story("https://news.example/amp/one", "marketaux", NOW + timedelta(minutes=1))
        cache.save_item(first)
        cache.save_item(second)
        early = cache.items(NOW)
        late = cache.items(NOW + timedelta(minutes=1))
        assert len(early) == len(late) == 1
        assert early[0]["item_id"] == late[0]["item_id"] == first["item_id"]
        assert len(early[0]["provenance"]) == 1 and len(late[0]["provenance"]) == 2
        assert len(late[0]["alias_item_ids"]) == 2
        assert late[0]["first_seen_at"] == first["first_seen_at"]
        assert late[0]["version_available_at"] == second["first_seen_at"]
        tomorrow = NOW + timedelta(days=1)
        cache.save_item(story("https://news.example/two", "rss", tomorrow, tomorrow))
        assert len(cache.items(tomorrow)) == 2  # Repeated daily headline is a new publication.
    finally:
        cache.close()


def test_provenance_added_later_does_not_appear_in_historical_query(tmp_path):
    cache = SourceCache(tmp_path / "sources.sqlite3")
    try:
        cache.save_item(story("https://news.example/one", "rss", NOW))
        cache.save_item(story("https://news.example/one", "marketaux", NOW + timedelta(minutes=1)))
        assert [origin["provider"] for origin in cache.items(NOW)[0]["provenance"]] == ["rss"]
        assert len(cache.items(NOW + timedelta(minutes=1))[0]["provenance"]) == 2
    finally:
        cache.close()
