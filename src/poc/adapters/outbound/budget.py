"""Shared operational database. Reservations count even if a sender crashes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poc.config import GlobalAICostLimit
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
          CREATE TABLE IF NOT EXISTS ai_cost_policy(
            revision INTEGER PRIMARY KEY, cost_limit_enabled INTEGER NOT NULL
            CHECK(cost_limit_enabled IN (0,1)), max_cost TEXT NOT NULL,
            updated_at TEXT NOT NULL, actor TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS ai_budget_policy_receipts(
            ai_call_id TEXT PRIMARY KEY, policy_revision INTEGER NOT NULL,
            cost_limit_enabled INTEGER NOT NULL, max_cost TEXT NOT NULL,
            max_calls INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS session_ai_budget_policies(
            run_id TEXT PRIMARY KEY, max_calls INTEGER NOT NULL CHECK(max_calls>0),
            cost_limit_enabled INTEGER NOT NULL CHECK(cost_limit_enabled IN (0,1)),
            max_cost TEXT NOT NULL, policy_hash TEXT NOT NULL, bound_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS session_ai_budget_receipts(
            ai_call_id TEXT PRIMARY KEY REFERENCES attempts(ai_call_id),
            run_id TEXT NOT NULL, policy_hash TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS attempts_run_day ON attempts(run_id,day);
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

    def _stored_cost_policy(self) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM ai_cost_policy ORDER BY revision DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def cost_policy(self, now: datetime) -> dict:
        row = self._stored_cost_policy()
        if row:
            return {
                "cost_limit_enabled": bool(row["cost_limit_enabled"]),
                "max_observed_cost_usd_per_day": row["max_cost"],
                "revision": row["revision"],
                "updated_at": row["updated_at"],
                "actor": row["actor"],
                "source": "GLOBAL_POLICY",
            }
        day = self.connection.execute(
            "SELECT max_cost FROM days WHERE day=?", (utc(now).date().isoformat(),)
        ).fetchone()
        limit = decimal(day["max_cost"]) if day else Decimal("0.05")
        return {
            "cost_limit_enabled": True,
            "max_observed_cost_usd_per_day": str(limit if limit > 0 else Decimal("0.05")),
            "revision": 0,
            "updated_at": None,
            "actor": None,
            "source": "LEGACY_DAILY_DEFAULTS",
        }

    def set_cost_limit(self, policy: GlobalAICostLimit, now: datetime, actor: str) -> dict:
        if not isinstance(policy, GlobalAICostLimit) or not actor or len(actor) > 128:
            raise DomainError("Invalid global cost policy or actor")
        with self.transaction():
            current = self._stored_cost_policy()
            unchanged = current and (
                bool(current["cost_limit_enabled"]) == policy.cost_limit_enabled
                and decimal(current["max_cost"]) == policy.max_observed_cost_usd_per_day
            )
            if not unchanged:
                self.connection.execute(
                    "INSERT INTO ai_cost_policy VALUES(?,?,?,?,?)",
                    (
                        current["revision"] + 1 if current else 1,
                        int(policy.cost_limit_enabled),
                        str(policy.max_observed_cost_usd_per_day),
                        iso(now),
                        actor,
                    ),
                )
        return self.status(now)

    def status(self, now: datetime) -> dict:
        with self.transaction():
            summary = self.summary(now, legacy_only=True)
            policy = self.cost_policy(now)
            row = self.connection.execute(
                "SELECT max_calls FROM days WHERE day=?", (summary["day_utc"],)
            ).fetchone()
            call_limit = row["max_calls"] if row else 240
            return {
                "scope": "LEGACY_GLOBAL",
                **summary,
                "policy": policy,
                "max_calls_per_day": call_limit,
                "call_limit_reached": summary["physical_attempts"] >= call_limit,
                "cost_limit_reached": policy["cost_limit_enabled"]
                and decimal(summary["observed_cost_usd"])
                >= decimal(policy["max_observed_cost_usd_per_day"]),
                "recovery_blocked": call_limit == 0,
            }

    def _bind_session(self, run_id, max_calls, max_cost, enabled, now):
        amount = format(decimal(max_cost).normalize(), "f")
        digest = stable_id("session_ai_budget_v1", run_id, max_calls, amount, enabled)
        row = self.connection.execute(
            "SELECT * FROM session_ai_budget_policies WHERE run_id=?", (run_id,)
        ).fetchone()
        if row and row["policy_hash"] != digest:
            raise DomainError("Session AI budget is immutable; create a new session to change it")
        if not row:
            self.connection.execute(
                "INSERT INTO session_ai_budget_policies VALUES(?,?,?,?,?,?)",
                (run_id, max_calls, int(enabled), amount, digest, iso(now)),
            )
        return {
            "max_calls": max_calls,
            "cost_limit_enabled": enabled,
            "max_cost": amount,
            "policy_hash": digest,
        }

    def bind_session(self, run_id, max_calls, max_cost, enabled, now):
        self._validate_limits(max_calls, max_cost, enabled)
        with self.transaction():
            return self._bind_session(run_id, max_calls, max_cost, enabled, now)

    @staticmethod
    def _validate_limits(max_calls, max_cost, enabled):
        if (
            isinstance(max_calls, bool)
            or not isinstance(max_calls, int)
            or max_calls <= 0
            or max_calls > 9223372036854775807
            or not isinstance(enabled, bool)
            or decimal(max_cost) <= 0
        ):
            raise DomainError("Invalid session AI budget")

    def session_status(self, now: datetime, run_id: str, settings: dict | None = None) -> dict:
        row = self.connection.execute(
            "SELECT * FROM session_ai_budget_policies WHERE run_id=?", (run_id,)
        ).fetchone()
        if row:
            limit, enabled, cost = (
                row["max_calls"],
                bool(row["cost_limit_enabled"]),
                row["max_cost"],
            )
        elif settings and settings.get("budget_scope") == "SESSION":
            limit = settings["max_calls_per_day"]
            enabled, cost = (
                settings["cost_limit_enabled"],
                settings["max_observed_cost_usd_per_day"],
            )
        else:
            return {
                **self.status(now),
                "run_id": run_id,
                "session_usage": self.summary(now, run_id),
            }
        usage = self.summary(now, run_id)
        blocked = self.connection.execute(
            "SELECT max_calls FROM days WHERE day=?", (usage["day_utc"],)
        ).fetchone()
        return {
            "scope": "SESSION",
            "run_id": run_id,
            **usage,
            "max_calls_per_day": limit,
            "policy": {
                "cost_limit_enabled": enabled,
                "max_observed_cost_usd_per_day": str(cost),
                "source": "SESSION_SNAPSHOT",
            },
            "call_limit_reached": usage["physical_attempts"] >= limit,
            "cost_limit_reached": enabled and decimal(usage["observed_cost_usd"]) >= decimal(cost),
            "recovery_blocked": bool(blocked and blocked[0] == 0),
        }

    def aggregate_status(self, now: datetime) -> dict:
        runs = [
            r[0]
            for r in self.connection.execute(
                "SELECT run_id FROM session_ai_budget_policies ORDER BY run_id"
            )
        ]
        return {
            "scope": "ALL_SESSIONS_REPORT",
            **self.summary(now),
            "sessions": [self.session_status(now, run) for run in runs],
            "legacy": self.status(now),
        }

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
        *,
        cost_limit_enabled: bool | None = None,
    ) -> dict[str, Any]:
        session_scope = cost_limit_enabled is not None
        if session_scope:
            self._validate_limits(max_calls, max_cost, cost_limit_enabled)
        if index not in (1, 2) or (
            not session_scope and (not 0 < max_calls <= 240 or not 0 < max_cost <= Decimal(".05"))
        ):
            raise DomainError("Invalid global budget limits or attempt")
        call_id = stable_id(run_id, purpose, logical, index)
        day = utc(now).date().isoformat()
        with self.transaction():
            if (
                not session_scope
                and self.connection.execute(
                    "SELECT 1 FROM session_ai_budget_policies WHERE run_id=?", (run_id,)
                ).fetchone()
            ):
                raise DomainError("A session AI budget cannot fall back to legacy global limits")
            session_policy = (
                self._bind_session(run_id, max_calls, max_cost, cost_limit_enabled, now)
                if session_scope
                else None
            )
            if self.attempt(call_id):
                return {
                    "granted": False,
                    "ai_call_id": call_id,
                    "reason": "ATTEMPT_ALREADY_RESERVED",
                }
            if session_scope:
                recovery = self.connection.execute(
                    "SELECT max_calls FROM days WHERE day=?", (day,)
                ).fetchone()
                if recovery and recovery[0] == 0:
                    return {"granted": False, "reason": "AI_RECOVERY_BLOCKED"}
                call_limit, cost_enabled, cost_limit = max_calls, cost_limit_enabled, max_cost
                policy = None
                summary = self.summary(now, run_id)
            else:
                self.connection.execute(
                    "INSERT OR IGNORE INTO days VALUES(?,?,?)", (day, max_calls, str(max_cost))
                )
                limits = self.connection.execute(
                    "SELECT * FROM days WHERE day=?", (day,)
                ).fetchone()
                call_limit = min(max_calls, limits["max_calls"])
                policy = self._stored_cost_policy()
                cost_enabled = bool(policy["cost_limit_enabled"]) if policy else True
                cost_limit = (
                    decimal(policy["max_cost"])
                    if policy
                    else min(max_cost, decimal(limits["max_cost"]))
                )
                self.connection.execute(
                    "UPDATE days SET max_calls=?,max_cost=? WHERE day=?",
                    (call_limit, str(cost_limit), day),
                )
                summary = self.summary(now, legacy_only=True)
            if summary["physical_attempts"] >= call_limit or (
                cost_enabled and decimal(summary["observed_cost_usd"]) >= cost_limit
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
            if session_scope:
                self.connection.execute(
                    "INSERT INTO session_ai_budget_receipts VALUES(?,?,?)",
                    (call_id, run_id, session_policy["policy_hash"]),
                )
            else:
                self.connection.execute(
                    "INSERT INTO ai_budget_policy_receipts VALUES(?,?,?,?,?)",
                    (
                        call_id,
                        policy["revision"] if policy else 0,
                        int(cost_enabled),
                        str(cost_limit),
                        call_limit,
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

    def summary(self, now: datetime, run_id: str | None = None, *, legacy_only=False) -> dict:
        query = "SELECT * FROM attempts WHERE day=?"
        params = [utc(now).date().isoformat()]
        if run_id is not None:
            query += " AND run_id=?"
            params.append(run_id)
        if legacy_only:
            query += " AND ai_call_id NOT IN (SELECT ai_call_id FROM session_ai_budget_receipts)"
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

    def clear_verified_auth_circuit(self, credential_id: str, verified_since: datetime) -> bool:
        """Only an explicitly verified credential may clear its older 401; never reset spend."""
        with self.transaction():
            cursor = self.connection.execute(
                "DELETE FROM circuits WHERE credential_id=? AND error_code='AI_HTTP_401' "
                "AND opened_at<=?",
                (credential_id, iso(verified_since)),
            )
        return cursor.rowcount == 1

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
