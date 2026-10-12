from datetime import timedelta

import httpx
import pytest
from test_cycles_engine import Clock
from test_prediction_quality import CONDITION, NOW, market

from poc.adapters.outbound.polymarket import PolymarketPublic
from poc.adapters.outbound.source_cache import SourceCache
from poc.config import Config
from poc.domain.prediction import probability_changes
from poc.domain.primitives import iso


@pytest.mark.asyncio
async def test_book_and_trade_shared_slots_restart_and_history_do_not_refresh_source_times(
    tmp_path,
):
    clock = Clock(NOW)
    calls = []

    def response(request):
        calls.append(str(request.url.copy_with(query=None)))
        if request.url.path == "/book":
            return httpx.Response(
                200,
                json={
                    "market": CONDITION,
                    "asset_id": "11",
                    "timestamp": str(int(clock.now().timestamp()) * 1000),
                    "bids": [{"price": "0.49", "size": "3000"}],
                    "asks": [{"price": "0.51", "size": "3000"}],
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "condition_id": CONDITION,
                        "token_id": "11",
                        "timestamp": int(clock.now().timestamp()),
                        "price": "0.50",
                        "size": "2",
                    }
                ]
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(response))
    cache = SourceCache(tmp_path / "sources.sqlite3")
    adapter = PolymarketPublic(Config().polymarket, cache, clock, client=http)
    metadata = market()
    try:
        first = await adapter.book(metadata)
        first_trade = await adapter.recent_trade(metadata)
        cache.close()
        cache = SourceCache(tmp_path / "sources.sqlite3")
        resumed = PolymarketPublic(Config().polymarket, cache, clock, client=http)
        clock.at += timedelta(seconds=40)
        assert await resumed.book(metadata) == first
        assert await resumed.recent_trade(metadata) == first_trade
        assert len(calls) == 2
        scope = {"condition_id": CONDITION, "token_id": "11"}
        assert not cache.history("poly_book", scope, NOW - timedelta(microseconds=1))
        assert cache.history("poly_book", scope, NOW)[0]["value"] == first
        clock.at += timedelta(minutes=5)
        second = await resumed.book(metadata)
        assert len(calls) == 3 and second["observed_at"] != first["observed_at"]
        changes = probability_changes(
            second, cache.history("poly_book", scope, clock.now()), clock.now(), Config().polymarket
        )
        assert changes["5m"]["change_pp"] == "0.00"
        assert changes["60m"]["status"] == "UNAVAILABLE"
    finally:
        cache.close()
        await http.aclose()


def test_delta_excludes_future_mismatched_stale_or_wide_references():
    current = {
        "condition_id": CONDITION,
        "token_id": "11",
        "source_at": iso(NOW),
        "observed_at": iso(NOW),
        "midpoint": "0.52",
    }
    previous = {
        **current,
        "source_at": iso(NOW - timedelta(hours=1)),
        "observed_at": iso(NOW - timedelta(hours=1)),
        "midpoint": "0.50",
        "spread_pp": "2",
    }
    valid = {"value": previous, "available_at": previous["observed_at"]}
    result = probability_changes(current, [valid], NOW, Config().polymarket)
    assert result["60m"]["change_pp"] == "2.00"
    for invalid in (
        {**valid, "available_at": iso(NOW + timedelta(seconds=1))},
        {**valid, "value": {**previous, "token_id": "12"}},
        {**valid, "value": {**previous, "spread_pp": "2.01"}},
        {**valid, "value": {**previous, "source_at": iso(NOW - timedelta(hours=2))}},
    ):
        assert (
            probability_changes(current, [invalid], NOW, Config().polymarket)["60m"]["status"]
            == "UNAVAILABLE"
        )
