"""Small external evidence records. Source content is never an instruction."""

import html
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from poc.domain.event_time import temporal_relation
from poc.domain.primitives import DomainError, iso, stable_id, utc

ALIASES = {
    "BTC": ("bitcoin",),
    "ETH": ("ethereum", "ether"),
    "SOL": ("solana",),
    "BNB": ("bnb",),
    "XRP": ("xrp",),
}
MACRO = (
    "federal reserve",
    "interest rate",
    "fed rate",
    "inflation",
    "regulation",
    "sanction",
    "war",
    "tariff",
    "central bank",
    "recession",
    "geopolitic",
    "election",
    "china",
    "xi jinping",
)


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.suppressed += 1
        elif tag in ("p", "br", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.suppressed = max(0, self.suppressed - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def clean_text(value: str, limit: int = 600) -> str:
    if not isinstance(value, str):
        raise DomainError("External text must be a string")
    parser = TextParser()
    parser.feed(value[:20000])
    cleaned = html.unescape("".join(parser.parts))
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch.isspace())
    return " ".join(cleaned.split())[:limit]


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise DomainError("Invalid public evidence URL")
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_")
        and k.lower()
        not in (
            "fbclid",
            "gclid",
            "api_token",
            "api_key",
            "apikey",
            "token",
            "access_token",
            "authorization",
            "secret",
        )
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def news_record(
    title: str,
    summary: str,
    url: str,
    source: str,
    published_at: datetime,
    first_seen_at: datetime,
    provider: str,
    provider_id: str | None = None,
) -> dict:
    title, summary = clean_text(title, 240), clean_text(summary, 600)
    url = canonical_url(url)
    if not title or not source or utc(published_at) > utc(first_seen_at):
        raise DomainError("Invalid news publication or origin")
    return {
        "item_id": stable_id("news_url_v1", url),
        "title": title,
        "summary": summary,
        "url": url,
        "source": clean_text(source, 120),
        "published_at": iso(published_at),
        "first_seen_at": iso(first_seen_at),
        "content_hash": stable_id(title, summary, url, source, iso(published_at)),
        "title_source_hash": stable_id(title.casefold(), source.casefold()),
        "provenance": [
            {"provider": provider, "provider_id": provider_id, "observed_at": iso(first_seen_at)}
        ],
    }


def relevant_candidates(
    items: list[dict], base_asset: str, cutoff: datetime, lookback_hours: int = 24
) -> list[dict]:
    aliases = (base_asset.casefold(), *ALIASES.get(base_asset, ()))
    result = []
    for item in items:
        if not utc(item["first_seen_at"]) <= utc(cutoff) or not utc(cutoff) - timedelta(
            hours=lookback_hours
        ) <= utc(item["published_at"]) <= utc(cutoff):
            continue
        text = (item["title"] + " " + item["summary"]).casefold()
        direct = any(
            re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text) for alias in aliases
        )
        macro = any(word in text for word in MACRO)
        if direct or macro:
            result.append(
                {
                    **item,
                    "candidate_reason": "ASSET_ALIAS_REQUIRES_CLASSIFICATION"
                    if direct
                    else "MACRO_REQUIRES_ASSET_CLASSIFICATION",
                }
            )
    return sorted(result, key=lambda item: (item["published_at"], item["item_id"]), reverse=True)


def context_at(context: dict | None, cutoff: datetime) -> dict:
    result = (
        {**context}
        if context
        else {
            "news": {"status": "unavailable", "items": []},
            "prediction_markets": {"status": "unavailable", "items": []},
        }
    )
    for section in ("news", "prediction_markets"):
        data = result[section]
        items = [
            {**item, "temporal_relation": temporal_relation(item, cutoff)}
            for item in data.get("items", [])
            if utc(item["available_at"]) <= utc(cutoff)
            and utc(item["source_observed_at"]) <= utc(cutoff)
            and utc(item["valid_until"]) >= utc(cutoff)
        ]
        if data.get("items") and not items:
            data = {
                **data,
                "status": "unavailable",
                "reason": "ALL_FACTORS_EXPIRED",
                "absence_verified_in_scope": False,
            }
        if data.get("absence_verified_in_scope"):
            scopes = (
                data.get("sources", {}).values()
                if section == "news"
                else [data.get("discovery", {})]
            )
            # An empty historical query outside the configured decision window
            # cannot stand in for an evaluated current scope. No clock refresh creates proof.
            current_scope = any(
                scope.get("observed_at")
                and utc(cutoff) - timedelta(hours=data.get("scope", {}).get("lookback_hours", 24))
                <= utc(scope["observed_at"])
                <= utc(cutoff)
                for scope in scopes
            )
            if not current_scope:
                data = {
                    **data,
                    "status": "unavailable",
                    "reason": "EMPTY_SCOPE_OUTSIDE_DECISION_WINDOW",
                    "absence_verified_in_scope": False,
                }
        result[section] = {**data, "items": items}
    return result
