from poc.domain.models import Quote
from poc.domain.primitives import DomainError, utc


def prefer_quote(previous: Quote | None, incoming: Quote) -> Quote:
    if previous is None:
        return incoming
    if incoming.symbol != previous.symbol:
        raise DomainError("Quote symbol differs from active market")
    if (
        incoming.update_id is not None
        and previous.update_id is not None
        and incoming.update_id <= previous.update_id
    ):
        return previous
    if utc(incoming.observed_at) <= utc(previous.observed_at):
        return previous
    if incoming.request_started_at is not None and (
        utc(incoming.request_started_at) < utc(previous.observed_at)
    ):
        return previous
    if (
        incoming.event_at is not None
        and previous.event_at is not None
        and utc(incoming.event_at) < utc(previous.event_at)
    ):
        return previous
    return incoming
