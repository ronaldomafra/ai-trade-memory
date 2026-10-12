"""Canonical session storage and a single atomic financial unit of work."""

import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, fields, replace
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from poc.domain.candles import Candle
from poc.domain.factors import CRITERIA_VERSION
from poc.domain.models import Action, DailyRiskState, Fill, Proposal, Quote, TradeResult, Wallet
from poc.domain.primitives import DomainError, canonical_json, decimal, iso, stable_id, utc

WALLET_MONEY = (
    "initial_usdt",
    "cash_usdt",
    "base_qty",
    "base_cost_basis_usdt",
    "realized_pnl_usdt",
    "entry_fill_price",
    "peak_equity_usdt",
    "max_drawdown_pct",
)
FILL_MONEY = (
    "qty_base",
    "fill_price",
    "gross_usdt",
    "fee_usdt",
    "net_cash_delta_usdt",
    "slippage_pct",
    "realized_pnl_usdt",
    "observed_bid",
    "observed_ask",
)


def sql_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    return value


class SessionDatabase:
    def __init__(self, path: str | Path, create: bool = False, readonly: bool = False):
        self.path = Path(path)
        if readonly and create:
            raise DomainError("Read-only storage cannot create a session")
        if not create and not self.path.is_file():
            raise DomainError("Session database does not exist")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # URI rw mode prevents a mistaken restore from creating an empty database.
        mode = "ro" if readonly else "rwc" if create else "rw"
        self.connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode={mode}",
            uri=True,
            isolation_level=None,
            timeout=10,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        if not readonly:
            self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.connection.execute("PRAGMA synchronous=FULL")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2, 3, 4, 5, 6) or (version == 0 and not create):
            self.connection.close()
            raise DomainError("Unknown or incompatible session schema")
        if readonly:
            if version != 6:
                self.connection.close()
                raise DomainError("Session schema must be migrated locally before remote reads")
            self.connection.execute("PRAGMA query_only=ON")
            return
        for migration in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            number = int(migration.name.split("_")[0])
            if number > version:
                self.connection.executescript(migration.read_text())

    def close(self) -> None:
        self.connection.close()

    def save_external_context(self, content: dict, now: datetime) -> str:
        self._require_transaction()
        content = {**content, "criteria_version": CRITERIA_VERSION}
        identity = stable_id("external_context_v1", content)
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO external_context_versions VALUES(?,?,?,?)",
            (identity, iso(now), canonical_json(content), CRITERIA_VERSION),
        )
        if cursor.rowcount:
            self.event(
                "EXTERNAL_CONTEXT_UPDATED",
                {
                    "context_id": identity,
                    "news_status": content["news"]["status"],
                    "prediction_status": content["prediction_markets"]["status"],
                },
                now,
                stable_id("external-update", identity),
            )
        return identity

    def external_context(self, cutoff: datetime) -> dict | None:
        row = self.connection.execute(
            "SELECT content_json FROM external_context_versions WHERE available_at<=? "
            "ORDER BY available_at DESC,rowid DESC LIMIT 1",
            (iso(cutoff),),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def queue_publication(self, publication_id: str, payload: dict, now: datetime):
        self._require_transaction()
        self.connection.execute(
            "INSERT OR IGNORE INTO learning_publication_outbox VALUES(?,?,?,?,?,?,?)",
            (
                publication_id,
                canonical_json(payload),
                iso(now),
                "PENDING",
                None,
                payload["core"]["sample_id"],
                payload["origin"]["origin_id"],
            ),
        )

    def unpublished_learning_records(self, cutoff: datetime) -> list[dict]:
        rows = self.connection.execute(
            "SELECT e.sample_id,e.core_json,o.origin_json FROM learning_examples e "
            "JOIN learning_origins o ON o.sample_id=e.sample_id "
            "WHERE e.fixture=0 AND o.available_at<? AND o.matured_at<? AND NOT EXISTS "
            "(SELECT 1 FROM learning_publication_outbox p WHERE p.sample_id=e.sample_id "
            "AND p.origin_id=o.origin_id) ORDER BY e.sample_id,o.origin_id",
            (iso(cutoff), iso(cutoff)),
        ).fetchall()
        grouped = {}
        for row in rows:
            record = grouped.setdefault(
                row["sample_id"], {"core": json.loads(row["core_json"]), "origins": []}
            )
            record["origins"].append(json.loads(row["origin_json"]))
        return list(grouped.values())

    def pending_publications(self) -> list[dict]:
        return [
            {**dict(row), "payload": json.loads(row["payload_json"])}
            for row in self.connection.execute(
                "SELECT * FROM learning_publication_outbox WHERE status='PENDING' "
                "ORDER BY created_at,publication_id"
            )
        ]

    def acknowledge_publication(self, publication_id: str, now: datetime):
        self._require_transaction()
        self.connection.execute(
            "UPDATE learning_publication_outbox SET status='PUBLISHED',acknowledged_at=? "
            "WHERE publication_id=?",
            (iso(now), publication_id),
        )

    def published_identities(self) -> list[str]:
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT publication_id FROM learning_publication_outbox WHERE status='PUBLISHED'"
            )
        ]

    def requeue_publications(self, identities: set[str]):
        self._require_transaction()
        self.connection.executemany(
            "UPDATE learning_publication_outbox SET status='PENDING',acknowledged_at=NULL "
            "WHERE publication_id=?",
            ((identity,) for identity in identities),
        )

    def save_transfer_shadow(self, record: dict):
        self._require_transaction()
        self.connection.execute(
            "INSERT OR IGNORE INTO transfer_shadows("
            "shadow_id,cycle_id,validation_group,source_group,position_context,label_kind,horizon_bars,"
            "market_regime,started_at,source_cutoff_at,p,baseline,source_query_hash,"
            "sources_json,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(
                record[key]
                for key in (
                    "shadow_id",
                    "cycle_id",
                    "validation_group",
                    "source_group",
                    "position_context",
                    "label_kind",
                    "horizon_bars",
                    "market_regime",
                    "started_at",
                    "source_cutoff_at",
                    "p",
                    "baseline",
                    "source_query_hash",
                    "sources_json",
                    "status",
                )
            ),
        )

    def score_transfer_shadows(self, now: datetime) -> int:
        self._require_transaction()
        rows = self.connection.execute(
            "SELECT s.shadow_id,o.outcome_id,o.status,o.matured_at,o.return_pct "
            "FROM transfer_shadows s "
            "JOIN decisions d ON d.cycle_id=s.cycle_id AND d.portfolio_id='JEV_LEARNING' "
            "JOIN decision_outcomes o ON o.decision_id=d.decision_id AND o.label_kind=s.label_kind "
            "AND o.horizon_bars=s.horizon_bars WHERE s.status='PENDING' AND o.status!='PENDING' "
            "AND COALESCE(o.matured_at,o.evaluated_at)<?",
            (iso(now),),
        ).fetchall()
        for row in rows:
            valid = row["status"] == "MATURED"
            value = decimal(row["return_pct"]) if valid else None
            y = (1 if value > 0 else 0 if value < 0 else None) if value is not None else None
            status = "SCORED" if valid and y is not None else "NEUTRAL" if valid else "UNAVAILABLE"
            self.connection.execute(
                "UPDATE transfer_shadows SET status=?,outcome_id=?,matured_at=?,y=?,return_pct=? "
                "WHERE shadow_id=?",
                (
                    status,
                    row["outcome_id"],
                    row["matured_at"],
                    y,
                    row["return_pct"],
                    row["shadow_id"],
                ),
            )
        return len(rows)

    def transfer_shadows(self, group: str) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM transfer_shadows WHERE validation_group=?", (group,)
            )
        ]

    def transfer_state(self, group: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM transfer_states WHERE source_group=?", (group,)
        ).fetchone()
        return dict(row) if row else None

    def set_transfer_state(self, group: str, state: str, detail: dict, now: datetime):
        self._require_transaction()
        previous = self.transfer_state(group)
        self.connection.execute(
            "INSERT INTO transfer_states VALUES(?,?,?,?) ON CONFLICT(source_group) "
            "DO UPDATE SET state=excluded.state,detail_json=excluded.detail_json,"
            "updated_at=excluded.updated_at",
            (group, state, canonical_json(detail), iso(now)),
        )
        if previous is None or previous["state"] != state:
            identity = stable_id("transfer-state", group, state, iso(now))
            self.connection.execute(
                "INSERT INTO transfer_state_events VALUES(?,?,?,?,?)",
                (identity, group, state, canonical_json(detail), iso(now)),
            )
            self.event(
                "TRANSFER_STATE_CHANGED",
                {"source_group": group, "state": state, "detail": detail},
                now,
                identity,
            )

    def observations_to_register(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT d.*,c.candle_close_time FROM decisions d JOIN decision_cycles c "
            "ON d.cycle_id=c.cycle_id WHERE d.status='COMPLETED' AND NOT EXISTS "
            "(SELECT 1 FROM learning_registration r WHERE r.decision_id=d.decision_id)"
        ).fetchall()
        return [{**dict(row), "state": json.loads(row["state_json"])} for row in rows]

    def mark_learning_registration(self, decision_id: str, status: str, reason: str) -> None:
        self._require_transaction()
        self.connection.execute(
            "INSERT OR IGNORE INTO learning_registration VALUES(?,?,?)",
            (decision_id, status, reason),
        )

    def save_pending_outcome(self, record: dict) -> None:
        self._require_transaction()
        self.connection.execute(
            "INSERT OR IGNORE INTO decision_outcomes(outcome_id,decision_id,horizon_bars,"
            "label_kind,maturity_time,status,reference_json) VALUES(?,?,?,?,?,?,?)",
            (
                record["outcome_id"],
                record["decision_id"],
                record["horizon_bars"],
                record["label_kind"],
                record["maturity_time"],
                "PENDING",
                record["reference_json"],
            ),
        )

    def pending_outcomes(self, now: datetime) -> list[dict]:
        rows = self.connection.execute(
            "SELECT o.*,d.portfolio_id FROM decision_outcomes o JOIN decisions d "
            "ON o.decision_id=d.decision_id WHERE o.status='PENDING' AND o.maturity_time<=? "
            "ORDER BY o.maturity_time,o.outcome_id",
            (iso(now),),
        ).fetchall()
        return [{**dict(row), "reference": json.loads(row["reference_json"])} for row in rows]

    def first_maturity_quote(
        self, symbol: str, maturity: datetime, cutoff: datetime
    ) -> Quote | None:
        from datetime import timedelta

        rows = self.connection.execute(
            "SELECT quote_id FROM price_quotes WHERE symbol=? AND observed_at>=? "
            "AND observed_at<=? AND received_at<=? ORDER BY observed_at,received_at,quote_id",
            (symbol, iso(maturity), iso(maturity + timedelta(seconds=90)), iso(cutoff)),
        ).fetchall()
        for row in rows:
            quote = self.quote(row[0])
            if quote.fresh(quote.received_at, 30):
                return quote
        return None

    def save_learning_record(self, core: dict, origin: dict, available_at: datetime) -> None:
        self._require_transaction()
        content = canonical_json(core)
        existing = self.connection.execute(
            "SELECT core_json FROM learning_examples WHERE sample_id=?", (core["sample_id"],)
        ).fetchone()
        if existing and existing[0] != content:
            raise DomainError("Conflicting learning example identity")
        self.connection.execute(
            "INSERT OR IGNORE INTO learning_examples VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                core["sample_id"],
                content,
                core["symbol"],
                core["protocol_hash"],
                core["position_context"],
                core["label_kind"],
                core["horizon_bars"],
                core["market_regime"],
                core["rsi_bucket"],
                core["volume_bucket"],
                core["volatility_bucket"],
                core["decision_at"],
                core["maturity_time"],
                core["return_pct"],
                int(core["fixture"]),
            ),
        )
        identity = self.connection.execute(
            "SELECT sample_id,origin_json FROM learning_origins WHERE origin_id=?",
            (origin["origin_id"],),
        ).fetchone()
        if identity and (identity[0] != core["sample_id"] or identity[1] != canonical_json(origin)):
            raise DomainError("Conflicting origin identity")
        self.connection.execute(
            "INSERT OR IGNORE INTO learning_origins VALUES(?,?,?,?,?,?,?,?)",
            (
                origin["origin_id"],
                core["sample_id"],
                canonical_json(origin),
                origin["matured_at"],
                iso(available_at),
                origin["origin_run_id"],
                origin["decision_id"],
                origin["portfolio_id"],
            ),
        )

    def finish_outcome(
        self, outcome: dict, now: datetime, core: dict | None, origin: dict | None, reason: str
    ) -> None:
        self._require_transaction()
        if core is not None:
            self.save_learning_record(core, origin, now)
        self.connection.execute(
            "UPDATE decision_outcomes SET status=?,reason=?,exit_quote_id=?,matured_at=?,"
            "return_pct=?,evaluated_at=?,"
            "sample_id=? WHERE outcome_id=? AND status='PENDING'",
            (
                "MATURED" if core else "UNAVAILABLE",
                reason,
                core["exit_quote"]["quote_id"] if core else None,
                iso(now) if core else None,
                core["return_pct"] if core else None,
                iso(now),
                core["sample_id"] if core else None,
                outcome["outcome_id"],
            ),
        )
        self.event(
            "OUTCOME_MATURED" if core else "OUTCOME_UNAVAILABLE",
            {
                "outcome_id": outcome["outcome_id"],
                "sample_id": core["sample_id"] if core else None,
                "reason": reason,
            },
            now,
            stable_id("outcome-finished", outcome["outcome_id"]),
            portfolio_id=outcome["portfolio_id"],
        )

    def learning_records(self, cutoff: datetime | None = None) -> list[dict]:
        rows = self.connection.execute(
            "SELECT sample_id,core_json FROM learning_examples ORDER BY sample_id"
        ).fetchall()
        result = []
        for row in rows:
            query = "SELECT origin_json FROM learning_origins WHERE sample_id=?"
            params = [row["sample_id"]]
            if cutoff is not None:
                query += " AND matured_at<? AND available_at<?"
                params.extend([iso(cutoff), iso(cutoff)])
            origins = [json.loads(origin[0]) for origin in self.connection.execute(query, params)]
            if origins:
                result.append({"core": json.loads(row["core_json"]), "origins": origins})
        return result

    def save_ai_call(self, row: dict) -> None:
        self._require_transaction()
        response = json.loads(row["response_json"]) if row.get("response_json") else {}
        request = json.loads(row["request_json_sanitized"])
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        values = {
            "ai_call_id": row["ai_call_id"],
            "logical_request_id": row["logical_request_id"],
            "call_purpose": row["call_purpose"],
            "attempt_index": row["attempt_index"],
            "provider_generation_id": response.get("id"),
            "requested_model": request["model"],
            "actual_model": response.get("model"),
            "provider": response.get("provider"),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "latency_ms": int(
                (utc(row["finished_at"]) - utc(row["started_at"])).total_seconds() * 1000
            )
            if row["finished_at"]
            else None,
            "http_status": row["http_status"],
            "retries": row["attempt_index"] - 1,
            "request_json_sanitized": row["request_json_sanitized"],
            "response_json": row["response_json"],
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cost_usd": row["cost_usd"],
            "cost_source": row["cost_source"],
            "error_code": row["error_code"],
            "error_message_safe": row["error_code"],
            "status": row["status"],
        }
        columns = ",".join(values)
        updates = ",".join(f"{key}=excluded.{key}" for key in values if key != "ai_call_id")
        self.connection.execute(
            f"INSERT INTO ai_calls({columns}) VALUES({','.join('?' for _ in values)}) "
            f"ON CONFLICT(ai_call_id) DO UPDATE SET {updates}",
            tuple(values.values()),
        )

    @contextmanager
    def transaction(self):
        if self.connection.in_transaction:
            raise RuntimeError("Nested financial transactions are not permitted")
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def _require_transaction(self) -> None:
        if not self.connection.in_transaction:
            raise RuntimeError("State mutation requires an explicit unit of work")

    def run(self) -> dict[str, Any] | None:
        rows = self.connection.execute("SELECT record_json FROM runs").fetchall()
        if len(rows) > 1:
            raise DomainError("Multiple runs found in an isolated session database")
        return json.loads(rows[0][0]) if rows else None

    def create_session(
        self, record: dict[str, Any], initial_usdt: str, strategies: tuple[str, ...], now: datetime
    ) -> None:
        with self.transaction():
            if self.run():
                raise DomainError("Session already initialized")
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record["run_id"],
                    record["profile_id"],
                    record["profile_version"],
                    record["symbol"],
                    record["base_asset"],
                    record["quote_asset"],
                    record["config_hash"],
                    canonical_json(record["config"]),
                    canonical_json(record),
                    iso(now),
                    record["status"],
                    record["code_version"],
                ),
            )
            for strategy in strategies:
                wallet = Wallet(
                    strategy,
                    strategy,
                    decimal(initial_usdt),
                    decimal(initial_usdt),
                    peak_equity_usdt=decimal(initial_usdt),
                )
                data = asdict(wallet)
                data["run_id"] = record["run_id"]
                self.connection.execute(
                    f"INSERT INTO portfolios ({','.join(data)}) "
                    f"VALUES({','.join('?' for _ in data)})",
                    tuple(sql_value(v) for v in data.values()),
                )
                self.connection.execute(
                    "INSERT INTO ledger_entries VALUES(?,?,?,?,?,?,?,?)",
                    (
                        stable_id("initial", strategy),
                        strategy,
                        None,
                        "INITIAL_CAPITAL",
                        "USDT",
                        initial_usdt,
                        initial_usdt,
                        iso(now),
                    ),
                )
            self.event(
                "SESSION_PREPARED",
                {
                    "profile_id": record["profile_id"],
                    "symbol": record["symbol"],
                    "config_hash": record["config_hash"],
                },
                now,
                stable_id("prepared", record["run_id"]),
            )

    def wallet(self, portfolio_id: str) -> Wallet:
        row = self.connection.execute(
            "SELECT * FROM portfolios WHERE portfolio_id=?", (portfolio_id,)
        ).fetchone()
        if not row:
            raise DomainError("Unknown portfolio")
        data = {field.name: row[field.name] for field in fields(Wallet)}
        for name in WALLET_MONEY:
            if data[name] is not None:
                data[name] = decimal(data[name])
        if data["entry_at"]:
            data["entry_at"] = utc(data["entry_at"])
        return Wallet(**data)

    def wallets(self) -> list[Wallet]:
        return [
            self.wallet(row[0])
            for row in self.connection.execute(
                "SELECT portfolio_id FROM portfolios ORDER BY portfolio_id"
            ).fetchall()
        ]

    def latest_risk(self, portfolio_id: str) -> DailyRiskState | None:
        row = self.connection.execute(
            "SELECT * FROM daily_risk_states WHERE portfolio_id=? ORDER BY day_utc DESC LIMIT 1",
            (portfolio_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        for name in ("day_start_equity_usdt", "trigger_equity_usdt"):
            if data[name] is not None:
                data[name] = decimal(data[name])
        for name in ("baseline_observed_at", "guard_triggered_at", "blocked_until_utc"):
            if data[name]:
                data[name] = utc(data[name])
        return DailyRiskState(**data)

    def save_risk(self, state: DailyRiskState) -> None:
        self._require_transaction()
        data = asdict(state)
        updates = ",".join(
            f"{k}=excluded.{k}" for k in data if k not in ("portfolio_id", "day_utc")
        )
        self.connection.execute(
            f"INSERT INTO daily_risk_states({','.join(data)}) "
            f"VALUES({','.join('?' for _ in data)}) "
            f"ON CONFLICT(portfolio_id,day_utc) DO UPDATE SET {updates}",
            tuple(sql_value(v) for v in data.values()),
        )

    def save_quote(self, quote: Quote) -> bool:
        self._require_transaction()
        data = asdict(quote)
        values = tuple(sql_value(v) for v in data.values())
        existing = self.connection.execute(
            "SELECT * FROM price_quotes WHERE quote_id=?", (quote.quote_id,)
        ).fetchone()
        if existing:
            if any(existing[k] != sql_value(v) for k, v in data.items()):
                raise DomainError("Conflicting quote identity")
            return False
        self.connection.execute(
            f"INSERT INTO price_quotes({','.join(data)}) VALUES({','.join('?' for _ in data)})",
            values,
        )
        return True

    def command(self, key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM paper_orders WHERE idempotency_key=?", (key,)
        ).fetchone()
        if not row:
            return None
        fill = self.connection.execute(
            "SELECT * FROM paper_fills WHERE order_id=?", (row["order_id"],)
        ).fetchone()
        result = dict(row)
        if fill:
            data = dict(fill)
            for name in FILL_MONEY:
                if data[name] is not None:
                    data[name] = decimal(data[name])
            data["side"] = Action(data["side"])
            data["filled_at"] = utc(data["filled_at"])
            result["fill"] = Fill(**data)
        else:
            result["fill"] = None
        return result

    def record_trade(self, trade: TradeResult, fingerprint: str) -> None:
        self._require_transaction()
        fill, wallet = trade.fill, trade.wallet
        self.connection.execute(
            "INSERT INTO paper_orders(order_id,portfolio_id,action,trigger,status,reason,"
            "idempotency_key,fingerprint,cycle_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                fill.order_id,
                fill.portfolio_id,
                fill.side.value,
                fill.trigger,
                "FILLED",
                fill.trigger,
                fill.idempotency_key,
                fingerprint,
                fill.cycle_id,
                iso(fill.filled_at),
            ),
        )
        data = asdict(fill)
        self.connection.execute(
            f"INSERT INTO paper_fills({','.join(data)}) VALUES({','.join('?' for _ in data)})",
            tuple(sql_value(v) for v in data.values()),
        )
        self._save_wallet(wallet, wallet.version - 1)
        base_asset = self.run()["base_asset"]
        base_delta = fill.qty_base if fill.side == Action.BUY else -fill.qty_base
        for asset, amount, balance in (
            ("USDT", fill.net_cash_delta_usdt, wallet.cash_usdt),
            (base_asset, base_delta, wallet.base_qty),
        ):
            self.connection.execute(
                "INSERT INTO ledger_entries VALUES(?,?,?,?,?,?,?,?)",
                (
                    stable_id(fill.fill_id, asset),
                    wallet.portfolio_id,
                    fill.fill_id,
                    "FILL_" + fill.side.value,
                    asset,
                    str(amount),
                    str(balance),
                    iso(fill.filled_at),
                ),
            )
        self.event(
            "PAPER_ORDER_FILLED",
            asdict(fill),
            fill.filled_at,
            fill.fill_id,
            wallet.portfolio_id,
            fill.cycle_id,
        )
        if fill.side == Action.SELL:
            self.event(
                "POSITION_CLOSED",
                {
                    "fill_id": fill.fill_id,
                    "trigger": fill.trigger,
                    "realized_pnl_usdt": fill.realized_pnl_usdt,
                },
                fill.filled_at,
                stable_id("closed", fill.fill_id),
                wallet.portfolio_id,
                fill.cycle_id,
            )

    def _save_wallet(self, wallet: Wallet, expected_version: int) -> None:
        data = asdict(wallet)
        data.pop("portfolio_id")
        cursor = self.connection.execute(
            f"UPDATE portfolios SET {','.join(k + '=?' for k in data)} "
            "WHERE portfolio_id=? AND version=?",
            (*[sql_value(v) for v in data.values()], wallet.portfolio_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise DomainError("Concurrent portfolio modification")

    def reject(
        self,
        portfolio_id: str,
        action: str,
        key: str,
        fingerprint: str,
        cycle_id: str,
        reason: str,
        now: datetime,
    ) -> None:
        self._require_transaction()
        self.connection.execute(
            "INSERT INTO paper_orders(order_id,portfolio_id,action,trigger,status,reason,"
            "idempotency_key,fingerprint,cycle_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                stable_id("order", key),
                portfolio_id,
                action,
                reason,
                "REJECTED",
                reason,
                key,
                fingerprint,
                cycle_id,
                iso(now),
            ),
        )
        self.event(
            "PAPER_ORDER_REJECTED",
            {"action": action, "reason_code": reason},
            now,
            stable_id("rejected", key),
            portfolio_id,
            cycle_id,
        )

    def mark(self, wallet: Wallet, quote: Quote, now: datetime, persist: bool = True) -> Wallet:
        self._require_transaction()
        with localcontext() as ctx:
            ctx.prec = 50
            equity = wallet.equity(quote.bid)
            peak = max(wallet.peak_equity_usdt, equity)
            drawdown = max(Decimal(0), (peak - equity) / peak * 100) if peak > 0 else Decimal(0)
            wallet = replace(
                wallet,
                peak_equity_usdt=peak,
                max_drawdown_pct=max(wallet.max_drawdown_pct, drawdown),
            )
            self._save_wallet(wallet, wallet.version)
            if not persist:
                return wallet
            snapshot_id = stable_id("snapshot", wallet.portfolio_id, quote.quote_id, wallet.version)
            self.connection.execute(
                "INSERT OR IGNORE INTO portfolio_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    snapshot_id,
                    wallet.portfolio_id,
                    iso(now),
                    quote.quote_id,
                    str(wallet.cash_usdt),
                    str(wallet.base_qty),
                    str(equity),
                    str(wallet.realized_pnl_usdt),
                    str(wallet.base_qty * quote.bid - wallet.base_cost_basis_usdt),
                    str(drawdown),
                ),
            )
            self.event(
                "PORTFOLIO_MARKED",
                {"equity_usdt": equity, "quote_id": quote.quote_id, "drawdown_pct": drawdown},
                now,
                snapshot_id,
                wallet.portfolio_id,
            )
            return wallet

    def event(
        self,
        event_type: str,
        data: dict[str, Any],
        now: datetime,
        identity: str,
        portfolio_id: str | None = None,
        cycle_id: str | None = None,
    ) -> None:
        self._require_transaction()
        run = self.run()
        if not run:
            raise DomainError("Session not initialized")
        payload = canonical_json(data)
        existing = self.connection.execute(
            "SELECT * FROM events WHERE event_id=?", (identity,)
        ).fetchone()
        if existing:
            if existing["event_type"] != event_type or existing["data_json"] != payload:
                raise DomainError("Conflicting event identity")
            return
        self.connection.execute(
            "INSERT INTO events(event_id,occurred_at,event_type,run_id,portfolio_id,cycle_id,"
            "data_json,schema_version) VALUES(?,?,?,?,?,?,?,1)",
            (identity, iso(now), event_type, run["run_id"], portfolio_id, cycle_id, payload),
        )

    def events(self, after_seq: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM events WHERE event_seq>? ORDER BY event_seq LIMIT ?",
            (after_seq, min(max(limit, 1), 10000)),
        ).fetchall()
        return [
            {
                "schema_version": r["schema_version"],
                "event_id": r["event_id"],
                "event_seq": r["event_seq"],
                "ts": r["occurred_at"],
                "run_id": r["run_id"],
                "portfolio_id": r["portfolio_id"],
                "cycle_id": r["cycle_id"],
                "event_type": r["event_type"],
                "data": json.loads(r["data_json"]),
            }
            for r in rows
        ]

    def audit(self) -> dict[str, Any]:
        owns_snapshot = not self.connection.in_transaction
        if owns_snapshot:
            self.connection.execute("BEGIN")
        try:
            return self._audit_snapshot()
        finally:
            if owns_snapshot:
                self.connection.rollback()

    def _audit_snapshot(self) -> dict[str, Any]:
        errors = []
        run = self.run()
        if not run:
            return {"ok": False, "errors": ["No initialized session"]}
        with localcontext() as ctx:
            ctx.prec = 50
            for wallet in self.wallets():
                for asset, expected in (
                    ("USDT", wallet.cash_usdt),
                    (run["base_asset"], wallet.base_qty),
                ):
                    rows = self.connection.execute(
                        "SELECT amount,balance_after FROM ledger_entries WHERE portfolio_id=? "
                        "AND asset=? ORDER BY rowid",
                        (wallet.portfolio_id, asset),
                    ).fetchall()
                    total = sum((decimal(r["amount"]) for r in rows), Decimal(0))
                    if total != expected or (
                        rows and decimal(rows[-1]["balance_after"]) != expected
                    ):
                        errors.append(f"Ledger mismatch: {wallet.portfolio_id}/{asset}")
            for fill in self.connection.execute("SELECT fill_id FROM paper_fills").fetchall():
                entries = self.connection.execute(
                    "SELECT COUNT(*) FROM ledger_entries WHERE fill_id=?", (fill["fill_id"],)
                ).fetchone()[0]
                event = self.connection.execute(
                    "SELECT 1 FROM events WHERE event_id=?", (fill["fill_id"],)
                ).fetchone()
                if entries != 2 or not event:
                    errors.append("Incomplete fill transaction: " + fill["fill_id"])
        if self.connection.execute("PRAGMA foreign_key_check").fetchall():
            errors.append("Foreign key violation")
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            errors.append("SQLite integrity failure")
        return {
            "ok": not errors,
            "errors": errors,
            "run_id": run["run_id"],
            "fill_count": self.connection.execute("SELECT COUNT(*) FROM paper_fills").fetchone()[0],
        }

    def quote(self, quote_id: str) -> Quote | None:
        row = self.connection.execute(
            "SELECT * FROM price_quotes WHERE quote_id=?", (quote_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        for name in ("bid", "ask", "bid_qty", "ask_qty"):
            if data[name] is not None:
                data[name] = decimal(data[name])
        for name in ("observed_at", "received_at", "event_at", "request_started_at"):
            if data[name] is not None:
                data[name] = utc(data[name])
        return Quote(**data)

    def save_candle(self, candle: Candle) -> bool:
        self._require_transaction()
        if not candle.is_closed:
            return False
        key = (candle.symbol, candle.interval, iso(candle.open_time))
        row = self.connection.execute(
            "SELECT * FROM candles WHERE symbol=? AND interval=? AND open_time_utc=?", key
        ).fetchone()
        if row:
            same = all(
                decimal(row[n]) == getattr(candle, n)
                for n in ("open", "high", "low", "close", "volume")
            )
            if not same or row["close_time_exclusive_utc"] != iso(candle.close_time_exclusive):
                raise DomainError("Conflicting finalized candle")
            return False
        self.connection.execute(
            "INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                *key,
                iso(candle.close_time_exclusive),
                *[str(getattr(candle, n)) for n in ("open", "high", "low", "close", "volume")],
                iso(candle.available_at),
                candle.source,
            ),
        )
        return True

    def candles(self, symbol: str, interval: str, limit: int = 1000) -> list[Candle]:
        rows = self.connection.execute(
            "SELECT * FROM candles WHERE symbol=? AND interval=? "
            "ORDER BY open_time_utc DESC LIMIT ?",
            (symbol, interval, min(max(limit, 1), 10000)),
        ).fetchall()
        return [
            Candle(
                r["symbol"],
                r["interval"],
                utc(r["open_time_utc"]),
                utc(r["close_time_exclusive_utc"]),
                *[decimal(r[n]) for n in ("open", "high", "low", "close", "volume")],
                utc(r["available_at"]),
                r["source"],
            )
            for r in reversed(rows)
        ]

    def cycle(self, cycle_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM decision_cycles WHERE cycle_id=?", (cycle_id,)
        ).fetchone()
        return dict(row) if row else None

    def start_cycle(
        self,
        cycle_id: str,
        candle: Candle,
        started_at: datetime,
        features: dict[str, Any],
        wallets: list[Wallet],
    ) -> bool:
        self._require_transaction()
        if self.cycle(cycle_id) is not None:
            return False
        run = self.run()
        snapshot_id = stable_id("snapshot", cycle_id)
        quality = "VALID" if features["valid"] else features["reason"]
        self.connection.execute(
            "INSERT INTO market_snapshots VALUES(?,?,?,?,?,?,?,?,?)",
            (
                snapshot_id,
                run["run_id"],
                candle.symbol,
                iso(candle.open_time),
                iso(started_at),
                canonical_json(features),
                canonical_json([asdict(w) for w in wallets]),
                features["feature_version"],
                quality,
            ),
        )
        self.connection.execute(
            "INSERT INTO decision_cycles VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                cycle_id,
                run["run_id"],
                candle.symbol,
                iso(candle.open_time),
                iso(candle.close_time_exclusive),
                "STARTED",
                iso(started_at),
                None,
                snapshot_id,
                None,
                quality,
            ),
        )
        self.event(
            "DECISION_CYCLE_STARTED",
            {"snapshot_id": snapshot_id, "data_status": quality},
            started_at,
            stable_id("cycle-started", cycle_id),
            cycle_id=cycle_id,
        )
        return True

    def save_proposal(
        self,
        cycle_id: str,
        wallet: Wallet,
        proposal: Proposal,
        started_at: datetime,
        finished_at: datetime,
        state: dict[str, Any],
    ) -> str:
        self._require_transaction()
        cycle = self.cycle(cycle_id)
        if not cycle:
            raise DomainError("Missing decision cycle")
        decision_id = stable_id("decision", cycle_id, wallet.portfolio_id)
        self.connection.execute(
            "INSERT INTO decisions(decision_id,cycle_id,portfolio_id,snapshot_id,ai_call_id,"
            "proposed_action,approved_action,executed_action,probabilities_json,confidence,"
            "reason_code,memory_json,state_json,decision_started_at,decision_at,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision_id,
                cycle_id,
                wallet.portfolio_id,
                cycle["snapshot_id"],
                proposal.ai_call_id,
                (proposal.proposed_action or proposal.action).value,
                "HOLD",
                "HOLD",
                canonical_json(proposal.probabilities)
                if proposal.probabilities is not None
                else None,
                str(proposal.confidence) if proposal.confidence is not None else None,
                proposal.reason,
                canonical_json(proposal.feedback) if proposal.feedback else None,
                canonical_json(state),
                iso(started_at),
                iso(finished_at),
                "PROPOSED",
            ),
        )
        return decision_id

    def complete_decision(
        self,
        decision_id: str,
        proposed: str,
        approved: str,
        executed: str,
        reason: str,
        quote_id: str | None,
        order_id: str | None = None,
    ) -> None:
        self._require_transaction()
        row = self.connection.execute(
            "SELECT * FROM decisions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if not row or row["proposed_action"] != proposed:
            raise DomainError("Missing or conflicting decision")
        self.connection.execute(
            "UPDATE decisions SET approved_action=?,executed_action=?,reason_code=?,"
            "decision_price_quote_id=?,status='COMPLETED' WHERE decision_id=?",
            (approved, executed, reason, quote_id, decision_id),
        )
        if order_id:
            cursor = self.connection.execute(
                "UPDATE paper_orders SET decision_id=? WHERE order_id=? AND portfolio_id=?",
                (decision_id, order_id, row["portfolio_id"]),
            )
            if cursor.rowcount != 1:
                raise DomainError("Order does not belong to decision portfolio")
        if quote_id:
            self.connection.execute(
                "UPDATE decision_cycles SET execution_quote_id=? WHERE cycle_id=?",
                (quote_id, row["cycle_id"]),
            )
        self.event(
            "DECISION_RECORDED",
            {
                "decision_id": decision_id,
                "proposed_action": proposed,
                "approved_action": approved,
                "executed_action": executed,
                "reason_code": reason,
                "quote_id": quote_id,
                "ai_call_id": row["ai_call_id"],
            },
            utc(row["decision_at"]),
            stable_id("decision-recorded", decision_id),
            row["portfolio_id"],
            row["cycle_id"],
        )

    def finish_cycle(self, cycle_id: str, now: datetime, status: str = "COMPLETED") -> None:
        self._require_transaction()
        self.connection.execute(
            "UPDATE decision_cycles SET status=?,ended_at=? WHERE cycle_id=?",
            (status, iso(now), cycle_id),
        )

    def recover_cycles(self, now: datetime) -> int:
        self._require_transaction()
        rows = self.connection.execute(
            "SELECT cycle_id FROM decision_cycles WHERE status='STARTED'"
        ).fetchall()
        for row in rows:
            self.finish_cycle(row["cycle_id"], now, "INTERRUPTED")
            self.event(
                "MISSED_DECISION_WINDOW",
                {"reason": "CRASH_DURING_CYCLE"},
                now,
                stable_id("interrupted", row["cycle_id"]),
                cycle_id=row["cycle_id"],
            )
        return len(rows)

    def runtime_state(
        self, name: str, value: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if value is not None:
            self._require_transaction()
            self.connection.execute(
                "INSERT INTO runtime_state VALUES(?,?) ON CONFLICT(name) "
                "DO UPDATE SET value_json=excluded.value_json",
                (name, canonical_json(value)),
            )
        row = self.connection.execute(
            "SELECT value_json FROM runtime_state WHERE name=?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def set_run_status(self, status: str, now: datetime) -> None:
        self._require_transaction()
        run = self.run()
        run["status"] = status
        run["status_updated_at"] = iso(now)
        self.connection.execute(
            "UPDATE runs SET status=?,record_json=? WHERE run_id=?",
            (status, canonical_json(run), run["run_id"]),
        )


class SQLiteStorage:
    def open(self, path: Path, create: bool = False) -> SessionDatabase:
        return SessionDatabase(path, create=create)

    def prepare_initial_learning(self, store: SessionDatabase, path: Path, now: datetime) -> None:
        from poc.adapters.outbound.datasets import DatasetFiles

        importer = DatasetFiles(store)
        if importer.imported():
            return  # Restore the accepted SQLite contents; never re-read the source file.
        importer.import_path(path, now)

    @contextmanager
    def lease(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DomainError("Session is already owned by another engine") from exc
            try:
                file.seek(0)
                file.truncate()
                file.write(str(os.getpid()))
                file.flush()
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)
