"""The only composition root for application and infrastructure."""

import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

from poc.adapters.outbound.sqlite import SQLiteStorage
from poc.application.sessions import SessionManager
from poc.config import Config, load_config
from poc.domain.primitives import DomainError


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
        explicit_file = os.environ.get("POC_ENV_FILE")
        env_path = Path(explicit_file) if explicit_file else Path.cwd() / ".env"
        if explicit_file and not env_path.is_file():
            raise DomainError("Credentials file is unavailable")
        for name, value in dotenv_values(env_path, interpolate=False).items():
            if name in allowed and value is not None:
                if name == "POC_DATA_DIR":
                    os.environ.setdefault(name, value)
                else:
                    # The configured local file is authoritative for provider credentials.
                    os.environ[name] = value
    config = load_config(path)
    directory = os.environ.get("POC_DATA_DIR")
    if directory:
        data = config.model_dump(mode="json")
        data["app"]["data_dir"] = directory
        config = type(config).model_validate(data)
    return config


def session_manager(config: Config) -> SessionManager:
    return SessionManager(config, SQLiteStorage())
