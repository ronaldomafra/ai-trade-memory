"""Marketaux free plan and RSS adapters. Credentials never enter returned records."""

import calendar
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from poc.domain.external import ALIASES, news_record
from poc.domain.primitives import DomainError, iso, utc


class NewsSources:
    def __init__(
        self,
        token: str | None,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.token = token
        self.client = client or httpx.AsyncClient(
            timeout=10, follow_redirects=False, trust_env=False
        )
        self.owns_client = client is None
        self.now = now or (lambda: datetime.now(UTC))

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    def _safe(self, value):
        if isinstance(value, dict):
            return {
                key: self._safe(child)
                for key, child in value.items()
                if key.casefold() not in ("api_token", "api_key", "authorization", "access_token")
            }
        if isinstance(value, list):
            return [self._safe(child) for child in value]
        if isinstance(value, str) and self.token:
            return value.replace(self.token, "[REDACTED]")
        return value

    async def marketaux(self, base_asset: str, lookback_hours: int = 24) -> dict:
        if not self.token:
            return {
                "status": "UNAVAILABLE",
                "reason": "MARKETAUX_TOKEN_NOT_CONFIGURED",
                "items": [],
            }
        terms = (base_asset, *ALIASES.get(base_asset, ()))
        params = {
            "api_token": self.token,
            "search": " | ".join('"' + term + '"' for term in terms),
            "limit": 3,
            "page": 1,
            "group_similar": "true",
            "language": "en",
            "published_after": (self.now() - timedelta(hours=lookback_hours)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        }
        response = await self.client.get("https://api.marketaux.com/v1/news/all", params=params)
        if response.status_code != 200:
            return {
                "status": "UNAVAILABLE",
                "reason": f"MARKETAUX_HTTP_{response.status_code}",
                "items": [],
            }
        if len(response.content) > 2 * 1024 * 1024:
            raise DomainError("Marketaux exceeds the 2 MB response bound")
        data = self._safe(response.json())
        if not isinstance(data.get("data"), list) or not isinstance(data.get("meta"), dict):
            raise DomainError("Invalid Marketaux response schema")
        meta = data["meta"]
        observed = self.now()
        items = []
        rejected = 0
        for raw in data["data"][:3]:
            try:
                items.append(
                    news_record(
                        raw["title"],
                        raw.get("description") or raw.get("snippet") or "",
                        raw["url"],
                        raw["source"],
                        utc(raw["published_at"]),
                        observed,
                        "marketaux",
                        raw["uuid"],
                    )
                )
            except (ValueError, TypeError, KeyError):
                rejected += 1
        complete = (
            type(meta.get("found")) is int
            and type(meta.get("returned")) is int
            and meta["returned"] == len(data["data"])
            and meta["found"] <= meta["returned"]
            and rejected == 0
        )
        return {
            "status": "COMPLETE" if complete else "PARTIAL",
            "reason": "FREE_PLAN_FIRST_PAGE",
            "items": items,
            "observed_at": iso(observed),
            "scope": {
                "base_asset": base_asset,
                "search": params["search"],
                "lookback_hours": lookback_hours,
                "page": 1,
                "limit": 3,
            },
            "rejected_items": rejected,
            "quota_headers": {
                k: self._safe(v)
                for k, v in response.headers.items()
                if k.lower().startswith("x-ratelimit-")
            },
            "complete": complete,
        }

    async def rss(self, url: str) -> dict:
        response = await self.client.get(url)
        if response.status_code != 200:
            return {
                "status": "UNAVAILABLE",
                "reason": f"RSS_HTTP_{response.status_code}",
                "items": [],
            }
        if len(response.content) > 2 * 1024 * 1024:
            raise DomainError("RSS exceeds the 2 MB response bound")
        feed = feedparser.parse(response.content)
        if feed.bozo:
            raise DomainError("RSS parsing failed")
        observed = self.now()
        items = []
        rejected = 0
        for entry in feed.entries[:200]:
            try:
                published = entry.get("published_parsed")
                if published is None:
                    raise DomainError("RSS publication time missing")
                at = datetime.fromtimestamp(calendar.timegm(published), UTC)
                items.append(
                    news_record(
                        entry["title"],
                        entry.get("summary", ""),
                        entry["link"],
                        feed.feed.get("title") or url,
                        at,
                        observed,
                        "rss",
                        entry.get("id"),
                    )
                )
            except (ValueError, TypeError, KeyError):
                rejected += 1
        complete = len(feed.entries) <= 200 and rejected == 0
        return {
            "status": "COMPLETE" if complete else "PARTIAL",
            "items": items,
            "observed_at": iso(observed),
            "scope": {"url": url, "lookback_hours": 24, "max_entries": 200},
            "rejected_items": rejected,
            "complete": complete,
            "reason": "RSS_CURRENT_FEED_ONLY",
        }
