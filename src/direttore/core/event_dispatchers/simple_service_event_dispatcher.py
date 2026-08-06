from __future__ import annotations

from direttore.core.contracts.handlers import (
    EventHandlerContext,
    SagaEventHandlerResult,
)
from direttore.core.contracts.messages import Event
from direttore.core.event_dispatchers.base_event_dispatcher import (
    BaseEventDispatcher,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import EventHandlerRegistration
from direttore.core.resolvers.event_handler_resolver import (
    EventHandlerResolver,
)
from direttore.core.tracing import Span


class SimpleServiceEventDispatcher(BaseEventDispatcher):
    def __init__(
        self,
        *,
        resolver: EventHandlerResolver,
    ) -> None:
        self.resolver = resolver

    def validate_event_handlers(self) -> None:
        self.resolver.validate()

    async def dispatch(
        self,
        *,
        event: Event,
        uow: BaseUnitOfWork,
        span: Span | None = None,
    ) -> list[tuple[SagaEventHandlerResult | None, EventHandlerRegistration]]:
        resolved_handlers = self.resolver.resolve(type(event))
        results: list[
            tuple[SagaEventHandlerResult | None, EventHandlerRegistration]
        ] = []

        for resolved in resolved_handlers:
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
