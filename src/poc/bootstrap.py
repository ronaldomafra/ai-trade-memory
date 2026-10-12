"""The only composition root for application and infrastructure."""

import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from poc.adapters.outbound.sqlite import SQLiteStorage
from poc.application.sessions import SessionManager
from poc.config import Config, load_config


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def configuration(path: str | Path, load_environment: bool = True) -> Config:
    if load_environment:
        allowed = {
            "OPENROUTER_API_KEY",
            "MARKETAUX_API_TOKEN",
            "POLYMARKET_PROXY_URL",
            "POC_DATA_DIR",
        }
        for name, value in dotenv_values(Path.cwd() / ".env").items():
            if name in allowed and value is not None:
                os.environ.setdefault(name, value)
    config = load_config(path)
    directory = os.environ.get("POC_DATA_DIR")
    if directory:
        data = config.model_dump(mode="json")
        data["app"]["data_dir"] = directory
        config = Config.model_validate(data)
    return config


def session_manager(config: Config) -> SessionManager:
    return SessionManager(config, SQLiteStorage())
