"""One explicit Decisions call with a fictional state and no trading service."""

import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.openrouter import OpenRouterDecisions
from poc.bootstrap import SystemClock
from poc.config import Config
from poc.domain.jev import parse_trade_response, trade_payload
from poc.domain.primitives import DomainError


async def check_openrouter(config: Config, recover: bool = False) -> dict:
    budget = AIBudget(Path(config.app.data_dir) / "operational" / "ai-budget.sqlite3")
    client = OpenRouterDecisions(
        config.ai, os.environ.get("OPENROUTER_API_KEY"), "check-openrouter", budget, SystemClock()
    )
    try:
        return await client.check_auth(recover)
    finally:
        await client.close()
        budget.close()


async def smoke_openrouter(config: Config) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise DomainError("OPENROUTER_API_KEY is not configured")
    clock = SystemClock()
    budget = AIBudget(Path(config.app.data_dir) / "operational" / "ai-budget.sqlite3")
    run_id = "smoke-openrouter-" + uuid4().hex
    client = OpenRouterDecisions(
        config.ai.model_copy(update={"max_retries": 0}), key, run_id, budget, clock
    )
    try:
        payload = trade_payload(
            {
                "symbol": config.market.symbol,
                "base_asset": config.market.symbol[:-4],
                "quote_asset": "USDT",
                "fixture": True,
                "portfolio": {"has_position": False},
                "market": {"status": "unavailable"},
                "news": {"status": "unavailable", "items": []},
                "prediction_markets": {"status": "unavailable", "items": []},
                "historical_feedback": {"status": "disabled"},
            },
            config.ai.model,
        )
        result = await client.call(payload, run_id, "smoke", clock.now() + timedelta(seconds=30))
        response = result.get("response") or {}
        call_id = result.get("ai_call_id")
        row = budget.attempt(call_id) if call_id else None
        proposal = parse_trade_response(response, 0.65, 0.10, call_id) if call_id else None
        return {
            "scope": "DECISIONS_API_SMOKE_NO_TRADING",
            "ai_call_id": call_id,
            "actual_model": response.get("model"),
            "provider_generation_id": response.get("id"),
            "usage": response.get("usage"),
            "cost_usd": row["cost_usd"] if row else None,
            "cost_source": row["cost_source"] if row else "unknown",
            "error_code": result.get("error_code"),
            "validation": proposal.reason if proposal else None,
            "global_budget": budget.summary(clock.now()),
        }
    finally:
        await client.close()
        budget.close()
