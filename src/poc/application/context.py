"""Semantic classification reuses immutable evidence; collection remains an outbound adapter."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from poc.application.ai_policy import DecisionsPort
from poc.application.ports import Clock
from poc.config import Config
from poc.domain.factors import (
    NEWS_CONFLICT_VERSION,
    classification_payload,
    classification_result,
    news_conflict_payload,
    news_conflict_result,
)
from poc.domain.primitives import DomainError, canonical_json, iso, stable_id, utc


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
        return await self._request(
            payload,
            lambda response, call_id, at: classification_result(response, item, peers, call_id, at),
        )

    async def classify_news(self, items: list[dict], base_asset: str) -> list[dict]:
        if len(items) > 5 or len({item["item_id"] for item in items}) != len(items):
            raise DomainError("News classification needs at most five distinct items")
        # Intrinsic interpretation never includes unrelated/changing peer evidence.
        results = [await self.classify(item, [], base_asset) for item in items]
        if len(items) < 2 or not any(
            result.get("status") == "READY" and result.get("relevance") in ("DIRECT", "CONTEXTUAL")
            for result in results
        ):
            return results
        try:
            payload = news_conflict_payload(
                items, self.config.market.symbol, base_asset, self.config.ai.model
            )
            comparison = await self._request(
                payload,
                lambda response, call_id, at: news_conflict_result(response, items, call_id, at),
            )
        except DomainError:
            comparison = {"status": "UNAVAILABLE", "reason": "NEWS_CONFLICT_CONTEXT_TOO_LARGE"}
        scope_ids = sorted(item["item_id"] for item in items)
        combined = []
        for item, result in zip(items, results, strict=True):
            if result.get("status") != "READY":
                combined.append(result)
                continue
            check = comparison.get("checks", {}).get(item["item_id"])
            ready = comparison["status"] == "READY" and check is not None
            available_at = max(
                utc(result["available_at"]),
                utc(comparison["available_at"]) if ready else self.clock.now(),
            )
            identity = stable_id(
                result["classification_id"],
                NEWS_CONFLICT_VERSION,
                comparison.get("classification_id"),
                scope_ids,
                comparison["status"],
                comparison.get("reason"),
            )
            raw_answers = {**result["raw_answers"]}
            if ready:
                raw_answers["factual_conflict"] = check
            factor = {
                **result,
                "factor_id": stable_id(result["factor_id"], identity),
                "classification_id": identity,
                "semantic_classification_id": result["classification_id"],
                "semantic_available_at": result["available_at"],
                "factual_conflict": check["choice"] if ready else "UNDETERMINED",
                "conflict_status": comparison["status"],
                "conflict_reason": comparison.get("reason"),
                "conflict_criteria_version": NEWS_CONFLICT_VERSION,
                "conflict_classification_id": comparison.get("classification_id"),
                "conflict_ai_call_id": comparison.get("ai_call_id"),
                "conflict_available_at": comparison.get("available_at"),
                "peer_evidence_ids": [
                    identity for identity in scope_ids if identity != item["item_id"]
                ],
                "available_at": iso(available_at),
                "raw_answers": raw_answers,
            }
            if ready:
                self.cache.save_classification(identity, factor, available_at)
            combined.append(factor)
        return combined

    async def _request(self, payload: dict, parse: Callable[[dict, str, str], dict]) -> dict:
        if getattr(self.config, "profile_definition", None):
            payload = {
                **payload,
                "state": {
                    **payload["state"],
                    "profile": "ASSET_EVIDENCE_V1",
                    "criteria_version": payload["state"]["criteria_version"] + "_asset_v1",
                },
            }
        identity = stable_id(payload)
        existing = self.cache.classification(identity, self.clock.now())
        if existing:
            return existing
        # Successful interpretations live indefinitely by evidence identity. Failed
        # processing can recover in a later collection window, with the physical
        # retries/budget still enforced by the Decisions client for each request.
        retry_seconds = self.config.news.poll_minutes * 60
        retry_slot = int(utc(self.clock.now()).timestamp()) // retry_seconds
        attempt_identity = stable_id(identity, self.credential_version, retry_slot)
        reservation_scope = {"input_id": attempt_identity}
        if getattr(self.config.ai, "budget_scope", None) == "SESSION":
            reservation_scope["retry_session_budget"] = True
        reserved = self.cache.reserve(
            "context-classification", reservation_scope, self.clock.now(), 10**12
        )
        if not reserved["granted"]:
            cached = reserved.get("cached")
            if (
                cached
                and cached.get("available_at")
                and utc(cached["available_at"]) > utc(self.clock.now())
            ):
                return {
                    "status": "PENDING",
                    "reason": "CLASSIFICATION_NOT_YET_AVAILABLE",
                    "classification_id": identity,
                }
            return cached or {
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
                result = parse(response["response"], response["ai_call_id"], iso(self.clock.now()))
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
        if getattr(self.config, "profile_definition", None):
            result["criteria_version"] = payload["state"]["criteria_version"]
        result.setdefault("available_at", iso(self.clock.now()))
        # Fresh and restored results share the same canonical representation.
        result = json.loads(canonical_json(result))
        if result["status"] == "READY":
            self.cache.save_classification(identity, result, self.clock.now())
        self.cache.finish(reserved["request_id"], result, self.clock.now())
        return result
