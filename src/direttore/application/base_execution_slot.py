from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from direttore.core.contracts.handlers import (
    SagaEventHandlerResult,
    SagaUseCaseHandlerResult,
    UseCaseEventDrainingMode,
    UseCaseHandler,
    UseCaseHandlerContext,
    UseCaseHandlerExecutionMode,
    UseCaseHandlerResult,
)
from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.messages import (
    Event,
    EventCompensation,
    UseCaseCommand,
    UseCaseCommandCompensation,
)
from direttore.core.contracts.operation_loader import OperationLoader
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.registrations import (
    EventHandlerRegistration,
    UseCaseHandlerRegistration,
)
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
from direttore.core.saga import (
    SagaEntry,
    SagaHandlerKind,
    SagaJournal,
    SagaRecord,
)
from direttore.core.tracing import Span, SpanFactory

type UseCaseRegistration = UseCaseHandlerRegistration[Lifecycle[Any, Any]]
type ResolvedUseCase = ResolvedHandler[UseCaseHandler, UseCaseRegistration]
type CompensableRegistration = UseCaseRegistration | EventHandlerRegistration


class BaseExecutionSlot[InputT, TraceT](ABC):
    """Shared use-case execution and resource boundary for physical slots."""

    def __init__(
        self,
        *,
        resource_holder: ResourceHolder,
        event_queue: EventQueue | None = None,
        operation_loader: OperationLoader | None = None,
        span_factory: SpanFactory[TraceT] | None = None,
        saga_journal: SagaJournal | None = None,
        max_processed_events: int = 100,
        execution_name: str = "direttore",
    ) -> None:
        self.resource_holder = resource_holder
        self.event_queue = event_queue if event_queue is not None else EventQueue()
        self.operation_loader = operation_loader
        self.span_factory = span_factory
        self.saga_journal = saga_journal

        self.max_processed_events = max_processed_events
        self.execution_name = execution_name
        self.generation = 0
        self._in_use = False

    @property
    def is_in_use(self) -> bool:
        return self._in_use

    async def prepare_slot(self, *, saga_id: str | None = None) -> int:
        if self._in_use:
            raise RuntimeError("Execution slot is already in use.")
        if self.resource_holder.has_open_resources:
            raise RuntimeError(
                "Resource holder was not reset after its previous scope."
            )
        self.generation += 1
        self._in_use = True
        self.resource_holder.saga_id = saga_id
        return self.generation

    async def handle(
        self,
        *,
        command: UseCaseCommand,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> UseCaseHandlerResult:
        command, resolved = await self._prepare_handle(command)
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> UseCaseHandlerResult:
        command, resolved = await self._prepare_handle_by_key(key, payload)
        return await self._execute_use_case(command, resolved, input, trace)

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> UseCaseHandlerResult:
        async with self._root_span(
            trace=trace,
            name=f"{self.execution_name}.use_case.handle_operation {operation_id}",
            attributes={"operation.id": operation_id},
        ) as span:
            command, resolved = await self._prepare_handle_operation(
                operation_id,
                span,
            )
            lifecycle_context = await self._create_lifecycle_context(
                resolved,
                input,
                span,
            )
            async with self._use_case_execution(lifecycle_context):
                return await self._invoke_use_case(
                    command,
                    resolved,
                    lifecycle_context=lifecycle_context,
                    span=span,
                )

    async def _prepare_handle(
        self,
        command: UseCaseCommand,
    ) -> tuple[UseCaseCommand, ResolvedUseCase]:
        return command, self._resolve_command(type(command))

    async def _prepare_handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
    ) -> tuple[UseCaseCommand, ResolvedUseCase]:
        resolved = self._resolve_by_key(key)
        command = self._build_message(resolved.registration.command_type, payload, key)
        return command, resolved

    async def _prepare_handle_operation(
        self,
        operation_id: int | str,
        span: Span | None,
    ) -> tuple[UseCaseCommand, ResolvedUseCase]:
        if self.operation_loader is None:
            raise RuntimeError("Use-case operation loader is not configured.")
        pair = await self.operation_loader.get_key_payload_pair(
            operation_id,
            self.resource_holder,
            span,
        )
        return await self._prepare_handle_by_key(pair.key, pair.payload)

    async def _execute_use_case(
        self,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
        input: InputT | None,
        trace: TraceT | None,
    ) -> UseCaseHandlerResult:
        async with self._root_span(
            trace=trace,
            name=self._span_name(f"{self.execution_name}.use_case.handle", command),
            attributes=self._span_attributes(command, resolved),
        ) as span:
            lifecycle_context = await self._create_lifecycle_context(
                resolved,
                input,
                span,
            )
            async with self._use_case_execution(lifecycle_context):
                return await self._invoke_use_case(
                    command,
                    resolved,
                    lifecycle_context=lifecycle_context,
                    span=span,
                )

    async def _create_lifecycle_context(
        self,
        resolved: ResolvedUseCase,
        input: InputT | None,
        span: Span | None,
    ) -> object | None:
        lifecycle = resolved.registration.lifecycle
        if lifecycle is None:
            return None
        return await lifecycle.create_context(
            input,
            resolved.registration.config,
            self.resource_holder,
            span,
        )

    async def _invoke_use_case(
        self,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
        *,
        lifecycle_context: object | None,
        span: Span | None,
    ) -> UseCaseHandlerResult:
        result = await resolved.handler.handle(
            command,
            UseCaseHandlerContext(
                uow=self._get_use_case_uow(resolved),
                queue=self.event_queue,
                lifecycle_context=lifecycle_context,
                span=span,
            ),
        )
        result = self._collect_use_case_result(
            result,
            resolved.registration,
        )
        if (
            resolved.registration.execution_mode
            is UseCaseHandlerExecutionMode.IN_TRANSACTION
        ):
            await self._drain_events(
                span,
                resolved.registration.event_draining_mode,
            )

        await self.commit(span)

        if (
            resolved.registration.execution_mode
            is UseCaseHandlerExecutionMode.AFTER_TRANSACTION
        ):
            await self._drain_events_after_transaction(
                span,
                resolved.registration.event_draining_mode,
            )

        return result

    async def compensate_saga(
        self,
        *,
        saga_id: str,
        trace: TraceT | None = None,
    ) -> None:
        if self.saga_journal is None:
            raise RuntimeError("SagaJournal is not configured.")
        async with self._root_span(
            trace=trace,
            name=f"{self.execution_name}.saga.compensate {saga_id}",
            attributes={"saga.id": saga_id},
        ) as span:
            record = await self.saga_journal.load(
                saga_id,
                self.resource_holder,
                span,
            )
            for entry in reversed(record.entries):
                await self._compensate_entry(entry, saga_id, span)
            await self.commit(span)

    def _collect_use_case_result(
        self,
        result: UseCaseHandlerResult | SagaUseCaseHandlerResult,
        registration: UseCaseRegistration,
    ) -> UseCaseHandlerResult:
        if not isinstance(result, SagaUseCaseHandlerResult):
            return result
        self._append_saga_compensation(
            compensation=result.compensation,
            registration=registration,
            kind=SagaHandlerKind.USE_CASE,
        )
        return result.result

    def _collect_event_result(
        self,
        result: SagaEventHandlerResult | None,
        registration: EventHandlerRegistration,
    ) -> None:
        if result is None:
            return
        self._append_saga_compensation(
            compensation=result.compensation,
            registration=registration,
            kind=SagaHandlerKind.EVENT,
        )

    def _append_saga_compensation(
        self,
        *,
        compensation: UseCaseCommandCompensation | EventCompensation,
        registration: CompensableRegistration,
        kind: SagaHandlerKind,
    ) -> None:
        if self.resource_holder.saga_id is None:
            return
        if registration.saga_key is None or registration.compensation_type is None:
            raise RuntimeError(
                "A saga handler result requires saga_key and compensation_type "
                "metadata."
            )
        if not isinstance(compensation, registration.compensation_type):
            raise TypeError("Handler returned the wrong compensation type.")
        self.resource_holder.append_saga_entry(
            SagaEntry(
                kind=kind,
                handler_key=registration.saga_key,
                payload=dict(compensation.to_payload()),
            )
        )

    async def commit(self, span: Span | None = None) -> None:
        self._ensure_in_use()
        await self._persist_saga_entries(span)
        await self.resource_holder.commit()

    async def rollback(self) -> None:
        self._ensure_in_use()
        await self.resource_holder.rollback()

    async def _drain_events_after_transaction(
        self,
        span: Span | None,
        mode: UseCaseEventDrainingMode,
    ) -> None:
        events: list[Event] = []
        while not self.event_queue.is_empty:
            events.append(self.event_queue.pop())
        if not events:
            return
        saga_id = self.resource_holder.saga_id
        try:
            await self.resource_holder.close()
        finally:
            self.resource_holder.reset()
        self.resource_holder.saga_id = saga_id
        self.event_queue.push_many(events)
        await self._drain_events(span, mode)
        await self._persist_saga_entries(span)
        await self.resource_holder.commit()

    async def finish_slot(self) -> None:
        try:
            if not self.resource_holder.is_finalized:
                await self.resource_holder.rollback()
        finally:
            try:
                await self.resource_holder.close()
            finally:
                try:
                    self.reset()
                finally:
                    self._in_use = False

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    async def _persist_saga_entries(self, span: Span | None) -> None:
        entries = self.resource_holder.saga_entries
        if not entries:
            return
        saga_id = self.resource_holder.saga_id
        if saga_id is None:
            self.resource_holder.clear_saga_entries()
            return
        if self.saga_journal is None:
            raise RuntimeError(
                "Saga entries were collected but no SagaJournal is configured."
            )
        await self.saga_journal.save(
            SagaRecord(saga_id=saga_id, entries=entries),
            self.resource_holder,
            span,
        )

    @staticmethod
    def _build_message(
        message_type: type[UseCaseCommand],
        payload: Mapping[str, Any],
        key: str,
    ) -> UseCaseCommand:
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
    def _span_attributes(
        message: object,
        resolved: ResolvedUseCase,
    ) -> dict[str, Any]:
        return {
            "message.type": f"{type(message).__module__}.{type(message).__qualname__}",
            "handler.type": (
                f"{resolved.handler_type.__module__}."
                f"{resolved.handler_type.__qualname__}"
            ),
            "handler.source_name": resolved.registration.source_name,
            "handler.key": resolved.registration.key,
        }

    @asynccontextmanager
    async def _use_case_execution(
        self,
        lifecycle_context: object | None,
    ) -> AsyncGenerator[None]:
        self.event_queue.clear()
        try:
            yield
        finally:
            self.event_queue.clear()

    @asynccontextmanager
    async def _root_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: Mapping[str, Any],
    ) -> AsyncGenerator[Span | None]:
        if self.span_factory is None:
            yield None
            return
        span = self.span_factory.create_span(
            trace=trace,
            name=name,
            attributes=attributes,
        )
        async with span as operation_span:
            yield operation_span

    def _ensure_in_use(self) -> None:
        if not self._in_use:
            raise RuntimeError("Execution slot is not in use.")

    @abstractmethod
    def _resolve_command(self, command_type: type[UseCaseCommand]) -> ResolvedUseCase:
        raise NotImplementedError

    @abstractmethod
    def _resolve_by_key(self, key: str) -> ResolvedUseCase:
        raise NotImplementedError

    @abstractmethod
    def _get_use_case_uow(self, resolved: ResolvedUseCase) -> BaseUnitOfWork:
        raise NotImplementedError

    @abstractmethod
    async def _drain_events(
        self,
        span: Span | None,
        mode: UseCaseEventDrainingMode = UseCaseEventDrainingMode.SEQUENTIAL,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def _compensate_entry(
        self,
        entry: SagaEntry,
        saga_id: str,
        span: Span | None,
    ) -> None:
        raise NotImplementedError
