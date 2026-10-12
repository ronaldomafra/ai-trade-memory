from datetime import UTC, datetime, timedelta

from poc.application.learning import LearningEngine, learning_protocol
from poc.config import Config
from poc.domain.primitives import iso

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


class Store:
    def __init__(self, rows):
        self.rows = rows

    def run(self):
        return {"run_id": "synthetic-statistics-test"}

    def learning_records(self, cutoff):
        return self.rows


def record(index, config, **overrides):
    core = {
        "sample_id": str(index),
        "symbol": "BTCUSDT",
        "protocol_hash": learning_protocol(config),
        "fixture": False,
        "position_context": "flat",
        "label_kind": "ENTRY_LONG_NET_RETURN",
        "horizon_bars": 4,
        "market_regime": "bullish",
        "rsi_bucket": "60_70",
        "volume_bucket": "high",
        "volatility_bucket": "medium",
        "decision_at": iso(NOW - timedelta(hours=index + 2)),
        "maturity_time": iso(NOW - timedelta(hours=index + 1)),
        "return_pct": "1",
        **overrides,
    }
    return {"core": core, "origins": [{"matured_at": iso(NOW - timedelta(hours=1))}]}


STATE = {
    "symbol": "BTCUSDT",
    "portfolio": {"has_position": False},
    "market": {
        "market_regime": "bullish",
        "rsi_14": 61,
        "volume_ratio": 1.3,
        "volatility_bucket": "medium",
    },
}


def test_exact_30_regime_50_and_foreign_or_other_family_never_count():
    config = Config()
    rows = [record(i, config) for i in range(29)]
    rows.extend(record(i + 50, config, symbol="ETHUSDT") for i in range(100))
    rows.extend(
        record(i + 200, config, label_kind="HOLD_VS_SELL_RETURN", position_context="holding")
        for i in range(100)
    )
    store = Store(rows)
    engine = LearningEngine(config, None, store)
    assert engine.feedback(STATE, NOW)["status"] == "insufficient_samples"
    store.rows.append(record(29, config))
    exact = engine.feedback(STATE, NOW)
    assert exact["patterns"][0]["sample_count"] == 30
    assert exact["patterns"][0]["aggregation_level"] == "exact"
    store.rows = [record(i, config, rsi_bucket="lt30" if i % 2 else "60_70") for i in range(50)]
    coarse = engine.feedback(STATE, NOW)
    assert coarse["patterns"][0]["sample_count"] == 50
    assert coarse["patterns"][0]["aggregation_level"] == "regime"
    assert "rsi_bucket" not in coarse["patterns"][0]
    assert len(coarse["patterns"]) == 1


def test_archive_older_than_60d_and_incompatible_protocol_excluded():
    config = Config()
    rows = [record(i, config, decision_at=iso(NOW - timedelta(days=61))) for i in range(50)]
    rows.extend(record(i + 100, config, protocol_hash="incompatible") for i in range(100))
    assert (
        LearningEngine(config, None, Store(rows)).feedback(STATE, NOW)["status"]
        == "insufficient_samples"
    )
