"""Server-side Docker lifecycle with fixed arguments and no shell or remote credentials."""

import asyncio
import ipaddress
import json
import os
import re
from pathlib import Path

from poc.application.sessions import valid_run_id
from poc.domain.primitives import DomainError, stable_id

IMAGE = "ai-trade-memory:0.1.0"
OWNER = "ai-trade-memory"
SECRET_NAMES = ("OPENROUTER_API_KEY", "MARKETAUX_API_TOKEN", "POLYMARKET_PROXY_URL")


class DockerRuntime:
    def __init__(self, data_root: Path, runner=None, host_data_root: Path | None = None):
        self.root = data_root.resolve()
        self.host_root = (host_data_root or data_root).resolve()
        if any("," in str(root) or "\x00" in str(root) for root in (self.root, self.host_root)):
            raise DomainError("Data root cannot be represented safely as a Docker bind mount")
        self.runner = runner or self._execute

    @staticmethod
    def name(run_id: str) -> str:
        valid_run_id(run_id)
        return "poc-engine-" + run_id[:24].lower() + "-" + stable_id(run_id)[:12]

    async def _execute(self, args: list[str]) -> tuple[int, str]:
        # argv is constructed by this adapter. No user text is interpreted by a shell.
        process = await asyncio.create_subprocess_exec(
            "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=55)
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise
        return process.returncode, stdout.decode("utf-8")

    async def inspect(self, run_id: str) -> dict | None:
        code, output = await self.runner(["inspect", self.name(run_id)])
        if code:
            # Distinguish absent container from an unavailable daemon before creating.
            healthy, _ = await self.runner(["info", "--format", "{{.ServerVersion}}"])
            if healthy:
                raise DomainError("Docker daemon is unavailable")
            found, identities = await self.runner(
                [
                    "ps",
                    "-a",
                    "--filter",
                    "label=poc.owner=" + OWNER,
                    "--filter",
                    "label=poc.run_id=" + run_id,
                    "--format",
                    "{{.ID}}",
                ]
            )
            ids = [
                value
                for value in identities.splitlines()
                if re.fullmatch(r"[0-9a-f]{12,64}", value)
            ]
            if found or not ids:
                return None
            if len(ids) != 1:
                raise DomainError("More than one Docker engine is registered for this session")
            code, output = await self.runner(["inspect", ids[0]])
            if code:
                raise DomainError("Registered session engine cannot be inspected")
        rows = json.loads(output)
        if not isinstance(rows, list) or len(rows) != 1:
            raise DomainError("Unexpected Docker inspection")
        container = rows[0]
        labels = container.get("Config", {}).get("Labels", {})
        if labels.get("poc.owner") != OWNER or labels.get("poc.run_id") != run_id:
            raise DomainError("Container identity conflicts with this session")
        state = container["State"]
        bindings = container.get("NetworkSettings", {}).get("Ports", {}).get("8081/tcp") or []
        endpoint = None
        if bindings:
            binding = bindings[0]
            if binding["HostIp"] != "127.0.0.1" or not str(binding["HostPort"]).isdigit():
                raise DomainError("Engine API must be private to the server loopback")
            endpoint = "http://127.0.0.1:" + str(binding["HostPort"])
        elif state["Running"]:
            for network in container.get("NetworkSettings", {}).get("Networks", {}).values():
                address = network.get("IPAddress")
                if address and ipaddress.ip_address(address).is_private:
                    endpoint = "http://" + address + ":8081"
                    break
        return {
            "run_id": run_id,
            "container_id": container["Id"],
            "image_id": container.get("Image"),
            "status": state["Status"],
            "running": state["Running"],
            "health": state.get("Health", {}).get("Status"),
            "endpoint": endpoint,
            "runtime": "docker",
        }

    async def start(self, run_id: str) -> dict:
        valid_run_id(run_id)
        session = self.root / "sessions" / run_id
        mounted_session = self.host_root / "sessions" / run_id
        if not (session / "poc.sqlite3").is_file():
            raise DomainError("Session must be prepared before starting its engine")
        current = await self.inspect(run_id)
        if current and current["running"]:
            return current
        if current and current.get("image_id"):
            code, image_id = await self.runner(["image", "inspect", "--format", "{{.Id}}", IMAGE])
            if code or image_id.strip() != current["image_id"]:
                raise DomainError(
                    "Session engine image changed; recreate its stopped "
                    "container preserving volumes"
                )
        if current is None:
            for directory in ("operational", "learning"):
                (self.root / directory).mkdir(parents=True, exist_ok=True)
            args = [
                "create",
                "--pull=never",
                "--name",
                self.name(run_id),
                "--label",
                "poc.owner=" + OWNER,
                "--label",
                "poc.run_id=" + run_id,
                "--restart",
                "unless-stopped",
                "--stop-timeout",
                "40",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--publish",
                "127.0.0.1::8081",
                "--env",
                "POC_DATA_DIR=/data",
                "--mount",
                f"type=bind,source={mounted_session},target=/data/sessions/{run_id}",
                "--mount",
                f"type=bind,source={self.host_root / 'operational'},target=/data/operational",
                "--mount",
                f"type=bind,source={self.host_root / 'learning'},target=/data/learning",
            ]
            for key in SECRET_NAMES:
                if os.environ.get(key):
                    args.extend(
                        ["--env", key]
                    )  # Docker inherits the value; it is absent from argv.
            args.extend([IMAGE, "run", "--resume", run_id, "--serve", "--host", "0.0.0.0"])
            code, _ = await self.runner(args)
            if code:
                # A concurrent identical provision can win the name; validate its identity.
                if await self.inspect(run_id) is None:
                    raise DomainError("Docker engine provisioning failed")
        identity = current["container_id"] if current else self.name(run_id)
        code, _ = await self.runner(["start", identity])
        if code:
            raise DomainError("Docker engine start failed")
        state = await self.inspect(run_id)
        if not state:
            raise DomainError("Provisioned engine was not found")
        return state

    async def stop(self, run_id: str) -> dict:
        current = await self.inspect(run_id)
        if not current:
            raise DomainError("Session engine is not provisioned")
        if current["running"]:
            code, _ = await self.runner(["stop", "--time", "40", current["container_id"]])
            if code:
                raise DomainError("Docker engine stop failed")
        return await self.inspect(run_id)
