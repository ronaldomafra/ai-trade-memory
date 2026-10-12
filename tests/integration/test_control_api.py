import asyncio
from datetime import timedelta

import httpx
import pyotp
import pytest
from test_accounting import NOW, config, meta
from test_cycles_engine import Clock

from poc.adapters.inbound.control_api import gateway_api
from poc.adapters.outbound.auth import AuthStore
from poc.adapters.outbound.control_store import ControlStore
from poc.adapters.outbound.session_view import SessionViews
from poc.adapters.outbound.sqlite import SQLiteStorage
from poc.application.control import ControlService


class Metadata:
    def __init__(self):
        self.calls = 0

    async def metadata(self, symbol):
        self.calls += 1
        await asyncio.sleep(0.01)
        return meta(symbol, symbol[:-4])


class Runtime:
    def __init__(self):
        self.starts = 0
        self.stops = 0
        self.running = False

    async def start(self, run_id):
        self.starts += 1
        self.running = True
        return {"run_id": run_id, "status": "running", "running": True, "runtime": "test-fixture"}

    async def stop(self, run_id):
        self.stops += 1
        self.running = False
        return {"run_id": run_id, "status": "exited", "running": False, "runtime": "test-fixture"}

    async def inspect(self, run_id):
        return {
            "run_id": run_id,
            "running": self.running,
            "status": "running" if self.running else "exited",
            "runtime": "test-fixture",
            "endpoint": None,
        }


