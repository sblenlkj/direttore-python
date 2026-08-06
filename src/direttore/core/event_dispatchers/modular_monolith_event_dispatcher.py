from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.core.contracts.handlers import (
    EventHandlerContext,
    SagaEventHandlerResult,
)
from direttore.core.contracts.messages import Event
from direttore.core.event_dispatchers.base_event_dispatcher import (
    BaseEventDispatcher,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.uow_routing_registries.event_uow_routing_registry import (
    EventUowRoutingRegistry,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import EventHandlerRegistration
from direttore.core.resolvers.event_handler_resolver import (
    EventHandlerResolver,
)
from direttore.core.tracing import Span


class ModularMonolithEventDispatcher(BaseEventDispatcher):
    """Event dispatcher for modular monolith execution.

    The dispatcher is stateless.

    The execution slot owns the coordinator and passes it into dispatch(...).
    The coordinator already contains application-specific slot-owned Unit of
    Work objects.

    For each event handler, the dispatcher resolves the handler module/root UoW
    through EventUowRoutingRegistry and gives the handler its own modular UoW
    through EventHandlerContext.
    """

    def __init__(
        self,
        *,
        resolver: EventHandlerResolver,
        event_uow_routing: EventUowRoutingRegistry,
    ) -> None:
        self.resolver = resolver
        self.event_uow_routing = event_uow_routing

    def validate_event_handlers(self) -> None:
        self.resolver.validate()

    async def dispatch(
        self,
        *,
        event: Event,
        coordinator: ModularUnitOfWorkCoordinator,
        overrides: Mapping[type[Any], Any] | None = None,
        span: Span | None = None,
    ) -> list[tuple[SagaEventHandlerResult | None, EventHandlerRegistration]]:
        resolved_handlers = self.resolver.resolve(
            type(event),
            overrides=overrides,
        )
        results: list[
            tuple[SagaEventHandlerResult | None, EventHandlerRegistration]
        ] = []

        for resolved in resolved_handlers:
            uow = self._get_handler_uow(
                resolved_handler_type=resolved.handler_type,
                coordinator=coordinator,
            )

            if span is None:
                result = await resolved.handler.handle(
                    event,
                    EventHandlerContext(
                        uow=uow,
                        span=None,
                    ),
                )
                results.append((result, resolved.registration))
                continue

            async with span.child(
                name=self._build_span_name(
                    event=event,
                    handler_type=resolved.handler_type,
                ),
                attributes=self._build_span_attributes(
                    event=event,
                    handler_type=resolved.handler_type,
                    source_name=resolved.registration.source_name,
                ),
            ) as child:
                result = await resolved.handler.handle(
                    event,
                    EventHandlerContext(
                        uow=uow,
                        span=child,
                    ),
                )
                results.append((result, resolved.registration))

        return results

    def _get_handler_uow(
        self,
        *,
        resolved_handler_type: type[Any],
        coordinator: ModularUnitOfWorkCoordinator,
    ) -> BaseUnitOfWork:
        root_uow_type = self.event_uow_routing.get_uow_type_by_handler_type(
            resolved_handler_type,
        )

        return coordinator.get_use_case_uow(root_uow_type)
