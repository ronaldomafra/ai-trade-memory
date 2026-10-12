"""Prediction-market identity, probability books and quality filters with explicit units."""

import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from poc.domain.external import clean_text
from poc.domain.primitives import DomainError, decimal, iso, stable_id, utc


class PredictionLimits(Protocol):
    snapshot_max_age_minutes: int
    liquidity_max_age_minutes: int
    volume_24h_max_age_minutes: int
    max_trade_age_minutes: int
    max_spread_pp: Decimal
    min_liquidity_usd: Decimal
    min_volume_24h_usd: Decimal
    min_depth_per_side_usd: Decimal
    depth_band_pp: Decimal
    max_tracked_markets: int
    max_markets_per_occurrence: int


def array(value) -> list:
    data = json.loads(value) if isinstance(value, str) else value
    if not isinstance(data, list):
        raise DomainError("Prediction market arrays are invalid")
    return data


def occurrence_association(raw: dict, observed_at: datetime) -> dict:
    """Verify only identical complete propositions; broader provider groups stay pending.

    Identical question and complete resolution rules bind the same object/period
    without extracting a schedule or assuming provider IDs are independent events.
    Different questions in a bundle require additional semantic evidence.
    """
    question = clean_text(raw["question"], 20000)
    rules = clean_text(raw.get("description", ""), 20000)
    events = raw.get("events", [])
    if not isinstance(events, list):
        raise DomainError("Invalid prediction event metadata")
    parents = [event for event in events if isinstance(event, dict) and event.get("id")]
    event_ids = sorted({str(event["id"]) for event in parents})
    complete = len(raw["question"]) <= 20000 and len(raw.get("description", "")) <= 20000
    matched = bool(question and rules and complete and len(event_ids) == 1 and parents)
    for parent in parents:
        title, description = parent.get("title", ""), parent.get("description", "")
        matched = matched and (
            isinstance(title, str)
            and isinstance(description, str)
            and len(title) <= 20000
            and len(description) <= 20000
            and clean_text(title, 20000) == question
            and clean_text(description, 20000) == rules
        )
    return {
        "provider_event_ids": event_ids,
        "occurrence_id": stable_id("poly_occurrence_literal_v1", question, rules)
        if matched
        else None,
        "association_status": "VERIFIED_LITERAL_PROPOSITION" if matched else "PENDING",
        "association_evidence": {
            "version": "poly_occurrence_literal_v1",
            "reason": "IDENTICAL_COMPLETE_QUESTION_AND_RULES"
            if matched
            else "PROVIDER_GROUP_REQUIRES_OBJECT_PERIOD_EVIDENCE",
            "question": question,
            "rules": rules,
            "parent_propositions": [
                {
                    "event_id": str(event["id"]),
                    "title": clean_text(event.get("title", ""), 20000),
                    "rules": clean_text(event.get("description", ""), 20000),
                }
                for event in parents
            ],
            "available_at": iso(observed_at),
            "limitation": (
                "Literal proposition identity; no inferred occurrence date or independence."
            ),
        },
    }


def normalize_market(
    raw: dict, observed_at: datetime, metric_unit_contract: str | None = None
) -> dict:
    outcomes, tokens = array(raw["outcomes"]), array(raw["clobTokenIds"])
    if (
        not 2 <= len(outcomes) == len(tokens) <= 50
        or len(set(outcomes)) != len(outcomes)
        or len(set(tokens)) != len(tokens)
    ):
        raise DomainError("Prediction result/token association is invalid")
    if any(not isinstance(value, str) or not value for value in outcomes) or any(
        not isinstance(token, str) or not token.isdecimal() for token in tokens
    ):
        raise DomainError("Prediction outcome/token identity is invalid")
    condition = raw["conditionId"]
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", condition) or not isinstance(raw["id"], str):
        raise DomainError("Invalid market condition identity")
    selected = next((i for i, value in enumerate(outcomes) if value.casefold() == "yes"), 0)
    association = occurrence_association(raw, observed_at)
    events = [event for event in raw.get("events", []) if isinstance(event, dict)]
    question = clean_text(raw["question"], 300)
    description = clean_text(raw.get("description", ""), 600)
    if not question:
        raise DomainError("Missing prediction question")
    liquidity = raw.get("liquidityClob", raw.get("liquidityNum"))
    volume = raw.get("volume24hrClob", raw.get("volume24hr"))
    return {
        "market_id": raw["id"],
        "url": "https://polymarket.com/event/"
        + next(
            (
                event["slug"]
                for event in events
                if isinstance(event.get("slug"), str)
                and re.fullmatch(r"[a-z0-9_-]+", event["slug"])
            ),
            raw.get("slug")
            if isinstance(raw.get("slug"), str) and re.fullmatch(r"[a-z0-9_-]+", raw["slug"])
            else raw["id"],
        ),
        "condition_id": condition,
        "question": question,
        "description": description,
        "outcome": outcomes[selected],
        "token_id": tokens[selected],
        "outcomes": outcomes,
        "all_token_ids": tokens,
        "selection_reason": "YES_OUTCOME"
        if outcomes[selected].casefold() == "yes"
        else "DECLARED_FIRST_OUTCOME",
        **association,
        "end_date": raw.get("endDate"),
        "resolution_source": clean_text(raw.get("resolutionSource", ""), 200),
        "active": raw.get("active") is True
        and raw.get("closed") is False
        and not raw.get("archived", False),
        "orderbook_enabled": raw.get("enableOrderBook") is True,
        "observed_at": iso(observed_at),
        "liquidity_observed_at": iso(observed_at),
        "volume_observed_at": iso(observed_at),
        "liquidity_reported": str(decimal(liquidity)) if liquidity is not None else None,
        "volume_24h_reported": str(decimal(volume)) if volume is not None else None,
        "metric_unit_contract": metric_unit_contract or "UNVERIFIED",
        "content_hash": stable_id(
            association["association_evidence"]["question"],
            association["association_evidence"]["rules"],
            outcomes,
            tokens,
            condition,
            association["provider_event_ids"],
            association["association_evidence"]["parent_propositions"],
            raw.get("endDate"),
        ),
    }


