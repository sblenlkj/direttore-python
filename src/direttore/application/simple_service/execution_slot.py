from __future__ import annotations

import asyncio
from typing import Any

from direttore.application.base_execution_slot import (
    BaseExecutionSlot,
    ResolvedUseCase,
)
from direttore.application.errors import EventLimitExceededError
from direttore.core.contracts.handlers import UseCaseEventDrainingMode
from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.messages import Event, UseCaseCommand
from direttore.core.contracts.operation_loader import OperationLoader
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)
from direttore.core.saga import (
    SagaCompensationContext,
    SagaEntry,
    SagaHandlerKind,
    SagaJournal,
)
from direttore.core.tracing import Span, SpanFactory


class SimpleServiceExecutionSlot[InputT, TraceT](BaseExecutionSlot[InputT, TraceT]):
    """Physical simple-service slot with one application UoW."""

    def __init__(
        self,
        *,
        use_case_resolver: UseCaseHandlerResolver[Lifecycle[InputT | None, Any]],
        resource_holder: ResourceHolder,
        uow: BaseUnitOfWork,
        event_dispatcher: SimpleServiceEventDispatcher | None = None,
        use_case_payload_loader: OperationLoader | None = None,
        span_factory: SpanFactory[TraceT] | None = None,
        saga_journal: SagaJournal | None = None,
        max_processed_events: int = 100,
    ) -> None:
        super().__init__(
            resource_holder=resource_holder,
            operation_loader=use_case_payload_loader,
            span_factory=span_factory,
            saga_journal=saga_journal,
            max_processed_events=max_processed_events,
            execution_name="simple",
        )
        self.use_case_resolver = use_case_resolver
        self.event_dispatcher = event_dispatcher
        self.uow = uow

    def _resolve_command(self, command_type: type[UseCaseCommand]) -> ResolvedUseCase:
        return self.use_case_resolver.resolve(command_type)

    def _resolve_by_key(self, key: str) -> ResolvedUseCase:
        return self.use_case_resolver.resolve_by_key(key)

    def _get_use_case_uow(self, resolved: ResolvedUseCase) -> BaseUnitOfWork:
        return self.uow

    async def _drain_events(
        self,
        span: Span | None,
        mode: UseCaseEventDrainingMode = UseCaseEventDrainingMode.SEQUENTIAL,
    ) -> None:
        if self.event_dispatcher is None:
            self.event_queue.clear()
            return
        events: list[Event] = []
        while not self.event_queue.is_empty:
            if len(events) >= self.max_processed_events:
                raise EventLimitExceededError(
                    f"Event processing limit {self.max_processed_events} exceeded."
                )
            events.append(self.event_queue.pop())
        if mode is UseCaseEventDrainingMode.PARALLEL:
            batches = await asyncio.gather(
                *(
                    self.event_dispatcher.dispatch(
                        event=event,
                        uow=self.uow,
                        span=span,
                    )
                    for event in events
                )
            )
        else:
            batches = []
            for event in events:
                batches.append(
                    await self.event_dispatcher.dispatch(
                        event=event,
                        uow=self.uow,
                        span=span,
                    )
                )
        for batch in batches:
            for result, registration in batch:
                self._collect_event_result(
                    result,
                    registration,
                )
        if not self.event_queue.is_empty:
            await self._drain_events(span, mode)

    async def _compensate_entry(
        self,
        entry: SagaEntry,
        saga_id: str,
        span: Span | None,
    ) -> None:
        if entry.kind is SagaHandlerKind.USE_CASE:
            resolved = self.use_case_resolver.resolve_by_saga_key(entry.handler_key)
        else:
            if self.event_dispatcher is None:
                raise RuntimeError("Event compensation is not configured.")
            resolved = self.event_dispatcher.resolver.resolve_by_saga_key(
                entry.handler_key
            )
        compensation_type = resolved.registration.compensation_type
        if compensation_type is None:
            raise RuntimeError(
                f"Saga handler {entry.handler_key!r} has no compensation type."
            )
        compensation = compensation_type.from_payload(entry.payload)
        compensate = getattr(resolved.handler, "compensate", None)
        if compensate is None:
            raise TypeError(
                f"Saga handler {entry.handler_key!r} has no compensate method."
            )
        await compensate(
            compensation,
            SagaCompensationContext(
                saga_id=saga_id,
                uow=self.uow,
                span=span,
            ),
        )

    def reset(self) -> None:
        try:
            self.event_queue.clear()
        finally:
            self.resource_holder.reset()
