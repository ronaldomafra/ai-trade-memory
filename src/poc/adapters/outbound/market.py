"""Allowlisted GET-only Binance market adapter; no account or trading methods."""

import asyncio
import json
import random
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from math import lcm
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from poc.domain.candles import INTERVAL_SECONDS, Candle
from poc.domain.models import MarketMetadata, MarketNotice, Quote
from poc.domain.primitives import DomainError, decimal, iso, stable_id, utc

PUBLIC_URL = "https://data-api.binance.vision"
PUBLIC_PATHS = frozenset(
    {"/api/v3/exchangeInfo", "/api/v3/klines", "/api/v3/ticker/bookTicker", "/api/v3/time"}
)


def quantity_step(steps: list[Decimal]) -> Decimal:
    if not steps or any(s <= 0 for s in steps):
        raise DomainError("No usable quantity step")
    fractions = [Fraction(s) for s in steps]
    denominator = lcm(*(f.denominator for f in fractions))
    numerator = lcm(*(f.numerator * (denominator // f.denominator) for f in fractions))
    return Decimal(numerator) / Decimal(denominator)


def parse_metadata(payload: dict[str, Any], symbol: str, now: datetime) -> MarketMetadata:
    entries = [r for r in payload.get("symbols", []) if r.get("symbol") == symbol]
    if len(entries) != 1:
        raise DomainError("Symbol missing or ambiguous in public exchangeInfo")
    raw = entries[0]
    if raw.get("status") != "TRADING" or raw.get("isSpotTradingAllowed") is not True:
        raise DomainError("Symbol is not active Spot")
    if raw.get("quoteAsset") != "USDT":
        raise DomainError("Only USDT quoted Spot pairs are supported")
    filters = {f["filterType"]: f for f in raw.get("filters", [])}
    lot = filters.get("LOT_SIZE")
    if not lot:
        raise DomainError("Missing quantity filter")
    steps, mins, maxs = [], [], []
    for f in (lot, filters.get("MARKET_LOT_SIZE")):
        if f is None:
            continue
        step, minimum, maximum = (decimal(f[k]) for k in ("stepSize", "minQty", "maxQty"))
        if step > 0:
            steps.append(step)
        if minimum < 0 or maximum <= 0:
            raise DomainError("Invalid market quantity filter")
        mins.append(minimum)
        maxs.append(maximum)
    lower, upper = [], []
    notional_found = False
    if "MIN_NOTIONAL" in filters:
        notional_found = True
        f = filters["MIN_NOTIONAL"]
        if not isinstance(f.get("applyToMarket"), bool):
            raise DomainError("Unverifiable minimum notional semantics")
        if f["applyToMarket"]:
            lower.append(decimal(f["minNotional"]))
    if "NOTIONAL" in filters:
        notional_found = True
        f = filters["NOTIONAL"]
        if not isinstance(f.get("applyMinToMarket"), bool) or not isinstance(
            f.get("applyMaxToMarket"), bool
        ):
            raise DomainError("Unverifiable notional semantics")
        if f["applyMinToMarket"]:
            lower.append(decimal(f["minNotional"]))
        if f["applyMaxToMarket"]:
            upper.append(decimal(f["maxNotional"]))
    if not notional_found:
        raise DomainError("Missing notional filter contract")
    return MarketMetadata(
        symbol,
        raw["baseAsset"],
        raw["quoteAsset"],
        quantity_step(steps),
        max(mins),
        min(maxs),
        max(lower, default=Decimal(0)),
        min(upper) if upper else None,
        now,
        {"provider": "binance_public", "record": raw, "fixture": False},
    )


class BinancePublic:
    def __init__(
        self, client: httpx.AsyncClient | None = None, now: Callable[[], datetime] | None = None
    ):
        self.client = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
        self.owns_client = client is None
        self.now = now or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        if self.owns_client:
            await self.client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if path not in PUBLIC_PATHS:
            raise DomainError("Only allowlisted public market GET paths are permitted")
        if params and any("key" in k.lower() or "signature" in k.lower() for k in params):
            raise DomainError("Authentication parameters are not permitted")
        response = await self.client.get(PUBLIC_URL + path, params=params)
        response.raise_for_status()
        return response.json()

    async def metadata(self, symbol: str) -> MarketMetadata:
        payload = await self.get("/api/v3/exchangeInfo", {"symbol": symbol})
        return parse_metadata(payload, symbol, self.now())

    async def quote(self, symbol: str) -> Quote:
        started = self.now()
        payload = await self.get("/api/v3/ticker/bookTicker", {"symbol": symbol})
        received = self.now()
        try:
            if payload["symbol"] != symbol:
                raise DomainError("Quote symbol differs from request")
            return Quote(
                stable_id("binance_rest", symbol, iso(received), payload),
                symbol,
                decimal(payload["bidPrice"]),
                decimal(payload["askPrice"]),
                received,
                received,
                "binance_rest",
                request_started_at=started,
                bid_qty=decimal(payload["bidQty"]),
                ask_qty=decimal(payload["askQty"]),
            )
        except (KeyError, TypeError) as exc:
            raise DomainError("Malformed public quote") from exc

    async def candles(
        self, symbol: str, interval: str, limit: int = 600, start_at: datetime | None = None
    ) -> list[Candle]:
        if interval not in INTERVAL_SECONDS or not 1 <= limit <= 1000:
            raise DomainError("Invalid candle query")
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit + 1, 1000),
        }
        if start_at is not None:
            params["startTime"] = int(utc(start_at).timestamp() * 1000)
        payload = await self.get("/api/v3/klines", params)
        if not isinstance(payload, list):
            raise DomainError("Malformed public candles")
        received = self.now()
        rows = [parse_kline(row, symbol, interval, received) for row in payload]
        return [row for row in rows if row.is_closed][-limit:]

    async def server_time(self) -> datetime:
        payload = await self.get("/api/v3/time")
        return from_milliseconds(payload["serverTime"])

    async def stream(
        self, symbol: str, stop: asyncio.Event
    ) -> AsyncIterator[Quote | Candle | MarketNotice]:
        lower = symbol.lower()
        url = (
            "wss://data-stream.binance.vision:443/stream?streams="
            f"{lower}@bookTicker/{lower}@kline_15m/{lower}@kline_1h"
        )
        delay = 1.0
        while not stop.is_set():
            try:
                async with connect(
                    url,
                    proxy=None,
                    open_timeout=10,
                    close_timeout=5,
                    ping_interval=None,
                    max_size=1024 * 1024,
                    max_queue=32,
                ) as websocket:
                    connected = asyncio.get_running_loop().time()
                    yield MarketNotice("CONNECTED", self.now())
                    while not stop.is_set():
                        raw = await asyncio.wait_for(websocket.recv(), timeout=45)
                        payload = json.loads(raw)
                        data = payload.get("data", payload)
                        if data.get("e") == "serverShutdown":
                            yield MarketNotice("DISCONNECTED", self.now(), "SERVER_SHUTDOWN")
                            break
                        try:
                            event = parse_stream(payload, symbol, self.now())
                        except DomainError:
                            yield MarketNotice("INVALID_MESSAGE", self.now(), "INVALID_MARKET_DATA")
                            continue
                        if event is not None:
                            yield event
                            delay = 1.0
                        if asyncio.get_running_loop().time() - connected >= 23.5 * 3600:
                            yield MarketNotice("DISCONNECTED", self.now(), "PLANNED_RENEWAL")
                            break
            except (OSError, TimeoutError, WebSocketException, ValueError, TypeError) as exc:
                yield MarketNotice("DISCONNECTED", self.now(), type(exc).__name__)
            if not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), delay + random.uniform(0, delay * 0.1))
                except TimeoutError:
                    pass
                delay = min(delay * 2, 60)


