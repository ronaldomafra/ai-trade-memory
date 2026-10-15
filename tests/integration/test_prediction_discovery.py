import httpx
import pytest
from test_accounting import NOW
from test_cycles_engine import Clock

from poc.adapters.outbound.polymarket import PolymarketPublic
from poc.adapters.outbound.source_cache import SourceCache
from poc.config import Config


def tag_response(request):
    slug = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(
        200,
        json={
            "id": {"bitcoin": "1", "ethereum": "39", "interest-rates": "131"}[slug],
            "slug": slug,
            "label": slug,
        },
    )


def row(identity):
    return {
        "id": str(identity),
        "conditionId": "0x" + "a" * 64,
        "question": "Ethereum price?",
        "outcomes": ["Yes", "No"],
        "clobTokenIds": ["11", "12"],
        "events": [{"id": "one"}],
        "active": True,
        "closed": False,
        "enableOrderBook": True,
        "version": "v1",
        "liquidityNum": "10000",
        "volume24hr": "1000",
    }


@pytest.mark.asyncio
async def test_discovery_targets_asset_shares_macro_and_preserves_five_request_cap(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        if request.url.path.startswith("/tags/slug/"):
            return tag_response(request)
        assert request.url.params["order"] == "volume24hr"
        assert request.url.params["version"] == "v1"
        tag = int(request.url.params["tag_id"])
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=[row(tag * 100000 + offset + i) for i in range(100)])

    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        first = await PolymarketPublic(
            Config().polymarket, cache, Clock(NOW), client=http
        ).discover("BTC")
        assert len(requests) == 5 and len(first["markets"]) == 300 and not first["complete"]
        assert first["markets"][0]["metric_unit_contract"] == "REPORTED_USD_V1"
        cache.close()
        cache = SourceCache(tmp_path / "cache.sqlite3")
        resumed = PolymarketPublic(Config().polymarket, cache, Clock(NOW), client=http)
        second = await resumed.discover("ETH")
        assert len(requests) == 8 and second["requests_this_process"] == 3
        assert {t["slug"] for t in second["scope"]["themes"]} == {"ethereum", "interest-rates"}
        assert any(m["market_id"].startswith("3900000") for m in second["markets"])
        shared1 = {m["market_id"]: m for m in first["markets"] if m["market_id"].startswith("131")}
        shared2 = {m["market_id"]: m for m in second["markets"] if m["market_id"].startswith("131")}
        assert shared1 == shared2
        assert (await resumed.discover("ETH"))["requests_this_process"] == 0
        assert len(requests) == 8
    cache.close()


@pytest.mark.asyncio
async def test_discovery_stops_repeated_page_without_claiming_complete_coverage(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.startswith("/tags/slug/"):
            return tag_response(request)
        if request.url.params["tag_id"] == "131":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[row("one")] * 100)

    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PolymarketPublic(Config().polymarket, cache, Clock(NOW), client=http)
        result = await client.discover("ETH")
        assert len(calls) == 5 and not result["complete"]
        assert "DISCOVERY_PAGE_NO_PROGRESS" in result["reasons"]
        assert len(result["markets"]) == 1
        assert not (await client.discover("ETH"))["complete"]
        assert len(calls) == 5
    cache.close()


@pytest.mark.asyncio
async def test_missing_asset_tag_falls_back_without_inventing_complete_asset_coverage(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/unknown"):
            return httpx.Response(404)
        if request.url.path.endswith("/crypto"):
            return httpx.Response(200, json={"id": "21", "slug": "crypto", "label": "Crypto"})
        if request.url.path.startswith("/tags/slug/"):
            return tag_response(request)
        return httpx.Response(200, json=[])

    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await PolymarketPublic(
            Config().polymarket, cache, Clock(NOW), client=http
        ).discover("UNKNOWN")
        assert len(calls) == 5 and not result["complete"]
        assert "ASSET_TAG_UNAVAILABLE_CRYPTO_FALLBACK" in result["reasons"]
    cache.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cap", [1, 2, 3, 4, 5])
async def test_discovery_cap_includes_tag_metadata_and_market_reads(tmp_path, cap):
    calls = []

    def handler(request):
        calls.append(request)
        return (
            tag_response(request)
            if request.url.path.startswith("/tags/slug/")
            else httpx.Response(200, json=[])
        )

    cfg = Config().polymarket.model_copy(update={"discovery_max_requests_per_refresh": cap})
    cache = SourceCache(tmp_path / "cache.sqlite3")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PolymarketPublic(cfg, cache, Clock(NOW), client=http)
        result = await client.discover("ETH")
        assert len(calls) <= cap and result["requests_this_process"] == len(calls)
        before = len(calls)
        assert (await client.discover("ETH"))["requests_this_process"] == 0
        assert len(calls) == before
    cache.close()
