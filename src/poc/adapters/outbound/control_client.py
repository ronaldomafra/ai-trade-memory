"""REST/WS-only client. Tokens live in memory; no exchange, Docker or SQLite access."""

import asyncio
import hashlib
import ipaddress
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from poc.application.event_stream import EventCursor, ResyncRequired
from poc.domain.primitives import DomainError
from poc.domain.security import AuthenticationError


class RemoteRejected(DomainError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Operação recusada pelo servidor (HTTP {status}).")


def server_url(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.path not in ("", "/")
        or not parts.hostname
        or parts.scheme not in ("https", "http")
    ):
        raise DomainError("Use a root HTTPS server URL without credentials or query parameters")
    try:
        local = ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        local = parts.hostname == "localhost"
    if parts.scheme == "http" and not local:
        raise DomainError("Remote control requires HTTPS")
    return value.rstrip("/")


class ControlClient:
    def __init__(self, server: str, http: httpx.AsyncClient | None = None, connector=None):
        self.server = server_url(server)
        self.http = http or httpx.AsyncClient(
            base_url=self.server, timeout=60, trust_env=False, follow_redirects=False
        )
        self.connector = connector or connect
        self.access_token = None
        self.refresh_token = None
        self.scopes = frozenset({"read", "manage"})
        self.refresh_lock = asyncio.Lock()
        self.challenge_expires_at = None

    @staticmethod
    def check(response: httpx.Response):
        if response.status_code == 401:
            raise AuthenticationError("Autenticação necessária. Entre novamente.")
        if response.status_code >= 400:
            # Never render provider response bodies that might reflect credentials.
            raise RemoteRejected(response.status_code)

    async def login(self, username: str, password: str, read_only: bool = False) -> str:
        scopes = ("read",) if read_only else ("read", "manage")
        response = await self.http.post(
            "/v1/auth/login", json={"username": username, "password": password, "scopes": scopes}
        )
        self.check(response)
        self.scopes = frozenset(scopes)
        payload = response.json()
        self.challenge_expires_at = datetime.fromisoformat(payload["expires_at"])
        return payload["challenge_token"]

    async def second_factor(self, challenge: str, code: str):
        response = await self.http.post(
            "/v1/auth/2fa", json={"challenge_token": challenge, "code": code}
        )
        self.check(response)
        self._tokens(response.json())

    def _tokens(self, payload: dict):
        self.access_token = payload["access_token"]
        self.refresh_token = payload["refresh_token"]

    async def refresh(self, failed_access: str | None = None):
        async with self.refresh_lock:
            if failed_access is not None and failed_access != self.access_token:
                return  # Another request already rotated this token.
            if not self.refresh_token:
                raise AuthenticationError("Entre para conectar ao servidor.")
            response = await self.http.post(
                "/v1/auth/refresh", json={"refresh_token": self.refresh_token}
            )
            if response.status_code >= 400:
                self.access_token = self.refresh_token = None
            self.check(response)
            self._tokens(response.json())

    async def request(self, method: str, path: str, *, body=None, key: str | None = None):
        token = self.access_token
        if token is None:
            raise AuthenticationError("Entre para conectar ao servidor.")
        headers = {"Authorization": "Bearer " + token}
        if key:
            headers["Idempotency-Key"] = key
        response = await self.http.request(method, path, json=body, headers=headers)
        if response.status_code == 401:
            await self.refresh(token)
            headers["Authorization"] = "Bearer " + self.access_token
            response = await self.http.request(method, path, json=body, headers=headers)
        self.check(response)
        return response.json()

    async def upload(self, path: Path) -> str:
        if not self.access_token:
            raise AuthenticationError("Entre antes de enviar um dataset.")
        if path.stat().st_size > 64 * 1024 * 1024:
            raise DomainError("Dataset excede 64 MB.")
        for attempt in range(2):
            token = self.access_token
            with path.open("rb") as stream:
                response = await self.http.post(
                    "/v1/datasets",
                    files={"file": ("dataset.jsonl", stream, "application/x-ndjson")},
                    headers={"Authorization": "Bearer " + token},
                )
            if response.status_code == 401 and attempt == 0:
                await self.refresh(token)
                continue
            self.check(response)
            return response.json()["dataset_id"]
        raise AuthenticationError("Autenticação necessária.")

    async def download(self, identity: str, path: Path):
        if not self.access_token:
            raise AuthenticationError("Entre antes de baixar um dataset.")
        # Refresh via a read request before opening a streamed local file.
        await self.request("GET", "/v1/profiles")
        path = path.expanduser().resolve()
        if path.exists():
            raise DomainError("Escolha um arquivo novo; exportação nunca sobrescreve dataset.")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".learning-", dir=path.parent)
        digest = hashlib.sha256()
        total = 0
        try:
            with os.fdopen(fd, "wb") as stream:
                async with self.http.stream(
                    "GET",
                    "/v1/datasets/" + identity,
                    headers={"Authorization": "Bearer " + self.access_token},
                ) as response:
                    self.check(response)
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > 64 * 1024 * 1024:
                            raise DomainError("Download excede 64 MB.")
                        digest.update(chunk)
                        stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if digest.hexdigest() != identity:
                raise DomainError("Hash do dataset recebido não confere.")
            os.link(name, path)  # Atomic no-overwrite publication, including concurrent clients.
        finally:
            Path(name).unlink(missing_ok=True)

    async def logout(self):
        try:
            if self.access_token:
                await self.http.post(
                    "/v1/auth/logout", headers={"Authorization": "Bearer " + self.access_token}
                )
        finally:
            self.access_token = self.refresh_token = None

    async def close(self):
        self.access_token = self.refresh_token = None
        await self.http.aclose()

    async def stream(self, run_id: str):
        """Yield immutable snapshots, deduplicated events and observable live frames."""
        cursor = None
        delay = 1
        ws_url = (
            ("wss" if self.server.startswith("https:") else "ws")
            + self.server[self.server.index(":") :]
            + "/v1/stream"
        )
        while True:
            token = self.access_token
            if token is None:
                raise AuthenticationError("Entre novamente para acompanhar a sessão.")
            try:
                if cursor is None:
                    snapshot = await self.request("GET", f"/v1/sessions/{run_id}/snapshot")
                    if snapshot.get("run_id") != run_id:
                        raise ResyncRequired("Snapshot de outra sessão recebido.")
                    cursor = EventCursor(run_id, snapshot["event_watermark"])
                    yield {"type": "snapshot", "snapshot": snapshot}
                token = self.access_token
                async with self.connector(
                    ws_url,
                    max_size=1024 * 1024,
                    max_queue=8,
                    ping_interval=20,
                    ping_timeout=20,
                    open_timeout=10,
                ) as socket:
                    await socket.send(
                        json.dumps(
                            {
                                "type": "authenticate",
                                "access_token": token,
                                "subscriptions": [{"run_id": run_id, "after_seq": cursor.seq}],
                            }
                        )
                    )
                    async for raw in socket:
                        message = json.loads(raw)
                        kind = message.get("type")
                        if kind == "ready":
                            delay = 1
                            yield {"type": "connected", "run_id": run_id}
                        elif kind == "event":
                            if cursor.accept(message["event"]):
                                yield message
                        elif kind == "live":
                            if message.get("run_id") != run_id:
                                raise ResyncRequired("Atualização de outra sessão recebida.")
                            yield message
                        elif kind == "resync_required":
                            raise ResyncRequired("Servidor solicita novo snapshot.")
                yield {"type": "disconnected", "retry_seconds": delay}
            except ConnectionClosed as exc:
                code = exc.rcvd.code if exc.rcvd else None
                if code == 4001:
                    await self.refresh(token)
                elif code == 4009:
                    cursor = None
                elif code in (1008, 4003):
                    raise DomainError("Assinatura recusada; confira escopo e sessão.") from None
                yield {"type": "disconnected", "retry_seconds": delay}
            except ResyncRequired:
                cursor = None
                yield {"type": "resync", "run_id": run_id}
            except (OSError, TimeoutError, httpx.HTTPError, ValueError):
                yield {"type": "disconnected", "retry_seconds": delay}
            await asyncio.sleep(delay)
            delay = min(30, delay * 2)

    @staticmethod
    def command_key() -> str:
        return uuid4().hex
