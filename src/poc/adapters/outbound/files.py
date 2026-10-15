"""Reconstructible JSONL and atomic JSON/CSV publication."""

import csv
import json
import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from poc.adapters.outbound.sqlite import SessionDatabase, SQLiteStorage
from poc.domain.external import context_at
from poc.domain.primitives import canonical_json, decimal, iso, utc


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class FileExporter:
    def __init__(self, database: SessionDatabase):
        self.db = database
        self.record = database.run()
        original = Path(self.record["paths"]["sqlite"]).parent
        current = database.path.resolve().parent
        self.logs = current / Path(self.record["paths"]["logs"]).relative_to(original)
        self.exports = current / Path(self.record["paths"]["exports"]).relative_to(original)

    def events(self, rebuild: bool = False) -> int:
        # One projection writer per session, independent of the financial engine lease.
        with SQLiteStorage().lease(self.logs / "projection.lock"):
            for path in self.logs.glob("*/events.jsonl"):
                with path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    if stream.tell():
                        stream.seek(-1, os.SEEK_END)
                        if stream.read(1) != b"\n":
                            rebuild = True
            return self._events_unlocked(rebuild)

    def _events_unlocked(self, rebuild: bool = False) -> int:
        row = self.db.connection.execute(
            "SELECT last_event_seq FROM export_cursors WHERE export_name='jsonl'"
        ).fetchone()
        cursor = row[0] if row and not rebuild else 0
        events = []
        # Establish an upper watermark; concurrent new events remain for the next projection.
        upper = self.db.connection.execute(
            "SELECT COALESCE(MAX(event_seq),0) FROM events"
        ).fetchone()[0]
        while cursor < upper:
            batch = [e for e in self.db.events(cursor, 10000) if e["event_seq"] <= upper]
            if not batch:
                break
            events.extend(batch)
            cursor = batch[-1]["event_seq"]
        by_day: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            day = utc(event["ts"]).date().isoformat()
            by_day.setdefault(day, []).append(event)
        for day, items in by_day.items():
            path = self.logs / day / "events.jsonl"
            text = "".join(canonical_json(e) + "\n" for e in items)
            if rebuild:
                atomic_write(path, text)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
        with self.db.transaction():
            self.db.connection.execute(
                "INSERT INTO export_cursors VALUES('jsonl',?,?) ON CONFLICT(export_name) "
                "DO UPDATE SET last_event_seq=excluded.last_event_seq,"
                "updated_at=excluded.updated_at",
                (upper, iso(datetime.now(UTC))),
            )
        return len(events)

    def dashboard(self) -> dict[str, Any]:
        owns_snapshot = not self.db.connection.in_transaction
        if owns_snapshot:
            self.db.connection.execute("BEGIN")
        try:
            record = self.db.run()
            quote = self.db.connection.execute(
                "SELECT * FROM price_quotes ORDER BY observed_at DESC,quote_id DESC LIMIT 1"
            ).fetchone()
            portfolios = []
            for wallet in self.db.wallets():
                snapshot = self.db.connection.execute(
                    "SELECT * FROM portfolio_snapshots WHERE portfolio_id=? "
                    "ORDER BY recorded_at DESC,rowid DESC LIMIT 1",
                    (wallet.portfolio_id,),
                ).fetchone()
                equity = decimal(snapshot["equity_usdt"]) if snapshot else wallet.cash_usdt
                closed = self.db.connection.execute(
                    "SELECT realized_pnl_usdt FROM paper_fills "
                    "WHERE portfolio_id=? AND side='SELL'",
                    (wallet.portfolio_id,),
                ).fetchall()
                pnl = [decimal(r[0]) for r in closed]
                portfolios.append(
                    {
                        "id": wallet.portfolio_id,
                        "initial_usdt": str(wallet.initial_usdt),
                        "cash_usdt": str(wallet.cash_usdt),
                        "base_qty": str(wallet.base_qty),
                        "entry_fill_price": str(wallet.entry_fill_price)
                        if wallet.entry_fill_price is not None
                        else None,
                        "entry_at": iso(wallet.entry_at) if wallet.entry_at else None,
                        "equity_usdt": str(equity),
                        "realized_pnl_usdt": str(wallet.realized_pnl_usdt),
                        "unrealized_pnl_usdt": snapshot["unrealized_pnl"]
                        if snapshot
                        else ("0" if not wallet.has_position else None),
                        "return_pct": str((equity / wallet.initial_usdt - 1) * 100),
                        "max_drawdown_pct": str(wallet.max_drawdown_pct),
                        "closed_trades": len(closed),
                        "win_rate_pct": str(Decimal(sum(v > 0 for v in pnl)) / len(pnl) * 100)
                        if pnl
                        else None,
                        "risk": as_risk(self.db.latest_risk(wallet.portfolio_id)),
                    }
                )
            series = []
            for portfolio in portfolios:
                series.extend(
                    dict(row)
                    for row in self.db.connection.execute(
                        "SELECT portfolio_id,recorded_at,equity_usdt "
                        "FROM portfolio_snapshots WHERE portfolio_id=? "
                        "ORDER BY recorded_at DESC LIMIT 500",
                        (portfolio["id"],),
                    )
                )
            series.sort(key=lambda row: (row["recorded_at"], row["portfolio_id"]))
            candles = [
                dict(row)
                for row in self.db.connection.execute(
                    "SELECT open_time_utc,close_time_exclusive_utc,open,high,low,close,volume "
                    "FROM candles WHERE symbol=? AND interval=? "
                    "AND close_time_exclusive_utc<=? AND available_at<=? "
                    "ORDER BY open_time_utc DESC LIMIT 200",
                    (
                        record["symbol"],
                        record["config"]["market"]["interval"],
                        iso(datetime.now(UTC)),
                        iso(datetime.now(UTC)),
                    ),
                )
            ]
            candles.reverse()
            fills = [
                dict(r)
                for r in self.db.connection.execute(
                    "SELECT * FROM paper_fills ORDER BY filled_at DESC LIMIT 20"
                ).fetchall()
            ]
            watermark = self.db.connection.execute(
                "SELECT COALESCE(MAX(event_seq),0) FROM events"
            ).fetchone()[0]
            calls = [
                dict(row)
                for row in self.db.connection.execute(
                    "SELECT ai_call_id,call_purpose,actual_model,cost_usd,cost_source,"
                    "status,started_at "
                    "FROM ai_calls"
                )
            ]
            daily_budget = None
            ai_settings = record["config"]["ai"]
            if ai_settings.get("budget_scope") == "SESSION":
                day = datetime.now(UTC).date()
                today = [r for r in calls if utc(r["started_at"]).date() == day]
                daily_cost = sum(
                    (decimal(r["cost_usd"]) for r in today if r["cost_usd"] is not None),
                    Decimal(0),
                )
                daily_budget = {
                    "scope": "SESSION",
                    "day_utc": day.isoformat(),
                    "max_calls_per_day": ai_settings["max_calls_per_day"],
                    "cost_limit_enabled": ai_settings["cost_limit_enabled"],
                    "max_observed_cost_usd_per_day": ai_settings["max_observed_cost_usd_per_day"],
                    "physical_attempts": len(today),
                    "observed_cost_usd": str(daily_cost),
                    "unknown_cost_calls": sum(r["cost_usd"] is None for r in today),
                }
            decisions = [
                dict(row)
                for row in self.db.connection.execute(
                    "SELECT * FROM decisions ORDER BY decision_at DESC LIMIT 20"
                )
            ]
            outcome_counts = {
                row[0]: row[1]
                for row in self.db.connection.execute(
                    "SELECT status,COUNT(*) FROM decision_outcomes GROUP BY status"
                )
            }
            examples = self.db.connection.execute(
                "SELECT COUNT(*),COALESCE(SUM(fixture),0) FROM learning_examples"
            ).fetchone()
            imported = [
                dict(row)
                for row in self.db.connection.execute(
                    "SELECT dataset_id,file_hash,imported_at,sample_count,status "
                    "FROM dataset_imports"
                )
            ]
            associated = {}
            coverage = {}
            for portfolio in portfolios:
                rows = self.db.connection.execute(
                    "SELECT ai_call_id,state_json,memory_json,proposed_action,executed_action,"
                    "reason_code "
                    "FROM decisions WHERE portfolio_id=?",
                    (portfolio["id"],),
                ).fetchall()
                references = set()
                with_memory = 0
                for row in rows:
                    if row["ai_call_id"]:
                        references.add(row["ai_call_id"])
                    state = json.loads(row["state_json"])
                    for section in ("news", "prediction_markets"):
                        for factor in state.get(section, {}).get("items", []):
                            if factor.get("ai_call_id"):
                                references.add(factor["ai_call_id"])
                    if state.get("historical_feedback", {}).get("status") == "available":
                        with_memory += 1
                associated[portfolio["id"]] = sorted(references)
                coverage[portfolio["id"]] = {
                    "decisions": len(rows),
                    "with_memory": with_memory,
                    "ai_failure_or_budget_holds": sum(
                        row["executed_action"] == "HOLD"
                        and row["reason_code"].startswith(
                            ("AI_", "INVALID_AI", "INVALID_CONTEXT", "EXTERNAL_CONTEXT", "ENTRY_")
                        )
                        for row in rows
                    ),
                }
            returns = {p["id"]: decimal(p["return_pct"]) for p in portfolios}
            return {
                "schema_version": 1,
                "generated_at": iso(datetime.now(UTC)),
                "run_id": record["run_id"],
                "profile_id": record["profile_id"],
                "profile_version": record["profile_version"],
                "event_watermark": watermark,
                "mode": "PAPER_ONLY",
                "health": self.db.runtime_state("engine"),
                "external_context": context_at(
                    self.db.external_context(datetime.now(UTC)), datetime.now(UTC)
                ),
                "fixture": record["market_metadata"]["raw"].get("fixture", False),
                "market": {
                    "symbol": record["symbol"],
                    "base_asset": record["base_asset"],
                    "quote_asset": record["quote_asset"],
                    "last_price_usdt": quote["bid"] if quote else None,
                    "quote_observed_at": quote["observed_at"] if quote else None,
                },
                "portfolios": portfolios,
                "recent_fills": fills,
                "equity_series": series,
                "chart_candles": candles,
                "chart_scope": {
                    "interval": record["config"]["market"]["interval"],
                    "max_candles": 200,
                    "max_equity_points_per_portfolio": 500,
                },
                "recent_decisions": decisions,
                "profile": {
                    "profile_id": record["profile_id"],
                    "version": record["profile_version"],
                    "style": record["config"]
                    .get("profile_definition", {})
                    .get("profile", {})
                    .get("style", "LEGACY"),
                    "interval": record["config"]["market"]["interval"],
                    "trend_interval": record["config"]["market"]["trend_interval"],
                },
                "opportunity_admission": self.db.runtime_state("profile_admission"),
                "learning": {
                    "version": "memory_v1",
                    "outcomes": outcome_counts,
                    "archived_unique_examples": examples[0],
                    "fixture_examples_excluded": examples[1],
                    "origin_links": self.db.connection.execute(
                        "SELECT COUNT(*) FROM learning_origins"
                    ).fetchone()[0],
                    "initial_datasets": imported,
                    "transfer": {
                        "states": [
                            dict(row)
                            for row in self.db.connection.execute(
                                "SELECT * FROM transfer_states ORDER BY source_group"
                            )
                        ],
                        "shadow_counts": {
                            row[0]: row[1]
                            for row in self.db.connection.execute(
                                "SELECT status,COUNT(*) FROM transfer_shadows GROUP BY status"
                            )
                        },
                        "publication_counts": {
                            row[0]: row[1]
                            for row in self.db.connection.execute(
                                "SELECT status,COUNT(*) FROM learning_publication_outbox "
                                "GROUP BY status"
                            )
                        },
                    },
                    "temporal_dependence": (
                        "Consecutive candle labels may overlap; unique count "
                        "is not independent sample size."
                    ),
                },
                "strategy_comparison": {
                    "b_minus_a_return_pp": str(
                        returns["JEV_STATIC"] - returns["BASELINE_TECHNICAL"]
                    ),
                    "c_minus_b_return_pp": str(returns["JEV_LEARNING"] - returns["JEV_STATIC"]),
                    "coverage": coverage,
                    "interpretation": (
                        "Observed paper return differences; no causal or profitability claim."
                    ),
                    "c_treatment": (
                        "Initial/local memory plus any separately validated transfer; "
                        "inspect each decision."
                    ),
                },
                "ai_cost": {
                    "daily_budget": daily_budget,
                    "currency": "USD",
                    "scope": "physical_calls_for_this_session",
                    "total_api_cost_actual": str(
                        sum(
                            (
                                decimal(row["cost_usd"])
                                for row in calls
                                if row["cost_usd"] is not None
                            ),
                            Decimal(0),
                        )
                    ),
                    "physical_calls": len(calls),
                    "unknown_cost_calls": sum(row["cost_usd"] is None for row in calls),
                    "associated_calls_by_strategy": associated,
                    "associated_cost_note": (
                        "References can be shared; never sum them as additional physical charges."
                    ),
                },
            }
        finally:
            if owns_snapshot:
                self.db.connection.rollback()

    def publish(self) -> dict[str, Any]:
        self.events()
        dashboard = self.dashboard()
        atomic_write(self.exports / "dashboard-latest.json", canonical_json(dashboard) + "\n")
        tables = {
            "fills.csv": "paper_fills",
            "portfolio_equity.csv": "portfolio_snapshots",
            "ledger.csv": "ledger_entries",
            "decisions.csv": "decisions",
            "ai_calls.csv": "ai_calls",
            "decision_outcomes.csv": "decision_outcomes",
            "transfer_shadows.csv": "transfer_shadows",
            "transfer_states.csv": "transfer_states",
        }
        for name, table in tables.items():
            rows = self.db.connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
            columns = [
                r[1] for r in self.db.connection.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            self.exports.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="." + name, dir=self.exports)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["schema_version", *columns])
                    writer.writerows([1, *tuple(r)] for r in rows)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.exports / name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return dashboard


def as_risk(state: Any) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "day_utc": state.day_utc,
        "day_start_equity_usdt": str(state.day_start_equity_usdt)
        if state.day_start_equity_usdt
        else None,
        "blocked_until_utc": iso(state.blocked_until_utc) if state.blocked_until_utc else None,
        "pending_exit_reason": state.pending_exit_reason,
    }
