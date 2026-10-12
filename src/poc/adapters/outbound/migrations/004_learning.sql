BEGIN IMMEDIATE;
CREATE TABLE decision_outcomes(
 outcome_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
 horizon_bars INTEGER NOT NULL CHECK(horizon_bars IN(4,16)), label_kind TEXT NOT NULL,
 maturity_time TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
 reference_json TEXT NOT NULL, exit_quote_id TEXT REFERENCES price_quotes(quote_id),
 matured_at TEXT, return_pct TEXT, sample_id TEXT, UNIQUE(decision_id,horizon_bars)
);
CREATE INDEX pending_outcomes ON decision_outcomes(status,maturity_time);
CREATE TABLE learning_registration(
 decision_id TEXT PRIMARY KEY REFERENCES decisions(decision_id),
 status TEXT NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE learning_examples(
 sample_id TEXT PRIMARY KEY, core_json TEXT NOT NULL,
 symbol TEXT NOT NULL, protocol_hash TEXT NOT NULL, position_context TEXT NOT NULL,
 label_kind TEXT NOT NULL, horizon_bars INTEGER NOT NULL, market_regime TEXT NOT NULL,
 rsi_bucket TEXT NOT NULL, volume_bucket TEXT NOT NULL, volatility_bucket TEXT NOT NULL,
 decision_at TEXT NOT NULL, maturity_time TEXT NOT NULL, return_pct TEXT NOT NULL,
 fixture INTEGER NOT NULL CHECK(fixture IN(0,1))
);
CREATE TABLE learning_origins(
 origin_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES learning_examples(sample_id),
 origin_json TEXT NOT NULL, matured_at TEXT NOT NULL, available_at TEXT NOT NULL,
 origin_run_id TEXT NOT NULL, decision_id TEXT NOT NULL, portfolio_id TEXT NOT NULL
);
CREATE INDEX learning_origin_cutoff ON learning_origins(sample_id,matured_at,available_at);
CREATE TABLE dataset_imports(
 dataset_id TEXT PRIMARY KEY, file_hash TEXT NOT NULL, header_json TEXT NOT NULL,
 imported_at TEXT NOT NULL, sample_count INTEGER NOT NULL, status TEXT NOT NULL
);
INSERT INTO schema_migrations VALUES(4,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=4;
COMMIT;
