import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from textual.events import Paste
from textual.widgets import Button, DataTable, Input, Select, Static, TextArea

from poc.adapters.inbound import tui
from poc.adapters.inbound.tui import LoginScreen, NewSessionScreen, TradeApp
from poc.config import Config
from poc.domain.primitives import DomainError


class FixtureClient:
    """UI-only synthetic fixture. Production has no fixture client or fabricated balances."""

    server = "https://synthetic-fixture.example"
    scopes = frozenset({"read", "manage"})

    def __init__(self, authenticated=True):
        self.access_token = "synthetic-token" if authenticated else None
        self.commands = []
        self.closed = False
        self.counter = 0
        self.snapshots = {
            run: {
                "run_id": run,
                "fixture": True,
                "event_watermark": 1,
                "market": {"symbol": symbol},
                "portfolios": [
                    {
                        "id": identity,
                        "cash_usdt": "100",
                        "equity_usdt": "100",
                        "base_qty": "0",
                        "return_pct": "0",
                        "realized_pnl_usdt": "0",
                        "max_drawdown_pct": "0",
                    }
                    for identity in Config().portfolios.strategies
                ],
                "recent_decisions": [],
                "chart_candles": [],
                "equity_series": [],
                "learning": {},
                "ai_cost": {},
                "external_context": {},
            }
            for run, symbol in (("fixture-btc", "BTCUSDT"), ("fixture-eth", "ETHUSDT"))
        }

    async def login(self, username, password, read_only=False):
        assert username == "owner" and password == "synthetic-password"
        self.scopes = frozenset({"read"}) if read_only else self.scopes
        return "synthetic-challenge"

    async def second_factor(self, challenge, code):
        assert code == "123456" and challenge == "synthetic-challenge"
        self.access_token = "synthetic-token"

    async def request(self, method, path, body=None, key=None):
        if method == "POST":
            self.commands.append((path, deepcopy(body), key))
            if path == "/v1/sessions":
                return {"session": {"run_id": "fixture-eth"}}
            return {"running": True}
        if path == "/v1/sessions":
            return {
                "sessions": [
                    {
                        "run_id": run,
                        "symbol": item["market"]["symbol"],
                        "profile_id": "trend_15m_v1",
                    }
                    for run, item in self.snapshots.items()
                ]
            }
        if path == "/v1/profiles":
            return {
                "profiles": [
                    {
                        "profile_id": "trend_15m_v1",
                        "symbol_default": "BTCUSDT",
                        "template": {
                            "strategy": Config().strategy.model_dump(mode="json"),
                            "learning": {"enabled": True, "transfer": {"enabled": True}},
                        },
                    }
                ]
            }
        run = path.split("/")[3]
        if path.endswith("snapshot"):
            return deepcopy(self.snapshots[run])
        if path.endswith("configuration"):
            return {
                "run_id": run,
                "editable": False,
                "symbol": self.snapshots[run]["market"]["symbol"],
            }
        if "/events?" in path:
            return {"events": []}
        raise AssertionError(path)

    async def stream(self, run):
        yield {"type": "snapshot", "snapshot": deepcopy(self.snapshots[run])}
        yield {"type": "connected", "run_id": run}
        await asyncio.Event().wait()

    async def logout(self):
        self.access_token = None

    async def close(self):
        self.closed = True

    def command_key(self):
        self.counter += 1
        return f"synthetic-command-{self.counter}"


@pytest.mark.asyncio
async def test_login_masks_and_clears_credentials_before_dashboard():
    client = FixtureClient(authenticated=False)
    app = TradeApp(client)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        assert isinstance(app.screen, LoginScreen)
        screen = app.screen
        screen.query_one("#username", Input).value = "owner"
        screen.query_one("#password", Input).value = "synthetic-password"
        assert screen.query_one("#password", Input).password
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert screen.query_one("#password", Input).value == ""
        otp = screen.query_one("#otp", Input)
        otp.value = "123456"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert client.access_token and not isinstance(app.screen, LoginScreen)
        assert otp.value == ""
        assert not client.commands


