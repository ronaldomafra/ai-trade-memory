from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_control_api import cleanup, fixture


async def prepare(items, run_id="stream-test"):
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    response = await client.post(
        "/v1/sessions",
        json={"profile_id": "trend_15m_v1", "symbol": "BTCUSDT", "run_id": run_id},
        headers={"Idempotency-Key": "prepare-" + run_id},
    )
    assert response.status_code == 201
    return app.state.views


def handshake(client, after_seq=None, run_id="stream-test"):
    return {
        "type": "authenticate",
        "access_token": client.headers["Authorization"][7:],
        "subscriptions": [{"run_id": run_id, "after_seq": after_seq}],
    }


def receive_type(socket, kind):
    for _ in range(30):
        message = socket.receive_json()
        if message["type"] == kind:
            return message
    raise AssertionError("Expected stream frame missing")


@pytest.mark.asyncio
async def test_snapshot_watermark_replay_reconnect_and_live_do_not_touch_wallets(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        views = await prepare(items)
        before = views.snapshot("stream-test")
        with TestClient(app, client=("127.0.0.1", 50000)) as transport:
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(handshake(client))
                snapshot = socket.receive_json()
                assert snapshot["type"] == "snapshot"
                watermark = snapshot["snapshot"]["event_watermark"]
                assert socket.receive_json()["type"] == "ready"
                live = receive_type(socket, "live")
                assert live["durable"] is False and live["run_id"] == "stream-test"
                db = views.database("stream-test")
                try:
                    with db.transaction():
                        db.event(
                            "TEST_OBSERVABLE",
                            {"stage": "test-fixture"},
                            clock.now(),
                            "test-event-id",
                        )
                finally:
                    db.close()
                event = receive_type(socket, "event")["event"]
                assert event["event_seq"] == watermark + 1
                assert event["event_id"]
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(handshake(client, watermark))
                assert socket.receive_json()["type"] == "ready"
                replayed = receive_type(socket, "event")["event"]
                assert replayed == event
        after = views.snapshot("stream-test")
        assert before["portfolios"] == after["portfolios"]
        assert runtime.stops == runtime.starts == 0
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_revocation_and_expiry_close_stream_without_stopping_runtime(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        await prepare(items)
        runtime.running = True
        with TestClient(app, client=("127.0.0.1", 50000)) as transport:
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(handshake(client, 0))
                receive_type(socket, "ready")
                auth.logout(client.headers["Authorization"][7:], clock.now())
                with pytest.raises(WebSocketDisconnect) as error:
                    while True:
                        socket.receive_json()
                assert error.value.code == 4001
        assert runtime.running and runtime.stops == 0
        # A fresh auth family is tested for expiry separately from revocation.
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_expired_stream_cursor_resync_and_credentials_forbidden_in_url(tmp_path):
    items = await fixture(tmp_path)
    client, auth, commands, runtime, metadata, clock, upstream, app = items
    try:
        await prepare(items)
        with TestClient(app, client=("127.0.0.1", 50000)) as transport:
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(handshake(client, 999999))
                assert socket.receive_json()["type"] == "resync_required"
                with pytest.raises(WebSocketDisconnect) as error:
                    socket.receive_json()
                assert error.value.code == 4009
            with pytest.raises(WebSocketDisconnect):
                with transport.websocket_connect("/v1/stream?access_token=synthetic-token"):
                    pass
            with transport.websocket_connect("/v1/stream") as socket:
                socket.send_json(handshake(client, 0))
                receive_type(socket, "ready")
                clock.at += timedelta(minutes=16)
                with pytest.raises(WebSocketDisconnect) as error:
                    while True:
                        socket.receive_json()
                assert error.value.code == 4001
        assert runtime.stops == 0
    finally:
        await cleanup(items)
