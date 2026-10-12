"""Cursor validation for at-least-once delivery of canonical durable events."""

from dataclasses import dataclass

from poc.domain.primitives import DomainError


class ResyncRequired(DomainError):
    pass


@dataclass
class EventCursor:
    run_id: str
    seq: int

    def validate_bounds(self, first: int, last: int) -> None:
        if self.seq > last or (first > 1 and self.seq < first - 1):
            raise ResyncRequired("Cursor is outside retained session history")

    def accept(self, event: dict) -> bool:
        if event["run_id"] != self.run_id:
            raise ResyncRequired("Event belongs to another session")
        seq = event["event_seq"]
        if seq <= self.seq:
            return False
        if seq != self.seq + 1:
            raise ResyncRequired("Durable event sequence has a gap")
        self.seq = seq
        return True
