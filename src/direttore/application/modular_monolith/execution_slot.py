from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.application.errors import EventLimitExceededError
from direttore.core.contracts.handlers import (
    QueryHandlerContext,
    UseCaseEventDrainingMode,
    UseCaseHandlerContext,
    UseCaseHandlerExecutionMode,
)
from direttore.core.contracts.messages import Event
from direttore.core.contracts.operation_loader import (
    ModularMonolithOperationLoader,
)
from direttore.core.event_dispatchers.modular_monolith_event_dispatcher import (
    ModularMonolithEventDispatcher,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.resolvers.query_handler_resolver import QueryHandlerResolver
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)
from direttore.core.saga import (
    SagaCompensationContext,
    SagaEntry,
    SagaHandlerKind,
    SagaHandlerResult,
    SagaJournal,
)
from direttore.core.tracing import Span, SpanFactory


class ModularMonolithExecutionSlot(BaseExecutionSlot):
    """Physical modular slot owning routing, runtime, and transactions."""

    def __init__(
        self,
        *,
        use_case_resolver: UseCaseHandlerResolver,
        use_case_uow_routing: UseCaseUowRoutingRegistry,
        resource_holder: ResourceHolder,
        coordinator: ModularUnitOfWorkCoordinator,
        runtime: ModularMonolithExecutionRuntime,
        event_queue: EventQueue,
        query_resolver: QueryHandlerResolver | None = None,
        query_uow_routing: QueryUowRoutingRegistry | None = None,
        event_dispatcher: ModularMonolithEventDispatcher | None = None,
        use_case_payload_loader: ModularMonolithOperationLoader | None = None,
        query_payload_loader: ModularMonolithOperationLoader | None = None,
        span_factory: SpanFactory[object] | None = None,
        saga_journal: SagaJournal | None = None,
        max_processed_events: int = 100,
    ) -> None:
        super().__init__(resource_holder=resource_holder, saga_journal=saga_journal)
        self.use_case_resolver = use_case_resolver
        self.use_case_uow_routing = use_case_uow_routing
        self.query_resolver = query_resolver
        self.query_uow_routing = query_uow_routing
        self.event_dispatcher = event_dispatcher
        self.coordinator = coordinator
        self.runtime = runtime
        self.event_queue = event_queue
        self.use_case_payload_loader = use_case_payload_loader
        self.query_payload_loader = query_payload_loader
        self.span_factory = span_factory
        self.max_processed_events = max_processed_events
        self._after_transaction_events: list[Event] = []
        self._lease_span: Span | None = None

    async def handle(self, *, command, input, trace=None):
        resolved = self.use_case_resolver.resolve(
            type(command), overrides=self.runtime._get_dependency_overrides()
        )
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_by_key(self, key, payload, *, input, trace=None):
        resolved = self.use_case_resolver.resolve_by_key(
            key, overrides=self.runtime._get_dependency_overrides()
        )
        command = self._build_message(resolved.registration.command_type, payload, key)
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_operation(self, operation_id, *, input, trace=None):
        if self.use_case_payload_loader is None:
            raise RuntimeError("Use-case operation loader is not configured.")
        pair = await self.use_case_payload_loader.get_key_payload_pair(
            operation_id, self.coordinator
        )
        return await self.handle_by_key(
            pair.key, pair.payload, input=input, trace=trace
        )

    async def handle_query(self, *, query, input, trace=None):
        resolver, _ = self._require_query_execution()
        resolved = resolver.resolve(
            type(query), overrides=self.runtime._get_dependency_overrides()
        )
        return await self._execute_query(query, resolved, input, trace)

    async def handle_query_by_key(self, key, payload, *, input, trace=None):
        resolver, _ = self._require_query_execution()
        resolved = resolver.resolve_by_key(
            key, overrides=self.runtime._get_dependency_overrides()
        )
        query = self._build_message(resolved.registration.query_type, payload, key)
        return await self._execute_query(query, resolved, input, trace)

    async def handle_query_operation(self, operation_id, *, input, trace=None):
        if self.query_payload_loader is None:
            raise RuntimeError("Query operation loader is not configured.")
        pair = await self.query_payload_loader.get_key_payload_pair(
            operation_id, self.coordinator
        )
        return await self.handle_query_by_key(
            pair.key, pair.payload, input=input, trace=trace
        )

    async def compensate_saga(self, *, saga_id, input, trace=None):
        if self.saga_journal is None:
            raise RuntimeError("SagaJournal is not configured.")
        record = await self.saga_journal.load(saga_id, self.resource_holder)
        async with self._root_span(
            trace=trace,
            name=f"modular.saga.compensate {saga_id}",
            attributes={"saga.id": saga_id},
        ) as span:
            for entry in reversed(record.entries):
                await self._compensate_entry(entry, saga_id, input, span)

    async def _execute_use_case(self, command, resolved, input, trace):
        self.event_queue.clear()
        root_uow = self._use_case_uow(resolved)
        try:
            async with self._root_span(
                trace=trace,
                name=self._span_name("modular.use_case.handle", command),
                attributes=self._span_attributes(command, resolved),
            ) as span:
                lifecycle_context = (
                    await resolved.registration.lifecycle.create_context(
                        input, resolved.registration.config, self.coordinator
                    )
                )
                self.runtime._set_lifecycle_context(lifecycle_context)
                result = await resolved.handler.handle(
                    command,
                    UseCaseHandlerContext(
                        uow=root_uow,
                        queue=self.event_queue,
                        lifecycle_context=lifecycle_context,
                        span=span,
                    ),
                )
                result = self._collect_saga_result(
                    result, resolved.registration, SagaHandlerKind.USE_CASE
                )
                if (
                    resolved.registration.execution_mode
                    is UseCaseHandlerExecutionMode.IN_TRANSACTION
                ):
                    await self._drain_events(
                        span, resolved.registration.event_draining_mode
                    )
                else:
                    while not self.event_queue.is_empty:
                        self._after_transaction_events.append(self.event_queue.pop())
                return result
        finally:
            self.runtime._set_lifecycle_context(None)
            self.event_queue.clear()

    async def _execute_query(self, query, resolved, input, trace):
        root_uow = self._query_uow(resolved)
        try:
            async with self._root_span(
                trace=trace,
                name=self._span_name("modular.query.handle", query),
                attributes=self._span_attributes(query, resolved),
            ) as span:
                lifecycle_context = (
                    await resolved.registration.lifecycle.create_context(
                        input, resolved.registration.config, self.coordinator
                    )
                )
                self.runtime._set_lifecycle_context(lifecycle_context)
                return await resolved.handler.handle(
                    query,
                    QueryHandlerContext(
                        uow=root_uow,
                        lifecycle_context=lifecycle_context,
                        span=span,
                    ),
                )
        finally:
            self.runtime._set_lifecycle_context(None)

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
                self._collect_saga_result(result, registration, SagaHandlerKind.EVENT)
        if not self.event_queue.is_empty:
            await self._drain_events(span, mode)

    async def after_transaction_commit(self) -> None:
        if not self._after_transaction_events:
            return
        events = tuple(self._after_transaction_events)
        self._after_transaction_events.clear()
        await self.resource_holder.close()
        await self.resource_holder.open()
        self.event_queue.push_many(events)
        await self._drain_events(self._lease_span)
        await self._persist_saga_entries()
        await self.resource_holder.commit()

    async def _compensate_entry(self, entry, saga_id, input, span):
        overrides = self.runtime._get_dependency_overrides()
        if entry.kind is SagaHandlerKind.USE_CASE:
            resolved = self.use_case_resolver.resolve_by_saga_key(
                entry.handler_key, overrides=overrides
            )
            uow = self._use_case_uow(resolved)
            lifecycle_context = await resolved.registration.lifecycle.create_context(
                input, resolved.registration.config, self.coordinator
            )
        else:
            if self.event_dispatcher is None:
                raise RuntimeError("Event compensation is not configured.")
            resolved = self.event_dispatcher.resolver.resolve_by_saga_key(
                entry.handler_key, overrides=overrides
            )
            uow = self.event_dispatcher._get_handler_uow(
                resolved_handler_type=resolved.handler_type,
                coordinator=self.coordinator,
            )
            lifecycle_context = None
        compensation_type: Any = resolved.registration.compensation_type
        if compensation_type is None:
            raise RuntimeError("Saga registration has no compensation type.")
        compensation = compensation_type.from_payload(entry.payload)
        compensate = getattr(resolved.handler, "compensate", None)
        if compensate is None:
            raise TypeError("Saga handler has no compensate method.")
        await compensate(
            compensation,
            SagaCompensationContext(
                saga_id=saga_id,
                uow=uow,
                lifecycle_context=lifecycle_context,
                span=span,
            ),
        )

    def _collect_saga_result(self, result, registration, kind):
        if not isinstance(result, SagaHandlerResult):
            return result
        if self.saga_id is not None:
            if registration.saga_key is None or registration.compensation_type is None:
                raise RuntimeError("Compensable registration metadata is incomplete.")
            if not isinstance(result.compensation, registration.compensation_type):
                raise TypeError("Handler returned the wrong compensation type.")
            self.resource_holder.append_saga_entry(
                SagaEntry(
                    kind=kind,
                    handler_key=registration.saga_key,
                    payload=dict(result.compensation.to_payload()),
                )
            )
        return result.result

    def _use_case_uow(self, resolved):
        uow_type = self.use_case_uow_routing.get_uow_type_by_handler_type(
            resolved.handler_type
        )
        return self.coordinator.get_use_case_uow(uow_type)

    def _query_uow(self, resolved):
        _, routing = self._require_query_execution()
        uow_type = routing.get_uow_type_by_handler_type(resolved.handler_type)
        return self.coordinator.get_query_uow(uow_type)

    def _require_query_execution(self):
        if self.query_resolver is None or self.query_uow_routing is None:
            raise RuntimeError("Modular query execution is not configured.")
        return self.query_resolver, self.query_uow_routing

    def reset(self):
        self.runtime._set_lifecycle_context(None)
        self.event_queue.clear()
        self._after_transaction_events.clear()
        self.coordinator.reset()

    async def finish_trace(self) -> None:
        if self._lease_span is None:
            return
        span = self._lease_span
        self._lease_span = None
        await span.__aexit__(None, None, None)

    @staticmethod
    def _build_message(message_type, payload, key):
        try:
            result = message_type.from_payload(payload)
        except Exception as exc:
            raise RuntimeError(f"Failed to build message for key {key!r}.") from exc
        if not isinstance(result, message_type):
            raise TypeError("from_payload returned the wrong message type.")
        return result

    @staticmethod
    def _span_name(operation, message):
        return f"{operation} {type(message).__module__}.{type(message).__qualname__}"

    @staticmethod
    def _span_attributes(message, resolved):
        return {
            "message.type": f"{type(message).__module__}.{type(message).__qualname__}",
            "handler.type": f"{resolved.handler_type.__module__}.{resolved.handler_type.__qualname__}",
            "handler.source_name": resolved.registration.source_name,
            "handler.key": resolved.registration.key,
        }

    @asynccontextmanager
    async def _root_span(
        self, *, trace, name, attributes
    ) -> AsyncGenerator[Span | None]:
        if self.span_factory is None:
            yield None
            return
        if self._lease_span is None:
            self._lease_span = self.span_factory.create_span(
                trace=trace,
                name="modular.slot_lease",
                attributes={"saga.id": self.saga_id},
            )
            await self._lease_span.__aenter__()
        async with self._lease_span.child(
            name=name, attributes=attributes
        ) as operation_span:
            yield operation_span
