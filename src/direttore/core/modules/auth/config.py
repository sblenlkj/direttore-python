from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from direttore.core.modules.auth.authenticator import (
    Authenticator,
    ContextAuthenticator,
)
from direttore.core.modules.auth.authorizer import (
    Authorizer,
)
from direttore.core.modules.auth.authorizer_modular import (
    ModularAuthorizer,
)
from direttore.core.primitives.uow import (
    BaseUnitOfWork,
)


@dataclass(frozen=True)
class SimpleServiceAuthConfig[
    AuthInputT,
    AuthT,
]:
    """Stateless authentication configuration for simple-service execution.

    Authentication is performed before the execution ResourceHolder is opened.

    Use this configuration for authentication mechanisms that do not require
    execution-scoped resources, for example:

    - JWT signature and claims validation;
    - signed API tokens;
    - Telegram init-data verification;
    - already resolved principals;
    - test authenticators.

    The authorizer is mandatory. Applications that intentionally allow every
    authenticated caller should provide an explicit allow-all authorizer.
    """

    authenticator: Authenticator[
        AuthInputT,
        AuthT,
    ]

    authorizer: Authorizer[
        AuthT,
    ]


@dataclass(frozen=True)
class SimpleServiceSessionAuthConfig[
    AuthInputT,
    AuthT,
]:
    """Resource-backed authentication for simple-service execution.

    Authentication is performed inside the opened ResourceHolder scope.

    The authenticator receives the current simple-service root Unit of Work
    through AuthenticationContext. The configuration does not contain a UoW
    type because simple-service execution has exactly one current root UoW.

    Use this configuration for:

    - database-backed session validation;
    - API-key lookup in a database;
    - login/password verification;
    - user lookup through a repository;
    - Redis-backed session validation.
    """

    authenticator: ContextAuthenticator[
        AuthInputT,
        AuthT,
        BaseUnitOfWork,
    ]

    authorizer: Authorizer[
        AuthT,
    ]


@dataclass(frozen=True)
class ModularMonolithAuthConfig[
    AuthInputT,
    AuthT,
]:
    """Stateless authentication configuration for modular-monolith execution.

    Authentication is performed before the execution ResourceHolder is opened.

    The modular authorizer additionally receives the execution location kind,
    allowing it to distinguish an external USER_REQUEST from an internal
    SYSTEM_INVOKE.
    """

    authenticator: Authenticator[
        AuthInputT,
        AuthT,
    ]

    authorizer: ModularAuthorizer[
        AuthT,
    ]


@dataclass(frozen=True)
class ModularMonolithSessionAuthConfig[
    AuthInputT,
    AuthT,
]:
    """Resource-backed authentication for modular-monolith execution.

    Authentication is performed inside an opened ResourceHolder scope.

    A modular execution slot can contain multiple Unit of Work instances.
    Consequently, the authentication UoW cannot be inferred from the current
    handler and must be selected explicitly for use-case and query execution.

    The configured UoW instances are resolved through the modular Unit of Work
    coordinator. They share the execution ResourceHolder with the handler UoW,
    while exposing a separate authentication-oriented repository contract.
    """

    authenticator: ContextAuthenticator[
        AuthInputT,
        AuthT,
        Any, #TODO return BaseUnitOfWork
    ]

    authorizer: ModularAuthorizer[
        AuthT,
    ]

    use_case_uow_type: type[
        BaseUnitOfWork
    ]

    query_uow_type: type[
        BaseUnitOfWork
    ] | None = None

    def __post_init__(self) -> None:
        if not issubclass(
            self.use_case_uow_type,
            BaseUnitOfWork,
        ):
            raise TypeError(
                "use_case_uow_type must inherit "
                "from BaseUnitOfWork."
            )

        if (
            self.query_uow_type is not None
            and not issubclass(
                self.query_uow_type,
                BaseUnitOfWork,
            )
        ):
            raise TypeError(
                "query_uow_type must inherit "
                "from BaseUnitOfWork."
            )