async def fixture(tmp_path, scopes=("read", "manage"), sessions=("*",)):
    cfg = config(tmp_path)
    auth = AuthStore(tmp_path / "control" / "auth.sqlite3")
    setup = auth.bootstrap_owner("owner", "synthetic-api-test-password", NOW)
    commands = ControlStore(tmp_path / "control" / "control.sqlite3")
    runtime = Runtime()
    metadata = Metadata()
    clock = Clock(NOW)
    service = ControlService(cfg, SQLiteStorage(), metadata, clock, runtime, commands)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(500)))
    app = gateway_api(service, auth, commands, SessionViews(cfg), clock, upstream)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")
    response = await client.post(
        "/v1/auth/login",
        json={
            "username": "owner",
            "password": "synthetic-api-test-password",
            "scopes": list(scopes),
            "sessions": list(sessions),
        },
    )
    assert response.status_code == 200
    challenge = response.json()["challenge_token"]
    response = await client.post(
        "/v1/auth/2fa",
        json={"challenge_token": challenge, "code": pyotp.TOTP(setup["totp_secret"]).at(NOW)},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = "Bearer " + token
    return client, auth, commands, runtime, metadata, clock, upstream, app


async def cleanup(items):
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    await client.aclose()
    await upstream.aclose()
    auth.close()
    commands.close()


@pytest.mark.asyncio
async def test_create_retry_parallel_start_snapshot_logout_do_not_reset_or_stop_engine(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        body = {"profile_id": "trend_15m_v1", "symbol": "ETHUSDT", "overrides": {}}
        headers = {"Idempotency-Key": "create-session-001"}
        first, second = await asyncio.gather(
            client.post("/v1/sessions", json=body, headers=headers),
            client.post("/v1/sessions", json=body, headers=headers),
        )
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json() and metadata.calls == 1
        run = first.json()["session"]["run_id"]
        conflict = await client.post(
            "/v1/sessions", json={**body, "symbol": "BTCUSDT"}, headers=headers
        )
        assert conflict.status_code == 409
        for _ in range(2):
            started = await client.post(
                f"/v1/sessions/{run}/start", headers={"Idempotency-Key": "start-engine-001"}
            )
            assert started.status_code == 200
        assert runtime.starts == 1
        snapshot = (await client.get(f"/v1/sessions/{run}/snapshot")).json()
        assert snapshot["market"]["symbol"] == "ETHUSDT"
        assert all(p["cash_usdt"] == "100" for p in snapshot["portfolios"])
        assert "endpoint" not in snapshot["runtime"]
        assert (await client.post("/v1/auth/logout")).status_code == 200
        assert runtime.running and runtime.stops == 0
        assert (await client.get("/v1/sessions")).status_code == 401
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_read_scope_invalid_config_and_validation_never_echo_credentials(tmp_path):
    items = await fixture(tmp_path, scopes=("read",))
    client, *_ = items
    try:
        denied = await client.post(
            "/v1/sessions",
            json={"profile_id": "trend_15m_v1", "symbol": "BTCUSDT"},
            headers={"Idempotency-Key": "prepare-session-001"},
        )
        assert denied.status_code == 403
        bad = await client.post("/v1/auth/login", json={"username": "owner", "password": "tiny"})
        assert bad.status_code == 422 and "tiny" not in bad.text
        assert (await client.get("/v1/profiles")).status_code == 200
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_remote_http_rejected_and_scoped_sessions_hidden(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("203.0.113.10", 123)),
            base_url="http://server.example",
        ) as remote:
            response = await remote.get("/health")
            assert response.status_code == 426
        clock.at += timedelta(minutes=16)
        assert (await client.get("/v1/profiles")).status_code == 401
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_session_scopes_apply_to_reads_commands_and_websocket(tmp_path):
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    items = await fixture(tmp_path, sessions=("allowed-session",))
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        response = await client.post(
            "/v1/sessions",
            json={"profile_id": "trend_15m_v1", "symbol": "BTCUSDT", "run_id": "allowed-session"},
            headers={"Idempotency-Key": "prepare-scoped-session"},
        )
        assert response.status_code == 201
        assert [s["run_id"] for s in (await client.get("/v1/sessions")).json()["sessions"]] == [
            "allowed-session"
        ]
        for path in ("snapshot", "events", "transfer"):
            assert (await client.get("/v1/sessions/other-session/" + path)).status_code == 403
        assert (
            await client.post(
                "/v1/sessions/other-session/start",
                headers={"Idempotency-Key": "start-denied-session"},
            )
        ).status_code == 403
        assert (await client.get("/v1/datasets")).status_code == 403
        with TestClient(app, client=("127.0.0.1", 50000)) as transport:
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(
                    {
                        "type": "authenticate",
                        "access_token": client.headers["Authorization"][7:],
                        "subscriptions": [{"run_id": "other-session", "after_seq": 0}],
                    }
                )
                with pytest.raises(WebSocketDisconnect) as error:
                    socket.receive_json()
                assert error.value.code == 4003
        assert runtime.starts == runtime.stops == 0
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_dataset_upload_export_download_import_before_start_and_invalid_configuration(
    tmp_path,
):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        for index, overrides in enumerate(
            [
                {"market": {"rest_url": "https://invalid.example"}},
                {"simulation": {"trading_fee_pct_per_side": 0.1}},
                {"ai": {"model": "other/model"}},
            ]
        ):
            response = await client.post(
                "/v1/sessions",
                json={"profile_id": "trend_15m_v1", "symbol": "BTCUSDT", "overrides": overrides},
                headers={"Idempotency-Key": "invalid-config-" + str(index)},
            )
            assert response.status_code in (409, 422)
        assert metadata.calls == 0 and not app.state.views.list()
        for run, symbol in (("export-source", "BTCUSDT"), ("import-target", "ETHUSDT")):
            response = await client.post(
                "/v1/sessions",
                json={"profile_id": "trend_15m_v1", "symbol": symbol, "run_id": run},
                headers={"Idempotency-Key": "prepare-" + run},
            )
            assert response.status_code == 201
        before = app.state.views.snapshot("import-target")["portfolios"]
        exported = await client.post("/v1/sessions/export-source/learning/export")
        assert exported.status_code == 200 and exported.json()["sample_count"] == 0
        identity = exported.json()["dataset_id"]
        download = await client.get("/v1/datasets/" + identity)
        assert download.status_code == 200
        upload = await client.post("/v1/datasets", files={"file": ("data.jsonl", download.content)})
        assert upload.status_code == 200 and upload.json()["dataset_id"] == identity
        invalid = await client.post("/v1/datasets", files={"file": ("bad.jsonl", b"invalid\n")})
        assert invalid.status_code == 409
        for _ in range(2):
            imported = await client.post(
                "/v1/sessions/import-target/learning/import", json={"dataset_id": identity}
            )
            assert imported.status_code == 200
        assert imported.json()["idempotent"]
        assert app.state.views.snapshot("import-target")["portfolios"] == before
        assert runtime.starts == runtime.stops == 0
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_chunked_body_is_bounded_before_json_parsing(tmp_path, monkeypatch):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        monkeypatch.setattr("poc.adapters.inbound.body_limit.MAX_REQUEST_BYTES", 1024)

        async def chunks():
            yield b"x" * 600
            yield b"x" * 600

        response = await client.post("/v1/auth/login", content=chunks())
        assert response.status_code == 413
        assert runtime.starts == runtime.stops == 0
    finally:
        await cleanup(items)
