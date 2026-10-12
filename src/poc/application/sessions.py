import re
from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from poc.application.ports import StorageFactory
from poc.config import Config
from poc.domain.models import MarketMetadata
from poc.domain.primitives import DomainError, iso, utc

PROFILE_ID = "trend_15m_v1"
PROFILE_VERSION = "1"


def valid_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
        raise DomainError("Invalid run_id")
    return run_id


def session_paths(config: Config, run_id: str) -> dict[str, str]:
    valid_run_id(run_id)
    result = {}
    for name, template in (
        ("sqlite", config.storage.sqlite_path),
        ("logs", config.storage.jsonl_dir),
        ("exports", config.storage.export_dir),
    ):
        value = template.format(run_id=run_id)
        if value.startswith("./data/"):
            value = str(Path(config.app.data_dir) / value[len("./data/") :])
        result[name] = str(Path(value).resolve())
    return result


class SessionManager:
    def __init__(self, config: Config, storage: StorageFactory):
        self.config = config
        self.storage = storage

    def prepare(
        self, run_id: str, profile_id: str, metadata: MarketMetadata, now: datetime
    ) -> dict[str, Any]:
        valid_run_id(run_id)
        if profile_id != PROFILE_ID:
            raise DomainError("Unknown or unimplemented profile")
        if metadata.symbol != self.config.market.symbol or utc(metadata.observed_at) > utc(now):
            raise DomainError("Metadata does not match selected symbol or is from the future")
        paths = session_paths(self.config, run_id)
        with self.storage.lease(Path(paths["sqlite"]).parent / "engine.lock"):
            db = self.storage.open(Path(paths["sqlite"]), create=True)
            try:
                existing = db.run()
                if existing:
                    if existing["run_id"] != run_id or existing["config_hash"] != self.config.hash:
                        raise DomainError(
                            "Existing session has a different identity or configuration"
                        )
                    if self.config.learning.initial_dataset_path:
                        self.storage.prepare_initial_learning(
                            db, Path(self.config.learning.initial_dataset_path), now
                        )
                    return existing
                record = {
                    "run_id": run_id,
                    "profile_id": profile_id,
                    "profile_version": PROFILE_VERSION,
                    "symbol": metadata.symbol,
                    "base_asset": metadata.base_asset,
                    "quote_asset": metadata.quote_asset,
                    "market_metadata": asdict(metadata),
                    "config_hash": self.config.hash,
                    "config": self.config.model_dump(mode="json"),
                    "paths": paths,
                    "created_at": iso(now),
                    "status": "PREPARED",
                    "code_version": "0.1.0",
                    "template_version": "trend_15m_v1.1",
                    "template_reference": "docs/SPEC.md#72",
                    "template_original": Config().model_dump(mode="json"),
                    "template_changes": configuration_changes(
                        Config().model_dump(mode="json"), self.config.model_dump(mode="json")
                    ),
                }
                db.create_session(
                    record,
                    str(self.config.portfolios.initial_usdt),
                    self.config.portfolios.strategies,
                    now,
                )
                if self.config.learning.initial_dataset_path:
                    self.storage.prepare_initial_learning(
                        db, Path(self.config.learning.initial_dataset_path), now
                    )
                return db.run()
            finally:
                db.close()

    def restore(self, run_id: str) -> dict[str, Any]:
        paths = session_paths(self.config, run_id)
        db = self.storage.open(Path(paths["sqlite"]), create=False)
        try:
            record = db.run()
            if not record or record["run_id"] != run_id:
                raise DomainError("Missing or incompatible session")
            saved = Config.model_validate(record["config"])
            if saved.hash != record["config_hash"] or record["profile_id"] != PROFILE_ID:
                raise DomainError("Persisted configuration or profile is incompatible")
            # The immutable record retains original mounts; access paths follow the current mount.
            record["persisted_paths"] = record["paths"]
            record["paths"] = paths
            return record
        finally:
            db.close()

    def lease(self, run_id: str) -> AbstractContextManager[None]:
        paths = session_paths(self.config, run_id)
        return self.storage.lease(Path(paths["sqlite"]).parent / "engine.lock")


def configuration_changes(
    defaults: dict[str, Any], effective: dict[str, Any], prefix: str = ""
) -> dict[str, Any]:
    result = {}
    for key, value in effective.items():
        name = f"{prefix}.{key}" if prefix else key
        original = defaults.get(key)
        if isinstance(value, dict) and isinstance(original, dict):
            result.update(configuration_changes(original, value, name))
        elif original != value:
            result[name] = {"default": original, "effective": value}
    return result
