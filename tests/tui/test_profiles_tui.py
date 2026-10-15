import json
from copy import deepcopy

import pytest
from test_tui import FixtureClient
from textual.widgets import Button, Input, Select, Static, TextArea

from poc.adapters.inbound.tui import NewSessionScreen, TradeApp
from poc.adapters.inbound.tui_profiles import ProfilesScreen
from poc.profile_config import ProfileDefinition, profile_template


class ProfileClient(FixtureClient):
    def __init__(self):
        super().__init__()
        self.records = []

    async def request(self, method, path, body=None, key=None):
        if path.startswith("/v1/profile-template"):
            return {
                "definition": profile_template(path.split("style=")[-1]),
                "parameter_schema": ProfileDefinition.model_json_schema(),
            }
        if path == "/v1/profiles/validate":
            definition = ProfileDefinition.model_validate(body)
            return {
                "valid": True,
                "definition": definition.model_dump(mode="json"),
                "preview": {
                    "interval": definition.parameters.market.interval,
                    "trend_interval": definition.parameters.market.trend_interval,
                    "maximum_holding_seconds": 900,
                    "horizon_seconds": [180, 900],
                    "maximum_cycles_per_day_utc": 80,
                },
            }
        if method == "POST" and (path == "/v1/profiles" or path.endswith("/publish")):
            self.records.append((path, deepcopy(body), key))
            return {"profile": {"status": "READY_FOR_PAPER"}}
        return await super().request(method, path, body, key)


@pytest.mark.asyncio
async def test_tui_profile_template_validate_edit_and_publish_is_explicit_and_never_starts_bot():
    client = ProfileClient()
    app = TradeApp(client)
    async with app.run_test(size=(150, 65)) as pilot:
        await pilot.pause(0.2)
        await pilot.click("#profiles")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ProfilesScreen)
        screen = app.screen
        screen.query_one("#profile-source", Select).value = "SCALPING"
        await pilot.pause(0.3)
        screen.query_one("#profile-id", Input).value = "meu_bot"
        settings = json.loads(screen.query_one("#profile-parameters", TextArea).text)
        settings["app"]["max_candle_decision_lag_seconds"] = 15
        settings["ai"].update(
            max_calls_per_day=1000, max_observed_cost_usd_per_day="0.50", cost_limit_enabled=False
        )
        screen.query_one("#profile-parameters", TextArea).load_text(json.dumps(settings))
        assert screen.query_one("#profile-publish", Button).disabled
        await screen.validate().wait()
        assert not screen.query_one("#profile-publish", Button).disabled
        assert "1m" in screen.query_one("#profile-message", Static).render().plain
        assert not client.records
        # A change invalidates the reviewed preview; it cannot be silently published.
        screen.query_one("#profile-name", Input).value = "Bot revisado"
        await screen.publish().wait()
        assert not client.records
        await screen.validate().wait()
        await screen.publish().wait()
        await pilot.pause(0.2)
        assert [r[0] for r in client.records] == [
            "/v1/profiles",
            "/v1/profiles/meu_bot/versions/1/publish",
        ]
        assert client.records[0][1]["parameters"]["market"]["interval"] == "1m"
        assert client.records[0][1]["parameters"]["ai"]["max_calls_per_day"] == 1000
        assert client.records[0][1]["parameters"]["ai"]["cost_limit_enabled"] is False
        assert client.records[0][1]["parameters"]["app"]["max_candle_decision_lag_seconds"] == 15
        assert not client.commands


@pytest.mark.asyncio
async def test_new_session_changes_defaults_with_profile_and_pins_revision_hash():
    client = ProfileClient()
    legacy = (await client.request("GET", "/v1/profiles"))["profiles"][0]
    definition = profile_template("SCALPING")
    profile = {
        "profile_id": "meu_bot",
        "version": "2",
        "profile_hash": "a" * 64,
        "definition": definition,
        "template": definition["parameters"],
        "symbol_default": "SOLUSDT",
        "status": "READY_FOR_PAPER",
        "style": "SCALPING",
    }
    draft = {**profile, "profile_id": "unpublished", "status": "DRAFT"}
    app = TradeApp(client)
    async with app.run_test(size=(150, 65)) as pilot:
        await pilot.pause(0.2)
        screen = NewSessionScreen(client, [legacy, draft, profile])
        app.push_screen(screen)
        await pilot.pause(0.2)
        screen.query_one("#profile", Select).value = "meu_bot@2"
        await pilot.pause(0.2)
        assert screen.query_one("#symbol", Input).value == "SOLUSDT"
        assert (
            json.loads(screen.query_one("#overrides", TextArea).text)["market"]["interval"] == "1m"
        )
        await screen.create_session().wait()
        await pilot.pause(0.2)
        command = next(c for c in client.commands if c[0] == "/v1/sessions")
        assert command[1]["profile_version"] == 2 and command[1]["profile_hash"] == "a" * 64
