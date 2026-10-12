import asyncio
import hashlib
import json

import httpx
import pytest

from poc.adapters.outbound.control_client import ControlClient, server_url
from poc.domain.primitives import DomainError


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.example",
        "https://user:password@server.example",
        "https://server.example/?access_token=secret",
        "file:///data/bank",
        "https://server.example/path",
    ],
)
def test_remote_server_urls_cannot_expose_secrets_or_use_plain_http(url):
    with pytest.raises(DomainError):
        server_url(url)
    assert server_url("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_parallel_unauthorized_reads_rotate_refresh_only_once():
    refreshes = []

    async def handler(request):
        if request.url.path == "/v1/auth/refresh":
            refreshes.append(json.loads(request.content))
            await asyncio.sleep(0.01)
            return httpx.Response(
                200, json={"access_token": "new-access", "refresh_token": "new-refresh"}
            )
        if request.headers.get("Authorization") == "Bearer expired-access":
            return httpx.Response(401)
        return httpx.Response(200, json={"sessions": []})

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://server.example"
    )
    client = ControlClient("https://server.example", http)
    client._tokens({"access_token": "expired-access", "refresh_token": "old-refresh"})
    try:
        first, second = await asyncio.gather(
            client.request("GET", "/v1/sessions"), client.request("GET", "/v1/sessions")
        )
        assert first == second == {"sessions": []}
        assert refreshes == [{"refresh_token": "old-refresh"}]
        assert client.refresh_token == "new-refresh"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_download_checks_hash_permissions_and_does_not_overwrite(tmp_path):
    content = b"synthetic-dataset-client-transport-test\n"
    identity = hashlib.sha256(content).hexdigest()
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, json={"profiles": []})
                if request.url.path == "/v1/profiles"
                else httpx.Response(200, content=content)
            )
        ),
        base_url="https://server.example",
    )
    client = ControlClient("https://server.example", http)
    client.access_token = "synthetic-access"
    path = tmp_path / "learning.jsonl"
    try:
        await client.download(identity, path)
        assert path.read_bytes() == content and path.stat().st_mode & 0o077 == 0
        with pytest.raises(DomainError, match="novo"):
            await client.download(identity, path)
        with pytest.raises(DomainError, match="Hash"):
            await client.download("0" * 64, tmp_path / "bad.jsonl")
        assert not (tmp_path / "bad.jsonl").exists()
        assert not list(tmp_path.glob(".learning-*"))
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ws_client_replays_deduplicates_and_resyncs_on_gap_without_credentials_in_url():
    connections = []

    class Socket:
        def __init__(self):
            self.messages = iter(
                [
                    {"type": "ready"},
                    {"type": "event", "event": {"run_id": "r", "event_seq": 11, "event_id": "e11"}},
                    {"type": "event", "event": {"run_id": "r", "event_seq": 11, "event_id": "e11"}},
                    {"type": "event", "event": {"run_id": "r", "event_seq": 13, "event_id": "e13"}},
                ]
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, payload):
            connections[-1]["frame"] = json.loads(payload)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return json.dumps(next(self.messages))
            except StopIteration:
                raise StopAsyncIteration from None

    def connector(url, **kwargs):
        connections.append({"url": url, "limits": kwargs})
        return Socket()

    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"run_id": "r", "event_watermark": 10})
        ),
        base_url="https://server.example",
    )
    client = ControlClient("https://server.example", http, connector)
    client.access_token = "synthetic-access-token"
    stream = client.stream("r")
    try:
        assert (await anext(stream))["type"] == "snapshot"
        assert (await anext(stream))["type"] == "connected"
        assert (await anext(stream))["event"]["event_seq"] == 11
        assert (await anext(stream))["type"] == "resync"
        assert connections[0]["url"] == "wss://server.example/v1/stream"
        assert connections[0]["frame"]["subscriptions"][0]["after_seq"] == 10
        assert connections[0]["frame"]["access_token"] == client.access_token
        assert connections[0]["limits"]["max_queue"] == 8
    finally:
        await stream.aclose()
        await client.close()
