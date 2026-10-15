-- Preserve every legacy outcome and its foreign-key identity; widen only the horizon constraint.
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
CREATE TABLE decision_outcomes_profiles(
 outcome_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
 horizon_bars INTEGER NOT NULL CHECK(horizon_bars > 0), label_kind TEXT NOT NULL,
 maturity_time TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
 reference_json TEXT NOT NULL, exit_quote_id TEXT REFERENCES price_quotes(quote_id),
 matured_at TEXT, return_pct TEXT, sample_id TEXT, evaluated_at TEXT,
 UNIQUE(decision_id,horizon_bars)
);
INSERT INTO decision_outcomes_profiles SELECT * FROM decision_outcomes;
DROP TABLE decision_outcomes;
ALTER TABLE decision_outcomes_profiles RENAME TO decision_outcomes;
CREATE INDEX pending_outcomes ON decision_outcomes(status,maturity_time);
INSERT INTO schema_migrations VALUES(7,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=7;
COMMIT;
PRAGMA foreign_keys=ON;
