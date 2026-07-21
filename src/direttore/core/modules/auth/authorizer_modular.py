from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum


class ModularAuthorizationLocationKind(StrEnum):
    """Describes how modular-monolith execution was initiated.

    `USER_REQUEST` means execution entered the modular monolith from an external
    adapter, such as an HTTP endpoint, Telegram command, CLI command, or another
    user-facing boundary.

    `SYSTEM_INVOKE` means execution was initiated by trusted in-process runtime
    code, such as a cross-context invoke from one module to another.

    This is not a transport type. External service-to-service HTTP/gRPC calls
    should be converted by the application into the appropriate auth object or
    treated as system invoke only if the application explicitly trusts that
    boundary.
    """

    USER_REQUEST = "user_request"
    SYSTEM_INVOKE = "system_invoke"


class ModularAuthorizer[AuthT](ABC):
    """Application-specific authorization contract for modular monolith execution.

    This authorizer receives the same authorization inputs as the simple service
    authorizer, plus `location_kind`.

    The location kind allows the application to distinguish direct user-facing
    execution from trusted in-process cross-context execution.

    The framework does not decide what `SYSTEM_INVOKE` means. The application
    must define whether system invokes bypass checks, use a service identity,
    require special tags, or are denied by default.
    """

    @abstractmethod
    def authorize(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
        location_kind: ModularAuthorizationLocationKind,
    ) -> None:
        raise NotImplementedError