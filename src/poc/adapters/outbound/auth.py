"""Local owner, Argon2 password, replay-protected TOTP and hashed opaque token families."""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from poc.application.sessions import valid_run_id
from poc.domain.primitives import DomainError, canonical_json, iso, stable_id, utc
from poc.domain.security import AuthenticationError, Principal


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(
            path, isolation_level=None, timeout=10, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
          CREATE TABLE IF NOT EXISTS users(
            user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, totp_secret TEXT NOT NULL,
            last_totp_step INTEGER NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS challenges(
            challenge_hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(user_id),
            scopes_json TEXT NOT NULL, sessions_json TEXT NOT NULL,
            expires_at TEXT NOT NULL, used INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS families(
            family_id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(user_id),
            scopes_json TEXT NOT NULL, sessions_json TEXT NOT NULL,
            expires_at TEXT NOT NULL, revoked INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS tokens(
            token_hash TEXT PRIMARY KEY, family_id TEXT REFERENCES families(family_id),
            kind TEXT NOT NULL, expires_at TEXT NOT NULL, revoked INTEGER NOT NULL,
            revoke_reason TEXT);
          CREATE TABLE IF NOT EXISTS rate_limits(
            bucket_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL);
        """)
        os.chmod(path, 0o600)
        self.hasher = PasswordHasher()
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))

    def close(self):
        with self.lock:
            self.connection.close()

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

    def initialized(self) -> bool:
        with self.lock:
            return self.connection.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def bootstrap_owner(self, username: str, password: str, now: datetime) -> dict:
        username = username.strip().casefold()
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9_.@-]{2,63}", username)
            or not 12 <= len(password) <= 256
        ):
            raise DomainError("Owner username/password does not meet the local setup format")
        with self.lock, self.transaction():
            if self.initialized():
                raise DomainError("An owner already exists; bootstrap never replaces it")
            secret = pyotp.random_base32()
            self.connection.execute(
                "INSERT INTO users VALUES(?,?,?,?,?,?)",
                (
                    stable_id("owner", username),
                    username,
                    self.hasher.hash(password),
                    secret,
                    -1,
                    iso(now),
                ),
            )
        return {
            "username": username,
            "totp_secret": secret,
            "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                username, issuer_name="ai-trade-memory"
            ),
        }

    def _rate(self, peer: str, now: datetime):
        key = stable_id("auth-rate", peer, int(utc(now).timestamp()) // 300)
        with self.transaction():
            row = self.connection.execute(
                "SELECT attempts FROM rate_limits WHERE bucket_key=?", (key,)
            ).fetchone()
            if row and row[0] >= 10:
                raise AuthenticationError("Authentication temporarily rate limited")
            self.connection.execute(
                "INSERT INTO rate_limits VALUES(?,1) "
                "ON CONFLICT(bucket_key) DO UPDATE SET attempts=attempts+1",
                (key,),
            )

    def begin_login(
        self,
        username: str,
        password: str,
        now: datetime,
        peer: str,
        scopes: tuple[str, ...] = ("read", "manage"),
        sessions: tuple[str, ...] = ("*",),
    ) -> dict:
        if not scopes or not set(scopes) <= {"read", "manage"} or not sessions:
            raise DomainError("Invalid token scope request")
        for session in sessions:
            if session != "*":
                valid_run_id(session)
        with self.lock:
            self._rate(peer, now)
            row = self.connection.execute(
                "SELECT * FROM users WHERE username=?", (username.strip().casefold(),)
            ).fetchone()
            try:
                self.hasher.verify(row["password_hash"] if row else self.dummy_hash, password)
            except (VerificationError, InvalidHashError):
                raise AuthenticationError("Invalid authentication") from None
            if row is None:
                raise AuthenticationError("Invalid authentication")
            token = secrets.token_urlsafe(32)
            expires = utc(now) + timedelta(minutes=2)
            with self.transaction():
                if self.hasher.check_needs_rehash(row["password_hash"]):
                    self.connection.execute(
                        "UPDATE users SET password_hash=? WHERE user_id=?",
                        (self.hasher.hash(password), row["user_id"]),
                    )
                self.connection.execute(
                    "INSERT INTO challenges VALUES(?,?,?,?,?,0)",
                    (
                        token_hash(token),
                        row["user_id"],
                        canonical_json(sorted(set(scopes))),
                        canonical_json(sorted(set(sessions))),
                        iso(expires),
                    ),
                )
            return {"challenge_token": token, "expires_at": iso(expires), "requires_2fa": True}

    def complete_login(self, challenge: str, code: str, now: datetime, peer: str) -> dict:
        with self.lock:
            self._rate(peer, now)
            with self.transaction():
                row = self.connection.execute(
                    "SELECT c.*,u.totp_secret,u.last_totp_step FROM challenges c "
                    "JOIN users u ON u.user_id=c.user_id WHERE c.challenge_hash=?",
                    (token_hash(challenge),),
                ).fetchone()
                if row is None or row["used"] or utc(row["expires_at"]) <= utc(now):
                    raise AuthenticationError("Invalid authentication")
                totp = pyotp.TOTP(row["totp_secret"])
                current = int(utc(now).timestamp()) // 30
                match = None
                if re.fullmatch(r"[0-9]{6}", code):
                    for step in (current, current - 1, current + 1):
                        if step > row["last_totp_step"] and hmac.compare_digest(
                            totp.at(step * 30), code
                        ):
                            match = step
                            break
                if match is None:
                    raise AuthenticationError("Invalid authentication")
                self.connection.execute(
                    "UPDATE challenges SET used=1 WHERE challenge_hash=?", (token_hash(challenge),)
                )
                self.connection.execute(
                    "UPDATE users SET last_totp_step=? WHERE user_id=?", (match, row["user_id"])
                )
                family = secrets.token_hex(24)
                self.connection.execute(
                    "INSERT INTO families VALUES(?,?,?,?,?,0)",
                    (
                        family,
                        row["user_id"],
                        row["scopes_json"],
                        row["sessions_json"],
                        iso(utc(now) + timedelta(days=30)),
                    ),
                )
                return self._issue(family, now)

    def _issue(self, family: str, now: datetime) -> dict:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        family_row = self.connection.execute(
            "SELECT expires_at FROM families WHERE family_id=?", (family,)
        ).fetchone()
        access_exp = min(utc(now) + timedelta(minutes=15), utc(family_row[0]))
        refresh_exp = min(utc(now) + timedelta(days=7), utc(family_row[0]))
        for value, kind, expiry in (
            (access, "access", access_exp),
            (refresh, "refresh", refresh_exp),
        ):
            self.connection.execute(
                "INSERT INTO tokens VALUES(?,?,?,?,0,NULL)",
                (token_hash(value), family, kind, iso(expiry)),
            )
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_at": iso(access_exp),
            "refresh_expires_at": iso(refresh_exp),
        }

    def authorize(
        self, token: str, now: datetime, scope: str, run_id: str | None = None
    ) -> Principal:
        with self.lock:
            row = self.connection.execute(
                "SELECT t.*,f.user_id,f.scopes_json,f.sessions_json,f.revoked AS family_revoked,"
                "f.expires_at AS family_expires,u.username FROM tokens t "
                "JOIN families f ON f.family_id=t.family_id "
                "JOIN users u ON u.user_id=f.user_id WHERE t.token_hash=? AND t.kind='access'",
                (token_hash(token),),
            ).fetchone()
            if (
                row is None
                or row["revoked"]
                or row["family_revoked"]
                or utc(row["expires_at"]) <= utc(now)
                or utc(row["family_expires"]) <= utc(now)
            ):
                raise AuthenticationError("Invalid or expired authentication")
            principal = Principal(
                row["user_id"],
                row["username"],
                tuple(json.loads(row["scopes_json"])),
                tuple(json.loads(row["sessions_json"])),
                utc(row["expires_at"]),
                row["family_id"],
            )
            principal.require(scope, run_id)
            return principal

    def refresh(self, token: str, now: datetime) -> dict:
        failure = None
        with self.lock, self.transaction():
            row = self.connection.execute(
                "SELECT t.*,f.revoked AS family_revoked,f.expires_at AS family_expires "
                "FROM tokens t JOIN families f ON f.family_id=t.family_id "
                "WHERE t.token_hash=? AND t.kind='refresh'",
                (token_hash(token),),
            ).fetchone()
            if row is None:
                failure = "Invalid authentication"
            elif row["revoked"]:
                self._revoke_family(row["family_id"], "REFRESH_REPLAY")
                failure = "Invalid authentication"
            elif (
                row["family_revoked"]
                or utc(row["expires_at"]) <= utc(now)
                or utc(row["family_expires"]) <= utc(now)
            ):
                failure = "Expired authentication"
            else:
                self.connection.execute(
                    "UPDATE tokens SET revoked=1,revoke_reason='ROTATED' "
                    "WHERE family_id=? AND kind='access'",
                    (row["family_id"],),
                )
                self.connection.execute(
                    "UPDATE tokens SET revoked=1,revoke_reason='ROTATED' WHERE token_hash=?",
                    (token_hash(token),),
                )
                result = self._issue(row["family_id"], now)
        if failure:
            raise AuthenticationError(failure)
        return result

    def _revoke_family(self, family: str, reason: str):
        self.connection.execute("UPDATE families SET revoked=1 WHERE family_id=?", (family,))
        self.connection.execute(
            "UPDATE tokens SET revoked=1,revoke_reason=? WHERE family_id=?", (reason, family)
        )

    def logout(self, token: str, now: datetime):
        with self.lock, self.transaction():
            row = self.connection.execute(
                "SELECT family_id FROM tokens WHERE token_hash=?", (token_hash(token),)
            ).fetchone()
            if row:
                self._revoke_family(row["family_id"], "LOGOUT")

    def reset_totp(self, username: str, now: datetime) -> dict:
        with self.lock, self.transaction():
            row = self.connection.execute(
                "SELECT user_id FROM users WHERE username=?", (username.strip().casefold(),)
            ).fetchone()
            if row is None:
                raise DomainError("Owner not found")
            secret = pyotp.random_base32()
            self.connection.execute(
                "UPDATE users SET totp_secret=?,last_totp_step=-1 WHERE user_id=?", (secret, row[0])
            )
            self.connection.execute("UPDATE challenges SET used=1 WHERE user_id=?", (row[0],))
            families = self.connection.execute(
                "SELECT family_id FROM families WHERE user_id=?", (row[0],)
            ).fetchall()
            for family in families:
                self._revoke_family(family[0], "LOCAL_2FA_RESET")
        return {
            "username": username,
            "totp_secret": secret,
            "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(
                username, issuer_name="ai-trade-memory"
            ),
        }
