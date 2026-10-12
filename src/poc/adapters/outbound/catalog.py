"""Owner-local statistical catalog. Publication timestamps never backdate imported data."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from poc.domain.dataset import validate_record
from poc.domain.primitives import DomainError, canonical_json, iso, stable_id, utc
from poc.domain.transfer import normalize_features


class LearningCatalog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS examples(
            sample_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, protocol_hash TEXT NOT NULL,
            decision_at TEXT NOT NULL, core_json TEXT NOT NULL, normalized_json TEXT NOT NULL,
            normalizer_version TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS publications(
            publication_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL REFERENCES examples(sample_id),
            origin_id TEXT NOT NULL, origin_json TEXT NOT NULL,
            publisher_run_id TEXT NOT NULL, available_at TEXT NOT NULL,
            UNIQUE(sample_id,origin_id,publisher_run_id));
          CREATE INDEX IF NOT EXISTS catalog_cutoff ON publications(sample_id,available_at);
        """)

    def close(self):
        self.connection.close()

    def missing_publications(self, identities: list[str]) -> set[str]:
        present = set()
        for start in range(0, len(identities), 500):
            part = identities[start : start + 500]
            if part:
                rows = self.connection.execute(
                    "SELECT publication_id FROM publications WHERE publication_id IN ("
                    + ",".join("?" for _ in part)
                    + ")",
                    part,
                ).fetchall()
                present.update(row[0] for row in rows)
        return set(identities) - present

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

    def publish(self, publication_id: str, core: dict, origin: dict, publisher: str, now: datetime):
        if (
            core["fixture"]
            or utc(origin["matured_at"]) >= utc(now)
            or utc(origin["available_at"]) > utc(now)
        ):
            raise DomainError("Catalog accepts only matured, available nonfixture observations")
        if publication_id != stable_id(
            "catalog-publication", publisher, core["sample_id"], origin["origin_id"]
        ):
            raise DomainError("Publication identity mismatch")
        normalized = normalize_features(core["features"])
        validate_record({"core": core, "origins": [origin]}, now)
        with self.transaction():
            old = self.connection.execute(
                "SELECT core_json FROM examples WHERE sample_id=?", (core["sample_id"],)
            ).fetchone()
            if old and old[0] != canonical_json(core):
                raise DomainError("Conflicting catalog example")
            self.connection.execute(
                "INSERT OR IGNORE INTO examples VALUES(?,?,?,?,?,?,?)",
                (
                    core["sample_id"],
                    core["symbol"],
                    core["protocol_hash"],
                    core["decision_at"],
                    canonical_json(core),
                    canonical_json(normalized),
                    "relative_features_v1",
                ),
            )
            old_origin = self.connection.execute(
                "SELECT origin_json FROM publications WHERE publication_id=?", (publication_id,)
            ).fetchone()
            if old_origin and old_origin[0] != canonical_json(origin):
                raise DomainError("Conflicting catalog origin")
            self.connection.execute(
                "INSERT OR IGNORE INTO publications VALUES(?,?,?,?,?,?)",
                (
                    publication_id,
                    core["sample_id"],
                    origin["origin_id"],
                    canonical_json(origin),
                    publisher,
                    iso(now),
                ),
            )

    def sources(self, target_symbol: str, protocol_hash: str, cutoff: datetime) -> list[dict]:
        records = []
        for row in self.connection.execute(
            "SELECT * FROM examples WHERE symbol!=? AND protocol_hash=? "
            "AND normalizer_version=? AND decision_at>=? AND decision_at<? ORDER BY sample_id",
            (
                target_symbol,
                protocol_hash,
                "relative_features_v1",
                iso(utc(cutoff) - timedelta(days=60)),
                iso(cutoff),
            ),
        ):
            eligible = self.connection.execute(
                "SELECT origin_json,available_at FROM publications "
                "WHERE sample_id=? AND available_at<? ORDER BY publication_id",
                (row["sample_id"], iso(cutoff)),
            ).fetchall()
            origins = [
                {**json.loads(origin[0]), "catalog_available_at": origin[1]}
                for origin in eligible
                if utc(json.loads(origin[0])["matured_at"]) < utc(cutoff)
            ]
            if origins:
                records.append(
                    {
                        "core": json.loads(row["core_json"]),
                        "normalized": json.loads(row["normalized_json"]),
                        "origins": origins,
                    }
                )
        return records
