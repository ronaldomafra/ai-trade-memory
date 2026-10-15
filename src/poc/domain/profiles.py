"""Pure profile rules: duration, UTC calendar and common structural entry setup."""

from datetime import datetime, timedelta

from poc.domain.candles import INTERVAL_SECONDS
from poc.domain.primitives import utc


def parameters(config):
    definition = getattr(config, "profile_definition", None)
    return definition.parameters if definition else None


def seconds(config):
    return INTERVAL_SECONDS[config.market.interval]


def boundary(now: datetime, duration: int) -> datetime:
    value = utc(now)
    return datetime.fromtimestamp(int(value.timestamp()) // duration * duration, value.tzinfo)


def age_bars(config, entry_at, now):
    if entry_at is None:
        return 0
    duration = seconds(config)
    if parameters(config):
        return max(0, int((utc(now) - utc(entry_at)).total_seconds() // duration))
    return max(
        0, int(utc(now).timestamp()) // duration - int(utc(entry_at).timestamp()) // duration
    )


def _time(day, value):
    hour, minute, second = map(int, value.split(":"))
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def window(config, now):
    p = parameters(config)
    if p is None or not p.operation_window.enabled:
        return None
    w, now = p.operation_window, utc(now)
    for days in range(8):
        day = now - timedelta(days=days)
        start = _time(day, w.start_utc)
        if start > now or start.weekday() not in w.weekdays_utc:
            continue
        end = _time(day, w.end_utc) + timedelta(days=int(w.end_next_day))
        cutoff = _time(day, w.entry_cutoff_utc) if w.entry_cutoff_utc else end
        flatten = _time(day, w.flatten_utc) if w.flatten_utc else end
        if cutoff < start:
            cutoff += timedelta(days=1)
        if flatten < start:
            flatten += timedelta(days=1)
        return start, cutoff, flatten, end
    return None


def entry_window_open(config, now):
    p = parameters(config)
    if p is None or not p.operation_window.enabled:
        return True
    span = window(config, now)
    return bool(span and span[0] <= utc(now) < span[1])


def scheduled_exit_due(config, entry_at, now):
    p = parameters(config)
    if p is None or not p.operation_window.force_flat_at_end or entry_at is None:
        return False
    span = window(config, entry_at)
    return span is None or utc(now) >= span[2]


def window_seconds(config, now):
    duration = config.strategy.max_holding_candles * seconds(config)
    span = window(config, now)
    p = parameters(config)
    if p and p.operation_window.force_flat_at_end:
        return min(duration, max(0, int((span[2] - utc(now)).total_seconds()))) if span else 0
    return duration


def structural_setup(features):
    return bool(features.valid and getattr(features, "structural_entry_setup", False))


def strategy_context(config, features, now):
    p = parameters(config)
    if p is None:
        return None
    profile = config.profile_definition.profile
    return {
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "style": profile.style,
        "family": profile.strategy_family,
        "interval": config.market.interval,
        "trend_interval": config.market.trend_interval,
        "maximum_holding_seconds": config.strategy.max_holding_candles * seconds(config),
        "operational_window_remaining_seconds": window_seconds(config, now),
        "structural_entry_setup": structural_setup(features),
        "entry_window_open": entry_window_open(config, now),
        "execution_constraints": p.execution_quality.model_dump(mode="json"),
        "decision_deadline_seconds": config.app.max_candle_decision_lag_seconds,
        "action_probability_threshold": config.strategy.action_probability_threshold,
        "action_margin_threshold": config.strategy.action_margin_threshold,
        "risk_parameters": {
            k: str(getattr(config.strategy, k))
            for k in (
                "stop_loss_pct",
                "take_profit_pct",
                "max_allocation_pct",
                "daily_loss_guard_pct",
            )
        },
        "technical_parameters": config.strategy.technical.model_dump(mode="json"),
        "instructions": p.jev_instructions.model_dump(exclude={"max_characters"}),
    }
