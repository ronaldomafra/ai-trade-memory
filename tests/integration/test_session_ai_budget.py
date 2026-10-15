from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from poc.adapters.outbound.budget import AIBudget
from poc.config import GlobalAICostLimit
from poc.domain.primitives import DomainError

NOW = datetime(2026, 10, 14, tzinfo=UTC)


def reserve(budget, run, logical, calls=3, cost="0.05", enabled=True, now=NOW):
    return budget.reserve(
        run, "trade", logical, 1, now, calls, Decimal(cost), {}, cost_limit_enabled=enabled
    )


def test_session_reservations_are_atomic_and_independent_across_bots(tmp_path):
    path = tmp_path / "budget.sqlite3"
    initial = AIBudget(path)
    # A legacy bot has exhausted the old shared limit; it cannot block new bots.
    initial.reserve("legacy", "trade", "last", 1, NOW, 1, Decimal(".05"), {})
    initial.close()

    def send(index):
        b = AIBudget(path)
        try:
            run = "scalp" if index % 2 else "swing"
            return run, reserve(b, run, str(index), calls=3 if run == "scalp" else 5)["granted"]
        finally:
            b.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(send, range(30)))
    assert sum(ok for run, ok in results if run == "scalp") == 3
    assert sum(ok for run, ok in results if run == "swing") == 5
    b = AIBudget(path)
    assert b.session_status(NOW, "scalp")["physical_attempts"] == 3
    assert b.session_status(NOW, "swing")["physical_attempts"] == 5
    assert b.summary(NOW)["physical_attempts"] == 9
    assert b.status(NOW)["physical_attempts"] == 1
    b.close()


def test_cost_toggle_and_limits_are_local_and_not_clamped_to_legacy_ceiling(tmp_path):
    b = AIBudget(tmp_path / "budget.sqlite3")
    # Disabling a legacy global guard must not disable a new bot's own guard.
    b.set_cost_limit(GlobalAICostLimit(cost_limit_enabled=False), NOW, "test")
    first = reserve(b, "small", "one", calls=500, cost="0.01")
    b.finish(first["ai_call_id"], NOW, {"usage": {"cost": "0.02"}}, 200, None)
    assert not reserve(b, "small", "two", calls=500, cost="0.01")["granted"]
    assert reserve(b, "large", "one", calls=1000, cost="1.00")["granted"]
    off = reserve(b, "off", "one", calls=2, cost="0.01", enabled=False)
    b.finish(off["ai_call_id"], NOW, {"usage": {"cost": "2.00"}}, 200, None)
    assert reserve(b, "off", "two", calls=2, cost="0.01", enabled=False)["granted"]
    assert not reserve(b, "off", "three", calls=2, cost="0.01", enabled=False)["granted"]
    assert b.session_status(NOW, "large")["max_calls_per_day"] == 1000
    assert b.session_status(NOW, "large")["policy"]["max_observed_cost_usd_per_day"] == "1"
    assert not b.session_status(NOW, "off")["cost_limit_reached"]
    assert b.session_status(NOW, "small")["cost_limit_reached"]
    b.close()


def test_restart_unknown_cost_replay_rollover_and_recovery_block_are_preserved(tmp_path):
    path = tmp_path / "budget.sqlite3"
    b = AIBudget(path)
    first = reserve(b, "a", "one", calls=1, enabled=False)
    b.close()
    b = AIBudget(path)
    replay = reserve(b, "a", "one", calls=1, enabled=False)
    assert replay["reason"] == "ATTEMPT_ALREADY_RESERVED"
    assert replay["ai_call_id"] == first["ai_call_id"]
    assert b.session_status(NOW, "a")["unknown_cost_calls"] == 1
    assert not reserve(b, "a", "two", calls=1, enabled=False)["granted"]
    with pytest.raises(DomainError, match="fall back"):
        b.reserve("a", "trade", "bypass", 1, NOW, 240, Decimal(".05"), {})
    assert reserve(b, "b", "one", calls=1)["granted"]
    with pytest.raises(DomainError, match="immutable"):
        reserve(b, "a", "changed", calls=2, enabled=False)
    tomorrow = NOW + timedelta(days=1)
    assert reserve(b, "a", "next-day", calls=1, enabled=False, now=tomorrow)["granted"]
    b.block_day(tomorrow)
    assert not reserve(b, "c", "recovery", enabled=False, now=tomorrow)["granted"]
    assert b.session_status(tomorrow, "a")["recovery_blocked"]
    b.close()


