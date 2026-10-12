from datetime import UTC, datetime
from decimal import Decimal as D

import httpx
import pytest

from poc.adapters.outbound.market import BinancePublic, parse_metadata, quantity_step
from poc.domain.primitives import DomainError


def payload(symbol="ETHUSDT", base="ETH", step="0.0001"):
    return {
        "symbols": [
            {
                "symbol": symbol,
                "baseAsset": base,
                "quoteAsset": "USDT",
                "status": "TRADING",
                "isSpotTradingAllowed": True,
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": step, "minQty": step, "maxQty": "10000"},
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "stepSize": "0",
                        "minQty": "0",
                        "maxQty": "5000",
                    },
                    {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True},
                ],
            }
        ]
    }


def test_metadata_is_generic_and_uses_applicable_filters():
    m = parse_metadata(payload(), "ETHUSDT", datetime.now(UTC))
    assert m.base_asset == "ETH"
    assert m.qty_step == D("0.0001")
    assert m.max_qty == D("5000")
    assert m.min_notional_usdt == D("5")
    assert quantity_step([D("0.005"), D("0.002")]) == D("0.010")


@pytest.mark.parametrize(
    "change",
    [
        {"status": "BREAK"},
        {"isSpotTradingAllowed": False},
        {"quoteAsset": "BTC"},
        {"baseAsset": "BTC"},
        {"filters": []},
    ],
)
def test_inactive_nonspot_or_invalid_filters_rejected(change):
    p = payload()
    p["symbols"][0].update(change)
    with pytest.raises(DomainError):
        parse_metadata(p, "ETHUSDT", datetime.now(UTC))


def test_notional_flag_is_not_assumed():
    p = payload()
    del p["symbols"][0]["filters"][2]["applyToMarket"]
    with pytest.raises(DomainError, match="semantics"):
        parse_metadata(p, "ETHUSDT", datetime.now(UTC))


@pytest.mark.asyncio
async def test_public_transport_has_no_order_or_authenticated_paths():
    observed = []

    def response(request):
        observed.append(request)
        return httpx.Response(200, json=payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        source = BinancePublic(client)
        assert (await source.metadata("ETHUSDT")).base_asset == "ETH"
        with pytest.raises(DomainError):
            await source.get("/api/v3/order")
        with pytest.raises(DomainError):
            await source.get("/api/v3/account")
        with pytest.raises(DomainError):
            await source.get("/api/v3/klines", {"signature": "unusable"})
    assert len(observed) == 1
    assert observed[0].method == "GET"
    assert observed[0].url.host == "data-api.binance.vision"
    assert "Authorization" not in observed[0].headers
