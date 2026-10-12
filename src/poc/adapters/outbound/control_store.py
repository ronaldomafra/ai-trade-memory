"""Server command registry is reconstructible coordination, never a financial ledger."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from poc.domain.primitives import DomainError, canonical_json, iso, stable_id


class ControlStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS commands(
            command_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, kind TEXT NOT NULL,
            request_hash TEXT NOT NULL, run_id TEXT NOT NULL, status TEXT NOT NULL,
            response_json TEXT, created_at TEXT NOT NULL, finished_at TEXT);
          CREATE TABLE IF NOT EXISTS sessions(
            run_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL,symbol TEXT NOT NULL,
            config_hash TEXT NOT NULL,created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS datasets(
            dataset_id TEXT PRIMARY KEY,file_hash TEXT NOT NULL,path TEXT NOT NULL,
            metadata_json TEXT NOT NULL,created_at TEXT NOT NULL);
        """)

    def close(self):
        self.connection.close()

    def reserve_command(
        self, actor: str, key: str, kind: str, body: dict, run_id: str, now: datetime
    ) -> dict:
        identity = stable_id("control-command", actor, key)
        digest = stable_id(kind, body)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT * FROM commands WHERE command_id=?", (identity,)
            ).fetchone()
            if row:
                if row["request_hash"] != digest or row["kind"] != kind:
                    raise DomainError("Idempotency-Key conflicts with a previous command")
                return {
                    **dict(row),
                    "new": False,
                    "response": json.loads(row["response_json"]) if row["response_json"] else None,
                }
            self.connection.execute(
                "INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?)",
                (identity, actor, kind, digest, run_id, "PENDING", None, iso(now), None),
            )
            return {
                "command_id": identity,
                "run_id": run_id,
                "status": "PENDING",
                "new": True,
                "response": None,
            }
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            if self.connection.in_transaction:
                self.connection.commit()

    def finish_command(self, command_id: str, response: dict, now: datetime):
        self.connection.execute(
            "UPDATE commands SET status='COMPLETED',response_json=?,finished_at=? "
            "WHERE command_id=?",
            (canonical_json(response), iso(now), command_id),
        )

    def register_session(self, record: dict):
        self.connection.execute(
            "INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?)",
            (
                record["run_id"],
                record["profile_id"],
                record["symbol"],
                record["config_hash"],
                record["created_at"],
            ),
        )

    def register_dataset(
        self, identity: str, file_hash: str, path: Path, metadata: dict, now: datetime
    ):
        self.connection.execute(
            "INSERT OR IGNORE INTO datasets VALUES(?,?,?,?,?)",
            (identity, file_hash, str(path.resolve()), canonical_json(metadata), iso(now)),
        )

    def dataset(self, identity: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM datasets WHERE dataset_id=?", (identity,)
        ).fetchone()
        return dict(row) if row else None

    def datasets(self) -> list[dict]:
        return [
            {
                "dataset_id": row["dataset_id"],
                "file_hash": row["file_hash"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in self.connection.execute("SELECT * FROM datasets ORDER BY created_at DESC")
        ]
