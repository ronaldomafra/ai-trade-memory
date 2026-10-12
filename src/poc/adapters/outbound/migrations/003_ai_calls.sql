BEGIN IMMEDIATE;
CREATE TABLE ai_calls(
 ai_call_id TEXT PRIMARY KEY, logical_request_id TEXT NOT NULL, call_purpose TEXT NOT NULL,
 attempt_index INTEGER NOT NULL, provider_generation_id TEXT, requested_model TEXT NOT NULL,
 actual_model TEXT, provider TEXT, started_at TEXT NOT NULL, finished_at TEXT,
 latency_ms INTEGER, http_status INTEGER, retries INTEGER NOT NULL,
 request_json_sanitized TEXT NOT NULL, response_json TEXT, input_tokens INTEGER,
 output_tokens INTEGER, cost_usd TEXT, cost_source TEXT NOT NULL, error_code TEXT,
 error_message_safe TEXT, status TEXT NOT NULL,
 UNIQUE(logical_request_id,call_purpose,attempt_index)
);
INSERT INTO schema_migrations VALUES(3,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=3;
COMMIT;
