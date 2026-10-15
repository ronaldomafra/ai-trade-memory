"""Additive profile catalog in the existing control database; no financial authority."""

import json
from datetime import datetime

from poc.domain.primitives import DomainError, canonical_json, iso, stable_id


class SQLiteProfiles:
    def __init__(self, connection):
        self.connection = connection
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS strategy_profile_versions(
              profile_id TEXT NOT NULL,version INTEGER NOT NULL,
              definition_json TEXT NOT NULL,profile_hash TEXT NOT NULL,
              status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
              PRIMARY KEY(profile_id,version));
            CREATE TABLE IF NOT EXISTS strategy_profile_events(
              event_id TEXT PRIMARY KEY,profile_id TEXT NOT NULL,version INTEGER NOT NULL,
              action TEXT NOT NULL,actor TEXT NOT NULL,occurred_at TEXT NOT NULL,
              profile_hash TEXT NOT NULL);
        """)

    @staticmethod
    def _record(row):
        if row is None:
            return None
        result = dict(row)
        result["definition"] = json.loads(result.pop("definition_json"))
        return result

    def list_profiles(self):
        return [
            self._record(r)
            for r in self.connection.execute(
                "SELECT * FROM strategy_profile_versions ORDER BY profile_id,version DESC"
            )
        ]

    def profile(self, profile_id: str, version: int | None = None):
        if version is None:
            row = self.connection.execute(
                "SELECT * FROM strategy_profile_versions WHERE profile_id=? "
                "AND status='READY_FOR_PAPER' ORDER BY version DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM strategy_profile_versions WHERE profile_id=? AND version=?",
                (profile_id, version),
            ).fetchone()
        return self._record(row)

    def register_profile(self, definition: dict, digest: str, actor: str, now: datetime):
        identity, version = definition["profile"]["profile_id"], definition["profile"]["version"]
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            previous = self.profile(identity, version)
            if previous:
                if previous["profile_hash"] != digest:
                    raise DomainError(
                        "Profile ID/version already has different content; create a new revision"
                    )
                return previous
            self.connection.execute(
                "INSERT INTO strategy_profile_versions VALUES(?,?,?,?,?,?,?)",
                (
                    identity,
                    version,
                    canonical_json(definition),
                    digest,
                    "DRAFT",
                    iso(now),
                    iso(now),
                ),
            )
            self._event(identity, version, "REGISTER", digest, actor, now)
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            if self.connection.in_transaction:
                self.connection.rollback()
        return self.profile(identity, version)

    def transition_profile(
        self, profile_id: str, version: int, status: str, actor: str, now: datetime
    ):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            old = self.profile(profile_id, version)
            if old is None:
                raise DomainError("Profile revision not found")
            if old["status"] == status:
                return old
            if old["status"] == "ARCHIVED" or status not in ("READY_FOR_PAPER", "ARCHIVED"):
                raise DomainError("Archived revisions cannot be republished; create a new revision")
            self.connection.execute(
                "UPDATE strategy_profile_versions SET status=?,updated_at=? "
                "WHERE profile_id=? AND version=?",
                (status, iso(now), profile_id, version),
            )
            self._event(profile_id, version, status, old["profile_hash"], actor, now)
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        finally:
            if self.connection.in_transaction:
                self.connection.rollback()
        return self.profile(profile_id, version)

    def _event(self, profile_id, version, action, digest, actor, now):
        self.connection.execute(
            "INSERT INTO strategy_profile_events VALUES(?,?,?,?,?,?,?)",
            (
                stable_id(profile_id, version, action),
                profile_id,
                version,
                action,
                actor,
                iso(now),
                digest,
            ),
        )