@pytest.mark.asyncio
async def test_api_profile_and_creation_budget_overrides_are_scoped_and_global_write_is_retired(
    tmp_path,
):
    from test_control_api import cleanup, fixture

    from poc.profile_config import profile_template

    items = await fixture(tmp_path)
    client, _, _, runtime, _, _, _, _ = items
    try:
        definition = profile_template("SCALPING")
        definition["profile"]["profile_id"] = "budget_profile"
        definition["parameters"]["ai"].update(
            max_calls_per_day=1000, max_observed_cost_usd_per_day="0.50"
        )
        preview = await client.post("/v1/profiles/validate", json=definition)
        assert preview.status_code == 200
        assert preview.json()["preview"]["ai_budget"]["scope"] == "SESSION"
        assert (
            await client.post(
                "/v1/profiles", json=definition, headers={"Idempotency-Key": "budget-register"}
            )
        ).status_code == 201
        assert (
            await client.post(
                "/v1/profiles/budget_profile/versions/1/publish",
                headers={"Idempotency-Key": "budget-publish"},
            )
        ).status_code == 200
        body = {
            "profile_id": "budget_profile",
            "run_id": "budget-bot",
            "symbol": "ETHUSDT",
            "overrides": {
                "ai": {
                    "max_calls_per_day": 1500,
                    "max_observed_cost_usd_per_day": "1.00",
                    "cost_limit_enabled": False,
                }
            },
        }
        assert (
            await client.post(
                "/v1/sessions", json=body, headers={"Idempotency-Key": "budget-session"}
            )
        ).status_code == 201
        status = await client.get("/v1/sessions/budget-bot/ai-budget")
        assert status.status_code == 200 and status.json()["scope"] == "SESSION"
        assert status.json()["max_calls_per_day"] == 1500
        assert status.json()["policy"]["cost_limit_enabled"] is False
        assert status.json()["policy"]["max_observed_cost_usd_per_day"] == "1.00"
        rejected = await client.put(
            "/v1/ai-budget",
            json={"cost_limit_enabled": False, "max_observed_cost_usd_per_day": "1.00"},
        )
        assert rejected.status_code == 409
        assert (await client.get("/v1/ai-budget")).json()["scope"] == "ALL_SESSIONS_REPORT"
        assert runtime.starts == 0
        client.headers.pop("Authorization")
        assert (await client.get("/v1/sessions/budget-bot/ai-budget")).status_code == 401
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_exhausted_bot_does_not_poison_shared_classification_and_cache_hits_are_free(
    tmp_path,
):
    import json

    import httpx
    from test_news_classification_reuse import Client, Clock, item

    from poc.adapters.outbound.openrouter import OpenRouterDecisions
    from poc.adapters.outbound.source_cache import SourceCache
    from poc.application.context import ContextClassifier
    from poc.config import Config
    from poc.profile_config import ProfileDefinition, profile_template, resolve_profile

    definition = profile_template("SCALPING")
    definition["parameters"]["ai"]["max_calls_per_day"] = 1
    cfg = resolve_profile(ProfileDefinition.model_validate(definition), Config(), "ETHUSDT")
    clock = Clock()
    b = AIBudget(tmp_path / "budget.sqlite3")
    cache = SourceCache(tmp_path / "sources.sqlite3")
    semantic = Client(clock)

    async def respond(request):
        payload = json.loads(request.content)
        response = await semantic.call(payload, "fixture", "context_classification", clock.now())
        response["response"]["usage"] = {"cost": "0.01"}
        return httpx.Response(200, json=response["response"])

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    a = OpenRouterDecisions(cfg.ai, "synthetic-key", "exhausted", b, clock, client=http)
    funded = OpenRouterDecisions(cfg.ai, "synthetic-key", "funded", b, clock, client=http)
    try:
        reserve(b, "exhausted", "used", calls=1, now=clock.now())
        first = ContextClassifier(cfg, a, cache, clock, a.credential_id)
        second = ContextClassifier(cfg, funded, cache, clock, funded.credential_id)
        assert (await first.classify(item("same"), [], "ETH"))["status"] == "UNAVAILABLE"
        accepted = await second.classify(item("same"), [], "ETH")
        assert accepted["status"] == "READY" and len(semantic.calls) == 1
        reused = await first.classify(item("same"), [], "ETH")
        assert reused["classification_id"] == accepted["classification_id"]
        assert len(semantic.calls) == 1
        assert b.session_status(clock.now(), "funded")["physical_attempts"] == 1
        assert b.session_status(clock.now(), "exhausted")["physical_attempts"] == 1
    finally:
        await http.aclose()
        cache.close()
        b.close()


