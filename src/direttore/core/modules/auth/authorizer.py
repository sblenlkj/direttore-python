from __future__ import annotations

from abc import ABC, abstractmethod


class Authorizer[AuthT](ABC):
    """Application-specific authorization contract for simple service execution.

    The engine calls `authorize()` before executing a handler.

    The framework passes only:

    - `allowed_access_tags` from handler config;
    - resolved `auth` object.

    `allowed_access_tags` is a set of plain strings.

    The application decides what every case means:

    - `allowed_access_tags is None`;
    - `allowed_access_tags` is empty;
    - `auth is None`;
    - which fields inside `auth` represent roles, permissions, scopes, tenants,
      or access tags;
    - which exception type should be raised when access is denied.

    Implementations should return normally when access is allowed and raise an
    application-specific exception when access must be denied.
    """

    @abstractmethod
    def authorize(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
    ) -> None:
        raise NotImplementedError