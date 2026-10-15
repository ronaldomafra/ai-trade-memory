"""UI fixtures only: no server mutations, inference or operational database writes."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from test_tui import FixtureClient
from textual.widgets import Select, Static

from poc.adapters.inbound.tui import TradeApp
from poc.adapters.inbound.tui_charts import CandleChart
from poc.adapters.inbound.tui_presenters import (
    STRATEGIES,
    cycle_groups,
    decision_summary,
    source_summary,
    technical_summary,
    update_source_records,
)

NOW = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def decision(identity, cycle="new", at=NOW, action="HOLD", **overrides):
    return {
        "decision_id": cycle + identity,
        "cycle_id": cycle,
        "portfolio_id": identity,
        "decision_at": at.isoformat(),
        "decision_started_at": at.isoformat(),
        "status": "COMPLETED",
        "proposed_action": action,
        "approved_action": action,
        "executed_action": action,
        "reason_code": "HOLD" if identity == "BASELINE_TECHNICAL" else "JEV_CHOICE",
        "state_json": json.dumps(
            {
                "portfolio": {"has_position": False},
                "market": {
                    "valid": True,
                    "as_of": at.isoformat(),
                    "rsi_14": 37.6,
                    "trend_1h": "bearish",
                    "macd_histogram": -1.5,
                    "volume_ratio": 2,
                    "ema_short": 2500,
                    "ema_mid": 2505,
                    "ema_long": 2510,
                    "atr_pct": 0.3,
                },
                "historical_feedback": {"status": "insufficient_samples"},
            }
        ),
        **overrides,
    }


def factor(identity="old", observed=NOW, **overrides):
    return {
        "factor_id": identity,
        "available_at": observed.isoformat(),
        "source_observed_at": observed.isoformat(),
        "valid_until": (observed + timedelta(minutes=10)).isoformat(),
        "evidence": {
            "title": identity + " [red]texto literal[/red]",
            "source": "fixture",
            "published_at": observed.isoformat(),
            "excerpt": "Resumo publicado.",
        },
        "impact_direction": "UNDETERMINED",
        "classification_confidence": "UNDETERMINED",
        **overrides,
    }


def candles():
    return [
        {
            "open_time_utc": (NOW + timedelta(minutes=15 * n)).isoformat(),
            "close_time_exclusive_utc": (NOW + timedelta(minutes=15 * (n + 1))).isoformat(),
            "open": "2500",
            "high": "2520",
            "low": "2490",
            "close": "2510",
            "volume": "10",
        }
        for n in range(3)
    ]


def test_decision_summary_preserves_blocked_proposal_and_incomplete_cycle():
    rows = [
        decision(
            "JEV_STATIC",
            proposed_action="BUY",
            executed_action="HOLD",
            approved_action="HOLD",
            reason_code="STALE_QUOTE",
            probabilities_json='{"buy":"0.8","sell":"0.1","hold":"0.1"}',
        ),
        decision("JEV_LEARNING", status="PROPOSED"),
    ]
    text = decision_summary(rows).plain
    assert "proposta BUY → executada HOLD" in text
    assert "Cotação desatualizada" in text and "BUY 80.0%" in text
    assert "COMPROU" not in text
    assert text.count("Aguardando conclusão") == 2
    assert "RSI: 37.6" in technical_summary(rows).plain
    assert "Tendência 1h: baixa" in technical_summary(rows).plain
    bad = decision("BASELINE_TECHNICAL", state_json="invalid")
    assert "indisponíveis" in technical_summary([bad]).plain


def test_source_uses_latest_observed_record_and_labels_retained_history():
    old, new = factor(), factor("new", NOW + timedelta(minutes=1))
    snapshot = {"external_context": {"news": {"status": "available", "items": [old, new]}}}
    records = update_source_records(snapshot, {})
    assert records["news"]["item"]["factor_id"] == "new"
    text = source_summary("news", records["news"], snapshot["external_context"]["news"], NOW).plain
    assert "new [red]texto literal[/red]" in text
    assert "Impacto classificado: indeterminada" in text
    unavailable = {"status": "unavailable", "items": []}
    retained = update_source_records({"external_context": {"news": unavailable}}, records)
    assert retained == records
    stale = source_summary("news", retained["news"], unavailable, NOW).plain
    assert "REGISTRO ANTERIOR" in stale and "Fonte agora: unavailable" in stale
    expired = source_summary(
        "news", records["news"], snapshot["external_context"]["news"], NOW + timedelta(hours=1)
    ).plain
    assert "REGISTRO ANTERIOR" in expired
    poly = factor(
        question="Ethereum acima de X?",
        implied_probability="0.97",
        outcome="Yes",
        spread_pp="0.9",
        probability_changes={"5m": {"status": "AVAILABLE", "change_pp": "-0.4"}},
    )
    text = source_summary(
        "prediction_markets", {"item": poly}, {"status": "available", "items": [poly]}, NOW
    ).plain
    assert "97.0%" in text and "5m -0.40 pp" in text and "60m indisponível" in text


@pytest.mark.asyncio
async def test_dashboard_full_width_history_selection_and_sources_independent_of_cycle():
    client = FixtureClient()
    snapshot = client.snapshots["fixture-eth"]
    snapshot["chart_candles"] = candles()
    old_time = NOW - timedelta(minutes=15)
    old = [decision(k, "old", old_time) for k in STRATEGIES]
    newest = [decision(k) for k in STRATEGIES]
    old_state = json.loads(old[0]["state_json"])
    old_state["market"]["rsi_14"] = 51
    old[0]["state_json"] = json.dumps(old_state)
    snapshot["recent_decisions"] = newest + old
    item = factor("latest-news", NOW + timedelta(minutes=5))
    snapshot["external_context"] = {"news": {"status": "available", "items": [item]}}
    app = TradeApp(client)
    async with app.run_test(size=(150, 65)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#sessions", Select).value = "fixture-eth"
        await pilot.pause(0.3)
        assert app.query_one("#price-panel").size.width > 140
        chart_region = app.query_one("#price-panel").region
        wallets_region = app.query_one("#wallet-panel").region
        equity_region = app.query_one("#equity-panel").region
        assert chart_region.bottom <= wallets_region.y
        assert wallets_region.y == equity_region.y
        assert wallets_region.right < equity_region.x
        assert "amostras insuficientes" in app.query_one("#cycle-summary", Static).render().plain
        assert app.query_one("#cycle-progress", Static).render().plain == ""
        assert "RSI: 37.6" in app.query_one("#cycle-indicators", Static).render().plain
        app.query_one("#cycle-selector", Select).value = "old"
        await pilot.pause()
        assert "RSI: 51.0" in app.query_one("#cycle-indicators", Static).render().plain
        assert "latest-news" in app.query_one("#news-summary", Static).render().plain
        # Refresh does not move a selected historical cycle or regress the latest source.
        updated = deepcopy(snapshot)
        updated["recent_decisions"] = (
            [
                decision(
                    "BASELINE_TECHNICAL", "pending", NOW + timedelta(minutes=15), status="PROPOSED"
                )
            ]
            + newest
            + old
        )
        app.render_snapshot(updated)
        await pilot.pause()
        assert app.selected_cycle == "old"
        chart = app.query_one("#price-chart", CandleChart)
        chart.post_message(CandleChart.CycleSelected("new"))
        await pilot.pause()
        assert app.selected_cycle == "new"
        app.query_one("#cycle-selector", Select).value = "latest"
        await pilot.pause()
        assert "Aguardando conclusão" in app.query_one("#cycle-summary", Static).render().plain
        assert "JEV escolheu" not in app.query_one("#cycle-summary", Static).render().plain
        assert "em processamento" in app.query_one("#cycle-progress", Static).render().plain
        await pilot.resize_terminal(70, 25)
        await pilot.pause()
        assert app.query_one("#sources-grid").has_class("narrow")
        assert app.query_one("#price-panel").size.width > 60
        assert app.query_one("#balances-grid").has_class("narrow")
        assert (
            app.query_one("#wallet-panel").region.bottom <= app.query_one("#equity-panel").region.y
        )
        app.query_one("#sessions", Select).value = "fixture-btc"
        await pilot.pause(0.3)
        assert not app.source_records
        assert "latest-news" not in app.query_one("#news-summary", Static).render().plain
        assert not app.selected_cycle
        assert not client.commands


@pytest.mark.asyncio
async def test_chart_marks_only_confirmed_fills_and_keeps_after_close_events_separate():
    client = FixtureClient()
    snapshot = client.snapshots["fixture-eth"]
    snapshot["chart_candles"] = candles()
    during = NOW + timedelta(minutes=2)
    after = NOW + timedelta(minutes=45, seconds=1)
    snapshot["recent_decisions"] = [
        decision("JEV_STATIC", "cycle", during, proposed_action="BUY", reason_code="STALE_QUOTE")
    ]
    common = {
        "filled_at": during.isoformat(),
        "fill_price": "2512",
        "qty_base": "0.01",
        "side": "BUY",
        "realized_pnl_usdt": None,
        "cycle_id": "cycle",
    }
    snapshot["recent_fills"] = [
        {**common, "fill_id": "fill-B", "portfolio_id": "JEV_STATIC"},
        {**common, "fill_id": "fill-C", "portfolio_id": "JEV_LEARNING"},
        {
            **common,
            "fill_id": "after",
            "portfolio_id": "BASELINE_TECHNICAL",
            "side": "SELL",
            "filled_at": after.isoformat(),
        },
    ]
    app = TradeApp(client)
    async with app.run_test(size=(140, 65)) as pilot:
        await pilot.pause(0.2)
        app.query_one("#sessions", Select).value = "fixture-eth"
        await pilot.pause(0.3)
        chart = app.query_one("#price-chart", CandleChart)
        bars, visible, pending = chart.visible_records()
        assert len([m for m in visible if m["kind"] == "cycle"]) == 1
        assert len([m for m in visible if m["kind"] == "BUY"]) == 2
        assert {m["wallet"] for m in pending} == {"A"}
        assert "Após último candle fechado" in chart.render().plain
        assert chart.click_cycles
        await pilot.click(chart, offset=next(iter(chart.click_cycles)))
        await pilot.pause()
        assert app.selected_cycle == "cycle"
        same_wallet = [
            {**common, "fill_id": "buy", "portfolio_id": "JEV_STATIC"},
            {**common, "fill_id": "sell", "portfolio_id": "JEV_STATIC", "side": "SELL"},
        ]
        chart.set_records(candles(), snapshot["recent_decisions"], same_wallet)
        assert "◆" in chart.render().plain
        # A recorded BUY proposal without a fill must never draw a BUY marker.
        chart.set_records(candles(), snapshot["recent_decisions"], [])
        assert all(m["kind"] == "cycle" for m in chart.markers)
        assert list(cycle_groups(snapshot["recent_decisions"])) == ["cycle"]
        assert not client.commands
