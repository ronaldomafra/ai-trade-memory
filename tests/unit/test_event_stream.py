import asyncio

import pytest

from poc.adapters.inbound.event_ws import send_bounded
from poc.application.event_stream import EventCursor, ResyncRequired


def test_durable_cursor_dedup_gap_wrong_identity_and_pruned_history():
    cursor = EventCursor("run", 10)
    cursor.validate_bounds(1, 15)
    assert not cursor.accept({"run_id": "run", "event_seq": 10})
    assert cursor.accept({"run_id": "run", "event_seq": 11})
    with pytest.raises(ResyncRequired):
        cursor.accept({"run_id": "run", "event_seq": 13})
    with pytest.raises(ResyncRequired):
        cursor.accept({"run_id": "other", "event_seq": 12})
    with pytest.raises(ResyncRequired):
        cursor.validate_bounds(13, 20)
    with pytest.raises(ResyncRequired):
        cursor.validate_bounds(1, 10)


@pytest.mark.asyncio
async def test_slow_stream_sender_is_cancelled_instead_of_building_a_queue(monkeypatch):
    cancelled = asyncio.Event()

    class SlowSocket:
        async def send_text(self, text):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    real_wait = asyncio.wait_for

    async def short_wait(task, timeout):
        assert timeout == 2
        return await real_wait(task, timeout=0.01)

    monkeypatch.setattr("poc.adapters.inbound.event_ws.asyncio.wait_for", short_wait)
    with pytest.raises(TimeoutError):
        await send_bounded(SlowSocket(), {"type": "event"})
    assert cancelled.is_set()
