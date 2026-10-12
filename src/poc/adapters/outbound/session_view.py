"""Private canonical reads for stopped engines and registry reconstruction on the server."""

from __future__ import annotations

import json
from pathlib import Path

from poc.adapters.outbound.datasets import DatasetFiles
from poc.adapters.outbound.files import FileExporter
from poc.adapters.outbound.sqlite import SessionDatabase
from poc.application.sessions import session_paths, valid_run_id
from poc.config import Config
from poc.domain.primitives import DomainError


def session_public(record: dict) -> dict:
    return {
        key: record.get(key)
        for key in (
            "run_id",
            "profile_id",
            "profile_version",
            "symbol",
            "base_asset",
            "quote_asset",
            "created_at",
            "status",
            "config_hash",
            "template_version",
        )
    }


class SessionViews:
    def __init__(self, config: Config):
        self.config = config

    def database(self, run_id: str, readonly: bool = False) -> SessionDatabase:
        valid_run_id(run_id)
        path = Path(session_paths(self.config, run_id)["sqlite"])
        expected = Path(self.config.app.data_dir).resolve() / "sessions"
        if not path.resolve().is_relative_to(expected):
            raise DomainError("Remote session storage must remain in the configured server root")
        return SessionDatabase(path, create=False, readonly=readonly)

    def list(self) -> list[dict]:
        result = []
        root = Path(self.config.app.data_dir) / "sessions"
        for directory in sorted(root.iterdir()) if root.exists() else []:
            if not (directory / "poc.sqlite3").is_file():
                continue
            try:
                db = self.database(directory.name, readonly=True)
                try:
                    record = db.run()
                    if record and record["run_id"] == directory.name:
                        result.append(session_public(record))
                finally:
                    db.close()
            except (DomainError, OSError):
                continue
        return result

    def snapshot(self, run_id: str) -> dict:
        db = self.database(run_id, readonly=True)
        try:
            return FileExporter(db).dashboard()
        finally:
            db.close()

    def events(self, run_id: str, after: int, limit: int) -> list[dict]:
        db = self.database(run_id, readonly=True)
        try:
            return db.events(after, limit)
        finally:
            db.close()

    def dataset_metadata(self, run_id: str) -> dict | None:
        db = self.database(run_id, readonly=True)
        try:
            imported = DatasetFiles(db).imported()
            return (
                {key: value for key, value in imported.items() if key != "header_json"}
                if imported
                else None
            )
        finally:
            db.close()

    def event_bounds(self, run_id: str) -> tuple[int, int]:
        db = self.database(run_id, readonly=True)
        try:
            row = db.connection.execute(
                "SELECT COALESCE(MIN(event_seq),0),COALESCE(MAX(event_seq),0) FROM events"
            ).fetchone()
            return tuple(row)
        finally:
            db.close()

    def live(self, run_id: str) -> dict:
        db = self.database(run_id, readonly=True)
        try:
            db.connection.execute("BEGIN")
            quote = db.connection.execute(
                "SELECT bid,ask,observed_at FROM price_quotes ORDER BY observed_at DESC LIMIT 1"
            ).fetchone()
            cycle = db.connection.execute(
                "SELECT * FROM decision_cycles ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            return {
                "quote": dict(quote) if quote else None,
                "health": db.runtime_state("engine"),
                "cycle": {
                    key: value for key, value in dict(cycle).items() if not key.endswith("_json")
                }
                if cycle
                else None,
                "stage": self._stage(db),
            }
        finally:
            db.close()

    @staticmethod
    def _stage(db: SessionDatabase) -> dict | None:
        row = db.connection.execute(
            "SELECT event_type,occurred_at,data_json FROM events ORDER BY event_seq DESC LIMIT 1"
        ).fetchone()
        return {"event_type": row[0], "at": row[1], "data": json.loads(row[2])} if row else None
