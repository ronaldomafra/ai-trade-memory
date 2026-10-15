"""Authenticated REST gateway. Engines are server-side and independent of client connections."""

import asyncio
import ipaddress
import re
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, ValidationError

from poc.adapters.inbound.body_limit import MAX_REQUEST_BYTES, BodyLimit
from poc.adapters.inbound.event_ws import register_stream
from poc.adapters.outbound.auth import AuthStore
from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.control_store import ControlStore
from poc.adapters.outbound.datasets import DatasetFiles, read_dataset
from poc.adapters.outbound.profiles import SQLiteProfiles
from poc.adapters.outbound.session_view import SessionViews
from poc.application.control import ControlService, public_settings
from poc.application.ports import Clock
from poc.application.profiles import ProfileService
from poc.config import GlobalAICostLimit, PositiveMoney, parse_config
from poc.domain.primitives import DomainError
from poc.domain.security import AuthenticationError, PermissionDenied, Principal
from poc.profile_config import ProfileDefinition, Style


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Body):
    username: str = Field(min_length=3, max_length=64)
    password: SecretStr = Field(min_length=12, max_length=256)
    scopes: tuple[Literal["read", "manage"], ...] = ("read", "manage")
    sessions: tuple[str, ...] = ("*",)


class SecondFactor(Body):
    challenge_token: SecretStr
    code: SecretStr


class Refresh(Body):
    refresh_token: SecretStr


class Prepare(Body):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    profile_version: int | None = Field(default=None, gt=0)
    profile_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,30}USDT$")
    run_id: str | None = None
    overrides: dict = Field(default_factory=dict)
    dataset_id: str | None = None


class ImportDataset(Body):
    dataset_id: str


class ConfigureGlobalAIBudget(GlobalAICostLimit):
    # PUT replaces both settings explicitly; omitting the value must never reset it.
    cost_limit_enabled: StrictBool = Field(...)
    max_observed_cost_usd_per_day: PositiveMoney = Field(...)


def loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def gateway_api(
    service: ControlService,
    auth: AuthStore,
    commands: ControlStore,
    views: SessionViews,
    clock: Clock,
    http: httpx.AsyncClient,
) -> FastAPI:
    if service.profile_service is None:
        service.profile_service = ProfileService(
            SQLiteProfiles(commands.connection), service.template
        )
    app = FastAPI(title="ai-trade-memory control API", version="1", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def transport(request: Request, call_next):
        if request.url.scheme != "https" and not loopback(
            request.client.host if request.client else ""
        ):
            return JSONResponse({"error": "TLS_REQUIRED"}, status_code=426)
        length = request.headers.get("content-length", "0")
        if len(length) > 12 or not length.isascii() or not length.isdecimal():
            return JSONResponse({"error": "INVALID_CONTENT_LENGTH"}, status_code=400)
        if int(length) > MAX_REQUEST_BYTES:
            return JSONResponse({"error": "REQUEST_TOO_LARGE"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def invalid(request, error):
        # Never echo supplied password, OTP, token or invalid configuration values.
        return JSONResponse(
            {
                "error": "INVALID_REQUEST",
                "details": [
                    {"loc": detail["loc"], "type": detail["type"]} for detail in error.errors()
                ],
            },
            status_code=422,
        )

    @app.exception_handler(AuthenticationError)
    async def unauthorized(request, error):
        return JSONResponse(
            {"error": "AUTHENTICATION_REQUIRED", "message": str(error)}, status_code=401
        )

    @app.exception_handler(PermissionDenied)
    async def forbidden(request, error):
        return JSONResponse({"error": "PERMISSION_DENIED"}, status_code=403)

    @app.exception_handler(DomainError)
    async def domain_error(request, error):
        return JSONResponse({"error": "INVALID_OPERATION", "message": str(error)}, status_code=409)

    async def principal(authorization: str | None = Header(default=None)) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("Authentication required")
        return auth.authorize(authorization[7:], clock.now(), "read")

    Actor = Annotated[Principal, Depends(principal)]

    def command_key(value: str | None) -> str:
        if value is None or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
            raise DomainError("An 8-128 character Idempotency-Key is required")
        return value

    def global_permission(user: Principal, scope: str):
        user.require(scope)
        if "*" not in user.sessions:
            raise PermissionDenied("Global owner scope is required")

    def dataset_path(identity: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise DomainError("Invalid dataset identity")
        record = commands.dataset(identity)
        if record is None:
            raise DomainError("Dataset is not registered on this server")
        path = Path(record["path"])
        if not path.resolve().is_relative_to(
            Path(service.template.app.data_dir).resolve() / "datasets"
        ):
            raise DomainError("Dataset path is outside the server registry")
        return path

    @app.get("/health")
    async def health():
        return {
            "service": "paper-control",
            "api_version": 1,
            "owner_initialized": auth.initialized(),
        }

    @app.post("/v1/auth/login")
    async def login(body: Login, request: Request):
        return await asyncio.to_thread(
            auth.begin_login,
            body.username,
            body.password.get_secret_value(),
            clock.now(),
            request.client.host,
            body.scopes,
            body.sessions,
        )

    @app.post("/v1/auth/2fa")
    async def second_factor(body: SecondFactor, request: Request):
        return await asyncio.to_thread(
            auth.complete_login,
            body.challenge_token.get_secret_value(),
            body.code.get_secret_value(),
            clock.now(),
            request.client.host,
        )

    @app.post("/v1/auth/refresh")
    async def refresh(body: Refresh):
        return auth.refresh(body.refresh_token.get_secret_value(), clock.now())

    @app.post("/v1/auth/logout")
    async def logout(authorization: str | None = Header(default=None)):
        if authorization and authorization.startswith("Bearer "):
            auth.logout(authorization[7:], clock.now())
        return {"logged_out": True, "engines_unchanged": True}

    @app.get("/v1/profiles")
    async def profiles(user: Actor):
        return service.profiles()

    @app.get("/v1/profile-template")
    async def profile_template(user: Actor, style: Style = "DAY_TRADE"):
        return service.profile_service.template(style)

    @app.post("/v1/profiles/validate")
    async def validate_profile(body: ProfileDefinition, user: Actor):
        return service.profile_service.validate(body.model_dump(mode="json"))

    @app.get("/v1/profiles/{profile_id}/versions/{version}")
    async def profile_version(profile_id: str, version: int, user: Actor):
        record = service.profile_service.repository.profile(profile_id, version)
        if record is None:
            raise DomainError("Profile revision not found")
        return {"profile": record}

    async def profile_command(user, key, profile_id, version, action, definition=None):
        global_permission(user, "manage")
        body = {
            "profile_id": profile_id,
            "version": version,
            "action": action,
            "definition": definition,
        }
        command = commands.reserve_command(
            user.user_id,
            command_key(key),
            "PROFILE_" + action.upper(),
            body,
            profile_id,
            clock.now(),
        )
        if command["response"] is not None:
            return command["response"]
        result = (
            service.profile_service.register(definition, user.user_id, clock.now())
            if action == "register"
            else service.profile_service.transition(
                profile_id, version, action, user.user_id, clock.now()
            )
        )
        response = {"profile": result, "command_id": command["command_id"]}
        commands.finish_command(command["command_id"], response, clock.now())
        return response

    @app.post("/v1/profiles", status_code=201)
    async def register_profile(
        body: ProfileDefinition, user: Actor, idempotency_key: str | None = Header(default=None)
    ):
        return await profile_command(
            user,
            idempotency_key,
            body.profile.profile_id,
            body.profile.version,
            "register",
            body.model_dump(mode="json"),
        )

    @app.post("/v1/profiles/{profile_id}/versions", status_code=201)
    async def new_profile_version(
        profile_id: str,
        body: ProfileDefinition,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        if profile_id != body.profile.profile_id:
            raise DomainError("Profile path and definition disagree")
        return await profile_command(
            user,
            idempotency_key,
            profile_id,
            body.profile.version,
            "register",
            body.model_dump(mode="json"),
        )

    @app.post("/v1/profiles/{profile_id}/versions/{version}/publish")
    async def publish_profile(
        profile_id: str,
        version: int,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        return await profile_command(user, idempotency_key, profile_id, version, "publish")

    @app.post("/v1/profiles/{profile_id}/versions/{version}/archive")
    async def archive_profile(
        profile_id: str,
        version: int,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        return await profile_command(user, idempotency_key, profile_id, version, "archive")

    @app.get("/v1/ai-budget")
    async def ai_budget(user: Actor):
        global_permission(user, "read")
        with closing(
            AIBudget(Path(service.template.app.data_dir) / "operational" / "ai-budget.sqlite3")
        ) as budget:
            return budget.aggregate_status(clock.now())

    @app.put("/v1/ai-budget")
    async def configure_ai_budget(body: ConfigureGlobalAIBudget, user: Actor):
        global_permission(user, "manage")
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Configure AI limits in the profile/session ai parameters. "
                "Global budget writes are retired for new bots."
            },
        )

    @app.put("/v1/legacy-ai-budget")
    async def configure_legacy_ai_budget(body: ConfigureGlobalAIBudget, user: Actor):
        global_permission(user, "manage")
        with closing(
            AIBudget(Path(service.template.app.data_dir) / "operational" / "ai-budget.sqlite3")
        ) as budget:
            return budget.set_cost_limit(body, clock.now(), user.user_id)

    @app.get("/v1/sessions/{run_id}/ai-budget")
    async def session_ai_budget(run_id: str, user: Actor):
        user.require("read", run_id)
        with closing(views.database(run_id, readonly=True)) as database:
            record = database.run()
            settings = record["config"]["ai"]
        with closing(
            AIBudget(Path(service.template.app.data_dir) / "operational" / "ai-budget.sqlite3")
        ) as budget:
            return {
                **budget.session_status(clock.now(), run_id, settings),
                "profile_id": record["profile_id"],
                "profile_version": record["profile_version"],
            }

    @app.get("/v1/sessions")
    async def sessions(user: Actor):
        records = views.list()
        for record in records:
            commands.register_session(record)
        return {
            "sessions": [
                record
                for record in records
                if "*" in user.sessions or record["run_id"] in user.sessions
            ]
        }

    @app.post("/v1/sessions", status_code=201)
    async def prepare(
        body: Prepare,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        user.require("manage")
        path = str(dataset_path(body.dataset_id)) if body.dataset_id else None
        return await service.prepare(user, command_key(idempotency_key), body.model_dump(), path)

    @app.post("/v1/sessions/{run_id}/start")
    async def start(
        run_id: str,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        return await service.lifecycle(user, command_key(idempotency_key), run_id, "start")

    @app.post("/v1/sessions/{run_id}/stop")
    async def stop(
        run_id: str,
        user: Actor,
        idempotency_key: str | None = Header(default=None),
    ):
        return await service.lifecycle(user, command_key(idempotency_key), run_id, "stop")

    @app.get("/v1/sessions/{run_id}/snapshot")
    async def snapshot(run_id: str, user: Actor):
        user.require("read", run_id)
        payload = views.snapshot(run_id)
        runtime = await service.runtime.inspect(run_id)
        if runtime and runtime["running"] and runtime.get("endpoint"):
            try:
                response = await http.get(runtime["endpoint"] + "/v1/session", timeout=3)
                if response.status_code == 200:
                    live = response.json()
                    if live.get("run_id") == run_id:
                        payload["health"] = live.get("health")
            except httpx.HTTPError:
                pass
        payload["runtime"] = {
            k: v
            for k, v in (runtime or {"status": "not_provisioned", "running": False}).items()
            if k not in ("endpoint", "container_id")
        }
        return payload

    @app.get("/v1/sessions/{run_id}/events")
    async def events(
        run_id: str,
        user: Actor,
        after_seq: int = Query(0, ge=0),
        limit: int = Query(1000, ge=1, le=10000),
    ):
        user.require("read", run_id)
        return {"run_id": run_id, "events": views.events(run_id, after_seq, limit)}

    @app.get("/v1/sessions/{run_id}/transfer")
    async def transfer(run_id: str, user: Actor):
        user.require("read", run_id)
        return views.snapshot(run_id)["learning"]["transfer"]

    @app.get("/v1/sessions/{run_id}/configuration")
    async def saved_configuration(run_id: str, user: Actor):
        user.require("read", run_id)
        db = views.database(run_id, readonly=True)
        try:
            record = db.run()
            return {
                "run_id": run_id,
                "profile_id": record["profile_id"],
                "profile_version": record["profile_version"],
                "profile_hash": record.get("profile_hash"),
                "symbol": record["symbol"],
                "config_hash": record["config_hash"],
                "editable": False,
                "settings": public_settings(parse_config(record["config"])),
            }
        finally:
            db.close()

    @app.get("/v1/datasets")
    async def datasets(user: Actor):
        global_permission(user, "read")
        return {"datasets": commands.datasets()}

    @app.post("/v1/datasets")
    async def upload(file: Annotated[UploadFile, File()], user: Actor):
        global_permission(user, "manage")
        root = Path(service.template.app.data_dir).resolve() / "datasets"
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / (".upload-" + uuid4().hex)
        try:
            total = 0
            with temporary.open("xb") as stream:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 64 * 1024 * 1024:
                        raise DomainError("Dataset upload exceeds 64 MB")
                    stream.write(chunk)
            data = read_dataset(temporary, clock.now())
            identity = data["file_hash"]
            destination = root / (identity + ".jsonl")
            if not destination.exists():
                temporary.rename(destination)
            commands.register_dataset(
                identity, data["file_hash"], destination, data["header"], clock.now()
            )
            return {"dataset_id": identity, "metadata": data["header"]}
        finally:
            temporary.unlink(missing_ok=True)
            await file.close()

    @app.get("/v1/datasets/{dataset_id}")
    async def download(dataset_id: str, user: Actor):
        global_permission(user, "read")
        return FileResponse(
            dataset_path(dataset_id),
            media_type="application/x-ndjson",
            filename=dataset_id + ".jsonl",
        )

    @app.post("/v1/sessions/{run_id}/learning/import")
    async def import_learning(run_id: str, body: ImportDataset, user: Actor):
        user.require("manage", run_id)
        path = dataset_path(body.dataset_id)
        db = views.database(run_id)
        try:
            return DatasetFiles(db).import_path(path, clock.now())
        finally:
            db.close()

    @app.post("/v1/sessions/{run_id}/learning/export")
    async def export_learning(run_id: str, user: Actor):
        user.require("read", run_id)
        root = Path(service.template.app.data_dir) / "datasets"
        root.mkdir(parents=True, exist_ok=True)
        path = root / ("export-" + uuid4().hex + ".jsonl")
        db = views.database(run_id)
        try:
            exported = DatasetFiles(db).export(path, clock.now())
            data = read_dataset(path, clock.now())
            identity = exported["file_hash"]
            destination = root / (identity + ".jsonl")
            if not destination.exists():
                path.rename(destination)
            commands.register_dataset(identity, identity, destination, data["header"], clock.now())
            return {"dataset_id": identity, "sample_count": exported["sample_count"]}
        finally:
            path.unlink(missing_ok=True)
            db.close()

    app.state.service = service
    app.state.auth = auth
    app.state.views = views
    app.add_middleware(BodyLimit)
    register_stream(app, auth, views, clock)
    return app
