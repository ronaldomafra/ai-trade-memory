"""Strict JSONL schema and provenance validation for reusable statistical observations."""

import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal

from poc.domain.candles import INTERVAL_SECONDS
from poc.domain.features import rsi_bucket, volume_bucket
from poc.domain.learning import hold_return, net_entry_return
from poc.domain.models import Quote
from poc.domain.primitives import DomainError, canonical_json, decimal, stable_id, utc

CORE_FIELDS = {
    "sample_id",
    "symbol",
    "base_asset",
    "quote_asset",
    "profile_id",
    "profile_version",
    "interval",
    "protocol_hash",
    "feature_version",
    "label_version",
    "equivalence_version",
    "position_context",
    "label_kind",
    "horizon_bars",
    "decision_at",
    "as_of",
    "maturity_time",
    "features",
    "market_regime",
    "rsi_bucket",
    "volume_bucket",
    "volatility_bucket",
    "reference_quote",
    "quantity",
    "reference_budget_usdt",
    "fee_fraction",
    "slippage_fraction",
    "fixture",
    "exit_quote",
    "return_pct",
}
PROFILE_CORE_FIELDS = CORE_FIELDS | {
    "interval_seconds",
    "trend_interval",
    "reference_candle_close_time",
    "outcome_quote_window_seconds",
}
ORIGIN_FIELDS = {
    "origin_id",
    "origin_run_id",
    "decision_id",
    "portfolio_id",
    "matured_at",
    "available_at",
    "code_version",
    "config_hash",
    "template_version",
    "protocol_parameters",
}


def encoded_records(records: list[dict]) -> bytes:
    return "".join(canonical_json(record) + "\n" for record in records).encode("utf-8")


def records_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def string_decimal(value) -> Decimal:
    if not isinstance(value, str):
        raise DomainError("Dataset financial numbers must be decimal strings")
    return decimal(value)