def from_milliseconds(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainError("Expected an integer timestamp in milliseconds")
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value)
    except (ValueError, OverflowError) as exc:
        raise DomainError("Invalid timestamp unit or range") from exc


def parse_kline(row: list[Any], symbol: str, interval: str, received: datetime) -> Candle:
    try:
        opened = from_milliseconds(row[0])
        closed = opened + timedelta(seconds=INTERVAL_SECONDS[interval])
        if from_milliseconds(row[6]) + timedelta(milliseconds=1) != closed:
            raise DomainError("Kline close does not match exclusive interval window")
        return Candle(
            symbol,
            interval,
            opened,
            closed,
            *[decimal(row[i]) for i in range(1, 6)],
            received,
            "binance_rest",
            is_closed=closed <= utc(received),
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise DomainError("Malformed public kline") from exc


def parse_stream(payload: dict[str, Any], symbol: str, received: datetime) -> Quote | Candle | None:
    try:
        data = payload.get("data", payload)
        if data.get("s") != symbol:
            raise DomainError("Stream symbol differs from subscription")
        if "k" in data:
            k = data["k"]
            if not isinstance(k.get("x"), bool):
                raise DomainError("Invalid closed-candle flag")
            if not k["x"]:
                return None
            row = [k["t"], k["o"], k["h"], k["l"], k["c"], k["v"], k["T"]]
            parsed = parse_kline(row, symbol, k["i"], received)
            if not parsed.is_closed:
                raise DomainError("Stream claims a future candle is closed")
            from dataclasses import replace

            return replace(parsed, source="binance_ws")
        update = data["u"]
        if isinstance(update, bool) or not isinstance(update, int) or update < 0:
            raise DomainError("Invalid book update identity")
        return Quote(
            stable_id("binance_ws", symbol, update),
            symbol,
            decimal(data["b"]),
            decimal(data["a"]),
            received,
            received,
            "binance_ws",
            event_at=from_milliseconds(data["E"]) if "E" in data else None,
            update_id=update,
            bid_qty=decimal(data["B"]),
            ask_qty=decimal(data["A"]),
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise DomainError("Malformed public market message") from exc
