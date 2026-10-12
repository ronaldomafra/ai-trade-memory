from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from poc.adapters.outbound.auth import AuthStore
from poc.domain.security import AuthenticationError, PermissionDenied

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)


def owner(tmp_path):
    store = AuthStore(tmp_path / "control" / "auth.sqlite3")
    setup = store.bootstrap_owner("owner", "synthetic-test-password-long", NOW)
    return store, setup


def login(store, setup, now=NOW, scopes=("read", "manage"), sessions=("*",)):
    challenge = store.begin_login(
        "owner", "synthetic-test-password-long", now, "test-peer", scopes, sessions
    )
    code = pyotp.TOTP(setup["totp_secret"]).at(now)
    return store.complete_login(challenge["challenge_token"], code, now, "test-peer")


def test_owner_requires_password_and_2fa_tokens_hashed_and_scoped(tmp_path):
    store, setup = owner(tmp_path)
    with pytest.raises(AuthenticationError):
        store.begin_login("owner", "incorrect-password", NOW, "test-peer")
    tokens = login(store, setup, scopes=("read",), sessions=("session-one",))
    principal = store.authorize(tokens["access_token"], NOW, "read", "session-one")
    assert principal.username == "owner"
    with pytest.raises(PermissionDenied):
        store.authorize(tokens["access_token"], NOW, "manage", "session-one")
    with pytest.raises(PermissionDenied):
        store.authorize(tokens["access_token"], NOW, "read", "session-two")
    dump = "\n".join(store.connection.iterdump())
    assert tokens["access_token"] not in dump and tokens["refresh_token"] not in dump
    assert "synthetic-test-password-long" not in dump
    assert store.path.stat().st_mode & 0o077 == 0
    store.close()


def test_totp_replay_expiry_rotation_replay_revokes_family_and_logout(tmp_path):
    store, setup = owner(tmp_path)
    tokens = login(store, setup)
    with pytest.raises(AuthenticationError):
        login(store, setup)
    with pytest.raises(AuthenticationError):
        store.authorize(tokens["access_token"], NOW + timedelta(minutes=16), "read")
    rotated = store.refresh(tokens["refresh_token"], NOW + timedelta(minutes=16))
    assert rotated["access_token"] != tokens["access_token"]
    assert store.authorize(rotated["access_token"], NOW + timedelta(minutes=16), "read")
    with pytest.raises(AuthenticationError):
        store.refresh(tokens["refresh_token"], NOW + timedelta(minutes=16, seconds=1))
    with pytest.raises(AuthenticationError):
        store.authorize(rotated["access_token"], NOW + timedelta(minutes=16, seconds=1), "read")
    later = NOW + timedelta(minutes=17)
    second = login(store, setup, later)
    store.logout(second["access_token"], later)
    with pytest.raises(AuthenticationError):
        store.authorize(second["access_token"], later, "read")
    store.close()


def test_bootstrap_never_replaces_owner_and_local_reset_revokes_tokens(tmp_path):
    store, setup = owner(tmp_path)
    tokens = login(store, setup)
    with pytest.raises(ValueError):
        store.bootstrap_owner("other", "different-password-long", NOW)
    recovered = store.reset_totp("owner", NOW + timedelta(minutes=1))
    assert recovered["totp_secret"] != setup["totp_secret"]
    with pytest.raises(AuthenticationError):
        store.authorize(tokens["access_token"], NOW + timedelta(minutes=1), "read")
    store.close()