@pytest.mark.asyncio
async def test_totp_paste_normalizes_whitespace_replaces_old_code_and_preserves_login():
    client = FixtureClient(authenticated=False)
    app = TradeApp(client)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        screen = app.screen
        otp = screen.query_one("#otp", Input)
        otp.post_message(Paste("123456"))
        await pilot.pause()
        assert otp.disabled and otp.value == ""
        screen.query_one("#username", Input).value = "owner"
        screen.query_one("#password", Input).value = "synthetic-password"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        otp = screen.query_one("#otp", Input)
        assert not otp.disabled and otp.password
        for text, expected in [
            ("123456", "123456"),
            ("123 456\r\n", "123456"),
            ("\n 001\u00a0234 \n", "001234"),
        ]:
            otp.value = "12"
            otp.post_message(Paste(text))
            await pilot.pause()
            assert otp.value == expected
        for text in ("12345", "1234567", "abc123456", "123456\n654321", "１２３４５６"):
            otp.post_message(Paste(text))
            await pilot.pause()
            assert otp.value == "001234"
        app.copy_to_clipboard("123 456\r\n")
        otp.focus()
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert otp.value == "123456"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert client.access_token and not isinstance(app.screen, LoginScreen)
        assert otp.value == "" and not client.commands


@pytest.mark.asyncio
async def test_totp_feedback_empty_submission_and_expired_login_do_not_call_server():
    class CountingClient(FixtureClient):
        second_factor_calls = 0

        async def second_factor(self, challenge, code):
            self.second_factor_calls += 1
            await super().second_factor(challenge, code)

    client = CountingClient(authenticated=False)
    app = TradeApp(client)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause(0.3)
        screen = app.screen
        screen.query_one("#username", Input).value = "owner"
        screen.query_one("#password", Input).value = "synthetic-password"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        otp = screen.query_one("#otp", Input)
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert client.second_factor_calls == 0
        assert "seis números" in str(screen.query_one("#login-error", Static).render())
        otp.focus()
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert "Ctrl+Shift+V" in str(screen.query_one("#otp-status", Static).render())
        otp.post_message(Paste("123 456"))
        await pilot.pause()
        assert "6/6" in str(screen.query_one("#otp-status", Static).render())
        assert "123456" not in str(screen.query_one("#otp-status", Static).render())
        screen.expire_login()
        await pilot.pause()
        assert screen.challenge is None and otp.disabled and otp.value == ""
        assert not screen.query_one("#password", Input).disabled
        assert not screen.query_one("#username", Input).disabled
        assert str(screen.query_one("#login-submit", Button).label) == "Entrar"
        assert "expirou" in str(screen.query_one("#login-error", Static).render())
        assert client.second_factor_calls == 0 and not client.commands
        # Re-entering the password creates a fresh challenge, without resetting the account.
        screen.query_one("#password", Input).value = "synthetic-password"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        otp.post_message(Paste("123456"))
        await pilot.pause()
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert client.access_token and client.second_factor_calls == 1


@pytest.mark.asyncio
async def test_local_paste_button_reads_only_on_request_and_keeps_invalid_code_out(monkeypatch):
    copied = iter([DomainError("Copie somente o código de seis números."), "123456"])
    reads = []

    async def read_clipboard():
        reads.append(True)
        item = next(copied)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(tui, "read_totp_clipboard", read_clipboard)
    client = FixtureClient(authenticated=False)
    app = TradeApp(client)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause(0.3)
        screen = app.screen
        assert screen.query_one("#paste-otp", Button).disabled and not reads
        screen.query_one("#username", Input).value = "owner"
        screen.query_one("#password", Input).value = "synthetic-password"
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert not screen.query_one("#paste-otp", Button).disabled and not reads
        await pilot.click("#paste-otp")
        await pilot.pause(0.3)
        assert len(reads) == 1 and screen.query_one("#otp", Input).value == ""
        assert "seis números" in str(screen.query_one("#otp-status", Static).render())
        await pilot.click("#paste-otp")
        await pilot.pause(0.3)
        assert len(reads) == 2 and screen.query_one("#otp", Input).value == "123456"
        assert "6/6" in str(screen.query_one("#otp-status", Static).render())
        await pilot.click("#login-submit")
        await pilot.pause(0.3)
        assert client.access_token and not client.commands


@pytest.mark.asyncio
async def test_server_challenge_deadline_automatically_reopens_password_step():
    class ShortChallengeClient(FixtureClient):
        async def login(self, username, password, read_only=False):
            result = await super().login(username, password, read_only)
            self.challenge_expires_at = datetime.now(UTC) + timedelta(seconds=0.1)
            return result

    client = ShortChallengeClient(authenticated=False)
    app = TradeApp(client)
    async with app.run_test(size=(120, 45)) as pilot:
        await pilot.pause(0.3)
        screen = app.screen
        screen.query_one("#username", Input).value = "owner"
        screen.query_one("#password", Input).value = "synthetic-password"
        await pilot.click("#login-submit")
        await pilot.pause(0.4)
        assert screen.challenge is None
        assert screen.query_one("#password", Input).value == ""
        assert not screen.query_one("#password", Input).disabled
        assert screen.query_one("#otp", Input).disabled
        assert screen.query_one("#paste-otp", Button).disabled
        assert "expirou" in str(screen.query_one("#login-error", Static).render())
        assert not client.access_token and not client.commands


