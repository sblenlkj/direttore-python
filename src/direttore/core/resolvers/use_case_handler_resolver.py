from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import UseCaseHandler
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.primitives.container import Container
from direttore.core.registries.registrations import (
    UseCaseHandlerRegistration,
)
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.resolvers.base_handler_resolver import (
    BaseHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)


class UseCaseHandlerResolver(
    BaseHandlerResolver[UseCaseHandlerRegistration, UseCaseHandler],
):
    def __init__(
        self,
        registry: UseCaseHandlerRegistry,
        container: Container,
        *,
        execution_dependency_types: set[type[Any]] | None = None,
        warm_up: bool = True,
        validate: bool = True,
    ) -> None:
        super().__init__(
            container=container,
            execution_dependency_types=execution_dependency_types or set(),
        )
        self.registry = registry

        if validate:
            self.validate()

        if warm_up:
            self.warm_up_cache(
                registrations=self.registry.iter_registrations(),
            )

    def validate(self) -> None:
        self.validate_handlers(
            registrations=self.registry.iter_registrations(),
        )

    def resolve(
        self,
        command_type: type[UseCaseCommand],
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> ResolvedHandler[UseCaseHandler, UseCaseHandlerRegistration]:
        registration = self.registry.get_registration(command_type)

        return super().resolve_registration(
            registration=registration,
            overrides=overrides,
        )

    def resolve_by_key(
        self,
        key: str,
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> ResolvedHandler[UseCaseHandler, UseCaseHandlerRegistration]:
        registration = self.registry.get_registration_by_key(key)

        return super().resolve_registration(
            registration=registration,
            overrides=overrides,
        )

    def _get_handler_type(
        self,
        registration: UseCaseHandlerRegistration,
    ) -> type[UseCaseHandler]:
        return registration.handler_type
