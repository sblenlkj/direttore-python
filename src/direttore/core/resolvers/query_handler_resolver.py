from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import QueryHandler
from direttore.core.contracts.messages import Query
from direttore.core.primitives.container import Container
from direttore.core.registries.query_handler_registry import (
    QueryHandlerRegistry,
)
from direttore.core.registries.registrations import (
    QueryHandlerRegistration,
)
from direttore.core.resolvers.base_handler_resolver import (
    BaseHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)


class QueryHandlerResolver(
    BaseHandlerResolver[QueryHandlerRegistration, QueryHandler],
):
    def __init__(
        self,
        registry: QueryHandlerRegistry,
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
        query_type: type[Query],
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> ResolvedHandler[QueryHandler, QueryHandlerRegistration]:
        registration = self.registry.get_registration(query_type)

        return super().resolve(
            registration=registration,
            overrides=overrides,
        )

    def resolve_by_key(
        self,
        key: str,
        *,
        overrides: Mapping[type[Any], Any] | None = None,
    ) -> ResolvedHandler[QueryHandler, QueryHandlerRegistration]:
        registration = self.registry.get_registration_by_key(key)

        return super().resolve(
            registration=registration,
            overrides=overrides,
        )

    def _get_handler_type(
        self,
        registration: QueryHandlerRegistration,
    ) -> type[QueryHandler]:
        return registration.handler_type