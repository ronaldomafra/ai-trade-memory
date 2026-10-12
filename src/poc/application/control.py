"""Remote control cases: immutable preparation and idempotent lifecycle on the server."""

import asyncio
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from poc.application.ports import Clock, PublicMetadataPort, StorageFactory
from poc.application.sessions import PROFILE_ID, SessionManager, valid_run_id
from poc.config import Config
from poc.domain.primitives import DomainError
from poc.domain.security import Principal

EDITABLE = {
    "strategy": set(type(Config().strategy).model_fields),
    "indicators": set(type(Config().indicators).model_fields),
    "simulation": set(type(Config().simulation).model_fields),
    "ai": {"timeout_seconds", "max_retries", "max_calls_per_day", "max_observed_cost_usd_per_day"},
    "news": {
        "enabled",
        "api_poll_minutes",
        "poll_minutes",
        "lookback_hours",
        "max_items_per_decision",
    },
    "polymarket": set(type(Config().polymarket).model_fields),
    "learning": {"enabled", "transfer"},
}


def public_settings(config: Config) -> dict:
    content = config.model_dump(mode="json")
    return {
        section: {key: value for key, value in content[section].items() if key in keys}
        for section, keys in EDITABLE.items()
    }


def merge_settings(base: dict, patch: dict) -> dict:
    result = {**base}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    return result


def effective_config(
    template: Config, symbol: str, overrides: dict, dataset_path: str | None = None
) -> Config:
    data = template.model_dump(mode="json")
    data["market"]["symbol"] = symbol
    for section, values in overrides.items():
        if (
            section not in EDITABLE
            or not isinstance(values, dict)
            or set(values) - EDITABLE[section]
        ):
            raise DomainError("Unsupported remote strategy configuration")
        data[section] = merge_settings(data[section], values)
    data["learning"]["initial_dataset_path"] = dataset_path
    return Config.model_validate(data)


class RuntimePort(Protocol):
    async def start(self, run_id: str) -> dict: ...
    async def stop(self, run_id: str) -> dict: ...
    async def inspect(self, run_id: str) -> dict | None: ...


class CommandStorePort(Protocol):
    def reserve_command(
        self, actor: str, key: str, kind: str, body: dict, run_id: str, now: datetime
    ) -> dict: ...
    def finish_command(self, command_id: str, response: dict, now: datetime): ...
    def register_session(self, record: dict): ...


class ControlService:
    def __init__(
        self,
        template: Config,
        storage: StorageFactory,
        metadata: PublicMetadataPort,
        clock: Clock,
        runtime: RuntimePort,
        commands: CommandStorePort,
    ):
        self.template, self.storage, self.metadata, self.clock = template, storage, metadata, clock
        self.runtime, self.commands = runtime, commands
        self.locks: dict[str, asyncio.Lock] = {}

    def profiles(self) -> dict:
        return {
            "profiles": [
                {
                    "profile_id": PROFILE_ID,
                    "version": "1",
                    "implemented": True,
                    "symbol_default": self.template.market.symbol,
                    "interval": "15m",
                    "trend_interval": "1h",
                    "template": public_settings(self.template),
                    "parameter_schema": Config.model_json_schema(),
                    "mode": "PAPER_ONLY",
                }
            ]
        }

    async def prepare(
        self, principal: Principal, key: str, body: dict, dataset_path: str | None = None
    ) -> dict:
        if body["profile_id"] != PROFILE_ID:
            raise DomainError("Unknown or incomplete profile")
        run_id = body.get("run_id") or "run-" + uuid4().hex[:16]
        valid_run_id(run_id)
        principal.require("manage", run_id)
        config = effective_config(
            self.template, body["symbol"], body.get("overrides", {}), dataset_path
        )
        command = self.commands.reserve_command(
            principal.user_id, key, "PREPARE_SESSION", body, run_id, self.clock.now()
        )
        async with self.locks.setdefault(command["command_id"], asyncio.Lock()):
            command = self.commands.reserve_command(
                principal.user_id, key, "PREPARE_SESSION", body, run_id, self.clock.now()
            )
            if command["response"] is not None:
                return command["response"]
            run_id = command["run_id"]
            principal.require("manage", run_id)
            metadata = await self.metadata.metadata(config.market.symbol)
            record = SessionManager(config, self.storage).prepare(
                run_id, body["profile_id"], metadata, self.clock.now()
            )
            self.commands.register_session(record)
            public = {
                key: record[key]
                for key in (
                    "run_id",
                    "profile_id",
                    "profile_version",
                    "symbol",
                    "base_asset",
                    "quote_asset",
                    "created_at",
                    "status",
                    "config_hash",
                    "template_version",
                )
            }
            response = {"command_id": command["command_id"], "session": public}
            self.commands.finish_command(command["command_id"], response, self.clock.now())
            return response

    async def lifecycle(self, principal: Principal, key: str, run_id: str, action: str) -> dict:
        valid_run_id(run_id)
        principal.require("manage", run_id)
        SessionManager(self.template, self.storage).restore(run_id)
        if action not in ("start", "stop"):
            raise DomainError("Unknown lifecycle action")
        body = {"run_id": run_id, "action": action}
        command = self.commands.reserve_command(
            principal.user_id, key, "ENGINE_" + action.upper(), body, run_id, self.clock.now()
        )
        async with self.locks.setdefault(command["command_id"], asyncio.Lock()):
            command = self.commands.reserve_command(
                principal.user_id, key, "ENGINE_" + action.upper(), body, run_id, self.clock.now()
            )
            if command["response"] is not None:
                return command["response"]
            state = await (
                self.runtime.start(run_id) if action == "start" else self.runtime.stop(run_id)
            )
            response = {
                "command_id": command["command_id"],
                "run_id": run_id,
                "status": state["status"],
                "running": state["running"],
                "runtime": state["runtime"],
            }
            self.commands.finish_command(command["command_id"], response, self.clock.now())
            return response
