from copy import deepcopy

import pytest
from test_control_api import cleanup, fixture

from poc.adapters.outbound.sqlite import SQLiteStorage
from poc.application.sessions import SessionManager
from poc.config import parse_config
from poc.profile_config import profile_template


@pytest.mark.asyncio
async def test_remote_profile_publish_create_revision_archive_and_restore_without_catalog(tmp_path):
    items = await fixture(tmp_path)
    client, _, commands, runtime, metadata, _, _, _ = items
    try:
        response = await client.get("/v1/profile-template?style=SCALPING")
        assert response.status_code == 200
        body = response.json()["definition"]
        body["profile"]["profile_id"] = "meu_bot"
        assert (await client.post("/v1/profiles/validate", json=body)).json()["preview"][
            "horizon_seconds"
        ] == [180, 900]
        assert metadata.calls == 0 and runtime.starts == 0
        headers = {"Idempotency-Key": "profile-register-01"}
        first = await client.post("/v1/profiles", json=body, headers=headers)
        assert first.status_code == 201
        assert (
            await client.post("/v1/profiles", json=body, headers=headers)
        ).json() == first.json()
        session = {
            "run_id": "profile-test",
            "profile_id": "meu_bot",
            "profile_version": 1,
            "symbol": "ETHUSDT",
        }
        assert (
            await client.post(
                "/v1/sessions", json=session, headers={"Idempotency-Key": "prepare-draft-01"}
            )
        ).status_code == 409
        assert metadata.calls == 0
        published = await client.post(
            "/v1/profiles/meu_bot/versions/1/publish",
            headers={"Idempotency-Key": "profile-publish-01"},
        )
        assert published.json()["profile"]["status"] == "READY_FOR_PAPER"
        assert runtime.starts == 0
        prepared = await client.post(
            "/v1/sessions", json=session, headers={"Idempotency-Key": "prepare-profile-01"}
        )
        assert prepared.status_code == 201, prepared.text
        assert metadata.calls == 1 and runtime.starts == 0
        # The session is resolved independently of the catalog on restore.
        from test_accounting import config

        manager = SessionManager(config(tmp_path), SQLiteStorage())
        saved = manager.restore("profile-test")
        effective = parse_config(saved["config"])
        assert (
            effective.market.interval == "1m"
            and effective.strategy.technical.entry_rule == "EMA_CROSS"
        )
        digest = saved["config_hash"]
        changed = deepcopy(body)
        changed["parameters"]["strategy"]["stop_loss_pct"] = "0.4"
        conflict = await client.post(
            "/v1/profiles", json=changed, headers={"Idempotency-Key": "profile-conflict-01"}
        )
        assert conflict.status_code == 409
        changed["profile"]["version"] = 2
        changed["parameters"]["app"]["max_candle_decision_lag_seconds"] = 15
        validation = await client.post("/v1/profiles/validate", json=changed)
        assert validation.status_code == 200, validation.text
        assert (
            await client.post(
                "/v1/profiles/meu_bot/versions",
                json=changed,
                headers={"Idempotency-Key": "profile-revision-02"},
            )
        ).status_code == 201
        assert (
            await client.post(
                "/v1/profiles/meu_bot/versions/2/publish",
                headers={"Idempotency-Key": "profile-publish-02"},
            )
        ).status_code == 200
        new_session = {**session, "run_id": "profile-test-v2", "profile_version": 2}
        updated = await client.post(
            "/v1/sessions", json=new_session, headers={"Idempotency-Key": "prepare-profile-02"}
        )
        assert updated.status_code == 201, updated.text
        revised = parse_config(manager.restore("profile-test-v2")["config"])
        assert revised.app.max_candle_decision_lag_seconds == 15
        assert revised.ai.timeout_seconds == 6
        assert (
            parse_config(
                manager.restore("profile-test")["config"]
            ).app.max_candle_decision_lag_seconds
            == 8
        )
        assert (
            await client.post(
                "/v1/profiles/meu_bot/versions/1/archive",
                headers={"Idempotency-Key": "profile-archive-01"},
            )
        ).status_code == 200
        assert manager.restore("profile-test")["config_hash"] == digest
        commands.connection.execute("DELETE FROM strategy_profile_versions")
        assert manager.restore("profile-test")["config_hash"] == digest
        assert runtime.starts == 0
    finally:
        await cleanup(items)


@pytest.mark.asyncio
async def test_uncertain_prepare_pins_published_version_before_metadata_and_retries(
    tmp_path, monkeypatch
):
    from poc.domain.primitives import DomainError

    items = await fixture(tmp_path)
    client, _, _, _, metadata, _, _, _ = items
    try:
        body = profile_template("DAY_TRADE")
        body["profile"]["profile_id"] = "revision_pin"
        assert (
            await client.post(
                "/v1/profiles", json=body, headers={"Idempotency-Key": "pin-register-v1"}
            )
        ).status_code == 201
        assert (
            await client.post(
                "/v1/profiles/revision_pin/versions/1/publish",
                headers={"Idempotency-Key": "pin-publish-v1"},
            )
        ).status_code == 200
        original = metadata.metadata

        async def failed(symbol):
            raise DomainError("Synthetic metadata outage")

        monkeypatch.setattr(metadata, "metadata", failed)
        request = {"profile_id": "revision_pin", "symbol": "ETHUSDT", "run_id": "pinned"}
        headers = {"Idempotency-Key": "prepare-pinned-once"}
        assert (await client.post("/v1/sessions", json=request, headers=headers)).status_code == 409
        assert (
            await client.post(
                "/v1/profiles/revision_pin/versions/1/archive",
                headers={"Idempotency-Key": "pin-archive-v1"},
            )
        ).status_code == 200
        body["profile"]["version"] = 2
        assert (
            await client.post(
                "/v1/profiles", json=body, headers={"Idempotency-Key": "pin-register-v2"}
            )
        ).status_code == 201
        assert (
            await client.post(
                "/v1/profiles/revision_pin/versions/2/publish",
                headers={"Idempotency-Key": "pin-publish-v2"},
            )
        ).status_code == 200
        monkeypatch.setattr(metadata, "metadata", original)
        result = await client.post("/v1/sessions", json=request, headers=headers)
        assert result.status_code == 201, result.text
        assert result.json()["session"]["profile_version"] == "1"
    finally:
        await cleanup(items)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scopes,sessions", [(("read",), ("*",)), (("read", "manage"), ("restricted",))]
)
async def test_profile_changes_require_global_manage_and_authenticated_reads(
    tmp_path, scopes, sessions
):
    items = await fixture(tmp_path, scopes=scopes, sessions=sessions)
    client = items[0]
    try:
        body = profile_template("DAY_TRADE")
        assert (await client.get("/v1/profile-template?style=DAY_TRADE")).status_code == 200
        assert (
            await client.post(
                "/v1/profiles", json=body, headers={"Idempotency-Key": "denied-profile-01"}
            )
        ).status_code == 403
        client.headers.clear()
        assert (await client.get("/v1/profile-template")).status_code == 401
    finally:
        await cleanup(items)
