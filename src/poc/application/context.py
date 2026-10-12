"""Semantic classification reuses immutable evidence; collection remains an outbound adapter."""

from datetime import datetime, timedelta
from typing import Protocol

from poc.application.ai_policy import DecisionsPort
from poc.application.ports import Clock
from poc.config import Config
from poc.domain.factors import classification_payload, classification_result
from poc.domain.primitives import iso, stable_id


class ContextCachePort(Protocol):
    def classification(self, identity: str, cutoff: datetime) -> dict | None: ...
    def save_classification(self, identity: str, result: dict, now: datetime) -> None: ...
    def reserve(self, provider: str, scope: dict, now: datetime, poll_seconds: int) -> dict: ...
    def finish(self, request_id: str, result: dict, now: datetime) -> None: ...


class ContextClassifier:
    def __init__(
        self,
        config: Config,
        client: DecisionsPort,
        cache: ContextCachePort,
        clock: Clock,
        credential_version: str | None,
    ):
        self.config, self.client, self.cache, self.clock = config, client, cache, clock
        self.credential_version = credential_version

    async def classify(self, item: dict, peers: list[dict], base_asset: str) -> dict:
        payload = classification_payload(
            item, peers, self.config.market.symbol, base_asset, self.config.ai.model
        )
        identity = stable_id(payload)
        existing = self.cache.classification(identity, self.clock.now())
        if existing:
            return existing
        attempt_identity = stable_id(identity, self.credential_version)
        reserved = self.cache.reserve(
            "context-classification", {"input_id": attempt_identity}, self.clock.now(), 10**12
        )
        if not reserved["granted"]:
            return reserved.get("cached") or {
                "status": "PENDING",
                "reason": reserved["reason"],
                "classification_id": identity,
            }
        try:
            response = await self.client.call(
                payload,
                attempt_identity,
                "context_classification",
                self.clock.now() + timedelta(seconds=45),
            )
        except Exception as error:
            response = {
                "error_code": "CLASSIFICATION_OPERATION_UNAVAILABLE_" + type(error).__name__
            }
        if response.get("response") is not None and not response.get("error_code"):
            try:
                result = classification_result(
                    response["response"], item, peers, response["ai_call_id"], iso(self.clock.now())
                )
            except (ValueError, TypeError, KeyError):
                result = {
                    "status": "UNAVAILABLE",
                    "reason": "INVALID_CONTEXT_CLASSIFICATION",
                    "ai_call_id": response.get("ai_call_id"),
                }
        else:
            result = {
                "status": "UNAVAILABLE",
                "reason": response.get("error_code") or "CONTEXT_CLASSIFICATION_FAILED",
                "ai_call_id": response.get("ai_call_id"),
            }
        result["classification_id"] = identity
        if result["status"] == "READY":
            self.cache.save_classification(identity, result, self.clock.now())
        self.cache.finish(reserved["request_id"], result, self.clock.now())
        return result
