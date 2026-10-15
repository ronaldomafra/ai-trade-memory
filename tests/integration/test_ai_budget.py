from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from poc.adapters.outbound.budget import AIBudget
from poc.config import GlobalAICostLimit
from poc.domain.primitives import DomainError

NOW = datetime(2026, 10, 12, tzinfo=UTC)


@pytest.mark.parametrize("enabled", [True, False])
def test_global_reservation_atomic_between_sessions(tmp_path, enabled):
    path = tmp_path / "budget.sqlite3"
    initial = AIBudget(path)
    initial.set_cost_limit(GlobalAICostLimit(cost_limit_enabled=enabled), NOW, "test-owner")
    initial.close()

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
    assert Decimal(budget.summary(NOW)["observed_cost_usd"]) == Decimal(".05")
    assert not budget.reserve("b", "trade", "other", 1, NOW, 240, Decimal(".05"), {})["granted"]
    later = NOW + timedelta(days=1)
    assert budget.reserve("b", "trade", "other", 1, later, 1, Decimal(".05"), {})["granted"]
    assert not budget.reserve("c", "trade", "more", 1, later, 240, Decimal(".05"), {})["granted"]
    with pytest.raises(DomainError):
        budget.reserve("d", "trade", "third", 3, later, 240, Decimal(".05"), {})
    budget.close()


def test_global_cost_policy_raise_disable_reenable_preserves_spend_and_history(tmp_path):
    path = tmp_path / "budget.sqlite3"
    a, b = AIBudget(path), AIBudget(path)
    try:
        first = a.reserve("a", "trade", "first", 1, NOW, 240, Decimal(".05"), {})
        a.finish(first["ai_call_id"], NOW, {"usage": {"cost": "0.05"}}, 200, None)
        assert not b.reserve("b", "trade", "blocked", 1, NOW, 240, Decimal(".05"), {})["granted"]
        raised = b.set_cost_limit(
            GlobalAICostLimit(max_observed_cost_usd_per_day="0.10"), NOW, "owner"
        )
        assert raised["policy"]["revision"] == 1
        assert a.reserve("a", "trade", "higher", 1, NOW, 240, Decimal(".01"), {})["granted"]
        # An already-open connection sees the new GLOBAL policy; session defaults cannot undo it.
        b.set_cost_limit(
            GlobalAICostLimit(cost_limit_enabled=False, max_observed_cost_usd_per_day="0.10"),
            NOW,
            "owner",
        )
        cost_before = a.summary(NOW)
        unlimited = a.reserve("b", "context_classification", "off", 1, NOW, 240, Decimal(".01"), {})
        assert unlimited["granted"]
        a.finish(unlimited["ai_call_id"], NOW, {"usage": {"cost": "0.20"}}, 200, None)
        assert Decimal(a.summary(NOW)["observed_cost_usd"]) == Decimal("0.25")
        policy = GlobalAICostLimit(max_observed_cost_usd_per_day="0.20")
        resumed = b.set_cost_limit(policy, NOW, "owner")
        assert resumed["cost_limit_reached"] and resumed["policy"]["revision"] == 3
        assert b.set_cost_limit(policy, NOW, "owner")["policy"]["revision"] == 3
        assert not a.reserve("a", "trade", "on", 1, NOW, 240, Decimal(".05"), {})["granted"]
        assert a.summary(NOW)["physical_attempts"] == cost_before["physical_attempts"] + 1
        assert a.summary(NOW)["unknown_cost_calls"] == 1
        assert a.reserve(
            "a", "trade", "tomorrow", 1, NOW + timedelta(days=1), 240, Decimal(".05"), {}
        )["granted"]
        assert a.connection.execute("SELECT COUNT(*) FROM ai_cost_policy").fetchone()[0] == 3
        receipt = a.connection.execute(
            "SELECT policy_revision,cost_limit_enabled FROM ai_budget_policy_receipts "
            "WHERE ai_call_id=?",
            (unlimited["ai_call_id"],),
        ).fetchone()
        assert tuple(receipt) == (2, 0)
    finally:
        a.close()
        b.close()
    restored = AIBudget(path)
    assert restored.status(NOW)["policy"]["max_observed_cost_usd_per_day"] == "0.20"
    assert Decimal(restored.status(NOW)["observed_cost_usd"]) == Decimal("0.25")
    restored.close()


def test_disabling_cost_does_not_disable_call_limit_or_restore_day_block(tmp_path):
    budget = AIBudget(tmp_path / "budget.sqlite3")
    try:
        budget.set_cost_limit(GlobalAICostLimit(cost_limit_enabled=False), NOW, "cli")
        for i in range(2):
            assert budget.reserve("a", "trade", str(i), 1, NOW, 2, Decimal(".05"), {})["granted"]
        status = budget.status(NOW)
        assert status["call_limit_reached"] and not status["cost_limit_reached"]
        assert not budget.reserve("b", "trade", "third", 1, NOW, 240, Decimal(".05"), {})["granted"]
        later = NOW + timedelta(days=1)
        budget.block_day(later)
        budget.set_cost_limit(GlobalAICostLimit(cost_limit_enabled=False), later, "cli")
        assert budget.status(later)["recovery_blocked"]
        assert not budget.reserve("b", "trade", "restored", 1, later, 240, Decimal(".05"), {})[
            "granted"
        ]
    finally:
        budget.close()
