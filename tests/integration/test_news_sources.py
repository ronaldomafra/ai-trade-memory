from datetime import UTC, datetime, timedelta

import httpx
import pytest

from poc.adapters.outbound.news import NewsSources
from poc.adapters.outbound.source_cache import SourceCache
from poc.domain.external import news_record

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


@pytest.mark.asyncio
async def test_marketaux_free_query_missing_key_partial_and_no_secret_in_results():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["limit"] == "3"
        assert "ETHUSDT" not in request.url.params["search"]
        assert request.url.params["api_token"] == "secret"
        return httpx.Response(
            200,
            json={
                "meta": {"found": 10, "returned": 1, "limit": 3, "page": 1},
                "data": [
                    {
                        "uuid": "one",
                        "title": "Ethereum upgrade",
                        "description": "Short report",
                        "source": "news.example",
                        "url": "https://news.example/one",
                        "published_at": "2026-10-12T11:00:00Z",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        absent = NewsSources(None, http, lambda: NOW)
        assert (await absent.marketaux("ETH"))["reason"] == "MARKETAUX_TOKEN_NOT_CONFIGURED"
        assert not calls
        source = NewsSources("secret", http, lambda: NOW)
        result = await source.marketaux("ETH")
        assert result["status"] == "PARTIAL" and len(result["items"]) == 1
        assert "secret" not in str(result)
        assert result["items"][0]["first_seen_at"].startswith("2026-10-12T12:")


@pytest.mark.asyncio
async def test_rss_normalization_and_missing_time_is_partial():
    xml = """<rss version="2.0"><channel><title>News</title><item><title>Ethereum</title>
    <link>https://news.example/one</link><description>Short report</description>
    <pubDate>Mon, 12 Oct 2026 11:00:00 GMT</pubDate></item>
    <item><title>Unknown time</title><link>https://news.example/two</link></item>
    </channel></rss>"""
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=xml))
    ) as http:
        result = await NewsSources(None, http, lambda: NOW).rss("https://news.example/rss")
        assert result["status"] == "PARTIAL" and len(result["items"]) == 1
        assert result["rejected_items"] == 1


def test_shared_source_slot_quota_and_restart_do_not_repeat_physical_collection(tmp_path):
    path = tmp_path / "cache.sqlite3"
    cache = SourceCache(path)
    first = cache.reserve("marketaux", {"asset": "ETH"}, NOW, 1800)
    assert first["granted"]
    cache.close()
    cache = SourceCache(path)
    assert (
        cache.reserve("marketaux", {"asset": "ETH"}, NOW, 1800)["reason"]
        == "COLLECTION_INDETERMINATE"
    )
    cache.finish(first["request_id"], {"status": "COMPLETE", "items": []}, NOW)
    reused = cache.reserve("marketaux", {"asset": "ETH"}, NOW, 1800)
    assert reused["cached"]["items"] == [] and not reused["granted"]
    for i in range(99):
        assert cache.reserve("marketaux", {"asset": str(i)}, NOW, 1800)["granted"]
    assert (
        cache.reserve("marketaux", {"asset": "next"}, NOW, 1800)["reason"]
        == "FREE_NEWS_QUOTA_EXHAUSTED"
    )
    assert cache.reserve("marketaux", {"asset": "next"}, NOW + timedelta(days=1), 1800)["granted"]
    cache.close()


def test_item_versions_first_seen_and_classification_cutoff_survive_reuse(tmp_path):
    cache = SourceCache(tmp_path / "cache.sqlite3")
    original = news_record(
        "Ethereum", "Upgrade", "https://news.example/a", "news.example", NOW, NOW, "rss"
    )
    stored = cache.save_item(original)
    reread = news_record(
        "Ethereum",
        "Upgrade",
        "https://news.example/a",
        "news.example",
        NOW,
        NOW + timedelta(hours=1),
        "rss",
    )
    assert cache.save_item(reread)["first_seen_at"] == stored["first_seen_at"]
    corrected = news_record(
        "Ethereum",
        "Upgrade postponed",
        "https://news.example/a",
        "news.example",
        NOW,
        NOW + timedelta(hours=2),
        "rss",
    )
    cache.save_item(corrected)
    assert cache.items(NOW + timedelta(hours=1))[0]["summary"] == "Upgrade"
    assert cache.items(NOW + timedelta(hours=3))[0]["summary"] == "Upgrade postponed"
    cache.save_classification("id", {"status": "READY"}, NOW)
    assert cache.classification("id", NOW - timedelta(seconds=1)) is None
    assert cache.classification("id", NOW)["status"] == "READY"
    cache.close()


@pytest.mark.asyncio
async def test_marketaux_reflected_credential_is_removed_from_text_url_and_headers():
    token = "synthetic-private-api-token"

    def response(request):
        return httpx.Response(
            200,
            headers={"x-ratelimit-extra": token},
            json={
                "meta": {"found": 1, "returned": 1},
                "data": [
                    {
                        "uuid": "example",
                        "title": "Ethereum report " + token,
                        "description": "Reflected data " + token,
                        "source": "news.example",
                        "url": "https://news.example/one?api_token=" + token,
                        "published_at": "2026-10-12T11:00:00Z",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        result = await NewsSources(token, http, lambda: NOW).marketaux("ETH")
        assert token not in str(result)
        assert "api_token" not in result["items"][0]["url"]
        assert result["quota_headers"]["x-ratelimit-extra"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_marketaux_query_scope_uses_configured_window():
    def response(request):
        assert request.url.params["published_after"] == "2026-10-12T10:00:00"
        return httpx.Response(200, json={"meta": {"found": 0, "returned": 0}, "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        result = await NewsSources("synthetic-token", http, lambda: NOW).marketaux("ETH", 2)
        assert result["scope"]["lookback_hours"] == 2 and result["status"] == "COMPLETE"
