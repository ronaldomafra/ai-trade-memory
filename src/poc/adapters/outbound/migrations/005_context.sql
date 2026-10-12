BEGIN IMMEDIATE;
CREATE TABLE external_context_versions(
 context_id TEXT PRIMARY KEY, available_at TEXT NOT NULL,
 content_json TEXT NOT NULL, criteria_version TEXT NOT NULL
);
CREATE INDEX external_context_cutoff ON external_context_versions(available_at);
INSERT INTO schema_migrations VALUES(5,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=5;
COMMIT;
