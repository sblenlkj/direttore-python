from __future__ import annotations

from direttore.core.contracts.handlers import EventHandlerContext
from direttore.core.contracts.messages import Event
from direttore.core.event_dispatchers.base_event_dispatcher import (
    BaseEventDispatcher,
)
from direttore.core.tracing import TraceSpan, Tracer
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.resolvers.event_handler_resolver import (
    EventHandlerResolver,
)


class SimpleServiceEventDispatcher[TraceT](BaseEventDispatcher):
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
        context: EventHandlerContext[BaseUnitOfWork],
        trace: TraceT | None = None,
        tracer: Tracer[TraceT] | None = None,
        parent_span: TraceSpan | None = None,
    ) -> None:
        resolved_handlers = self.resolver.resolve(type(event))

        for resolved in resolved_handlers:
            if tracer is None:
                await resolved.handler(
                    event,
                    context,
                )
                continue

            async with tracer.start_span(
                trace=trace,
                name=self._build_span_name(
                    event=event,
                    handler_type=resolved.handler_type,
                ),
                attributes=self._build_span_attributes(
                    event=event,
                    handler_type=resolved.handler_type,
                    source_name=resolved.registration.source_name,
                ),
                parent_span=parent_span,
            ):
                await resolved.handler(
                    event,
                    context,
                )