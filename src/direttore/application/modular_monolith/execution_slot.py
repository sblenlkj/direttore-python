from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
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
from direttore.core.event_dispatchers.modular_monolith_event_dispatcher import (
    ModularMonolithEventDispatcher,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.primitives.event_queue import EventQueue
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


class ModularMonolithExecutionSlot[InputT, TraceT](BaseExecutionSlot[InputT, TraceT]):
    """Physical modular slot with bounded-context UoW routing."""

    def __init__(
        self,
        *,
        use_case_resolver: UseCaseHandlerResolver[Lifecycle[InputT | None, Any]],
        use_case_uow_routing: UseCaseUowRoutingRegistry,
        resource_holder: ResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        event_dispatcher: ModularMonolithEventDispatcher | None = None,
        use_case_payload_loader: OperationLoader | None = None,
        span_factory: SpanFactory[TraceT] | None = None,
        saga_journal: SagaJournal | None = None,
        max_processed_events: int = 100,
    ) -> None:
        super().__init__(
            resource_holder=resource_holder,
            event_queue=event_queue,
            operation_loader=use_case_payload_loader,
            span_factory=span_factory,
            saga_journal=saga_journal,
            max_processed_events=max_processed_events,
            execution_name="modular",
        )
        self.use_case_resolver = use_case_resolver
        self.use_case_uow_routing = use_case_uow_routing
        self.event_dispatcher = event_dispatcher
        self.coordinator = coordinator
        self.runtime = runtime

    def _resolve_command(self, command_type: type[UseCaseCommand]) -> ResolvedUseCase:
        return self.use_case_resolver.resolve(
            command_type,
            overrides=self.runtime._get_dependency_overrides(),
        )

    def _resolve_by_key(self, key: str) -> ResolvedUseCase:
        return self.use_case_resolver.resolve_by_key(
            key,
            overrides=self.runtime._get_dependency_overrides(),
        )

    def _get_use_case_uow(self, resolved: ResolvedUseCase) -> BaseUnitOfWork:
        uow_type = self.use_case_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type
        )
        return self.coordinator.get_use_case_uow(uow_type)

    @asynccontextmanager
    async def _use_case_execution(
        self,
        lifecycle_context: object | None,
    ) -> AsyncGenerator[None]:
        self.event_queue.clear()
        self.runtime._set_lifecycle_context(lifecycle_context)
        try:
            yield
        finally:
            self.runtime._set_lifecycle_context(None)
            self.event_queue.clear()

    async def _drain_events(
        self,
        span: Span | None,
        mode: UseCaseEventDrainingMode = UseCaseEventDrainingMode.SEQUENTIAL,
    ) -> None:
        if self.event_dispatcher is None:
            self.event_queue.clear()
            return
        event_dispatcher = self.event_dispatcher
        events: list[Event] = []
        while not self.event_queue.is_empty:
            if len(events) >= self.max_processed_events:
                raise EventLimitExceededError(
                    f"Event processing limit {self.max_processed_events} exceeded."
                )
            events.append(self.event_queue.pop())

        def dispatch(event: Event):
            return event_dispatcher.dispatch(
                event=event,
                coordinator=self.coordinator,
                overrides=self.runtime._get_dependency_overrides(),
                span=span,
            )

        if mode is UseCaseEventDrainingMode.PARALLEL:
            batches = await asyncio.gather(*(dispatch(event) for event in events))
        else:
            batches = [await dispatch(event) for event in events]
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
        overrides = self.runtime._get_dependency_overrides()
        if entry.kind is SagaHandlerKind.USE_CASE:
            resolved = self.use_case_resolver.resolve_by_saga_key(
                entry.handler_key,
                overrides=overrides,
            )
            uow = self._get_use_case_uow(resolved)
        else:
            if self.event_dispatcher is None:
                raise RuntimeError("Event compensation is not configured.")
            resolved = self.event_dispatcher.resolver.resolve_by_saga_key(
                entry.handler_key,
                overrides=overrides,
            )
            uow = self.event_dispatcher._get_handler_uow(
                resolved_handler_type=resolved.handler_type,
                coordinator=self.coordinator,
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
                uow=uow,
                span=span,
            ),
        )

    def reset(self) -> None:
        try:
            self.runtime._set_lifecycle_context(None)
            self.event_queue.clear()
            self.coordinator.reset()
        finally:
            self.resource_holder.reset()
