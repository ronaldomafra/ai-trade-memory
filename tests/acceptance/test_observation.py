import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from test_accounting import NOW, setup

from poc.adapters.inbound.observe import observe, sample_session
from poc.adapters.outbound.session_view import SessionViews
from poc.domain.primitives import DomainError


@pytest.mark.asyncio
async def test_observer_rejects_fixtures_and_never_modifies_or_stops_session(tmp_path):
    cfg, manager, db, trading = setup(tmp_path)
    db.close()
    path = tmp_path / "sessions" / "run-1" / "poc.sqlite3"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(DomainError, match="fixture"):
        sample_session(SessionViews(cfg), "run-1", datetime.now(UTC))
    result = await observe(cfg, ["run-1"], tmp_path / "observation", 0.000001, 1)
    assert result["state"] == "COMPLETED" and result["unavailable_samples"] > 0
    assert result["invariant_failure_samples"] == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert (tmp_path / "observation" / "samples.jsonl").exists()
    with pytest.raises(DomainError, match="new observation"):
        await observe(cfg, ["run-1"], tmp_path / "observation", 0.000001, 1)


def test_observer_ages_quote_after_snapshot_read_without_hiding_genuine_future(
    monkeypatch, tmp_path
):
    import poc.adapters.inbound.observe as module

    cfg, _, db, _ = setup(tmp_path)
    db.close()
    exporter = module.FileExporter.dashboard
    stamp = NOW + timedelta(milliseconds=25)

    def dashboard(self):
        snapshot = exporter(self)
        snapshot["fixture"] = False  # Synthetic snapshot confined to this test.
        snapshot["market"]["quote_observed_at"] = stamp.isoformat()
        snapshot["health"] = {
            "status": "RUNNING",
            "clock_status": "VERIFIED",
            "last_heartbeat": NOW.isoformat(),
        }
        return snapshot

    class Clock:
        @staticmethod
        def now(tz):
            return stamp + timedelta(milliseconds=5)

    monkeypatch.setattr(module.FileExporter, "dashboard", dashboard)
    monkeypatch.setattr(module, "datetime", Clock)
    sample = sample_session(SessionViews(cfg), "run-1")
    assert sample["quote_age_seconds"] == 0.005 and sample["feed_healthy"]
    future = sample_session(SessionViews(cfg), "run-1", NOW)
    assert future["quote_age_seconds"] == -0.025 and not future["feed_healthy"]


def test_observer_records_factor_coverage_without_inventing_availability_or_writing(
    tmp_path, monkeypatch
):
    import poc.adapters.inbound.observe as module

    cfg, _, db, _ = setup(tmp_path)
    db.close()
    exporter = module.FileExporter.dashboard

    def dashboard(self):
        snap = exporter(self)
        snap["fixture"] = False
        snap["external_context"] = {
            "news": {
                "status": "available",
                "coverage": "PARTIAL",
                "items": [{"factor_id": "synthetic-news"}],
            },
            "prediction_markets": {
                "status": "unavailable",
                "coverage": "PARTIAL",
                "items": [],
                "pending": [{"reason": "INSUFFICIENT_DEPTH"}],
                "discovery": {"scope": {"coverage": "ASSET_TAG_ONLY"}},
            },
        }
        return snap

    monkeypatch.setattr(module.FileExporter, "dashboard", dashboard)
    p = tmp_path / "sessions" / "run-1" / "poc.sqlite3"
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    sample = sample_session(SessionViews(cfg), "run-1", NOW)
    assert sample["external_coverage"]["news"]["factor_ids"] == ["synthetic-news"]
    poly = sample["external_coverage"]["prediction_markets"]
    assert poly["usable_factor_count"] == 0 and poly["pending_count"] == 1
    assert poly["status"] == "unavailable" and poly["scope"]["coverage"] == "ASSET_TAG_ONLY"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gap", "reason"),
    [(timedelta(hours=25), "SAMPLING_GAP"), (timedelta(minutes=-5), "CLOCK_MOVED_BACKWARD")],
)
async def test_observer_interrupts_on_suspend_or_clock_jump_without_claiming_24h(
    tmp_path, monkeypatch, gap, reason
):
    import json

    import poc.adapters.inbound.observe as module

    cfg, _, db, _ = setup(tmp_path)
    db.close()
    path = tmp_path / "sessions" / "run-1" / "poc.sqlite3"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    moments = iter([NOW, NOW, NOW + gap])

    class WallClock:
        @staticmethod
        def now(tz):
            return next(moments)

    class ReadOnlyRuntime:
        def __init__(self, *args):
            pass

        async def inspect(self, run_id):
            return {"running": True, "status": "running"}

    async def next_frame(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(module, "datetime", WallClock)
    monkeypatch.setattr(module, "DockerRuntime", ReadOnlyRuntime)
    monkeypatch.setattr(module.asyncio, "wait_for", next_frame)
    # Valid operational samples confined to this test; production rejects fixtures.
    monkeypatch.setattr(
        module, "sample_session", lambda *args: {"invariants_ok": True, "feed_healthy": True}
    )
    result = await observe(cfg, ["run-1"], tmp_path / "observation", 24, 60)
    assert result["state"] == "INTERRUPTED"
    assert result["sample_frames"] == 2
    assert result["interruption"]["reason"] == reason
    assert result["interruption"]["gap_seconds"] == gap.total_seconds()
    assert result["elapsed_seconds"] == max(0, gap.total_seconds())
    stored = json.loads((tmp_path / "observation" / "observation.json").read_text())
    assert stored["state"] == "INTERRUPTED"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
