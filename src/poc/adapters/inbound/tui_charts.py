"""Terminal charts use Decimal coordinates; financial data stays exact."""

from decimal import Decimal

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static

from poc.adapters.inbound.tui_presenters import STRATEGIES, cycle_groups, cycle_time, timestamp


def spark(values: list[str], width: int = 60) -> str:
    if not values:
        return "Sem observações"
    values = [Decimal(value) for value in values[-max(1, width) :]]
    lower, upper = min(values), max(values)
    steps = "▁▂▃▄▅▆▇█"
    return "".join(
        steps[3 if upper == lower else int((value - lower) / (upper - lower) * 7)]
        for value in values
    )


class CandleChart(Static):
    """Markers refer to evaluation/fill timestamps, never inferred or proposed fills."""

    class CycleSelected(Message):
        def __init__(self, cycle_id: str):
            super().__init__()
            self.cycle_id = cycle_id

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.candles = []
        self.markers = []
        self.selected_cycle = None
        self.click_cycles = {}

    def set_candles(self, candles: list[dict]):
        self.set_records(candles, [], [])

    def set_records(self, candles, decisions, fills, selected_cycle=None):
        self.candles = candles
        self.selected_cycle = selected_cycle
        self.markers = []
        for identity, rows in cycle_groups(decisions).items():
            if any(row.get("status") == "COMPLETED" for row in rows):
                self.markers.append({"kind": "cycle", "cycle_id": identity, "at": cycle_time(rows)})
        seen = set()
        for fill in fills:
            if not fill.get("fill_id") or fill["fill_id"] in seen:
                continue
            seen.add(fill["fill_id"])
            if fill.get("side") in ("BUY", "SELL"):
                self.markers.append(
                    {
                        "kind": fill["side"],
                        "cycle_id": fill.get("cycle_id"),
                        "at": fill.get("filled_at"),
                        "price": fill["fill_price"],
                        "wallet": STRATEGIES.get(fill.get("portfolio_id"), "?"),
                    }
                )
        self.refresh()

    def on_click(self, event: events.Click):
        identity = self.click_cycles.get((event.x, event.y))
        if identity:
            self.post_message(self.CycleSelected(identity))

    def visible_records(self):
        width = max(1, self.content_size.width - 14)
        candles = self.candles[-width:]
        visible, pending = [], []
        if candles:
            end = timestamp(candles[-1]["close_time_exclusive_utc"])
            for marker in self.markers:
                stamp = timestamp(marker.get("at"))
                if not stamp:
                    continue
                if end and stamp >= end:
                    pending.append(marker)
                    continue
                for x, candle in enumerate(candles):
                    start = timestamp(candle["open_time_utc"])
                    stop = timestamp(candle["close_time_exclusive_utc"])
                    if start and stop and start <= stamp < stop:
                        visible.append({**marker, "x": x})
                        break
        return candles, visible, pending

    def render(self):
        candles, markers, pending = self.visible_records()
        self.click_cycles = {}
        if not candles:
            return Text("Aguardando candles fechados do perfil.", style="dim")
        prices = [Decimal(marker["price"]) for marker in markers if "price" in marker]
        low = min([Decimal(candle["low"]) for candle in candles] + prices)
        high = max([Decimal(candle["high"]) for candle in candles] + prices)
        height = 10
        scale = high - low or Decimal(1)

        def y(price):
            return height - 1 - int((Decimal(price) - low) / scale * (height - 1))

        rows = []
        fills = [m for m in markers if m["kind"] != "cycle"]
        cells = {}
        for marker in fills:
            cells.setdefault((marker["x"], y(marker["price"])), []).append(marker)
        for row in range(height):
            text = Text(f"{high - Decimal(row) / (height - 1) * scale:>12.2f} ", style="dim")
            for x, candle in enumerate(candles):
                body_top, body_bottom = sorted((y(candle["open"]), y(candle["close"])))
                color = (
                    "#00ff9f" if Decimal(candle["close"]) >= Decimal(candle["open"]) else "#ff5b6e"
                )
                char = (
                    "█"
                    if body_top <= row <= body_bottom
                    else ("│" if y(candle["high"]) <= row <= y(candle["low"]) else " ")
                )
                plotted = cells.get((x, row), [])
                if plotted:
                    sides = {m["kind"] for m in plotted}
                    char = "▲" if sides == {"BUY"} else "▼" if sides == {"SELL"} else "◆"
                    color = (
                        "#00ff9f"
                        if sides == {"BUY"}
                        else "#ff5b6e"
                        if sides == {"SELL"}
                        else "magenta"
                    )
                text.append(char, style=color)
            rows.append(text)
        # Separate lanes keep cycle and per-wallet identities readable when fills coincide.
        for lane in ("Ciclos", "A", "B", "C"):
            text = Text(f"{lane:>12} ", style="cyan")
            for x in range(len(candles)):
                matching = [
                    m
                    for m in markers
                    if m["x"] == x
                    and (m["kind"] == "cycle" if lane == "Ciclos" else m.get("wallet") == lane)
                ]
                char, color = " ", "dim"
                if matching:
                    if lane == "Ciclos":
                        active = next(
                            (m for m in matching if m["cycle_id"] == self.selected_cycle), None
                        )
                        char, color = ("◎", "white") if active else ("●", "cyan")
                    else:
                        sides = {m["kind"] for m in matching}
                        char = "▲" if sides == {"BUY"} else "▼" if sides == {"SELL"} else "◆"
                        color = (
                            "#00ff9f"
                            if sides == {"BUY"}
                            else "#ff5b6e"
                            if sides == {"SELL"}
                            else "magenta"
                        )
                    identity = matching[-1].get("cycle_id")
                    if identity:
                        self.click_cycles[(13 + x, len(rows))] = identity
                text.append(char, style=color)
            rows.append(text)
        rows.append(
            Text(
                f"{candles[0]['open_time_utc'][5:16]} → {candles[-1]['open_time_utc'][5:16]} UTC",
                style="dim",
            )
        )
        rows.append(
            Text(
                "● avaliação · ▲ compra · ▼ venda · ◆ coincidência · "
                "clique nas faixas A/B/C ou Ciclos",
                style="dim",
            )
        )
        if pending:
            labels = []
            for marker in pending[-8:]:
                stamp = timestamp(marker["at"]).strftime("%H:%M:%S")
                label = (
                    "● ciclo"
                    if marker["kind"] == "cycle"
                    else (("▲" if marker["kind"] == "BUY" else "▼") + marker.get("wallet", "?"))
                )
                labels.append(f"{label} {stamp}")
            rows.append(
                Text("Após último candle fechado (UTC): " + " · ".join(labels), style="yellow")
            )
        rows.append(
            Text(
                "Marcadores limitados aos registros recentes recebidos; "
                "● indica o instante da avaliação.",
                style="dim",
            )
        )
        return Text("\n").join(rows)
