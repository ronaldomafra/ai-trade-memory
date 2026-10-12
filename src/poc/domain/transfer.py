"""Relative feature protocol, balanced source rounds and prospective transfer scoring."""

from collections import deque
from datetime import datetime, timedelta

from poc.domain.primitives import DomainError, decimal, utc


def normalize_features(features: dict) -> dict:
    close = decimal(features["close"])
    if close <= 0:
        raise DomainError("Normalizer requires a positive original close")
    values = {}
    for field in ("rsi_14", "atr_pct", "volume_ratio"):
        value = decimal(str(features[field]))
        if value < 0 or (field == "rsi_14" and value > 100):
            raise DomainError("Invalid relative source feature")
        values[field] = str(value)
    for field in ("ema_short", "ema_mid", "ema_long"):
        value = decimal(str(features[field]))
        if value <= 0:
            raise DomainError("Invalid EMA denominator")
        values["price_" + field + "_ratio"] = str(close / value)
    return values


def balanced_sources(records: list[dict], limit: int) -> list[dict]:
    by_symbol = {}
    for record in records:
        if decimal(record["core"]["return_pct"]) == 0:
            continue
        by_symbol.setdefault(record["core"]["symbol"], []).append(record)
    queues = {
        symbol: deque(
            sorted(
                rows,
                key=lambda row: (
                    -utc(row["core"]["decision_at"]).timestamp(),
                    row["core"]["sample_id"],
                ),
            )
        )
        for symbol, rows in by_symbol.items()
    }
    selected = []
    while queues and len(selected) < limit:
        for symbol in sorted(list(queues)):
            if len(selected) >= limit:
                break
            selected.append(queues[symbol].popleft())
            if not queues[symbol]:
                del queues[symbol]
    return selected


def brier_gate(shadows: list[dict], cutoff: datetime, minimum: int = 30) -> dict:
    eligible = [
        row
        for row in shadows
        if row["status"] == "SCORED"
        and type(row.get("y")) is int
        and row["y"] in (0, 1)
        and utc(cutoff) - timedelta(days=60) <= utc(row["started_at"])
        and utc(row["started_at"]) < utc(row["matured_at"]) < utc(cutoff)
    ]
    eligible.sort(
        key=lambda row: (utc(row["started_at"]), utc(row["matured_at"]), row["shadow_id"])
    )
    independent_intervals = []
    last_end = None
    for row in eligible:
        if last_end is None or utc(row["started_at"]) > last_end:
            independent_intervals.append(row)
            last_end = utc(row["matured_at"])
    selected = independent_intervals[-minimum:]
    transfer, baseline = None, None
    if selected:
        for row in selected:
            if not 0 <= decimal(row["p"]) <= 1 or not 0 <= decimal(row["baseline"]) <= 1:
                raise DomainError("Invalid prospective probability")
        transfer = sum((decimal(row["p"]) - row["y"]) ** 2 for row in selected) / len(selected)
        baseline = sum((decimal(row["baseline"]) - row["y"]) ** 2 for row in selected) / len(
            selected
        )
    enough = len(selected) >= minimum
    better = enough and transfer < baseline
    return {
        "eligible": bool(better),
        "sample_count": len(selected),
        "brier_transfer": str(transfer) if transfer is not None else None,
        "brier_baseline": str(baseline) if baseline is not None else None,
        "shadow_ids": [row["shadow_id"] for row in selected],
        "reason": "STRICTLY_BETTER_THAN_BASELINE"
        if better
        else "INSUFFICIENT_VALIDATION"
        if not enough
        else "NOT_STRICTLY_BETTER",
        "selection": "chronological_nonoverlapping_intervals_last_30_v1",
        "independence_limitation": "Nonoverlap does not establish statistical independence.",
    }
