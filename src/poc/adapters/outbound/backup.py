"""Online SQLite backups; JSONL/CSV projections are reconstructed from the restored ledger."""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from poc.adapters.outbound.budget import AIBudget
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.sessions import valid_run_id
from poc.domain.primitives import DomainError, canonical_json, iso


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_backup(source: sqlite3.Connection, destination: Path):
    target = sqlite3.connect(destination)
    try:
        source.backup(target, pages=1000, sleep=0.01)
        target.execute("PRAGMA journal_mode=DELETE")
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DomainError("Backup SQLite integrity check failed")
        target.commit()
    finally:
        target.close()
    with destination.open("rb") as stream:
        os.fsync(stream.fileno())


class SessionBackups:
    def __init__(self, data_root: Path):
        self.root = data_root.resolve()

    def create(self, database: SessionDatabase, destination: Path, now: datetime) -> dict:
        if destination.exists():
            raise DomainError("Backup destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="." + destination.name, dir=destination.parent))
        try:
            sqlite_backup(database.connection, staging / "session.sqlite3")
            verification = SessionDatabase(staging / "session.sqlite3")
            try:
                audit = verification.audit()
                record = verification.run()
                watermark = verification.connection.execute(
                    "SELECT COALESCE(MAX(event_seq),0) FROM events"
                ).fetchone()[0]
                if not audit["ok"]:
                    raise DomainError("Backup financial audit failed")
            finally:
                verification.close()
            files = {"session.sqlite3": file_hash(staging / "session.sqlite3")}
            for relative in (
                "operational/ai-budget.sqlite3",
                "operational/source-cache.sqlite3",
                "learning/catalog.sqlite3",
            ):
                path = self.root / relative
                if path.is_file():
                    source = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
                    try:
                        output = staging / relative
                        output.parent.mkdir(parents=True, exist_ok=True)
                        sqlite_backup(source, output)
                        files[relative] = file_hash(output)
                    finally:
                        source.close()
            manifest = {
                "schema_version": 1,
                "run_id": record["run_id"],
                "created_at": iso(now),
                "config_hash": record["config_hash"],
                "files": files,
                "audit": audit,
                "event_watermark": watermark,
                "consistency": (
                    "Each SQLite is individually consistent; "
                    "no atomic multi-database snapshot is assumed."
                ),
            }
            (staging / "manifest.json").write_text(canonical_json(manifest) + "\n")
            # An existing archive must never be overwritten by a new backup.
            if destination.exists():
                raise DomainError("Backup destination appeared during preparation")
            os.rename(staging, destination)
            return {**manifest, "path": str(destination)}
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def restore(self, source: Path, run_id: str, now: datetime) -> dict:
        valid_run_id(run_id)
        manifest = json.loads((source / "manifest.json").read_text())
        if manifest.get("schema_version") != 1 or manifest.get("run_id") != run_id:
            raise DomainError("Backup identity or schema mismatch")
        allowed = {
            "session.sqlite3",
            "operational/ai-budget.sqlite3",
            "operational/source-cache.sqlite3",
            "learning/catalog.sqlite3",
        }
        if set(manifest.get("files", {})) - allowed or "session.sqlite3" not in manifest.get(
            "files", {}
        ):
            raise DomainError("Unknown backup file")
        for relative, expected in manifest["files"].items():
            if file_hash(source / relative) != expected:
                raise DomainError("Backup file hash mismatch")
        target = self.root / "sessions" / run_id
        if target.exists():
            raise DomainError("Restore destination exists; financial state is never overwritten")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="." + run_id, dir=target.parent))
        try:
            shutil.copyfile(source / "session.sqlite3", staging / "poc.sqlite3")
            database = SessionDatabase(staging / "poc.sqlite3")
            try:
                if (
                    database.run()["run_id"] != run_id
                    or database.run()["config_hash"] != manifest["config_hash"]
                    or not database.audit()["ok"]
                ):
                    raise DomainError("Restored identity or ledger is invalid")
            finally:
                database.close()
            # Existing operational state is authoritative and is never rewound by a session backup.
            budget_path = self.root / "operational" / "ai-budget.sqlite3"
            fresh_operational = not budget_path.exists()
            for relative in manifest["files"]:
                if relative == "session.sqlite3":
                    continue
                destination = self.root / relative
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        (source / relative).open("rb") as incoming,
                        destination.open("xb") as outgoing,
                    ):
                        shutil.copyfileobj(incoming, outgoing)
            # If the destination operational database is new/restored, calls after the backup
            # cannot be proved absent. A day latch prevents spending reconstructed capacity.
            if fresh_operational:
                budget = AIBudget(budget_path)
                try:
                    budget.block_day(now)
                finally:
                    budget.close()
                from poc.adapters.outbound.source_cache import SourceCache

                cache = SourceCache(self.root / "operational" / "source-cache.sqlite3")
                try:
                    cache.block_marketaux_day(now)
                finally:
                    cache.close()
            os.rename(staging, target)
            return {
                "run_id": run_id,
                "sqlite": str(target / "poc.sqlite3"),
                "ai_blocked_until_next_utc_day": fresh_operational,
                "restored_at": iso(now),
            }
        finally:
            if staging.exists():
                shutil.rmtree(staging)
