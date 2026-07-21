from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthenticationContext[UnitOfWorkT]:
    uow: UnitOfWorkT


class Authenticator[AuthInputT, AuthT](ABC):
    """Stateless authentication contract.

    The engine calls this authenticator before opening ResourceHolder.

    Use it for authentication that does not need execution resources:

    - JWT verification;
    - signed API tokens;
    - Telegram init data signature;
    - already resolved auth objects;
    - test auth fixtures.

    Implementations should return the resolved auth object or raise an
    application-specific authentication exception.
    """

    @abstractmethod
    async def authenticate(
        self,
        auth_input: AuthInputT,
    ) -> AuthT:
        raise NotImplementedError


class ContextAuthenticator[
    AuthInputT,
    AuthT,
    UnitOfWorkT,
](ABC):
    """Resource-backed authentication contract.

    The engine calls this authenticator inside an opened ResourceHolder scope.

    Use it for authentication that needs current execution resources:

    - session token lookup in DB;
    - API key lookup in DB;
    - login/password verification;
    - user loading from repository;
    - Redis-backed session validation.

    The authenticator receives the current UoW through AuthenticationContext.
    """

    @abstractmethod
    async def authenticate(
        self,
        *,
        auth_input: AuthInputT,
        context: AuthenticationContext[UnitOfWorkT],
    ) -> AuthT:
        raise NotImplementedError