"""Terminal charts use Decimal coordinates; financial data stays exact."""

from decimal import Decimal

from rich.text import Text
from textual.widgets import Static


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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.candles = []

    def set_candles(self, candles: list[dict]):
        self.candles = candles
        self.refresh()

    def render(self):
        width = max(10, self.size.width - 15)
        candles = self.candles[-width:]
        if not candles:
            return Text("Aguardando candles fechados de 15m.", style="dim")
        low = min(Decimal(candle["low"]) for candle in candles)
        high = max(Decimal(candle["high"]) for candle in candles)
        height = 10
        scale = high - low or Decimal(1)

        def y(price):
            return height - 1 - int((Decimal(price) - low) / scale * (height - 1))

        rows = []
        for row in range(height):
            text = Text(f"{high - Decimal(row) / (height - 1) * scale:>12.2f} ", style="dim")
            for candle in candles:
                body_top, body_bottom = sorted((y(candle["open"]), y(candle["close"])))
                color = (
                    "#00ff9f" if Decimal(candle["close"]) >= Decimal(candle["open"]) else "#ff5b6e"
                )
                char = (
                    "█"
                    if body_top <= row <= body_bottom
                    else ("│" if y(candle["high"]) <= row <= y(candle["low"]) else " ")
                )
                text.append(char, style=color)
            rows.append(text)
        rows.append(
            Text(
                f"{candles[0]['open_time_utc'][5:16]} → {candles[-1]['open_time_utc'][5:16]} UTC",
                style="dim",
            )
        )
        return Text("\n").join(rows)
