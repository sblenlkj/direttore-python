from __future__ import annotations

from direttore.application.simple_service.config import SimpleServiceSlotCreatorConfig
from direttore.application.simple_service.execution_slot import (
    SimpleServiceExecutionSlot,
)
from direttore.application.slot_provider import SlotCreator
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.container import Container
from direttore.core.resolvers.event_handler_resolver import EventHandlerResolver
from direttore.core.resolvers.use_case_handler_resolver import UseCaseHandlerResolver


class SimpleServiceSlotCreator[InputT, TraceT](
    SlotCreator[SimpleServiceExecutionSlot[InputT, TraceT], InputT, TraceT]
):
    """Builds every dependency owned by a simple-service execution slot."""

    def __init__(
        self,
        *,
        config: SimpleServiceSlotCreatorConfig[InputT, TraceT],
        container: Container,
    ) -> None:
        self.config = config
        self.container = container
        self.use_case_resolver = UseCaseHandlerResolver(
            registry=config.handlers.use_case_registry,
            container=container,
        )
        self.event_dispatcher = self._build_event_dispatcher()

    def create_slot(self) -> SimpleServiceExecutionSlot[InputT, TraceT]:
        holder = self.config.slot.resource_holder_factory()
        uow = self.config.slot.uow_factory(holder)
        return SimpleServiceExecutionSlot(
            use_case_resolver=self.use_case_resolver,
            event_dispatcher=self.event_dispatcher,
            resource_holder=holder,
            uow=uow,
            use_case_payload_loader=self.config.use_case_execution.operation_loader,
            span_factory=self.config.span_factory,
            saga_journal=self.config.saga_journal,
            max_processed_events=self.config.use_case_execution.max_processed_events,
        )

    def validate(self) -> None:
        self.use_case_resolver.validate()
        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def _build_event_dispatcher(self) -> SimpleServiceEventDispatcher | None:
        if self.config.handlers.event_registry is None:
            return None
        return SimpleServiceEventDispatcher(
            resolver=EventHandlerResolver(
                registry=self.config.handlers.event_registry,
                container=self.container,
            )
        )
