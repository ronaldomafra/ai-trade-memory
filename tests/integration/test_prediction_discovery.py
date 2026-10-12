import httpx
import pytest
from test_accounting import NOW
from test_cycles_engine import Clock

from poc.adapters.outbound.polymarket import PolymarketPublic
from poc.adapters.outbound.source_cache import SourceCache
from poc.config import Config


@pytest.mark.asyncio
async def test_discovery_requests_persist_and_are_shared_across_assets_and_restart(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        offset = int(request.url.params["offset"])
        rows = [
            {
                "id": str(offset + i),
                "conditionId": "0x" + "a" * 64,
                "question": "Bitcoin price?",
                "outcomes": '["Yes","No"]',
                "clobTokenIds": '["11","12"]',
                "events": [{"id": "one", "slug": "bitcoin-price"}],
                "active": True,
                "closed": False,
                "enableOrderBook": True,
                "liquidityClob": "10000",
                "volume24hrClob": "1000",
            }
            for i in range(100)
        ]
        return httpx.Response(200, json=rows)

    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PolymarketPublic(Config().polymarket, cache, Clock(NOW), client=http)
        first = await client.discover("BTC")
        assert len(requests) == 5 and len(first["markets"]) == 500 and not first["complete"]
        assert first["status"] == "PARTIAL"
        cache.close()
        cache = SourceCache(tmp_path / "cache.sqlite3")
        resumed = PolymarketPublic(Config().polymarket, cache, Clock(NOW), client=http)
        second = await resumed.discover("ETH")
        assert len(requests) == 5 and second["requests_this_process"] == 0
        assert second["markets"][0]["observed_at"] == first["markets"][0]["observed_at"]
    cache.close()


@pytest.mark.asyncio
async def test_discovery_stops_repeated_page_without_claiming_complete_coverage(tmp_path):
    calls = []
    row = {
        "id": "one",
        "conditionId": "0x" + "a" * 64,
        "question": "Ethereum upgrade?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": ["11", "12"],
        "events": [{"id": "event"}],
        "active": True,
        "closed": False,
        "enableOrderBook": True,
    }

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[row] * 100)

    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PolymarketPublic(Config().polymarket, cache, Clock(NOW), client=http)
        result = await client.discover("ETH")
        assert len(calls) == 2 and not result["complete"]
        assert "DISCOVERY_PAGE_NO_PROGRESS" in result["reasons"]
        assert len(result["markets"]) == 1
        assert not (await client.discover("ETH"))["complete"]
        assert len(calls) == 2  # Reuse the interrupted revision, without spending three more pages.
    cache.close()
