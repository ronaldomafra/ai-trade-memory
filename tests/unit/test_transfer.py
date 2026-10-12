from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from poc.domain.transfer import balanced_sources, brier_gate, normalize_features

NOW = datetime(2026, 10, 12, tzinfo=UTC)


def row(index, symbol="BTCUSDT", return_pct="1"):
    return {
        "core": {
            "sample_id": str(index),
            "symbol": symbol,
            "decision_at": (NOW - timedelta(hours=index + 1)).isoformat(),
            "return_pct": return_pct,
        }
    }


def test_normalization_relative_to_price_does_not_transfer_absolute_units():
    first = normalize_features(
        {
            "close": "100",
            "rsi_14": 60,
            "ema_short": 90,
            "ema_mid": 80,
            "ema_long": 70,
            "atr_pct": 1,
            "volume_ratio": 1.2,
        }
    )
    second = normalize_features(
        {
            "close": "10000",
            "rsi_14": 60,
            "ema_short": 9000,
            "ema_mid": 8000,
            "ema_long": 7000,
            "atr_pct": 1,
            "volume_ratio": 1.2,
        }
    )
    assert first == second
    assert "close" not in first and "price_ema_short_ratio" in first
    with pytest.raises(ValueError):
        normalize_features({"close": "0"})


def test_source_rounds_balance_symbols_without_selecting_by_gain():
    rows = [row(i, "BTCUSDT", "-1" if i % 2 else "1") for i in range(100)]
    rows.extend(row(i + 100, "ETHUSDT", "-1") for i in range(20))
    selected = balanced_sources(rows, 40)
    assert sum(r["core"]["symbol"] == "BTCUSDT" for r in selected) == 20
    assert sum(r["core"]["symbol"] == "ETHUSDT" for r in selected) == 20
    assert any(Decimal(r["core"]["return_pct"]) < 0 for r in selected)


def shadow(index, p=".8", baseline=".5", y=1, start=None):
    at = start or NOW - timedelta(days=35 - index)
    return {
        "shadow_id": str(index),
        "started_at": at.isoformat(),
        "matured_at": (at + timedelta(hours=1)).isoformat(),
        "p": p,
        "baseline": baseline,
        "y": y,
        "status": "SCORED",
    }


def test_prospective_gate_minimum_nonoverlap_and_strict_improvement():
    rows = [shadow(i) for i in range(30)]
    good = brier_gate(rows, NOW, 30)
    assert good["eligible"] and good["sample_count"] == 30
    assert Decimal(good["brier_transfer"]) < Decimal(good["brier_baseline"])
    assert not brier_gate(rows[:29], NOW, 30)["eligible"]
    assert not brier_gate([shadow(i, p=".5") for i in range(30)], NOW, 30)["eligible"]
    overlapping = [
        shadow(i, start=NOW - timedelta(hours=2) + timedelta(minutes=i)) for i in range(30)
    ]
    assert brier_gate(overlapping, NOW, 30)["sample_count"] == 1


def test_neutrals_future_and_stale_shadows_never_score():
    rows = [shadow(i) for i in range(30)]
    rows.extend(
        [
            shadow(100, y=None),
            shadow(101, start=NOW + timedelta(hours=1)),
            shadow(102, start=NOW - timedelta(days=61)),
        ]
    )
    result = brier_gate(rows, NOW, 30)
    assert result["sample_count"] == 30
