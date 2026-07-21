from __future__ import annotations

from typing import Any, cast

from direttore.core.engines.base_engine import BaseEngine
from direttore.core.modules.auth import (
    AuthenticationContext,
    Authenticator,
    Authorizer,
    ContextAuthenticator,
)
from direttore.core.primitives.uow import BaseUnitOfWork


class BaseSimpleServiceEngine[AuthInputT, AuthT](BaseEngine):
    def __init__(
        self,
        *,
        authorizer: Authorizer[AuthT] | None = None,
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

    def _authorize(
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