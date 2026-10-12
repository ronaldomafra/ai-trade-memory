from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from poc.adapters.outbound.budget import AIBudget
from poc.domain.primitives import DomainError

NOW = datetime(2026, 10, 12, tzinfo=UTC)


def test_global_reservation_atomic_between_sessions(tmp_path):
    path = tmp_path / "budget.sqlite3"
    AIBudget(path).close()

    def reserve(index):
        budget = AIBudget(path)
        try:
            return budget.reserve(
                str(index), "trade", str(index), 1, NOW, 2, Decimal(".05"), {}
            ).get("granted", False)
        finally:
            budget.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(reserve, range(12))) == 2
    budget = AIBudget(path)
    assert budget.summary(NOW)["physical_attempts"] == 2
    budget.close()


def test_crash_reservation_replay_cost_rollover_and_tightest_limit(tmp_path):
    path = tmp_path / "budget.sqlite3"
    budget = AIBudget(path)
    first = budget.reserve(
        "a", "trade", "logical", 1, NOW, 240, Decimal(".05"), {"model": "typesafe/jev-1.13"}
    )
    budget.close()
    budget = AIBudget(path)
    replay = budget.reserve("a", "trade", "logical", 1, NOW, 240, Decimal(".05"), {})
    assert not replay["granted"] and replay["reason"] == "ATTEMPT_ALREADY_RESERVED"
    assert budget.summary(NOW)["unknown_cost_calls"] == 1
    budget.finish(first["ai_call_id"], NOW, {"usage": {"cost": Decimal(".05")}}, 200, None)
    budget.finish(first["ai_call_id"], NOW, {"usage": {"cost": Decimal(".05")}}, 200, None)
    assert budget.summary(NOW)["observed_cost_usd"] == ".05" or Decimal(
        budget.summary(NOW)["observed_cost_usd"]
    ) == Decimal(".05")
    assert not budget.reserve("b", "trade", "other", 1, NOW, 240, Decimal(".05"), {})["granted"]
    later = NOW + timedelta(days=1)
    assert budget.reserve("b", "trade", "other", 1, later, 1, Decimal(".05"), {})["granted"]
    assert not budget.reserve("c", "trade", "more", 1, later, 240, Decimal(".05"), {})["granted"]
    with pytest.raises(DomainError):
        budget.reserve("d", "trade", "third", 3, later, 240, Decimal(".05"), {})
    budget.close()