def normalize_book(raw: dict, market: dict, observed_at: datetime) -> dict:
    if raw.get("market") != market["condition_id"] or raw.get("asset_id") != market["token_id"]:
        raise DomainError("Book token or condition mismatches metadata")
    timestamp = decimal(raw["timestamp"])
    # Documented CLOB book clock: epoch milliseconds, not Gamma updatedAt.
    if timestamp < Decimal("1000000000000") or timestamp != timestamp.to_integral_value():
        raise DomainError("Book timestamp unit is unverifiable")
    at = datetime.fromtimestamp(int(timestamp) / 1000, UTC)
    if utc(at) > utc(observed_at):
        raise DomainError("Future book timestamp")
    sides = {}
    for side in ("bids", "asks"):
        levels = []
        seen = set()
        for row in raw[side]:
            price, size = decimal(row["price"]), decimal(row["size"])
            if not 0 < price < 1 or size <= 0 or price in seen:
                raise DomainError("Invalid probability order book level")
            seen.add(price)
            levels.append({"price": str(price), "size": str(size)})
        if not levels:
            raise DomainError("Empty probability book side")
        sides[side] = levels
    bid = max(decimal(row["price"]) for row in sides["bids"])
    ask = min(decimal(row["price"]) for row in sides["asks"])
    if bid >= ask:
        raise DomainError("Crossed or locked probability book")
    return {
        **sides,
        "best_bid": str(bid),
        "best_ask": str(ask),
        "midpoint": str((bid + ask) / 2),
        "spread_pp": str((ask - bid) * 100),
        "observed_at": iso(observed_at),
        "source_at": iso(at),
        "token_id": market["token_id"],
        "condition_id": market["condition_id"],
        "depth_unit_contract": "USDC_PER_SHARE_V1",
        "source": "CLOB_PUBLIC_BOOK",
    }


def metadata_quality(market: dict, cutoff: datetime, limits: PredictionLimits) -> list[str]:
    reasons = []

    def age(value, minutes):
        return value is not None and timedelta(0) <= utc(cutoff) - utc(value) <= timedelta(
            minutes=minutes
        )

    if not market["active"] or not market["orderbook_enabled"]:
        reasons.append("INACTIVE_OR_NO_ORDERBOOK")
    if (
        market["association_status"] != "VERIFIED_LITERAL_PROPOSITION"
        or not market["occurrence_id"]
    ):
        reasons.append("OCCURRENCE_ASSOCIATION_PENDING")
    if market["metric_unit_contract"] != "REPORTED_USD_V1":
        reasons.append("GAMMA_METRIC_UNITS_UNVERIFIED")
    for field, minimum, stamp, max_age in (
        (
            "liquidity_reported",
            limits.min_liquidity_usd,
            "liquidity_observed_at",
            limits.liquidity_max_age_minutes,
        ),
        (
            "volume_24h_reported",
            limits.min_volume_24h_usd,
            "volume_observed_at",
            limits.volume_24h_max_age_minutes,
        ),
    ):
        if market[field] is None or decimal(market[field]) < minimum:
            reasons.append("INSUFFICIENT_" + field.upper())
        if not age(market.get(stamp), max_age):
            reasons.append("STALE_" + field.upper())
    return reasons


