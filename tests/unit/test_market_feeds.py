from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import httpx
import pytest

from poc.adapters.outbound.market import BinancePublic, parse_kline, parse_stream
from poc.application.market_state import prefer_quote
from poc.domain.models import Quote
from poc.domain.primitives import DomainError

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def ms(at):
    return int(at.timestamp()) * 1000


def kline(at):
    return [
        ms(at),
        "3000",
        "3010",
        "2990",
        "3005",
        "10",
        ms(at + timedelta(minutes=15)) - 1,
        "30000",
        10,
        "5",
        "15000",
        "0",
    ]


def test_rest_kline_window_and_open_candle_exclusion():
    closed = parse_kline(kline(NOW - timedelta(minutes=15)), "ETHUSDT", "15m", NOW)
    opened = parse_kline(kline(NOW), "ETHUSDT", "15m", NOW)
    assert closed.is_closed and not opened.is_closed
    assert closed.close_time_exclusive == NOW and closed.available_at == NOW
    assert closed.close == D("3005")


def test_stream_uses_closed_flag_and_has_no_invented_book_event_time():
    q = parse_stream(
        {"u": 12, "s": "ETHUSDT", "b": "3000", "B": "2", "a": "3001", "A": "2"}, "ETHUSDT", NOW
    )
    assert q.event_at is None and q.update_id == 12
    event = {
        "e": "kline",
        "s": "ETHUSDT",
        "k": {
            "i": "15m",
            "t": ms(NOW - timedelta(minutes=15)),
            "T": ms(NOW) - 1,
            "o": "3000",
            "h": "3010",
            "l": "2990",
            "c": "3005",
            "v": "10",
            "x": False,
        },
    }
    assert parse_stream(event, "ETHUSDT", NOW) is None
    event["k"]["x"] = True
    assert parse_stream({"stream": "ethusdt@kline_15m", "data": event}, "ETHUSDT", NOW).is_closed
    with pytest.raises(DomainError):
        parse_stream(
            {"u": 13, "s": "BTCUSDT", "b": "3000", "B": "2", "a": "3001", "A": "2"}, "ETHUSDT", NOW
        )


def test_stale_rest_result_or_duplicate_update_cannot_renew_quote():
    old = Quote("q1", "ETHUSDT", D("3000"), D("3001"), NOW, NOW, "binance_ws", update_id=12)
    late_rest = Quote(
        "q2",
        "ETHUSDT",
        D("2990"),
        D("2991"),
        NOW + timedelta(seconds=2),
        NOW + timedelta(seconds=2),
        "binance_rest",
        request_started_at=NOW - timedelta(seconds=1),
    )
    assert prefer_quote(old, late_rest) == old
    duplicate = Quote(
        "q1",
        old.symbol,
        old.bid,
        old.ask,
        NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=1),
        "binance_ws",
        update_id=12,
    )
    assert prefer_quote(old, duplicate) == old
    current = Quote(
        "q3",
        old.symbol,
        old.bid,
        old.ask,
        NOW + timedelta(seconds=1),
        NOW + timedelta(seconds=1),
        "binance_ws",
        update_id=13,
    )
    assert prefer_quote(old, current) == current


@pytest.mark.asyncio
async def test_rest_quote_and_pagination_are_public_and_bounded():
    observed = []

    def reply(request):
        observed.append(request)
        if request.url.path.endswith("bookTicker"):
            return httpx.Response(
                200,
                json={
                    "symbol": "ETHUSDT",
                    "bidPrice": "3000",
                    "bidQty": "2",
                    "askPrice": "3001",
                    "askQty": "2",
                },
            )
        return httpx.Response(200, json=[kline(NOW - timedelta(minutes=15)), kline(NOW)])

    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        source = BinancePublic(client, now=lambda: NOW)
        q = await source.quote("ETHUSDT")
        assert q.event_at is None and q.bid_qty == 2
        rows = await source.candles("ETHUSDT", "15m", 600)
        assert len(rows) == 1 and rows[0].close_time_exclusive == NOW
    assert all(r.method == "GET" for r in observed)
    assert observed[-1].url.params["limit"] == "601"
