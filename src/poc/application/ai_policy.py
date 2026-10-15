"""Equivalent B/C states share one physical inference; memory stays exclusive to C."""

import asyncio
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol

from poc.config import Config
from poc.domain.factors import entry_foundation
from poc.domain.jev import compact_trade_state, parse_trade_response, trade_payload
from poc.domain.models import Action, Proposal
from poc.domain.primitives import stable_id


class DecisionsPort(Protocol):
    async def call(
        self, payload: dict, logical_id: str, purpose: str, deadline: datetime
    ) -> dict: ...


class JEVPolicy:
    def __init__(self, config: Config, client: DecisionsPort):
        self.config, self.client = config, client

    async def propose(
        self, cycle_id: str, states: dict[str, dict[str, Any]], deadline: datetime
    ) -> dict[str, Proposal]:
        grouped: dict[str, list[tuple[str, dict]]] = {}
        for portfolio, state in states.items():
            # An unavailable/insufficient memory has no statistical evidence. Canonicalize it
            # to the disabled control state to preserve the comparison until C can use memory.
            state = {**state}
            if state.get("historical_feedback", {}).get("status") not in ("ready", "available"):
                state["historical_feedback"] = {"status": "disabled"}
            state = compact_trade_state(state)
            grouped.setdefault(stable_id(state), []).append((portfolio, state))

        async def infer(fingerprint, members):
            try:
                payload = trade_payload(members[0][1], self.config.ai.model)
            except ValueError:
                proposal = Proposal(Action.HOLD, "AI_CONTEXT_TOO_LARGE")
            else:
                row = await self.client.call(
                    payload,
                    stable_id(cycle_id, self.config.ai.prompt_version, fingerprint),
                    "trade",
                    deadline,
                )
                proposal = (
                    parse_trade_response(
                        row["response"],
                        self.config.strategy.action_probability_threshold,
                        self.config.strategy.action_margin_threshold,
                        row["ai_call_id"],
                    )
                    if row.get("response") is not None and not row.get("error_code")
                    else Proposal(
                        Action.HOLD,
                        row.get("error_code") or "AI_FAILURE",
                        ai_call_id=row.get("ai_call_id"),
                    )
                )
                if proposal.action == Action.BUY:
                    eligible, reason = entry_foundation(members[0][1], row["response"])
                    if not eligible:
                        proposal = replace(proposal, action=Action.HOLD, reason=reason)
            return {
                portfolio: replace(proposal, feedback=states[portfolio].get("historical_feedback"))
                for portfolio, _ in members
            }

        results = await asyncio.gather(*(infer(key, members) for key, members in grouped.items()))
        return {key: proposal for result in results for key, proposal in result.items()}
