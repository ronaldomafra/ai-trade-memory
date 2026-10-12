"""Atomic shared collection slots; retries/crashes never silently reset account quota."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from poc.domain.primitives import canonical_json, iso, stable_id, utc


class SourceCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS collections(
            request_id TEXT PRIMARY KEY, provider TEXT NOT NULL, scope_hash TEXT NOT NULL,
            slot INTEGER NOT NULL, day TEXT NOT NULL, reserved_at TEXT NOT NULL,
            finished_at TEXT, response_json TEXT, status TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS source_daily_limits(
            provider TEXT NOT NULL, day TEXT NOT NULL, blocked INTEGER NOT NULL,
            PRIMARY KEY(provider,day));
          CREATE TABLE IF NOT EXISTS source_items(
            version_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, content_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL, item_json TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS classifications(
            classification_id TEXT PRIMARY KEY, available_at TEXT NOT NULL,
            result_json TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS collection_history ON
            collections(provider,scope_hash,finished_at);
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

    def block_marketaux_day(self, now: datetime):
        with self.transaction():
            self.connection.execute(
                "INSERT OR REPLACE INTO source_daily_limits VALUES(?,?,1)",
                ("marketaux", utc(now).date().isoformat()),
            )

    def reserve(self, provider: str, scope: dict, now: datetime, poll_seconds: int) -> dict:
        slot = int(utc(now).timestamp()) // poll_seconds
        scope_hash = stable_id(scope)
        identity = stable_id(provider, scope_hash, slot)
        day = utc(now).date().isoformat()
        with self.transaction():
            previous = self.connection.execute(
                "SELECT * FROM collections WHERE request_id=?", (identity,)
            ).fetchone()
            if previous:
                return {
                    "granted": False,
                    "request_id": identity,
                    "cached": json.loads(previous["response_json"])
                    if previous["response_json"]
                    else None,
                    "reason": "SHARED_SLOT"
                    if previous["finished_at"]
                    else "COLLECTION_INDETERMINATE",
                }
            if provider == "marketaux":
                used = self.connection.execute(
                    "SELECT COUNT(*) FROM collections WHERE provider=? AND day=?", (provider, day)
                ).fetchone()[0]
                blocked = self.connection.execute(
                    "SELECT blocked FROM source_daily_limits WHERE provider=? AND day=?",
                    (provider, day),
                ).fetchone()
                if used >= 100 or (blocked and blocked[0]):
                    return {"granted": False, "reason": "FREE_NEWS_QUOTA_EXHAUSTED"}
            self.connection.execute(
                "INSERT INTO collections VALUES(?,?,?,?,?,?,?,?,?)",
                (identity, provider, scope_hash, slot, day, iso(now), None, None, "RESERVED"),
            )
        return {"granted": True, "request_id": identity}

    def finish(self, request_id: str, result: dict, now: datetime):
        with self.transaction():
            self.connection.execute(
                "UPDATE collections SET finished_at=?,response_json=?,status=? "
                "WHERE request_id=? AND finished_at IS NULL",
                (iso(now), canonical_json(result), result["status"], request_id),
            )
            if result.get("reason") in ("MARKETAUX_HTTP_429", "MARKETAUX_HTTP_402"):
                self.connection.execute(
                    "INSERT OR REPLACE INTO source_daily_limits VALUES(?,?,?)",
                    ("marketaux", utc(now).date().isoformat(), 1),
                )

    def save_item(self, item: dict) -> dict:
        version = stable_id(item["item_id"], item["content_hash"])
        with self.transaction():
            previous = self.connection.execute(
                "SELECT item_json FROM source_items WHERE version_id=?", (version,)
            ).fetchone()
            if previous:
                old = json.loads(previous[0])
                old["provenance"] = list(
                    {
                        canonical_json(origin): origin
                        for origin in old["provenance"] + item["provenance"]
                    }.values()
                )
                # Bounded source audit preserves earliest discovery per provider/id.
                sources = {}
                for origin in old["provenance"]:
                    key = (origin["provider"], origin.get("provider_id"))
                    if key not in sources or origin["observed_at"] < sources[key]["observed_at"]:
                        sources[key] = origin
                old["provenance"] = sorted(sources.values(), key=canonical_json)
                item = old
            self.connection.execute(
                "INSERT INTO source_items VALUES(?,?,?,?,?) "
                "ON CONFLICT(version_id) DO UPDATE SET item_json=excluded.item_json",
                (
                    version,
                    item["item_id"],
                    item["content_hash"],
                    item["first_seen_at"],
                    canonical_json(item),
                ),
            )
        return item

    def items(self, cutoff: datetime) -> list[dict]:
        records = [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT item_json FROM source_items WHERE first_seen_at<=? "
                "ORDER BY first_seen_at,item_id",
                (iso(cutoff),),
            )
        ]
        latest = list({item["item_id"]: item for item in records}.values())
        groups = {}
        for item in latest:
            # Repeated daily headlines stay separate; same publisher/title/publication
            # can identify duplicate URLs without discarding either provider's provenance.
            key = (item.get("title_source_hash", item["item_id"]), item["published_at"])
            groups.setdefault(key, []).append(item)
        result = []
        for group in groups.values():
            primary = min(group, key=lambda item: (item["first_seen_at"], item["item_id"]))
            selected = max(group, key=lambda item: (item["first_seen_at"], item["item_id"]))
            origins = {}
            for item in group:
                for origin in item["provenance"]:
                    if utc(origin["observed_at"]) <= utc(cutoff):
                        provenance = {**origin, "evidence_url": item["url"]}
                        origins[canonical_json(provenance)] = provenance
            result.append(
                {
                    **selected,
                    "item_id": primary["item_id"],
                    "first_seen_at": primary["first_seen_at"],
                    "version_available_at": selected["first_seen_at"],
                    "alias_item_ids": sorted(item["item_id"] for item in group),
                    "duplicate_match": "TITLE_SOURCE_PUBLICATION" if len(group) > 1 else "URL",
                    "provenance": sorted(origins.values(), key=canonical_json),
                }
            )
        return result

    def history(self, provider: str, scope: dict, cutoff: datetime, limit: int = 300) -> list[dict]:
        return [
            {**json.loads(row[1]), "available_at": row[0]}
            for row in self.connection.execute(
                "SELECT finished_at,response_json FROM collections WHERE provider=? "
                "AND scope_hash=? AND status='COMPLETE' AND finished_at<=? "
                "ORDER BY finished_at DESC LIMIT ?",
                (provider, stable_id(scope), iso(cutoff), min(300, max(1, limit))),
            )
        ]

    def classification(self, identity: str, cutoff: datetime) -> dict | None:
        row = self.connection.execute(
            "SELECT result_json FROM classifications WHERE classification_id=? AND available_at<=?",
            (identity, iso(cutoff)),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save_classification(self, identity: str, result: dict, now: datetime):
        with self.transaction():
            self.connection.execute(
                "INSERT OR IGNORE INTO classifications VALUES(?,?,?)",
                (identity, iso(now), canonical_json(result)),
            )
