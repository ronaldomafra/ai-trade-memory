"""Public, GET-only Gamma/CLOB/Data adapters. No trading SDK or wallet credentials."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from poc.adapters.outbound.source_cache import SourceCache
from poc.application.ports import Clock
from poc.config import Polymarket
from poc.domain.external import ALIASES
from poc.domain.prediction import normalize_book, normalize_market
from poc.domain.primitives import DomainError, decimal, iso, stable_id

PUBLIC_PATHS = {
    ("https://gamma-api.polymarket.com", "/markets"),
    ("https://clob.polymarket.com", "/book"),
    ("https://data-api.polymarket.com", "/v2/trades"),
}


class PolymarketPublic:
    def __init__(
        self,
        config: Polymarket,
        cache: SourceCache,
        clock: Clock,
        proxy: str | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.config, self.cache, self.clock = config, cache, clock
        self.client = client or httpx.AsyncClient(
            proxy=proxy, timeout=15, follow_redirects=False, trust_env=False
        )
        self.owns_client = client is None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    async def get(self, base: str, path: str, params: dict) -> dict | list:
        if (base, path) not in PUBLIC_PATHS and not (
            base == "https://gamma-api.polymarket.com"
            and re.fullmatch(r"/tags/slug/[a-z0-9-]{1,64}", path)
        ):
            raise DomainError("Only allowlisted public prediction-market reads are permitted")
        response = await self.client.get(base + path, params=params)
        if response.status_code != 200:
            raise DomainError(f"POLYMARKET_HTTP_{response.status_code}")
        if len(response.content) > 4 * 1024 * 1024:
            raise DomainError("Prediction-market response exceeds 4 MB")
        return json.loads(response.content, parse_float=Decimal)

    async def _tag(self, slug: str) -> tuple[dict, bool]:
        scope = {"policy": "gamma_asset_tags_v3", "slug": slug}
        slot = self.cache.reserve(
            "poly_tag", scope, self.clock.now(), self.config.markets_poll_minutes * 60
        )
        if not slot["granted"]:
            return slot.get("cached") or {"status": "UNAVAILABLE"}, False
        try:
            raw = await self.get("https://gamma-api.polymarket.com", "/tags/slug/" + slug, {})
            if (
                not isinstance(raw, dict)
                or raw.get("slug") != slug
                or not str(raw.get("id", "")).isdecimal()
            ):
                raise DomainError("Invalid public asset tag identity")
            result = {
                "status": "COMPLETE",
                "id": str(raw["id"]),
                "slug": slug,
                "label": str(raw.get("label", slug)),
                "observed_at": iso(self.clock.now()),
            }
        except Exception as error:
            result = {"status": "UNAVAILABLE", "reason": type(error).__name__}
        self.cache.finish(slot["request_id"], result, self.clock.now())
        return result, True

    async def discover(self, base_asset: str) -> dict:
        markets, reasons, observations = [], [], []
        attempted, rejected, lookups = 0, 0, 0
        themes = []
        cap = self.config.discovery_max_requests_per_refresh
        asset_slug = ALIASES.get(base_asset, (base_asset.lower(),))[0]
        for kind, slug in (("ASSET", asset_slug), ("MACRO", "interest-rates")):
            if lookups >= cap:
                reasons.append("DISCOVERY_TAG_REQUEST_LIMIT")
                break
            tag, sent = await self._tag(slug)
            lookups += 1
            attempted += int(sent)
            if tag["status"] != "COMPLETE" and kind == "ASSET" and lookups < cap:
                reasons.append("ASSET_TAG_UNAVAILABLE_CRYPTO_FALLBACK")
                tag, sent = await self._tag("crypto")
                lookups += 1
                attempted += int(sent)
            if tag["status"] == "COMPLETE":
                aliases = (
                    (base_asset, tag["label"], base_asset + "USDT")
                    if kind == "ASSET" and tag["slug"] != "crypto"
                    else ()
                )
                themes.append(
                    {
                        "kind": kind,
                        "tag": tag,
                        "offset": 0,
                        "complete": False,
                        "stopped": False,
                        "aliases": aliases,
                    }
                )
            else:
                reasons.append("DISCOVERY_TAG_UNAVAILABLE_" + slug)
        seen = set()
        cursor = 0
        for _ in range(max(0, cap - lookups)):
            pending = [theme for theme in themes if not theme["complete"] and not theme["stopped"]]
            if not pending:
                break
            theme = pending[cursor % len(pending)]
            cursor += 1
            tag = theme["tag"]
            scope = {
                "policy": "gamma_asset_tags_dollar_v3",
                "tag_id": tag["id"],
                "offset": theme["offset"],
                "page_size": self.config.discovery_page_size,
                "subject_aliases": theme["aliases"],
                "order": "volume24hr",
                "version": "v1",
            }
            slot = self.cache.reserve(
                "poly_discovery", scope, self.clock.now(), self.config.markets_poll_minutes * 60
            )
            if not slot["granted"]:
                result = slot.get("cached")
                if result is None:
                    theme["stopped"] = True
                    reasons.append(slot["reason"])
                    continue
            else:
                attempted += 1
                try:
                    raw = await self.get(
                        "https://gamma-api.polymarket.com",
                        "/markets",
                        {
                            "active": "true",
                            "closed": "false",
                            "version": "v1",
                            "tag_id": tag["id"],
                            "include_tag": "true",
                            "limit": self.config.discovery_page_size,
                            "offset": theme["offset"],
                            "order": "volume24hr",
                            "ascending": "false",
                        },
                    )
                    if not isinstance(raw, list) or len(raw) > self.config.discovery_page_size:
                        raise DomainError("Invalid discovery page schema")
                    normalized, invalid = [], 0
                    for item in raw:
                        try:
                            normalized.append(
                                normalize_market(
                                    item,
                                    self.clock.now(),
                                    "GAMMA_NUM_DOLLAR_FIELDS_V1",
                                    theme["aliases"],
                                )
                            )
                        except (ValueError, TypeError, KeyError):
                            invalid += 1
                    result = {
                        "status": "COMPLETE" if not invalid else "PARTIAL",
                        "markets": normalized,
                        "raw_count": len(raw),
                        "rejected": invalid,
                        "observed_at": iso(self.clock.now()),
                    }
                except Exception as error:
                    result = {
                        "status": "UNAVAILABLE",
                        "markets": [],
                        "raw_count": 0,
                        "rejected": 0,
                        "reason": type(error).__name__,
                        "observed_at": iso(self.clock.now()),
                    }
                self.cache.finish(slot["request_id"], result, self.clock.now())
            if result["status"] == "UNAVAILABLE":
                theme["stopped"] = True
                reasons.append(result.get("reason", "DISCOVERY_FAILURE"))
                continue
            rejected += result.get("rejected", 0)
            if result.get("observed_at"):
                observations.append(result["observed_at"])
            progress = 0
            for item in result["markets"]:
                if item["market_id"] not in seen:
                    seen.add(item["market_id"])
                    markets.append(item)
                    progress += 1
            if result["raw_count"] and not progress:
                theme["stopped"] = True
                reasons.append("DISCOVERY_PAGE_NO_PROGRESS")
            elif result["raw_count"] < self.config.discovery_page_size:
                theme["complete"] = result.get("rejected", 0) == 0
                theme["stopped"] = not theme["complete"]
            theme["offset"] += self.config.discovery_page_size
        complete = (
            bool(themes) and all(t["complete"] for t in themes) and not reasons and rejected == 0
        )
        if not complete:
            reasons.append("DISCOVERY_PARTIAL_OR_REQUEST_LIMIT")
        return {
            "status": "COMPLETE" if complete else "PARTIAL",
            "observed_at": max(observations) if observations else None,
            "markets": markets,
            "requests_this_process": attempted,
            "rejected_items": rejected,
            "complete": complete,
            "reasons": list(dict.fromkeys(reasons)),
            "scope": {
                "base_asset": base_asset,
                "active": True,
                "closed": False,
                "max_requests": cap,
                "page_size": self.config.discovery_page_size,
                "coverage": "ASSET_AND_INTEREST_RATE_TAGS_ONLY",
                "themes": [
                    {
                        "kind": t["kind"],
                        "tag_id": t["tag"]["id"],
                        "slug": t["tag"]["slug"],
                        "complete": t["complete"],
                    }
                    for t in themes
                ],
            },
        }

    async def book(self, market: dict) -> dict:
        return await self._snapshot("poly_book", market, lambda: self._book(market))

    async def _snapshot(self, provider: str, market: dict, collect):
        scope = {"condition_id": market["condition_id"], "token_id": market["token_id"]}
        slot = self.cache.reserve(
            provider, scope, self.clock.now(), self.config.prices_poll_minutes * 60
        )
        if not slot["granted"]:
            cached = slot.get("cached")
            if cached is None or cached.get("status") != "COMPLETE":
                raise DomainError("Public prediction snapshot is pending or unavailable")
            return cached["value"]
        try:
            value = await collect()
        except Exception as error:
            self.cache.finish(
                slot["request_id"],
                {"status": "UNAVAILABLE", "reason": type(error).__name__},
                self.clock.now(),
            )
            raise
        self.cache.finish(
            slot["request_id"],
            {"status": "COMPLETE", "value": value, "observed_at": iso(self.clock.now())},
            self.clock.now(),
        )
        return value

    async def _book(self, market: dict) -> dict:
        raw = await self.get(
            "https://clob.polymarket.com", "/book", {"token_id": market["token_id"]}
        )
        return normalize_book(raw, market, self.clock.now())

    async def recent_trade(self, market: dict) -> dict | None:
        return await self._snapshot("poly_trade", market, lambda: self._recent_trade(market))

    async def _recent_trade(self, market: dict) -> dict | None:
        raw = await self.get(
            "https://data-api.polymarket.com",
            "/v2/trades",
            {"condition": market["condition_id"], "limit": 100},
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
            raise DomainError("Invalid public trade envelope")
        candidates = []
        for row in raw["data"]:
            if (
                row.get("condition_id") != market["condition_id"]
                or row.get("token_id") != market["token_id"]
            ):
                continue
            try:
                stamp = decimal(row["timestamp"])
                price, size = decimal(row["price"]), decimal(row["size"])
                if (
                    stamp != stamp.to_integral_value()
                    or not Decimal("1000000000") <= stamp < Decimal("10000000000")
                    or not 0 < price < 1
                    or size <= 0
                ):
                    continue
                at = datetime.fromtimestamp(int(stamp), UTC)
                if at > self.clock.now():
                    continue
                candidates.append(
                    {
                        "source_at": iso(at),
                        "observed_at": iso(self.clock.now()),
                        "token_id": market["token_id"],
                        "condition_id": market["condition_id"],
                        "price": str(price),
                        "shares": str(size),
                        "trade_id": stable_id(row),
                    }
                )
            except (ValueError, KeyError, TypeError):
                continue
        return max(candidates, key=lambda row: row["source_at"]) if candidates else None
