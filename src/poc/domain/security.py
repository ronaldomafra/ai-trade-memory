"""A remote client's authorization is independent from engine lifecycle."""

from dataclasses import dataclass
from datetime import datetime

from poc.domain.primitives import DomainError, utc


class AuthenticationError(DomainError):
    pass


class PermissionDenied(DomainError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    scopes: tuple[str, ...]
    sessions: tuple[str, ...]
    expires_at: datetime
    token_family: str

    def require(self, scope: str, run_id: str | None = None):
        if scope not in self.scopes:
            raise PermissionDenied("Token does not permit this action")
        if run_id is not None and "*" not in self.sessions and run_id not in self.sessions:
            raise PermissionDenied("Token does not permit this session")

    def current(self, now: datetime):
        if utc(now) >= utc(self.expires_at):
            raise AuthenticationError("Authentication expired")
