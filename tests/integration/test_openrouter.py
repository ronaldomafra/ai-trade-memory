import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from test_accounting import setup

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.openrouter import OpenRouterDecisions
from poc.application.ai_policy import JEVPolicy
from poc.config import Config, GlobalAICostLimit
from poc.domain.models import Action
from poc.domain.primitives import stable_id
from poc.profile_config import ProfileDefinition, profile_template, resolve_profile


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 12, tzinfo=UTC)

    def now(self):
        return self.value

    async def sleep(self, seconds):
        self.value += timedelta(seconds=seconds)


@pytest.mark.asyncio
@pytest.mark.parametrize("lag,sends", [(8, 0), (15, 1)])
async def test_scalping_preparation_latency_leaves_room_for_inference(tmp_path, lag, sends):
    definition = profile_template("SCALPING")
    definition["parameters"]["app"]["max_candle_decision_lag_seconds"] = lag
    cfg = resolve_profile(ProfileDefinition.model_validate(definition), Config(), "ZECUSDT")
    clock = Clock()
    deadline = clock.now() + timedelta(seconds=cfg.app.max_candle_decision_lag_seconds)
    clock.value += timedelta(seconds=2.3)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=http_response())

    budget = AIBudget(tmp_path / "budget.sqlite3")
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterDecisions(
                cfg.ai, "synthetic-key", "scalping-fixture", budget, clock, client=http
            )
            result = await client.call({}, "scalping-cycle", "trade", deadline)
            assert len(requests) == sends
            assert budget.summary(clock.now())["physical_attempts"] == sends
            if sends:
                assert result.get("response") and not result.get("error_code")
            else:
                assert result["error_code"] == "AI_DEADLINE_EXCEEDED"
    finally:
        budget.close()


@pytest.mark.asyncio
async def test_configured_global_cost_toggle_is_used_by_openrouter_without_resetting_usage(
    tmp_path,
):
    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    sent = []

    def handler(request):
        sent.append(request)
        response = http_response()
        response["usage"]["cost"] = "0.08"
        return httpx.Response(200, json=response)

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterDecisions(
                Config().ai, "synthetic-key", "run", budget, clock, client=http
            )
            deadline = clock.now() + timedelta(seconds=90)
            assert (await client.call({}, "one", "trade", deadline)).get("response")
            assert (await client.call({}, "two", "trade", deadline))[
                "error_code"
            ] == "AI_BUDGET_EXCEEDED"
            budget.set_cost_limit(GlobalAICostLimit(cost_limit_enabled=False), clock.now(), "owner")
            assert (await client.call({}, "three", "context_classification", deadline)).get(
                "response"
            )
            assert len(sent) == 2
            assert budget.summary(clock.now())["physical_attempts"] == 2
            assert Decimal(budget.summary(clock.now())["observed_cost_usd"]) == Decimal("0.16")
    finally:
        budget.close()


@pytest.mark.asyncio
async def test_hundreds_of_pending_markets_do_not_block_or_enter_decisions_request(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        assert len(request.content) < 6000
        assert "rejected-market-" not in request.content.decode()
        return httpx.Response(200, json=http_response())

    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(Config().ai, "synthetic-key", "r", budget, clock, client=http)
        state = {
            "historical_feedback": {"status": "disabled"},
            "portfolio": {"has_position": False},
            "prediction_markets": {
                "status": "unavailable",
                "items": [],
                "coverage": "PARTIAL",
                "absence_verified_in_scope": False,
                "pending": [
                    {
                        "market_id": f"rejected-market-{i}",
                        "reasons": ["GAMMA_METRIC_UNITS_UNVERIFIED"],
                    }
                    for i in range(500)
                ],
            },
        }
        results = await JEVPolicy(Config(), client).propose(
            "cycle",
            {"JEV_STATIC": state, "JEV_LEARNING": state},
            clock.now() + timedelta(seconds=90),
        )
        assert len(calls) == 1 and budget.summary(clock.now())["physical_attempts"] == 1
        assert calls[0]["state"]["prediction_markets"]["pending_count"] == 500
        assert all(p.reason == "EXTERNAL_CONTEXT_UNAVAILABLE" for p in results.values())
        assert all(p.action == Action.HOLD for p in results.values())
        assert len(state["prediction_markets"]["pending"]) == 500
    budget.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,recover,cleared",
    [
        (200, {"data": {}}, True, True),
        (200, {"data": {}}, False, False),
        (401, {"error": {"message": "synthetic-key"}}, True, False),
        (403, {"error": {"message": "synthetic-key"}}, True, False),
        (200, {"error": "not key metadata"}, True, False),
    ],
)
async def test_key_check_only_recovers_verified_401_without_inference_or_reset(
    tmp_path, status, body, recover, cleared
):
    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    identity = stable_id("openrouter-credential", "synthetic-key")
    budget.open_circuit(identity, "AI_HTTP_401", clock.now())
    budget.open_circuit("other-credential", "AI_HTTP_401", clock.now())
    reservation = budget.reserve("old", "trade", "old", 1, clock.now(), 240, Decimal(".05"), {})
    before = budget.summary(clock.now())
    requests = []

    def handler(request):
        assert request.method == "GET"
        assert str(request.url) == "https://openrouter.ai/api/v1/key"
        requests.append(request)
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterDecisions(Config().ai, "synthetic-key", "r", budget, clock, client=http)
        result = await client.check_auth(recover)
        assert len(requests) == 1 and result["auth_circuit_cleared"] is cleared
        assert result["circuit_open"] is (not cleared)
        assert "synthetic-key" not in str(result)
        assert budget.summary(clock.now()) == before
        assert budget.attempt(reservation["ai_call_id"])["status"] == "RESERVED"
        assert budget.circuit("other-credential")
    budget.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,newer", [("AI_HTTP_402", False), ("AI_HTTP_403", False), ("AI_HTTP_401", True)]
)
async def test_auth_recovery_keeps_non_auth_and_newer_failures(tmp_path, error, newer):
    budget, clock = AIBudget(tmp_path / "budget.sqlite3"), Clock()
    identity = stable_id("openrouter-credential", "synthetic-key")
    opened = clock.now() + timedelta(seconds=1) if newer else clock.now()
    budget.open_circuit(identity, error, opened)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {}}))
    ) as http:
        client = OpenRouterDecisions(Config().ai, "synthetic-key", "r", budget, clock, client=http)
        result = await client.check_auth(recover=True)
        assert result["authenticated"] and result["circuit_open"]
        assert not result["auth_circuit_cleared"]
    budget.close()


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
