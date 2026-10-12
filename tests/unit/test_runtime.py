import json

import pytest

from poc.adapters.outbound.runtime import DockerRuntime
from poc.domain.primitives import DomainError


@pytest.mark.asyncio
async def test_container_identity_and_shell_injection_are_rejected(tmp_path):
    runtime = DockerRuntime(tmp_path)
    with pytest.raises(DomainError):
        await runtime.start("bad; touch /tmp/injected")
    assert DockerRuntime.name("Session-A") != DockerRuntime.name("session-a")

    async def wrong_container(args):
        return 0, json.dumps([{"Config": {"Labels": {"poc.owner": "other", "poc.run_id": "r"}}}])

    runtime = DockerRuntime(tmp_path, wrong_container)
    with pytest.raises(DomainError, match="identity"):
        await runtime.inspect("r")


@pytest.mark.asyncio
async def test_start_stop_idempotent_fixed_args_and_credentials_absent_from_argv(
    tmp_path, monkeypatch
):
    session = tmp_path / "sessions" / "r"
    session.mkdir(parents=True)
    (session / "poc.sqlite3").write_bytes(b"synthetic-database-for-runtime-argv-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-secret")
    commands = []
    state = {"exists": False, "running": False}

    async def runner(args):
        commands.append(args)
        if args[0] == "inspect":
            if not state["exists"]:
                return 1, ""
            return 0, json.dumps(
                [
                    {
                        "Id": "test",
                        "Config": {"Labels": {"poc.owner": "ai-trade-memory", "poc.run_id": "r"}},
                        "State": {
                            "Status": "running" if state["running"] else "exited",
                            "Running": state["running"],
                        },
                        "NetworkSettings": {
                            "Ports": {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18081"}]}
                        },
                    }
                ]
            )
        if args[0] == "create":
            state["exists"] = True
        if args[0] == "start":
            state["running"] = True
        if args[0] == "stop":
            state["running"] = False
        return 0, "ok"

    runtime = DockerRuntime(tmp_path, runner, host_data_root=tmp_path / "host-data")
    assert (await runtime.start("r"))["running"]
    assert (await runtime.start("r"))["running"]
    assert sum(args[0] == "create" for args in commands) == 1
    assert (await runtime.stop("r"))["running"] is False
    await runtime.stop("r")
    assert sum(args[0] == "stop" for args in commands) == 1
    assert "test-secret" not in str(commands)
    create = next(args for args in commands if args[0] == "create")
    assert "127.0.0.1::8081" in create and "--pull=never" in create
    assert any(f"source={tmp_path / 'host-data' / 'sessions' / 'r'}," in arg for arg in create)


@pytest.mark.asyncio
async def test_stopped_engine_cannot_start_with_stale_image_after_schema_upgrade(tmp_path):
    session = tmp_path / "sessions" / "r"
    session.mkdir(parents=True)
    path = session / "poc.sqlite3"
    path.write_bytes(b"synthetic-runtime-only-file")
    commands = []

    async def runner(args):
        commands.append(args)
        if args[0] == "image":
            return 0, "sha256:new-image\n"
        return 0, json.dumps(
            [
                {
                    "Id": "synthetic",
                    "Image": "sha256:old-image",
                    "Config": {"Labels": {"poc.owner": "ai-trade-memory", "poc.run_id": "r"}},
                    "State": {"Status": "exited", "Running": False},
                    "NetworkSettings": {},
                }
            ]
        )

    runtime = DockerRuntime(tmp_path, runner)
    with pytest.raises(DomainError, match="recreate"):
        await runtime.start("r")
    assert all(command[0] not in ("create", "start", "rm") for command in commands)
    assert path.read_bytes() == b"synthetic-runtime-only-file"
