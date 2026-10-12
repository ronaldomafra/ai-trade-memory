BEGIN IMMEDIATE;
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE runs(
  run_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, profile_version TEXT NOT NULL,
  symbol TEXT NOT NULL, base_asset TEXT NOT NULL, quote_asset TEXT NOT NULL,
  config_hash TEXT NOT NULL, config_json TEXT NOT NULL, record_json TEXT NOT NULL,
  created_at TEXT NOT NULL, status TEXT NOT NULL, code_version TEXT NOT NULL
);
CREATE TABLE portfolios(
  portfolio_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
  strategy_type TEXT NOT NULL, initial_usdt TEXT NOT NULL, cash_usdt TEXT NOT NULL,
  base_qty TEXT NOT NULL, base_cost_basis_usdt TEXT NOT NULL, realized_pnl_usdt TEXT NOT NULL,
  entry_fill_price TEXT, entry_at TEXT, peak_equity_usdt TEXT NOT NULL,
  max_drawdown_pct TEXT NOT NULL, last_exit_cycle_id TEXT, version INTEGER NOT NULL
);
CREATE TABLE price_quotes(
  quote_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, bid TEXT NOT NULL, ask TEXT NOT NULL,
  observed_at TEXT NOT NULL, received_at TEXT NOT NULL, source TEXT NOT NULL, event_at TEXT
);
CREATE INDEX quote_time ON price_quotes(symbol,observed_at);
CREATE TABLE daily_risk_states(
  portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id), day_utc TEXT NOT NULL,
  day_start_equity_usdt TEXT, baseline_observed_at TEXT, baseline_quote_id TEXT,
  guard_triggered_at TEXT, trigger_equity_usdt TEXT, trigger_quote_id TEXT,
  blocked_until_utc TEXT, pending_exit_reason TEXT,
  PRIMARY KEY(portfolio_id,day_utc)
);
CREATE TABLE paper_orders(
  order_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
  action TEXT NOT NULL, trigger TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
  idempotency_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
  cycle_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE paper_fills(
  fill_id TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL REFERENCES paper_orders(order_id),
  portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
  quote_id TEXT NOT NULL REFERENCES price_quotes(quote_id), filled_at TEXT NOT NULL,
  side TEXT NOT NULL, qty_base TEXT NOT NULL, fill_price TEXT NOT NULL,
  gross_usdt TEXT NOT NULL, fee_usdt TEXT NOT NULL, net_cash_delta_usdt TEXT NOT NULL,
  slippage_pct TEXT NOT NULL, realized_pnl_usdt TEXT, trigger TEXT NOT NULL,
  cycle_id TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL,
  observed_bid TEXT NOT NULL, observed_ask TEXT NOT NULL
);
CREATE TABLE ledger_entries(
  ledger_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
  fill_id TEXT REFERENCES paper_fills(fill_id), event_type TEXT NOT NULL, asset TEXT NOT NULL,
  amount TEXT NOT NULL, balance_after TEXT NOT NULL, recorded_at TEXT NOT NULL,
  UNIQUE(fill_id,asset,event_type)
);
CREATE TABLE portfolio_snapshots(
  snapshot_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
  recorded_at TEXT NOT NULL, quote_id TEXT NOT NULL REFERENCES price_quotes(quote_id),
  cash_usdt TEXT NOT NULL, base_qty TEXT NOT NULL, equity_usdt TEXT NOT NULL,
  realized_pnl TEXT NOT NULL, unrealized_pnl TEXT NOT NULL, drawdown_pct TEXT NOT NULL
);
CREATE TABLE events(
  event_seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
  occurred_at TEXT NOT NULL, event_type TEXT NOT NULL, run_id TEXT NOT NULL,
  portfolio_id TEXT, cycle_id TEXT, data_json TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE export_cursors(export_name TEXT PRIMARY KEY,last_event_seq INTEGER NOT NULL,updated_at TEXT NOT NULL);
CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger_entries BEGIN SELECT RAISE(ABORT,'ledger append-only'); END;
CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger_entries BEGIN SELECT RAISE(ABORT,'ledger append-only'); END;
CREATE TRIGGER fills_no_update BEFORE UPDATE ON paper_fills BEGIN SELECT RAISE(ABORT,'fills append-only'); END;
CREATE TRIGGER fills_no_delete BEFORE DELETE ON paper_fills BEGIN SELECT RAISE(ABORT,'fills append-only'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'events append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'events append-only'); END;
INSERT INTO schema_migrations VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=1;
COMMIT;