@pytest.mark.asyncio
async def test_scoped_budget_read_does_not_expose_other_sessions(tmp_path):
    from test_accounting import config, meta
    from test_control_api import cleanup, fixture

    from poc.adapters.outbound.sqlite import SQLiteStorage
    from poc.application.sessions import SessionManager
    from poc.profile_config import ProfileDefinition, profile_template, resolve_profile

    items = await fixture(tmp_path, scopes=("read",), sessions=("own",))
    client = items[0]
    try:
        definition = ProfileDefinition.model_validate(profile_template("SCALPING"))
        cfg = resolve_profile(definition, config(tmp_path), "BTCUSDT")
        SessionManager(cfg, SQLiteStorage()).prepare(
            "own", definition.profile.profile_id, meta(), NOW
        )
        assert (await client.get("/v1/sessions/own/ai-budget")).status_code == 200
        assert (await client.get("/v1/sessions/other/ai-budget")).status_code == 403
        assert (await client.get("/v1/ai-budget")).status_code == 403
    finally:
        await cleanup(items)


def test_session_can_use_more_than_240_calls_without_resetting_other_usage(tmp_path):
    b = AIBudget(tmp_path / "budget.sqlite3")
    try:
        for i in range(241):
            assert reserve(b, "scalp", str(i), calls=300, enabled=False)["granted"]
        assert b.session_status(NOW, "scalp")["physical_attempts"] == 241
        assert reserve(b, "swing", "first", calls=2)["granted"]
        assert b.session_status(NOW, "swing")["physical_attempts"] == 1
    finally:
        b.close()


@pytest.mark.asyncio
async def test_existing_published_profile_gets_session_budget_without_rewriting_catalog(tmp_path):
    from test_control_api import cleanup, fixture

    from poc.adapters.outbound.profiles import SQLiteProfiles
    from poc.adapters.outbound.sqlite import SessionDatabase
    from poc.profile_config import ProfileDefinition, profile_template

    items = await fixture(tmp_path)
    client, _, commands, _, _, clock, _, _ = items
    try:
        old = profile_template("SCALPING")
        old["profile"]["profile_id"] = "existing_scalp"
        old["parameters"]["ai"].pop("budget_scope")
        old["parameters"]["ai"].pop("cost_limit_enabled")
        old["platform_bindings"].pop("ai_budget_reference")
        old["platform_bindings"].update(
            global_ai_policy_reference="SERVER_GLOBAL_AI_BUDGET", physical_calls_global_ceiling=240
        )
        definition = ProfileDefinition.model_validate(old)
        raw = definition.model_dump(mode="json")
        repository = SQLiteProfiles(commands.connection)
        repository.register_profile(raw, definition.hash, "fixture-seed", clock.now())
        repository.transition_profile(
            "existing_scalp", 1, "READY_FOR_PAPER", "fixture-seed", clock.now()
        )
        profiles = (await client.get("/v1/profiles")).json()["profiles"]
        selected = next(p for p in profiles if p["profile_id"] == "existing_scalp")
        assert selected["template"]["ai"]["budget_scope"] == "SESSION"
        assert "budget_scope" not in selected["definition"]["parameters"]["ai"]
        response = await client.post(
            "/v1/sessions",
            json={
                "profile_id": "existing_scalp",
                "profile_version": 1,
                "profile_hash": definition.hash,
                "symbol": "ETHUSDT",
                "run_id": "adopted",
                "overrides": {"ai": {"max_calls_per_day": 1000}},
            },
            headers={"Idempotency-Key": "adopt-budget-session"},
        )
        assert response.status_code == 201
        assert repository.profile("existing_scalp", 1)["definition"] == raw
        db = SessionDatabase(tmp_path / "sessions/adopted/poc.sqlite3", create=False, readonly=True)
        assert db.run()["config"]["ai"]["budget_scope"] == "SESSION"
        assert db.run()["config"]["ai"]["max_calls_per_day"] == 1000
        db.close()
    finally:
        await cleanup(items)
