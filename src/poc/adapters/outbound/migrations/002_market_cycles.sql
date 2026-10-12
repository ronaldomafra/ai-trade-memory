BEGIN IMMEDIATE;
ALTER TABLE price_quotes ADD COLUMN request_started_at TEXT;
ALTER TABLE price_quotes ADD COLUMN update_id INTEGER;
ALTER TABLE price_quotes ADD COLUMN bid_qty TEXT;
ALTER TABLE price_quotes ADD COLUMN ask_qty TEXT;
CREATE TABLE candles(
 symbol TEXT NOT NULL, interval TEXT NOT NULL, open_time_utc TEXT NOT NULL,
 close_time_exclusive_utc TEXT NOT NULL, open TEXT NOT NULL, high TEXT NOT NULL,
 low TEXT NOT NULL, close TEXT NOT NULL, volume TEXT NOT NULL, available_at TEXT NOT NULL,
 source TEXT NOT NULL, PRIMARY KEY(symbol,interval,open_time_utc)
);
CREATE INDEX closed_candle_time ON candles(symbol,interval,close_time_exclusive_utc);
CREATE TABLE market_snapshots(
 snapshot_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
 symbol TEXT NOT NULL, candle_open_time TEXT NOT NULL, as_of TEXT NOT NULL,
 features_json TEXT NOT NULL, portfolios_json TEXT NOT NULL,
 feature_version TEXT NOT NULL, data_quality_status TEXT NOT NULL
);
CREATE TABLE decision_cycles(
 cycle_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
 symbol TEXT NOT NULL, candle_open_time TEXT NOT NULL, candle_close_time TEXT NOT NULL,
 status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
 snapshot_id TEXT NOT NULL REFERENCES market_snapshots(snapshot_id),
 execution_quote_id TEXT REFERENCES price_quotes(quote_id), data_status TEXT NOT NULL
);
CREATE TABLE decisions(
 decision_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES decision_cycles(cycle_id),
 portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
 snapshot_id TEXT NOT NULL REFERENCES market_snapshots(snapshot_id),
 ai_call_id TEXT, proposed_action TEXT NOT NULL, approved_action TEXT NOT NULL,
 executed_action TEXT NOT NULL, probabilities_json TEXT, confidence TEXT,
 reason_code TEXT NOT NULL, memory_json TEXT, state_json TEXT NOT NULL,
 decision_started_at TEXT NOT NULL, decision_at TEXT NOT NULL,
 decision_price_quote_id TEXT REFERENCES price_quotes(quote_id),
 status TEXT NOT NULL, UNIQUE(cycle_id,portfolio_id)
);
ALTER TABLE paper_orders ADD COLUMN decision_id TEXT REFERENCES decisions(decision_id);
CREATE TABLE runtime_state(name TEXT PRIMARY KEY,value_json TEXT NOT NULL);
INSERT INTO schema_migrations VALUES(2,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=2;
COMMIT;