def validate_record(record: dict, cutoff: datetime) -> None:
    if set(record) != {"core", "origins"} or not isinstance(record["core"], dict):
        raise DomainError("Unknown dataset record fields")
    core = record["core"]
    v2 = core.get("label_version") == "profile_labels_v2"
    if set(core) != (PROFILE_CORE_FIELDS if v2 else CORE_FIELDS) or core["fixture"] is not False:
        raise DomainError("Invalid schema or fixture in reusable dataset")
    if core["sample_id"] != stable_id(
        "profile_equivalence_v2" if v2 else "equivalence_v1",
        {k: v for k, v in core.items() if k != "sample_id"},
    ):
        raise DomainError("Learning example hash mismatch")
    if (
        not re.fullmatch(r"[A-Z0-9]{2,30}USDT", core["symbol"])
        or core["symbol"] != core["base_asset"] + "USDT"
        or core["quote_asset"] != "USDT"
    ):
        raise DomainError("Invalid asset identity")
    if not v2 and (
        core["interval"] != "15m"
        or core["profile_id"] != "trend_15m_v1"
        or core["profile_version"] != "1"
        or core["label_version"] != "labels_v1"
        or core["equivalence_version"] != "equivalence_v1"
    ):
        raise DomainError("Unsupported label/profile schema")
    if v2 and (
        core["interval"] not in INTERVAL_SECONDS
        or core["interval_seconds"] != INTERVAL_SECONDS[core["interval"]]
        or core["trend_interval"] not in INTERVAL_SECONDS
        or core["equivalence_version"] != "profile_equivalence_v2"
        or core["feature_version"] != "profile_features_v2"
        or not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", core["profile_id"])
        or not str(core["profile_version"]).isdigit()
        or type(core["outcome_quote_window_seconds"]) is not int
        or not 1 <= core["outcome_quote_window_seconds"] <= 90
    ):
        raise DomainError("Unsupported generic profile protocol")
    if (
        type(core["horizon_bars"]) is not int
        or core["horizon_bars"] <= 0
        or (not v2 and core["horizon_bars"] not in (4, 16))
    ):
        raise DomainError("Invalid horizon")
    expected_kind = {"flat": "ENTRY_LONG_NET_RETURN", "holding": "HOLD_VS_SELL_RETURN"}.get(
        core["position_context"]
    )
    if core["label_kind"] != expected_kind:
        raise DomainError("Position and label family conflict")
    if core["market_regime"] not in ("bullish", "bearish", "range") or core[
        "volatility_bucket"
    ] not in ("low", "medium", "high"):
        raise DomainError("Invalid context buckets")
    features = core["features"]
    if (
        not features.get("valid")
        or core["feature_version"] != features.get("feature_version")
        or core["market_regime"] != features.get("market_regime")
        or core["volatility_bucket"] != features.get("volatility_bucket")
    ):
        raise DomainError("Invalid original features")
    if core["rsi_bucket"] != rsi_bucket(features["rsi_14"]) or core[
        "volume_bucket"
    ] != volume_bucket(features["volume_ratio"]):
        raise DomainError("Original buckets do not match features")
    if utc(features["as_of"]) > utc(core["decision_at"]) or utc(core["as_of"]) > utc(
        core["decision_at"]
    ):
        raise DomainError("Future original feature cutoff")
    reference = quote_from_record(core["reference_quote"])
    exit_quote = quote_from_record(core["exit_quote"])
    at, maturity = utc(core["decision_at"]), utc(core["maturity_time"])
    expected_maturity = at.replace(
        minute=at.minute // 15 * 15, second=0, microsecond=0
    ) + timedelta(minutes=15 * core["horizon_bars"])
    if v2:
        anchor = utc(core["reference_candle_close_time"])
        if int(anchor.timestamp()) % core[
            "interval_seconds"
        ] != 0 or not anchor <= at <= anchor + timedelta(seconds=90):
            raise DomainError("Invalid reference closed-candle anchor")
        expected_maturity = anchor + timedelta(
            seconds=core["interval_seconds"] * core["horizon_bars"]
        )
    if (
        maturity != expected_maturity
        or reference.symbol != core["symbol"]
        or exit_quote.symbol != core["symbol"]
    ):
        raise DomainError("Maturity or quote symbol mismatch")
    if (
        not at < reference.observed_at < maturity
        or not maturity
        <= exit_quote.observed_at
        <= maturity + timedelta(seconds=core.get("outcome_quote_window_seconds", 90))
    ):
        raise DomainError("Quote outside label window")
    if not reference.fresh(reference.received_at, 30) or not exit_quote.fresh(
        exit_quote.received_at, 30
    ):
        raise DomainError("Stale historical quote")
    quantity = string_decimal(core["quantity"])
    if quantity <= 0:
        raise DomainError("Invalid hypothetical quantity")
    if (
        core["reference_budget_usdt"] is not None
        and string_decimal(core["reference_budget_usdt"]) <= 0
    ):
        raise DomainError("Invalid hypothetical budget")
    fee, slip = string_decimal(core["fee_fraction"]), string_decimal(core["slippage_fraction"])
    result = (
        net_entry_return(reference.ask, exit_quote.bid, fee, slip)
        if expected_kind == "ENTRY_LONG_NET_RETURN"
        else hold_return(reference.bid, exit_quote.bid, fee, slip)
    )
    if abs(string_decimal(core["return_pct"]) - result) > Decimal("1e-18"):
        raise DomainError("Invalid recomputed counterfactual return")
    if not isinstance(record["origins"], list) or not record["origins"]:
        raise DomainError("Missing provenance")
    for origin in record["origins"]:
        if set(origin) != ORIGIN_FIELDS or any(
            not isinstance(origin[key], str) or not origin[key]
            for key in ORIGIN_FIELDS - {"protocol_parameters"}
        ):
            raise DomainError("Invalid origin schema")
        if origin["origin_id"] != stable_id(
            "origin", origin["origin_run_id"], origin["decision_id"], core["horizon_bars"]
        ):
            raise DomainError("Invalid original identity")
        if origin["portfolio_id"] not in ("BASELINE_TECHNICAL", "JEV_STATIC", "JEV_LEARNING"):
            raise DomainError("Invalid original portfolio")
        if (
            not exit_quote.received_at
            <= utc(origin["matured_at"])
            <= utc(origin["available_at"])
            <= utc(cutoff)
        ):
            raise DomainError("Future or unavailable origin")
    canonical_json(record)  # Reject all nonfinite features/unknown serializable types.


def quote_from_record(raw: dict) -> Quote:
    allowed = set(Quote.__dataclass_fields__)
    if set(raw) != allowed or raw["source"] not in ("binance_rest", "binance_ws"):
        raise DomainError("Unknown historical quote schema/source")
    values = {**raw}
    for key in ("bid", "ask", "bid_qty", "ask_qty"):
        if values[key] is not None:
            values[key] = string_decimal(values[key])
    for key in ("observed_at", "received_at", "event_at", "request_started_at"):
        if values[key] is not None:
            values[key] = utc(values[key])
    if values["received_at"] < values["observed_at"]:
        raise DomainError("Quote available before observation")
    return Quote(**values)
