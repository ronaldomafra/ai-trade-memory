"""Composition of the single control service; shutdown closes clients, never engines."""

import os
from pathlib import Path

import httpx
import uvicorn

from poc.adapters.inbound.control_api import gateway_api
from poc.adapters.outbound.auth import AuthStore
from poc.adapters.outbound.control_store import ControlStore
from poc.adapters.outbound.market import BinancePublic
from poc.adapters.outbound.profiles import SQLiteProfiles
from poc.adapters.outbound.runtime import DockerRuntime
from poc.adapters.outbound.session_view import SessionViews
from poc.adapters.outbound.sqlite import SQLiteStorage
from poc.application.control import ControlService
from poc.bootstrap import SystemClock
from poc.config import Config


async def serve_control(config: Config, host: str = "127.0.0.1", port: int = 8080):
    root = Path(config.app.data_dir)
    auth = AuthStore(root / "control" / "auth.sqlite3")
    commands = ControlStore(root / "control" / "control.sqlite3")
    source = BinancePublic()
    http = httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False)
    clock = SystemClock()
    host_root = os.environ.get("POC_HOST_DATA_DIR")
    runtime = DockerRuntime(root, host_data_root=Path(host_root) if host_root else None)
    service = ControlService(
        config,
        SQLiteStorage(),
        source,
        clock,
        runtime,
        commands,
        SQLiteProfiles(commands.connection),
    )
    app = gateway_api(service, auth, commands, SessionViews(config), clock, http)
    try:
        await uvicorn.Server(
            uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="warning",
                access_log=False,
                proxy_headers=True,
                forwarded_allow_ips="127.0.0.1,::1",
                ws="websockets",
                ws_max_size=16384,
                ws_max_queue=8,
                ws_ping_interval=20,
                ws_ping_timeout=20,
            )
        ).serve()
    finally:
        await http.aclose()
        await source.close()
        auth.close()
        commands.close()
