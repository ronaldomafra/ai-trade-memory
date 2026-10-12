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
