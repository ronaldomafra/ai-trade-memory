"""Precision, UTC and deterministic identity shared by the domain."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from typing import Any


class DomainError(ValueError):
    """An operation violates the paper trading contract."""


def decimal(value: Any) -> Decimal:
    if isinstance(value, (float, bool)):
        raise DomainError("Financial values must be decimal strings, integers or Decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError("Invalid decimal") from exc
    if not result.is_finite():
        raise DomainError("Decimal must be finite")
    return result


def floor_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0 or value < 0:
        raise DomainError("Invalid quantity or step")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def utc(value: datetime | str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DomainError("Naive timestamp is not permitted")
    return dt.astimezone(UTC)


def iso(value: datetime) -> str:
    return utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def next_utc_day(value: datetime) -> datetime:
    return utc(value).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    raise TypeError(f"Unsupported JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def stable_id(*values: Any) -> str:
    return hashlib.sha256(canonical_json(values).encode()).hexdigest()
