from __future__ import annotations

from typing import Any, cast

from direttore.core.engines.base_engine import BaseEngine
from direttore.core.modular_monolith_support.execution_dependencies import (
    ModularMonolithExecutionDependencyContext,
    ModularMonolithExecutionDependencyRegistry,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modules.auth import (
    AuthenticationContext,
    Authenticator,
    ContextAuthenticator,
    ModularAuthorizationLocationKind,
    ModularAuthorizer,
)
from direttore.core.primitives.uow import BaseUnitOfWork


class BaseModularMonolithEngine[AuthInputT, AuthT, TraceT](BaseEngine):
    def __init__(
        self,
        *,
        authorizer: ModularAuthorizer[AuthT] | None = None,
    ) -> None:
        self.authorizer = authorizer

    async def _authenticate_without_context(
        self,
        *,
        authenticator: Authenticator[AuthInputT, AuthT] | None,
        auth_input: AuthInputT | None,
    ) -> AuthT | None:
        if authenticator is None:
            return None

        return await authenticator.authenticate(
            cast(AuthInputT, auth_input),
        )

    async def _authenticate_with_context(
        self,
        *,
        authenticator: ContextAuthenticator[AuthInputT, AuthT, Any],
        auth_input: AuthInputT | None,
        uow: BaseUnitOfWork,
    ) -> AuthT:
        return await authenticator.authenticate(
            auth_input=cast(AuthInputT, auth_input),
            context=AuthenticationContext(uow=uow),
        )

    def _authorize_user_request(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
    ) -> None:
        if self.authorizer is None:
            return

        self.authorizer.authorize(
            allowed_access_tags=allowed_access_tags,
            auth=auth,
            location_kind=ModularAuthorizationLocationKind.USER_REQUEST,
        )

    def _authorize_system_invoke(
        self,
        *,
        allowed_access_tags: frozenset[str] | None,
        auth: AuthT | None,
    ) -> None:
        if self.authorizer is None:
            return

        self.authorizer.authorize(
            allowed_access_tags=allowed_access_tags,
            auth=auth,
            location_kind=ModularAuthorizationLocationKind.SYSTEM_INVOKE,
        )

    def _is_context_authenticator(
        self,
        authenticator: (
            Authenticator[AuthInputT, AuthT]
            | ContextAuthenticator[AuthInputT, AuthT, Any]
            | None
        ),
    ) -> bool:
        return isinstance(authenticator, ContextAuthenticator)

    def _build_dependency_overrides(
        self,
        *,
        runtime: ModularMonolithExecutionRuntime[AuthT, TraceT],
        dependency_registry: ModularMonolithExecutionDependencyRegistry | None,
    ) -> dict[type[Any], Any] | None:
        if dependency_registry is None:
            return None

        return dict(
            dependency_registry.build_overrides(
                context=ModularMonolithExecutionDependencyContext(
                    runtime=runtime,
                ),
            )
        )