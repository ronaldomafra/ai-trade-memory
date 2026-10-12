"""Shared operational database. Reservations count even if a sender crashes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poc.domain.primitives import DomainError, canonical_json, decimal, iso, stable_id, utc


class AIBudget:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS days(
            day TEXT PRIMARY KEY, max_calls INTEGER NOT NULL, max_cost TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS attempts(
            ai_call_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, call_purpose TEXT NOT NULL,
            logical_request_id TEXT NOT NULL, attempt_index INTEGER NOT NULL
            CHECK(attempt_index IN (1,2)),
            day TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
            request_json_sanitized TEXT NOT NULL, response_json TEXT, http_status INTEGER,
            status TEXT NOT NULL, error_code TEXT, cost_usd TEXT, cost_source TEXT NOT NULL,
            UNIQUE(run_id,call_purpose,logical_request_id,attempt_index));
          CREATE TABLE IF NOT EXISTS circuits(
            credential_id TEXT PRIMARY KEY, error_code TEXT NOT NULL, opened_at TEXT NOT NULL);
        """)

    @contextmanager
    def transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self):
        self.connection.close()

    def block_day(self, now: datetime):
        with self.transaction():
            self.connection.execute(
                "INSERT INTO days VALUES(?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET max_calls=0,max_cost='0'",
                (utc(now).date().isoformat(), 0, "0"),
            )

    def reserve(
        self,
        run_id: str,
        purpose: str,
        logical: str,
        index: int,
        now: datetime,
        max_calls: int,
        max_cost: Decimal,
        request: dict,
    ) -> dict[str, Any]:
        if index not in (1, 2) or not 0 < max_calls <= 240 or not 0 < max_cost <= Decimal(".05"):
            raise DomainError("Invalid global budget limits or attempt")
        call_id = stable_id(run_id, purpose, logical, index)
        day = utc(now).date().isoformat()
        with self.transaction():
            if self.attempt(call_id):
                return {
                    "granted": False,
                    "ai_call_id": call_id,
                    "reason": "ATTEMPT_ALREADY_RESERVED",
                }
            self.connection.execute(
                "INSERT OR IGNORE INTO days VALUES(?,?,?)", (day, max_calls, str(max_cost))
            )
            limits = self.connection.execute("SELECT * FROM days WHERE day=?", (day,)).fetchone()
            call_limit, cost_limit = (
                min(max_calls, limits["max_calls"]),
                min(max_cost, decimal(limits["max_cost"])),
            )
            self.connection.execute(
                "UPDATE days SET max_calls=?,max_cost=? WHERE day=?",
                (call_limit, str(cost_limit), day),
            )
            summary = self.summary(now)
            if (
                summary["physical_attempts"] >= call_limit
                or decimal(summary["observed_cost_usd"]) >= cost_limit
            ):
                return {"granted": False, "reason": "AI_BUDGET_EXCEEDED"}
            self.connection.execute(
                "INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    call_id,
                    run_id,
                    purpose,
                    logical,
                    index,
                    day,
                    iso(now),
                    None,
                    canonical_json(request),
                    None,
                    None,
                    "RESERVED",
                    None,
                    None,
                    "unknown",
                ),
            )
        return {"granted": True, "ai_call_id": call_id}

    def attempt(self, call_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM attempts WHERE ai_call_id=?", (call_id,)
        ).fetchone()
        return dict(row) if row else None

    def finish(
        self,
        call_id: str,
        now: datetime,
        response: dict | None,
        http_status: int | None,
        error: str | None,
    ):
        cost = None
        try:
            usage = (response or {}).get("usage")
            value = usage.get("cost") if isinstance(usage, dict) else None
            if value is not None:
                cost = decimal(value)
                if cost < 0:
                    cost = None
        except (ValueError, TypeError):
            pass
        with self.transaction():
            row = self.attempt(call_id)
            if not row:
                raise DomainError("Attempt was not reserved")
            if row["finished_at"] is not None:
                return row
            self.connection.execute(
                "UPDATE attempts SET finished_at=?,response_json=?,http_status=?,status=?,"
                "error_code=?,cost_usd=?,cost_source=? WHERE ai_call_id=?",
                (
                    iso(now),
                    canonical_json(response) if response is not None else None,
                    http_status,
                    "FAILED" if error else "COMPLETED",
                    error,
                    str(cost) if cost is not None else None,
                    "usage.cost" if cost is not None else "unknown",
                    call_id,
                ),
            )
        return self.attempt(call_id)

    def summary(self, now: datetime, run_id: str | None = None) -> dict:
        query = "SELECT * FROM attempts WHERE day=?"
        params = [utc(now).date().isoformat()]
        if run_id is not None:
            query += " AND run_id=?"
            params.append(run_id)
        rows = self.connection.execute(query, params).fetchall()
        return {
            "day_utc": params[0],
            "physical_attempts": len(rows),
            "observed_cost_usd": str(
                sum((decimal(r["cost_usd"]) for r in rows if r["cost_usd"] is not None), Decimal(0))
            ),
            "unknown_cost_calls": sum(r["cost_usd"] is None for r in rows),
            "indeterminate_calls": sum(r["finished_at"] is None for r in rows),
        }

    def circuit(self, credential_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM circuits WHERE credential_id=?", (credential_id,)
            ).fetchone()
            is not None
        )

    def open_circuit(self, credential_id: str, error: str, now: datetime):
        with self.transaction():
            self.connection.execute(
                "INSERT OR IGNORE INTO circuits VALUES(?,?,?)", (credential_id, error, iso(now))
            )

    def attempts_for_run(self, run_id: str) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM attempts WHERE run_id=? ORDER BY started_at,attempt_index", (run_id,)
            )
        ]

    def response(self, row: dict) -> dict | None:
        return (
            json.loads(row["response_json"], parse_float=Decimal) if row["response_json"] else None
        )
