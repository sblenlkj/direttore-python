from __future__ import annotations

from os import PathLike

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
from direttore.core.resolvers.validation_report import write_validation_report


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

    def validate(
        self,
        validation_results_path: str | PathLike[str] | None = None,
    ) -> None:
        self.use_case_resolver.validate()
        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

        if validation_results_path is None:
            return

        descriptions = self.use_case_resolver.describe_resolutions()
        if self.event_dispatcher is not None:
            descriptions.extend(
                self.event_dispatcher.resolver.describe_resolutions()
            )
        context_names = [
            self.config.handlers.use_case_registry.source_name or "<unnamed>"
        ]
        if self.config.handlers.event_registry is not None:
            context_names.append(
                self.config.handlers.event_registry.source_name or "<unnamed>"
            )
        write_validation_report(
            validation_results_path,
            descriptions,
            context_names=dict.fromkeys(context_names),
        )

    def _build_event_dispatcher(self) -> SimpleServiceEventDispatcher | None:
        if self.config.handlers.event_registry is None:
            return None
        return SimpleServiceEventDispatcher(
            resolver=EventHandlerResolver(
                registry=self.config.handlers.event_registry,
                container=self.container,
            )
        )
