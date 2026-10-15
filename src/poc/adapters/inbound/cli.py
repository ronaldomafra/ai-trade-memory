"""Commands are registered only when their implementations are available."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import ValidationError

from poc.adapters.inbound.smoke import smoke_offline
from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.market import BinancePublic
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.sessions import PROFILE_ID, valid_run_id
from poc.bootstrap import configuration, session_manager
from poc.domain.primitives import DomainError, canonical_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="ai-trade-memory — PAPER ONLY")
    subs = result.add_subparsers(dest="command", required=True)
    for name in (
        "config-check",
        "profiles",
        "smoke-offline",
        "prepare-session",
        "init-db",
        "status",
        "report",
        "export",
        "validate-data",
        "export-events",
        "run",
        "backfill",
        "smoke-openrouter",
        "check-openrouter",
        "import-learning",
        "export-learning",
        "evaluate-outcomes",
        "backup",
        "restore-backup",
        "start-engine",
        "stop-engine",
        "engine-status",
        "transfer-status",
        "bootstrap-owner",
        "reset-owner-2fa",
        "serve-control",
        "control-api",
        "tui",
        "observe",
        "ai-budget",
        "profile-template",
        "profile-validate",
        "profile-register",
        "profile-publish",
        "profile-archive",
    ):
        command = subs.add_parser(name)
        if name != "tui":
            command.add_argument("--config", default="config/default.yaml")
        if name in ("prepare-session", "init-db"):
            command.add_argument("--profile", required=True)
            command.add_argument("--run-id", required=True)
            command.add_argument("--symbol")
            command.add_argument("--profile-version", type=int)
        if name in ("status", "report", "export", "validate-data", "export-events"):
            command.add_argument("--run-id", required=True)
        if name == "run":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--new-session", action="store_true")
            selection.add_argument("--resume")
            command.add_argument("--profile")
            command.add_argument("--profile-version", type=int)
            command.add_argument("--symbol")
            command.add_argument("--run-id")
            command.add_argument("--duration-seconds", type=float)
            command.add_argument("--serve", action="store_true")
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8081)
        if name == "backfill":
            command.add_argument("--run-id", required=True)
            command.add_argument("--days", type=int, default=7)
        if name in (
            "import-learning",
            "export-learning",
            "evaluate-outcomes",
            "backup",
            "restore-backup",
        ):
            command.add_argument("--run-id", required=True)
        if name == "import-learning":
            command.add_argument("--input", required=True)
        if name == "export-learning":
            command.add_argument("--output", required=True)
        if name == "backup":
            command.add_argument("--output", required=True)
        if name == "restore-backup":
            command.add_argument("--input", required=True)
        if name in ("start-engine", "stop-engine", "engine-status", "transfer-status"):
            command.add_argument("--run-id", required=True)
        if name in ("bootstrap-owner", "reset-owner-2fa"):
            command.add_argument("--username", required=True)
        if name == "bootstrap-owner":
            command.add_argument("--password-file")
        if name in ("serve-control", "control-api"):
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8080)
        if name == "tui":
            command.add_argument("--server", required=True)
        if name == "smoke-offline":
            command.add_argument("--scope", choices=("pipeline", "accounting"), default="pipeline")
        if name == "check-openrouter":
            command.add_argument("--recover-auth", action="store_true")
        if name == "observe":
            command.add_argument("--run-id", action="append", required=True)
            command.add_argument("--output", required=True)
            command.add_argument("--duration-hours", type=float, default=24)
            command.add_argument("--poll-seconds", type=int, default=60)
        if name == "ai-budget":
            command.add_argument("--run-id", help="Read the selected bot's daily budget")
            command.add_argument(
                "--legacy-global", action="store_true", help="Legacy sessions only"
            )
            toggle = command.add_mutually_exclusive_group()
            toggle.add_argument(
                "--enable-cost-limit", dest="cost_limit_enabled", action="store_const", const=True
            )
            toggle.add_argument(
                "--disable-cost-limit", dest="cost_limit_enabled", action="store_const", const=False
            )
            command.add_argument(
                "--daily-limit-usd", help="Legacy-only observed-cost limit as a decimal string"
            )
        if name == "export-events":
            command.add_argument("--rebuild", action="store_true")
        if name == "profile-template":
            command.add_argument(
                "--style", choices=("swing", "scalping", "daytrade"), required=True
            )
            command.add_argument("--output", required=True)
        if name in ("profile-validate", "profile-register"):
            command.add_argument("--input", required=True)
        if name in ("profile-publish", "profile-archive"):
            command.add_argument("--profile", required=True)
            command.add_argument("--version", type=int, required=True)
        if name in ("export", "report"):
            command.add_argument("--format", choices=["all", "json"], default="json")
    return result


async def prepare(args, config):
    profile_record = None
    if args.profile != PROFILE_ID:
        from poc.adapters.outbound.control_store import ControlStore
        from poc.adapters.outbound.profiles import SQLiteProfiles
        from poc.application.profiles import ProfileService
        from poc.profile_config import ProfileDefinition, resolve_profile, with_session_budget

        commands = ControlStore(Path(config.app.data_dir) / "control" / "control.sqlite3")
        try:
            profile, profile_record = ProfileService(
                SQLiteProfiles(commands.connection), config
            ).resolve(args.profile, getattr(args, "profile_version", None))
            profile = ProfileDefinition.model_validate(
                with_session_budget(profile.model_dump(mode="json"))
            )
            config = resolve_profile(
                profile, config, args.symbol or profile.session_defaults.symbol
            )
        finally:
            commands.close()
    valid_run_id(args.run_id)
    if args.symbol:
        data = config.model_dump(mode="json")
        data["market"]["symbol"] = args.symbol
        config = type(config).model_validate(data)
    source = BinancePublic()
    try:
        metadata = await source.metadata(config.market.symbol)
    finally:
        await source.close()
    return session_manager(config).prepare(
        args.run_id or "run-" + uuid4().hex[:16],
        args.profile,
        metadata,
        datetime.now(UTC),
        profile_record,
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "tui":
            from poc.adapters.inbound.tui import TradeApp
            from poc.adapters.outbound.control_client import ControlClient

            # Client mode never loads server .env/credentials or opens local financial storage.
            TradeApp(ControlClient(args.server)).run()
            return 0
        config = configuration(args.config)
        if args.command == "ai-budget":
            from poc.adapters.outbound.budget import AIBudget
            from poc.config import GlobalAICostLimit

            change = args.cost_limit_enabled is not None or args.daily_limit_usd is not None
            if args.run_id and args.legacy_global:
                raise DomainError("Choose a session or --legacy-global, not both")
            if change and not args.legacy_global:
                raise DomainError(
                    "Configure AI limits in the profile/session ai parameters before creating "
                    "the bot. Global writes require --legacy-global and affect only old sessions."
                )
            record = None
            if args.run_id:
                from poc.adapters.outbound.session_view import SessionViews

                database = SessionViews(config).database(args.run_id, readonly=True)
                try:
                    record = database.run()
                    if not record:
                        raise DomainError("Missing session")
                finally:
                    database.close()
            budget = AIBudget(Path(config.app.data_dir) / "operational" / "ai-budget.sqlite3")
            try:
                now = datetime.now(UTC)
                if change:
                    current = budget.cost_policy(now)
                    policy = GlobalAICostLimit(
                        cost_limit_enabled=(
                            args.cost_limit_enabled
                            if args.cost_limit_enabled is not None
                            else current["cost_limit_enabled"]
                        ),
                        max_observed_cost_usd_per_day=(
                            args.daily_limit_usd
                            if args.daily_limit_usd is not None
                            else current["max_observed_cost_usd_per_day"]
                        ),
                    )
                    output = budget.set_cost_limit(policy, now, "local-cli")
                else:
                    output = (
                        budget.session_status(now, args.run_id, record["config"]["ai"])
                        if record
                        else budget.status(now)
                        if args.legacy_global
                        else budget.aggregate_status(now)
                    )
            finally:
                budget.close()
        elif args.command == "observe":
            from poc.adapters.inbound.observe import observe

            output = asyncio.run(
                observe(
                    config, args.run_id, Path(args.output), args.duration_hours, args.poll_seconds
                )
            )
        elif args.command in ("serve-control", "control-api"):
            from poc.adapters.inbound.gateway import serve_control

            asyncio.run(serve_control(config, args.host, args.port))
            return 0
        elif args.command in ("bootstrap-owner", "reset-owner-2fa"):
            import getpass

            from poc.adapters.outbound.auth import AuthStore

            auth = AuthStore(Path(config.app.data_dir) / "control" / "auth.sqlite3")
            try:
                if args.command == "bootstrap-owner":
                    if args.password_file:
                        path = Path(args.password_file)
                        if path.stat().st_mode & 0o077:
                            raise DomainError("Password file must be accessible only to its owner")
                        password = path.read_text().rstrip("\r\n")
                    else:
                        password = getpass.getpass("Senha do proprietário (mínimo 12 caracteres): ")
                    output = auth.bootstrap_owner(args.username, password, datetime.now(UTC))
                else:
                    output = auth.reset_totp(args.username, datetime.now(UTC))
            finally:
                auth.close()
        elif args.command == "config-check":
            output = {"valid": True, "mode": config.app.mode, "config_hash": config.hash}
        elif args.command.startswith("profile-") or args.command == "profiles":
            import yaml

            from poc.adapters.outbound.control_store import ControlStore
            from poc.adapters.outbound.profiles import SQLiteProfiles
            from poc.application.profiles import ProfileService
            from poc.profile_config import profile_template

            commands = ControlStore(Path(config.app.data_dir) / "control" / "control.sqlite3")
            try:
                service = ProfileService(SQLiteProfiles(commands.connection), config)
                if args.command == "profile-template":
                    style = {"daytrade": "DAY_TRADE", "swing": "SWING", "scalping": "SCALPING"}[
                        args.style
                    ]
                    document = profile_template(style)
                    destination = Path(args.output)
                    with destination.open("x", encoding="utf-8") as stream:
                        yaml.safe_dump(document, stream, sort_keys=False, allow_unicode=True)
                    output = {"path": str(destination), "style": style, "starts_engine": False}
                elif args.command in ("profile-validate", "profile-register"):
                    text = Path(args.input).read_bytes()
                    if len(text) > 128 * 1024:
                        raise DomainError("Profile exceeds 128 KiB")
                    if any(
                        isinstance(
                            token,
                            (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken),
                        )
                        for token in yaml.scan(text)
                    ):
                        raise DomainError("Profile YAML cannot contain aliases, anchors or tags")
                    document = yaml.safe_load(text)
                    output = (
                        service.validate(document)
                        if args.command == "profile-validate"
                        else {"profile": service.register(document, "local-cli", datetime.now(UTC))}
                    )
                elif args.command in ("profile-publish", "profile-archive"):
                    output = {
                        "profile": service.transition(
                            args.profile,
                            args.version,
                            "publish" if args.command == "profile-publish" else "archive",
                            "local-cli",
                            datetime.now(UTC),
                        )
                    }
                else:
                    output = {
                        "profiles": [
                            {
                                "profile_id": "trend_15m_v1",
                                "version": "1",
                                "status": "PAPER_CORE",
                                "continuous_engine_available": True,
                                "template": config.model_dump(mode="json"),
                                "parameter_schema": type(config).model_json_schema(),
                            }
                        ]
                    }
                    output["profiles"].extend(service.repository.list_profiles())
            finally:
                commands.close()
        elif args.command == "smoke-offline":
            if args.scope == "accounting":
                output = smoke_offline(config, session_manager(config))
            else:
                from poc.adapters.inbound.pipeline_smoke import smoke_pipeline

                output = asyncio.run(smoke_pipeline(config, session_manager(config)))
        elif args.command == "smoke-openrouter":
            from poc.adapters.inbound.ai_smoke import smoke_openrouter

            output = asyncio.run(smoke_openrouter(config))
        elif args.command == "check-openrouter":
            from poc.adapters.inbound.ai_smoke import check_openrouter

            output = asyncio.run(check_openrouter(config, args.recover_auth))
        elif args.command in ("init-db", "prepare-session"):
            output = asyncio.run(prepare(args, config))
        elif args.command == "run":
            from poc.adapters.inbound.service import run_service

            if args.new_session:
                if not args.profile:
                    raise DomainError("New sessions require an explicit profile")
                args.run_id = args.run_id or "run-" + uuid4().hex[:16]
                record = asyncio.run(prepare(args, config))
                run_id = record["run_id"]
            else:
                if args.profile or args.symbol or args.run_id:
                    raise DomainError("Restore uses persisted profile, symbol and identity")
                run_id = args.resume
            if args.duration_seconds is not None and args.duration_seconds <= 0:
                raise DomainError("Duration must be positive")
            output = asyncio.run(
                run_service(
                    config,
                    run_id,
                    args.duration_seconds,
                    args.serve,
                    args.host,
                    args.port,
                )
            )
        elif args.command in ("start-engine", "stop-engine", "engine-status"):
            from poc.adapters.outbound.runtime import DockerRuntime

            session_manager(config).restore(args.run_id)
            runtime = DockerRuntime(Path(config.app.data_dir))
            action = {
                "start-engine": runtime.start,
                "stop-engine": runtime.stop,
                "engine-status": runtime.inspect,
            }[args.command]
            output = asyncio.run(action(args.run_id))
        elif args.command == "restore-backup":
            from poc.adapters.outbound.backup import SessionBackups

            output = SessionBackups(Path(config.app.data_dir)).restore(
                Path(args.input), args.run_id, datetime.now(UTC)
            )
        elif args.command == "backfill":
            from poc.adapters.inbound.service import backfill

            output = asyncio.run(backfill(config, args.run_id, args.days))
        else:
            record = session_manager(config).restore(args.run_id)
            db = SessionDatabase(Path(record["paths"]["sqlite"]), create=False)
            try:
                exporter = FileExporter(db)
                if args.command == "transfer-status":
                    output = exporter.dashboard()["learning"]["transfer"]
                elif args.command == "validate-data":
                    output = db.audit()
                elif args.command == "backup":
                    from poc.adapters.outbound.backup import SessionBackups

                    output = SessionBackups(Path(config.app.data_dir)).create(
                        db, Path(args.output), datetime.now(UTC)
                    )
                elif args.command in ("import-learning", "export-learning"):
                    from poc.adapters.outbound.datasets import DatasetFiles

                    datasets = DatasetFiles(db)
                    if args.command == "import-learning":
                        output = datasets.import_path(Path(args.input), datetime.now(UTC))
                    else:
                        output = datasets.export(Path(args.output), datetime.now(UTC))
                elif args.command == "evaluate-outcomes":
                    from poc.application.learning import LearningEngine
                    from poc.config import parse_config
                    from poc.domain.models import MarketMetadata
                    from poc.domain.primitives import utc

                    metadata = record["market_metadata"].copy()
                    metadata["observed_at"] = utc(metadata["observed_at"])
                    learning = LearningEngine(
                        parse_config(record["config"]), MarketMetadata(**metadata), db
                    )
                    output = {
                        "matured_or_unavailable": learning.mature(datetime.now(UTC)),
                        "retroactive_trades": False,
                    }
                elif args.command == "export-events":
                    output = {"exported_events": exporter.events(rebuild=args.rebuild)}
                elif args.command == "export":
                    output = exporter.publish()
                else:
                    output = exporter.dashboard()
            finally:
                db.close()
        print(canonical_json(output))
        if args.command == "check-openrouter" and not output["authenticated"]:
            return 2
        if args.command == "smoke-openrouter" and (
            output.get("error_code") or output.get("validation") == "INVALID_AI_RESPONSE"
        ):
            return 2
        return 0
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "error": "INVALID_CONFIG",
                    "details": exc.errors(include_input=False, include_context=False),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except (DomainError, OSError, ValueError, httpx.HTTPError) as exc:
        # No request URLs/headers/response payloads are included in this safe diagnostic.
        message = str(exc) if isinstance(exc, DomainError) else type(exc).__name__
        print(canonical_json({"error": type(exc).__name__, "message": message}), file=sys.stderr)
        return 2