@pytest.mark.asyncio
async def test_select_two_symbols_empty_dashboard_resize_readonly_and_quit():
    client = FixtureClient()
    client.scopes = frozenset({"read"})
    app = TradeApp(client)
    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause(0.3)
        app.query_one("#sessions", Select).value = "fixture-eth"
        await pilot.pause(0.3)
        assert app.snapshot["market"]["symbol"] == "ETHUSDT"
        snapshot = deepcopy(app.snapshot)
        snapshot["external_context"] = {
            "news": {
                "status": "unavailable",
                "items": [],
                "sources": {
                    "api": {"status": "PARTIAL"},
                    "rss": {"status": "COMPLETE"},
                    "failed": {"status": "UNAVAILABLE"},
                },
            },
            "prediction_markets": {
                "status": "unavailable",
                "items": [],
                "discovery": {"status": "PARTIAL"},
            },
        }
        app.render_snapshot(snapshot)
        details = str(app.query_one("#ai-details", Static).render())
        assert "JEV: 0 chamadas" in details and "2/3 fontes responderam" in details
        assert "0 fatores utilizáveis" in details and "descoberta Polymarket: PARTIAL" in details
        assert app.query_one("#wallets", DataTable).row_count == 3
        assert app.query_one("#positions", DataTable).row_count == 0
        assert app.query_one("#new", Button).disabled
        await pilot.resize_terminal(70, 24)
        await pilot.pause(0.3)
        assert app.query_one("#dashboard-grid").has_class("narrow")
        app.query_one("#sessions", Select).value = "fixture-btc"
        await pilot.pause(0.3)
        assert app.snapshot["market"]["symbol"] == "BTCUSDT"
        await app.action_quit()
    assert not client.commands and not client.access_token
    assert client.closed


@pytest.mark.asyncio
async def test_wizard_invalid_json_then_other_symbol_without_dataset():
    client = FixtureClient()
    app = TradeApp(client)
    async with app.run_test(size=(130, 55)) as pilot:
        await pilot.pause(0.3)
        app.action_new()
        await pilot.pause(0.3)
        assert isinstance(app.screen, NewSessionScreen)
        screen = app.screen
        screen.query_one("#overrides", TextArea).load_text("invalid-json")
        await pilot.click("#create-session")
        await pilot.pause(0.3)
        assert not client.commands
        screen.query_one("#overrides", TextArea).load_text(
            json.dumps({"learning": {"transfer": {"enabled": True}}})
        )
        screen.query_one("#symbol", Input).value = "ETHUSDT"
        await pilot.click("#create-session")
        await pilot.pause(0.3)
        create, start = client.commands
        assert create[1]["symbol"] == "ETHUSDT" and create[1]["dataset_id"] is None
        assert start[0] == "/v1/sessions/fixture-eth/start"
        assert app.run_id == "fixture-eth" and app.snapshot["market"]["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_degraded_stream_identity_and_logout_do_not_issue_engine_commands():
    class OfflineClient(FixtureClient):
        async def stream(self, run):
            yield {"type": "snapshot", "snapshot": deepcopy(self.snapshots[run])}
            yield {"type": "disconnected", "retry_seconds": 1}
            await asyncio.Event().wait()

    client = OfflineClient()
    app = TradeApp(client)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.3)
        app.query_one("#sessions", Select).value = "fixture-btc"
        await pilot.pause(0.3)
        assert app.snapshot["run_id"] == "fixture-btc"
        with pytest.raises(DomainError):
            app.render_snapshot(client.snapshots["fixture-eth"])
        assert app.snapshot["run_id"] == "fixture-btc"
        await app.action_logout()
        assert app.snapshot is None and app.run_id is None
        assert app.query_one("#wallets", DataTable).row_count == 0
        assert not client.commands


@pytest.mark.asyncio
async def test_rest_unavailable_does_not_crash_empty_application():
    class OfflineClient(FixtureClient):
        async def request(self, *args, **kwargs):
            raise httpx.ConnectError("synthetic-test-connection-failure")

    client = OfflineClient()
    app = TradeApp(client)
    async with app.run_test(size=(70, 24)) as pilot:
        await pilot.pause(0.3)
        assert app.run_id is None and app.snapshot is None
        assert app.query_one("#wallets", DataTable).row_count == 0
        assert not client.commands
