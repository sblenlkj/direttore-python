from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import EventHandler
from direttore.core.contracts.messages import Event
from direttore.core.primitives.container import Container
from direttore.core.registries.event_handler_registry import (
    EventHandlerRegistry,
)
from direttore.core.registries.registrations import (
    EventHandlerRegistration,
)
from direttore.core.resolvers.base_handler_resolver import (
    BaseHandlerResolver,
)
from direttore.core.resolvers.resolved_handlers import (
    ResolvedHandler,
)


class EventHandlerResolver(
    BaseHandlerResolver[EventHandlerRegistration, EventHandler],
):
    def __init__(
        self,
        registry: EventHandlerRegistry,
        container: Container,
        *,
        execution_dependency_types: set[type[Any]] | None = None,
        warm_up: bool = True,
        validate: bool = True,
        ready_only: bool = True,
    ) -> None:
        super().__init__(
            container=container,
            execution_dependency_types=execution_dependency_types or set(),
        )
        self.registry = registry
        self.ready_only = ready_only

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
        event_type: type[Event],
        *,
        overrides: Mapping[type[Any], Any] | None = None,
        ready_only: bool | None = None,
    ) -> list[ResolvedHandler[EventHandler, EventHandlerRegistration]]:
        registrations = self.registry.get_registrations(
            event_type,
            ready_only=self.ready_only if ready_only is None else ready_only,
        )

        resolved_handlers: list[
            ResolvedHandler[EventHandler, EventHandlerRegistration]
        ] = []

        for registration in registrations:
            resolved_handlers.append(
                super().resolve_registration(
                    registration=registration,
                    overrides=overrides,
                )
            )

        return resolved_handlers

    def _get_handler_type(
        self,
        registration: EventHandlerRegistration,
    ) -> type[EventHandler]:
        return registration.handler_type
