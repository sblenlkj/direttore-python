from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
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
from direttore.core.contracts.messages import Event, Query, UseCaseCommand
from direttore.core.contracts.operation_loader import (
    SimpleServiceOperationLoader,
)
from direttore.core.event_dispatchers.simple_service_event_dispatcher import (
    SimpleServiceEventDispatcher,
)
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.resolvers.query_handler_resolver import QueryHandlerResolver
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
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


class SimpleServiceExecutionSlot(BaseExecutionSlot):
    """Physical simple-service slot owning the complete execution scope."""

    def __init__(
        self,
        *,
        use_case_resolver: UseCaseHandlerResolver,
        resource_holder: ResourceHolder,
        uow: BaseUnitOfWork,
        query_resolver: QueryHandlerResolver | None = None,
        event_dispatcher: SimpleServiceEventDispatcher | None = None,
        use_case_payload_loader: SimpleServiceOperationLoader | None = None,
        query_payload_loader: SimpleServiceOperationLoader | None = None,
        span_factory: SpanFactory[object] | None = None,
        saga_journal: SagaJournal | None = None,
        max_processed_events: int = 100,
    ) -> None:
        super().__init__(
            resource_holder=resource_holder,
            saga_journal=saga_journal,
        )
        self.use_case_resolver = use_case_resolver
        self.query_resolver = query_resolver
        self.event_dispatcher = event_dispatcher
        self.uow = uow
        self.use_case_payload_loader = use_case_payload_loader
        self.query_payload_loader = query_payload_loader
        self.span_factory = span_factory
        self.max_processed_events = max_processed_events
        self.event_queue = EventQueue()
        self._after_transaction_events: list[Event] = []
        self._lease_span: Span | None = None

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        input: object,
        trace: object | None = None,
    ) -> Any:
        resolved = self.use_case_resolver.resolve(type(command))
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        resolved = self.use_case_resolver.resolve_by_key(key)
        command = self._build_message(resolved.registration.command_type, payload, key)
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        if self.use_case_payload_loader is None:
            raise RuntimeError("Use-case operation loader is not configured.")
        pair = await self.use_case_payload_loader.get_key_payload_pair(
            operation_id, self.uow
        )
        return await self.handle_by_key(
            pair.key, pair.payload, input=input, trace=trace
        )

    async def handle_query(
        self,
        *,
        query: Query,
        input: object,
        trace: object | None = None,
    ) -> Any:
        resolver = self._require_query_resolver()
        resolved = resolver.resolve(type(query))
        return await self._execute_query(query, resolved, input, trace)

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        resolver = self._require_query_resolver()
        resolved = resolver.resolve_by_key(key)
        query = self._build_message(resolved.registration.query_type, payload, key)
        return await self._execute_query(query, resolved, input, trace)

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        if self.query_payload_loader is None:
            raise RuntimeError("Query operation loader is not configured.")
        pair = await self.query_payload_loader.get_key_payload_pair(
            operation_id, self.uow
        )
        return await self.handle_query_by_key(
            pair.key, pair.payload, input=input, trace=trace
        )

    async def compensate_saga(
        self,
        *,
        saga_id: str,
        input: object,
        trace: object | None = None,
    ) -> None:
        if self.saga_journal is None:
            raise RuntimeError("SagaJournal is not configured.")
        record = await self.saga_journal.load(saga_id, self.resource_holder)
        async with self._root_span(
            trace=trace,
            name=f"simple.saga.compensate {saga_id}",
            attributes={"saga.id": saga_id},
        ) as span:
            for entry in reversed(record.entries):
                await self._compensate_entry(entry, saga_id, input, span)

    async def _execute_use_case(
        self,
        command: UseCaseCommand,
        resolved: ResolvedHandler,
        input: object,
        trace: object | None,
    ) -> Any:
        self.event_queue.clear()
        try:
            async with self._root_span(
                trace=trace,
                name=self._span_name("simple.use_case.handle", command),
                attributes=self._span_attributes(command, resolved),
            ) as span:
                lifecycle_context = (
                    await resolved.registration.lifecycle.create_context(
                        input, resolved.registration.config, self.uow
                    )
                )
                result = await resolved.handler.handle(
                    command,
                    UseCaseHandlerContext(
                        uow=self.uow,
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
                        span,
                        resolved.registration.event_draining_mode,
                    )
                else:
                    while not self.event_queue.is_empty:
                        self._after_transaction_events.append(self.event_queue.pop())
                return result
        finally:
            self.event_queue.clear()

    async def _execute_query(
        self,
        query: Query,
        resolved: ResolvedHandler,
        input: object,
        trace: object | None,
    ) -> Any:
        async with self._root_span(
            trace=trace,
            name=self._span_name("simple.query.handle", query),
            attributes=self._span_attributes(query, resolved),
        ) as span:
            lifecycle_context = await resolved.registration.lifecycle.create_context(
                input, resolved.registration.config, self.uow
            )
            return await resolved.handler.handle(
                query,
                QueryHandlerContext(
                    uow=self.uow,
                    lifecycle_context=lifecycle_context,
                    span=span,
                ),
            )

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
                    self.event_dispatcher.dispatch(event=event, uow=self.uow, span=span)
                    for event in events
                )
            )
        else:
            batches = []
            for event in events:
                batches.append(
                    await self.event_dispatcher.dispatch(
                        event=event, uow=self.uow, span=span
                    )
                )
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

    async def _compensate_entry(
        self,
        entry: SagaEntry,
        saga_id: str,
        input: object,
        span: Span | None,
    ) -> None:
        if entry.kind is SagaHandlerKind.USE_CASE:
            resolved = self.use_case_resolver.resolve_by_saga_key(entry.handler_key)
            lifecycle_context = await resolved.registration.lifecycle.create_context(
                input, resolved.registration.config, self.uow
            )
        else:
            if self.event_dispatcher is None:
                raise RuntimeError("Event compensation is not configured.")
            resolved = self.event_dispatcher.resolver.resolve_by_saga_key(
                entry.handler_key
            )
            lifecycle_context = None
        compensation_type = resolved.registration.compensation_type
        if compensation_type is None:
            raise RuntimeError(
                f"Saga handler {entry.handler_key!r} has no compensation type."
            )
        compensation = compensation_type.from_payload(entry.payload)  # type: ignore[attr-defined]
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
                lifecycle_context=lifecycle_context,
                span=span,
            ),
        )

    def _collect_saga_result(
        self,
        result: Any,
        registration: Any,
        kind: SagaHandlerKind,
    ) -> Any:
        if not isinstance(result, SagaHandlerResult):
            return result
        if self.saga_id is not None:
            if registration.saga_key is None or registration.compensation_type is None:
                raise RuntimeError(
                    "A SagaHandlerResult requires saga_key and compensation_type metadata."
                )
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

    def reset(self) -> None:
        self.event_queue.clear()
        self._after_transaction_events.clear()

    async def finish_trace(self) -> None:
        if self._lease_span is None:
            return
        span = self._lease_span
        self._lease_span = None
        await span.__aexit__(None, None, None)

    def _require_query_resolver(self) -> QueryHandlerResolver:
        if self.query_resolver is None:
            raise RuntimeError("Simple-service query execution is not configured.")
        return self.query_resolver

    @staticmethod
    def _build_message(message_type, payload, key):
        try:
            result = message_type.from_payload(payload)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to build message for handler key {key!r}."
            ) from exc
        if not isinstance(result, message_type):
            raise TypeError("from_payload returned the wrong message type.")
        return result

    @staticmethod
    def _span_name(operation: str, message: object) -> str:
        return f"{operation} {type(message).__module__}.{type(message).__qualname__}"

    @staticmethod
    def _span_attributes(message: object, resolved: ResolvedHandler) -> dict[str, Any]:
        return {
            "message.type": f"{type(message).__module__}.{type(message).__qualname__}",
            "handler.type": f"{resolved.handler_type.__module__}.{resolved.handler_type.__qualname__}",
            "handler.source_name": resolved.registration.source_name,
            "handler.key": resolved.registration.key,
        }

    @asynccontextmanager
    async def _root_span(
        self,
        *,
        trace: object | None,
        name: str,
        attributes: Mapping[str, Any],
    ) -> AsyncGenerator[Span | None]:
        if self.span_factory is None:
            yield None
            return
        if self._lease_span is None:
            self._lease_span = self.span_factory.create_span(
                trace=trace,
                name="simple.slot_lease",
                attributes={"saga.id": self.saga_id},
            )
            await self._lease_span.__aenter__()
        async with self._lease_span.child(
            name=name, attributes=attributes
        ) as operation_span:
            yield operation_span
