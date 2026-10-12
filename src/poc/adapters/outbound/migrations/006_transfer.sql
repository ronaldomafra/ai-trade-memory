BEGIN IMMEDIATE;
ALTER TABLE decision_outcomes ADD COLUMN evaluated_at TEXT;
UPDATE decision_outcomes SET evaluated_at=matured_at,
 matured_at=CASE WHEN status='MATURED' THEN matured_at ELSE NULL END;
CREATE TABLE learning_publication_outbox(
 publication_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, status TEXT NOT NULL, acknowledged_at TEXT,
 sample_id TEXT NOT NULL, origin_id TEXT NOT NULL, UNIQUE(sample_id,origin_id)
);
CREATE TABLE transfer_shadows(
 shadow_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES decision_cycles(cycle_id),
 validation_group TEXT NOT NULL, source_group TEXT NOT NULL,
 position_context TEXT NOT NULL, label_kind TEXT NOT NULL, horizon_bars INTEGER NOT NULL,
 market_regime TEXT NOT NULL, started_at TEXT NOT NULL, source_cutoff_at TEXT NOT NULL,
 p TEXT NOT NULL, baseline TEXT NOT NULL, source_query_hash TEXT NOT NULL,
 sources_json TEXT NOT NULL, status TEXT NOT NULL, outcome_id TEXT REFERENCES decision_outcomes(outcome_id),
 matured_at TEXT, y INTEGER, return_pct TEXT,
 UNIQUE(cycle_id,position_context,label_kind,horizon_bars)
);
CREATE INDEX transfer_shadow_validation ON transfer_shadows(validation_group,status,matured_at);
CREATE TABLE transfer_states(
 source_group TEXT PRIMARY KEY, state TEXT NOT NULL, detail_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE transfer_state_events(
 state_event_id TEXT PRIMARY KEY, source_group TEXT NOT NULL,
 state TEXT NOT NULL, detail_json TEXT NOT NULL, occurred_at TEXT NOT NULL
);
INSERT INTO schema_migrations VALUES(6,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=6;
COMMIT;
