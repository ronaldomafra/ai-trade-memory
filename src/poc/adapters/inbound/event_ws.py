"""Bounded authenticated WS delivery. No engine lifecycle or inference calls."""

import asyncio
import ipaddress
import json
from contextlib import suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from poc.adapters.outbound.auth import AuthStore
from poc.adapters.outbound.session_view import SessionViews
from poc.application.event_stream import EventCursor, ResyncRequired
from poc.application.ports import Clock
from poc.domain.primitives import DomainError, canonical_json, iso
from poc.domain.security import AuthenticationError, PermissionDenied


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str = Field(min_length=1, max_length=80)
    after_seq: int | None = Field(default=None, ge=0)


class Authenticate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: str = Field(pattern="^authenticate$")
    access_token: SecretStr = Field(min_length=20, max_length=256)
    subscriptions: list[Subscription] = Field(min_length=1, max_length=8)


async def send_bounded(socket: WebSocket, message: dict) -> None:
    encoded = canonical_json(message)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise DomainError("Stream frame exceeds delivery bound; use REST history")
    await asyncio.wait_for(socket.send_text(encoded), timeout=2)


def register_stream(app: FastAPI, auth: AuthStore, views: SessionViews, clock: Clock):
    active: dict[str, int] = {}
    connections = 0

    @app.websocket("/v1/stream")
    async def stream(socket: WebSocket):
        nonlocal connections
        host = socket.client.host if socket.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        # Credentials never belong to URLs (including access logs at upstream proxies).
        if socket.query_params or (socket.url.scheme != "wss" and not local):
            await socket.close(code=1008, reason="TLS_REQUIRED_OR_INVALID_URL")
            return
        if connections >= 32:
            await socket.close(code=1013, reason="CONNECTION_LIMIT")
            return
        connections += 1
        owner = None
        incoming = None
        try:
            await socket.accept()
            raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
            if len(raw.encode("utf-8")) > 16384:
                raise ValueError("oversized frame")
            handshake = Authenticate.model_validate_json(raw)
            token = handshake.access_token.get_secret_value()
            principal = auth.authorize(token, clock.now(), "read")
            if active.get(principal.user_id, 0) >= 4:
                await socket.close(code=1013, reason="OWNER_CONNECTION_LIMIT")
                return
            owner = principal.user_id
            active[owner] = active.get(owner, 0) + 1
            cursors = {}
            for subscription in handshake.subscriptions:
                principal.require("read", subscription.run_id)
                if subscription.run_id in cursors:
                    raise DomainError("Duplicate session subscription")
                if subscription.after_seq is None:
                    snapshot = views.snapshot(subscription.run_id)
                    await send_bounded(socket, {"type": "snapshot", "snapshot": snapshot})
                    seq = snapshot["event_watermark"]
                else:
                    seq = subscription.after_seq
                cursor = EventCursor(subscription.run_id, seq)
                cursor.validate_bounds(*views.event_bounds(subscription.run_id))
                cursors[subscription.run_id] = cursor
            await send_bounded(
                socket,
                {"type": "ready", "cursors": {run: cursor.seq for run, cursor in cursors.items()}},
            )
            # One receive task, one serial writer, bounded batches: no per-client event queue.
            incoming = asyncio.create_task(socket.receive_text())
            tick = 0
            while True:
                principal = auth.authorize(token, clock.now(), "read")
                for run, cursor in cursors.items():
                    principal.require("read", run)
                    cursor.validate_bounds(*views.event_bounds(run))
                    batch = views.events(run, cursor.seq, 100)
                    for event in batch:
                        if cursor.accept(event):
                            await send_bounded(socket, {"type": "event", "event": event})
                    if tick % 2 == 0:
                        await send_bounded(
                            socket,
                            {
                                "type": "live",
                                "durable": False,
                                "run_id": run,
                                "observed_at": iso(clock.now()),
                                "data": views.live(run),
                            },
                        )
                if incoming.done():
                    message = incoming.result()
                    if len(message.encode("utf-8")) > 1024:
                        raise ValueError("oversized control frame")
                    value = json.loads(message)
                    if value != {"type": "ping"}:
                        raise ValueError("unknown stream command")
                    await send_bounded(socket, {"type": "pong", "at": iso(clock.now())})
                    incoming = asyncio.create_task(socket.receive_text())
                tick += 1
                await asyncio.sleep(0.5)
        except AuthenticationError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=4001, reason="REAUTHENTICATE")
        except PermissionDenied:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=4003, reason="PERMISSION_DENIED")
        except ResyncRequired:
            with suppress(RuntimeError, WebSocketDisconnect):
                await send_bounded(socket, {"type": "resync_required", "action": "REST_SNAPSHOT"})
                await socket.close(code=4009, reason="RESYNC_REQUIRED")
        except TimeoutError:
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=1013, reason="SLOW_CLIENT_OR_AUTH_TIMEOUT")
        except (DomainError, ValidationError, ValueError, KeyError, TypeError):
            with suppress(RuntimeError, WebSocketDisconnect):
                await socket.close(code=1008, reason="INVALID_STREAM_REQUEST")
        except WebSocketDisconnect:
            pass
        finally:
            if incoming is not None:
                incoming.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await incoming
            if owner:
                active[owner] -= 1
                if not active[owner]:
                    del active[owner]
            connections -= 1
