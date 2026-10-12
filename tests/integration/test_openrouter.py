from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from test_accounting import setup

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.openrouter import OpenRouterDecisions
from poc.application.ai_policy import JEVPolicy
from poc.config import Config
from poc.domain.models import Action


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 12, tzinfo=UTC)

    def now(self):
        return self.value

    async def sleep(self, seconds):
        self.value += timedelta(seconds=seconds)


def http_response():
    return {
        "id": "physical-1",
        "model": "typesafe/jev-1.13-test",
        "answers": {
            "action": {
                "type": "choice",
                "choice": "buy",
                "confidence": 0.81,
                "probabilities": {"buy": 0.74, "sell": 0.06, "hold": 0.20},
            },
            "adverse_news_risk": {"type": "noul", "noul": 0.08},
            "entry_foundation": {
                "type": "choice",
                "choice": "TECHNICAL_INDEPENDENT",
                "probabilities": {"TECHNICAL_INDEPENDENT": 1, "INSUFFICIENT": 0},
            },
        },
        "usage": {"input_tokens": 500, "output_tokens": 20, "cost": 0.000021},
    }


@pytest.mark.asyncio
async def test_shared_control_response_cost_is_counted_once_and_replay_does_not_send(tmp_path):
    calls = []

    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/alpha/decisions"
        assert request.headers["authorization"] == "Bearer test-secret"
        calls.append(request)
        return httpx.Response(200, json=http_response())

    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(
            Config().ai, "test-secret", "r", budget, clock, client=http, sleep=clock.sleep
        )
        policy = JEVPolicy(Config(), client)
        states = {
            "JEV_STATIC": {
                "historical_feedback": {"status": "disabled"},
                "portfolio": {"has_position": False},
            },
            "JEV_LEARNING": {
                "historical_feedback": {"status": "insufficient"},
                "portfolio": {"has_position": False},
            },
        }
        for state in states.values():
            state["news"] = {
                "status": "no_relevant_items",
                "items": [],
                "absence_verified_in_scope": True,
            }
            state["market"] = {
                "valid": True,
                "rsi_14": 60,
                "ema_short": 100,
                "ema_mid": 90,
                "ema_long": 80,
                "macd_histogram": 1,
                "atr_pct": 0.5,
                "volume_ratio": 1.2,
            }
        result = await policy.propose("cycle", states, clock.now() + timedelta(seconds=90))
        assert result["JEV_STATIC"].action == Action.BUY
        assert result["JEV_STATIC"].ai_call_id == result["JEV_LEARNING"].ai_call_id
        await policy.propose("cycle", states, clock.now() + timedelta(seconds=90))
        assert len(calls) == 1
        assert budget.summary(clock.now())["physical_attempts"] == 1
        assert Decimal(budget.summary(clock.now())["observed_cost_usd"]) == Decimal(".000021")
        assert "test-secret" not in str(budget.attempts_for_run("r"))
    budget.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(429, 2), (503, 2), (401, 1), (402, 1), (403, 1), (400, 1), (200, 1)]
)
async def test_only_transient_failures_retry_and_auth_opens_persistent_circuit(
    tmp_path, status, expected
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"message": "secret-key"}}, headers={"Retry-After": "1"}
        )

    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(
            Config().ai, "secret-key", "r", budget, clock, client=http, sleep=clock.sleep
        )
        await client.call(
            {"model": Config().ai.model}, "logical", "trade", clock.now() + timedelta(seconds=90)
        )
        assert len(calls) == expected
        assert budget.summary(clock.now())["unknown_cost_calls"] == expected
        assert "secret-key" not in str(budget.attempts_for_run("r"))
        if status in (401, 402, 403):
            result = await client.call(
                {"model": Config().ai.model}, "other", "trade", clock.now() + timedelta(seconds=90)
            )
            assert result["error_code"] == "AI_CIRCUIT_OPEN" and len(calls) == 1
    budget.close()


@pytest.mark.asyncio
async def test_timeout_counts_unknown_billing_and_never_third_attempt(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret not serialized", request=request)

    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(
            Config().ai, "secret", "r", budget, clock, client=http, sleep=clock.sleep
        )
        payload = {"model": Config().ai.model}
        await client.call(payload, "logical", "trade", clock.now() + timedelta(seconds=90))
        await client.call(payload, "logical", "trade", clock.now() + timedelta(seconds=90))
        assert len(calls) == 2
        assert budget.summary(clock.now())["unknown_cost_calls"] == 2
        assert budget.summary(clock.now())["observed_cost_usd"] == "0"
        no_window = await client.call(payload, "new", "trade", clock.now() + timedelta(seconds=19))
        assert no_window["error_code"] == "AI_DEADLINE_EXCEEDED" and len(calls) == 2
    budget.close()


@pytest.mark.asyncio
async def test_global_result_survives_crash_before_local_projection_and_is_reconciled(tmp_path):
    cfg, manager, db, _ = setup(tmp_path / "session")
    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=http_response())

    class FailingProjection:
        def __init__(self):
            self.saves = 0

        def transaction(self):
            return db.transaction()

        def save_ai_call(self, row):
            self.saves += 1
            if self.saves == 2:
                raise RuntimeError("simulated crash after global commit")
            db.save_ai_call(row)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(
            cfg.ai, "secret", "run-1", budget, clock, FailingProjection(), http
        )
        with pytest.raises(RuntimeError):
            await client.call(
                {"model": cfg.ai.model}, "logical", "trade", clock.now() + timedelta(seconds=90)
            )
        row = budget.attempts_for_run("run-1")[0]
        assert row["status"] == "COMPLETED"
        assert db.connection.execute("SELECT status FROM ai_calls").fetchone()[0] == "RESERVED"
        recovered = OpenRouterDecisions(cfg.ai, "secret", "run-1", budget, clock, db, http)
        recovered.reconcile()
        result = await recovered.call(
            {"model": cfg.ai.model}, "logical", "trade", clock.now() + timedelta(seconds=90)
        )
        assert result["response"]["id"] == "physical-1" and len(calls) == 1
        assert (
            db.connection.execute("SELECT status,cost_usd FROM ai_calls").fetchone()[0]
            == "COMPLETED"
        )
    db.close()
    budget.close()