def quality(
    market: dict, book: dict | None, trade: dict | None, cutoff: datetime, limits: PredictionLimits
) -> dict:
    reasons = metadata_quality(market, cutoff, limits)

    def age(value, minutes):
        return value is not None and timedelta(0) <= utc(cutoff) - utc(value) <= timedelta(
            minutes=minutes
        )

    depth_bid, depth_ask = None, None
    if book is None:
        reasons.append("BOOK_UNAVAILABLE")
    else:
        if book["condition_id"] != market["condition_id"] or book["token_id"] != market["token_id"]:
            reasons.append("BOOK_IDENTITY_MISMATCH")
        if not age(book["observed_at"], limits.snapshot_max_age_minutes) or not age(
            book["source_at"], limits.snapshot_max_age_minutes
        ):
            reasons.append("STALE_BOOK")
        if decimal(book["spread_pp"]) > limits.max_spread_pp:
            reasons.append("SPREAD_TOO_WIDE")
        mid = decimal(book["midpoint"])
        band = limits.depth_band_pp / 100
        depth_bid = sum(
            (
                decimal(row["price"]) * decimal(row["size"])
                for row in book["bids"]
                if mid - band <= decimal(row["price"]) <= mid
            ),
            Decimal(0),
        )
        depth_ask = sum(
            (
                decimal(row["price"]) * decimal(row["size"])
                for row in book["asks"]
                if mid <= decimal(row["price"]) <= mid + band
            ),
            Decimal(0),
        )
        if min(depth_bid, depth_ask) < limits.min_depth_per_side_usd:
            reasons.append("INSUFFICIENT_DEPTH")
    if (
        trade is None
        or trade.get("token_id") != market["token_id"]
        or trade.get("condition_id") != market["condition_id"]
        or not age(trade.get("source_at"), limits.max_trade_age_minutes)
        or utc(trade.get("observed_at", iso(cutoff))) > utc(cutoff)
    ):
        reasons.append("RECENT_RESULT_TRADE_UNVERIFIED")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "bid_depth_usd_equivalent": str(depth_bid) if depth_bid is not None else None,
        "ask_depth_usd_equivalent": str(depth_ask) if depth_ask is not None else None,
        "depth_conversion": "USDC nominal USD equivalent; not a fiat exchange quote",
        "version": "poly_quality_v1",
    }


def select_markets(candidates: list[dict], limits: PredictionLimits) -> list[dict]:
    eligible = [
        row
        for row in candidates
        if row["quality"]["eligible"] and row["relevance"] in ("DIRECT", "CONTEXTUAL")
    ]
    eligible.sort(
        key=lambda row: (
            0 if row["relevance"] == "DIRECT" else 1,
            0 if row.get("temporal_relation") == "IN_WINDOW" else 1,
            -utc(row["book"]["observed_at"]).timestamp(),
            decimal(row["book"]["spread_pp"]),
            -min(
                decimal(row["quality"]["bid_depth_usd_equivalent"]),
                decimal(row["quality"]["ask_depth_usd_equivalent"]),
            ),
            row["market"]["market_id"],
        )
    )
    occurrences = {}
    chosen = []
    for row in eligible:
        occurrence = row["market"]["occurrence_id"]
        if occurrences.get(occurrence, 0) >= limits.max_markets_per_occurrence:
            continue
        chosen.append(row)
        occurrences[occurrence] = occurrences.get(occurrence, 0) + 1
        if len(chosen) >= limits.max_tracked_markets:
            break
    return chosen


def probability_changes(
    current: dict, history: list[dict], cutoff: datetime, limits: PredictionLimits
) -> dict:
    """Descriptive midpoint changes from actual prior observations, never reconstructed bids."""
    result = {}
    end = utc(current["source_at"])
    for minutes in (5, 60):
        target = end - timedelta(minutes=minutes)
        valid = []
        for saved in history:
            book = saved.get("value")
            if not isinstance(book, dict):
                continue
            try:
                source = utc(book["source_at"])
                observed = utc(book["observed_at"])
                available = utc(saved["available_at"])
                if (
                    book["condition_id"] == current["condition_id"]
                    and book["token_id"] == current["token_id"]
                    and source
                    <= observed
                    <= available
                    <= min(utc(cutoff), utc(current["observed_at"]))
                    and target - timedelta(minutes=limits.snapshot_max_age_minutes)
                    <= source
                    <= target
                    and decimal(book["spread_pp"]) <= limits.max_spread_pp
                    and 0 < decimal(book["midpoint"]) < 1
                ):
                    valid.append((source, book, available))
            except (ValueError, TypeError, KeyError):
                continue
        if not valid:
            result[str(minutes) + "m"] = {"status": "UNAVAILABLE", "change_pp": None}
            continue
        source, previous, available = max(valid, key=lambda value: (value[0], value[2]))
        result[str(minutes) + "m"] = {
            "status": "AVAILABLE",
            "nominal_lookback_minutes": minutes,
            "change_pp": str((decimal(current["midpoint"]) - decimal(previous["midpoint"])) * 100),
            "from_source_at": iso(source),
            "to_source_at": iso(end),
            "reference_available_at": iso(available),
            "actual_interval_seconds": str(decimal(str((end - source).total_seconds()))),
            "basis": "OBSERVED_CLOB_MIDPOINTS_NOT_CALIBRATED_PROFIT_PROBABILITY",
        }
    return result
