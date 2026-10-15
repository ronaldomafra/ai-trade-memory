"""Decisions HTTP only; bounded retries, durable global reservations, safe diagnostics."""

import asyncio
import json
import random
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from poc.adapters.outbound.budget import AIBudget
from poc.application.ports import Clock, SessionStore
from poc.config import AI
from poc.domain.primitives import canonical_json, stable_id, utc


class OpenRouterDecisions:
    def __init__(
        self,
        config: AI,
        key: str | None,
        run_id: str,
        budget: AIBudget,
        clock: Clock,
        store: SessionStore | None = None,
        client: httpx.AsyncClient | None = None,
        sleep=asyncio.sleep,
    ):
        self.config, self.key, self.run_id, self.budget, self.clock = (
            config,
            key,
            run_id,
            budget,
            clock,
        )
        self.store = store
        self.sleep = sleep
        self.credential_id = stable_id("openrouter-credential", key) if key else None
        self.session_budget = getattr(config, "budget_scope", None) == "SESSION"
        if self.session_budget:
            budget.bind_session(
                run_id,
                config.max_calls_per_day,
                config.max_observed_cost_usd_per_day,
                config.cost_limit_enabled,
                clock.now(),
            )
        self.client = client or httpx.AsyncClient(
            timeout=config.timeout_seconds, follow_redirects=False, trust_env=False
        )
        self.owns_client = client is None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()

    async def check_auth(self, recover: bool = False) -> dict:
        """Explicit key GET, without inference, provider-body logging or budget reset."""
        result = {
            "scope": "OPENROUTER_KEY_CHECK_NO_INFERENCE",
            "authenticated": False,
            "http_status": None,
            "auth_circuit_cleared": False,
            "circuit_open": bool(self.credential_id and self.budget.circuit(self.credential_id)),
            "error_code": None,
        }
        if not self.key:
            return {**result, "error_code": "AI_NOT_CONFIGURED"}
        started = self.clock.now()
        try:
            response = await self.client.get(
                "https://openrouter.ai/api/v1/key",
                headers={"Authorization": f"Bearer {self.key}"},
                timeout=self.config.timeout_seconds,
            )
            result["http_status"] = response.status_code
            if response.status_code != 200:
                return {**result, "error_code": f"AI_HTTP_{response.status_code}"}
            if len(response.content) > 262144:
                return {**result, "error_code": "INVALID_AI_KEY_RESPONSE"}
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
                return {**result, "error_code": "INVALID_AI_KEY_RESPONSE"}
        except httpx.TransportError:
            return {**result, "error_code": "AI_AUTH_CHECK_UNAVAILABLE"}
        except (ValueError, UnicodeDecodeError):
            return {**result, "error_code": "INVALID_AI_KEY_RESPONSE"}
        result["authenticated"] = True
        if recover:
            result["auth_circuit_cleared"] = self.budget.clear_verified_auth_circuit(
                self.credential_id, started
            )
        result["circuit_open"] = self.budget.circuit(self.credential_id)
        return result

    def reconcile(self):
        if self.store:
            with self.store.transaction():
                for row in self.budget.attempts_for_run(self.run_id):
                    self.store.save_ai_call(row)

    def _persist(self, call_id):
        if self.store:
            with self.store.transaction():
                self.store.save_ai_call(self.budget.attempt(call_id))

    def _safe(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: self._safe(v)
                for k, v in data.items()
                if k.lower() not in ("authorization", "api_key", "token", "headers")
            }
        if isinstance(data, list):
            return [self._safe(v) for v in data]
        if isinstance(data, str) and self.key:
            return data.replace(self.key, "[REDACTED]")
        return data

    async def call(self, payload: dict, logical_id: str, purpose: str, deadline: datetime) -> dict:
        if not self.key:
            return {"error_code": "AI_NOT_CONFIGURED"}
        if self.budget.circuit(self.credential_id):
            return {"error_code": "AI_CIRCUIT_OPEN"}
        last = {"error_code": "AI_DEADLINE_EXCEEDED"}
        for index in range(1, 2 + self.config.max_retries):
            now = self.clock.now()
            if (utc(deadline) - utc(now)).total_seconds() < self.config.timeout_seconds:
                return last
            reservation = self.budget.reserve(
                self.run_id,
                purpose,
                logical_id,
                index,
                now,
                self.config.max_calls_per_day,
                self.config.max_observed_cost_usd_per_day,
                self._safe(payload),
                **(
                    {"cost_limit_enabled": self.config.cost_limit_enabled}
                    if self.session_budget
                    else {}
                ),
            )
            if not reservation["granted"]:
                call_id = reservation.get("ai_call_id")
                if call_id:
                    row = self.budget.attempt(call_id)
                    self._persist(call_id)
                    if row["status"] == "COMPLETED":
                        return {"ai_call_id": call_id, "response": self.budget.response(row)}
                    # A crash/indeterminate result never permits a new send on replay.
                    return {"ai_call_id": call_id, "error_code": "AI_ATTEMPT_INDETERMINATE"}
                return {"error_code": reservation["reason"]}
            call_id = reservation["ai_call_id"]
            self._persist(call_id)  # If the local projection fails, reservation remains counted.
            status, response, error, retry, retry_after = None, None, None, False, 0.0
            try:
                http = await self.client.post(
                    self.config.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": "application/json",
                    },
                    content=canonical_json(payload),
                    timeout=self.config.timeout_seconds,
                )
                status = http.status_code
                if len(http.content) <= 262144:
                    try:
                        parsed = json.loads(
                            http.content,
                            parse_float=Decimal,
                            parse_constant=lambda x: (_ for _ in ()).throw(
                                ValueError("Nonfinite JSON")
                            ),
                        )
                        if isinstance(parsed, dict):
                            response = self._safe(parsed)
                    except (ValueError, UnicodeDecodeError):
                        pass
                if status != 200:
                    error = f"AI_HTTP_{status}"
                    retry = status == 429 or 500 <= status <= 599
                    if status in (401, 402, 403):
                        self.budget.open_circuit(self.credential_id, error, self.clock.now())
                    try:
                        retry_after = max(0.0, float(http.headers.get("Retry-After", "0")))
                    except ValueError:
                        try:
                            retry_after = max(
                                0.0,
                                (
                                    utc(parsedate_to_datetime(http.headers["Retry-After"]))
                                    - utc(self.clock.now())
                                ).total_seconds(),
                            )
                        except (KeyError, ValueError, TypeError, OverflowError):
                            retry_after = 0.0
                elif response is None:
                    error = "INVALID_AI_RESPONSE"
            except (httpx.TransportError, TimeoutError):
                error, retry = "AI_TRANSPORT_UNKNOWN_BILLING", True
            # Cancellation deliberately leaves a RESERVED attempt with unknown billing.
            row = self.budget.finish(call_id, self.clock.now(), response, status, error)
            self._persist(call_id)
            last = {
                "ai_call_id": call_id,
                "response": self.budget.response(row),
                "error_code": error,
            }
            if not retry or index > self.config.max_retries:
                return last
            wait = max(retry_after, 0.5 + random.random() * 0.5)
            if (
                utc(deadline) - utc(self.clock.now())
            ).total_seconds() < wait + self.config.timeout_seconds:
                return last
            await self.sleep(wait)
        return last
