from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from direttore.application.base_execution_slot import (
    BaseExecutionSlot,
    ResolvedUseCase,
)
from direttore.core.contracts.handlers import UseCaseHandlerContext
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.tracing import Span


@dataclass(slots=True)
class SlotExecutionCache:
    lifecycle_context: object | None = None
    span: Span | None = None
    is_initialized: bool = False


class SlotLeaseError(RuntimeError):
    pass


class StaleSlotLeaseError(SlotLeaseError):
    pass


class ConcurrentSlotLeaseUseError(SlotLeaseError):
    pass


class SlotLeaseStateError(SlotLeaseError):
    pass


class SlotLeaseState(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"


type SlotReleaseCallback[InputT, TraceT] = Callable[
    [BaseExecutionSlot[InputT, TraceT]], Awaitable[None]
]


class SlotLease[InputT, TraceT]:
    """Generation-checked, sequential ownership of a physical slot."""

    def __init__(
        self,
        *,
        slot: BaseExecutionSlot[InputT, TraceT],
        generation: int,
        release_callback: SlotReleaseCallback[InputT, TraceT],
    ) -> None:
        self._slot = slot
        self._generation = generation
        self._release_callback = release_callback
        self._state = SlotLeaseState.ACTIVE
        self._released = False
        self._busy = False
        self._execution_cache = SlotExecutionCache()

    @property
    def state(self) -> SlotLeaseState:
        return self._state

    @property
    def saga_id(self) -> str | None:
        return self._slot.resource_holder.saga_id

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> Any:
        async with self._operation():
            command, resolved = await self._slot._prepare_handle(command)
            return await self._execute_with_new_cache(
                command,
                resolved,
                input=input,
                trace=trace,
            )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> Any:
        async with self._operation():
            command, resolved = await self._slot._prepare_handle_by_key(key, payload)
            return await self._execute_with_new_cache(
                command,
                resolved,
                input=input,
                trace=trace,
            )

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
    ) -> Any:
        async with self._operation():
            return await self._execute_operation_with_new_cache(
                operation_id,
                input=input,
                trace=trace,
            )

    async def handle_cache(self, command: UseCaseCommand) -> Any:
        async with self._operation():
            self._ensure_cache_initialized()
            command, resolved = await self._slot._prepare_handle(command)
            return await self._execute_with_cache(command, resolved)

    async def handle_by_key_cache(
        self,
        key: str,
        payload: Mapping[str, Any],
    ) -> Any:
        async with self._operation():
            self._ensure_cache_initialized()
            command, resolved = await self._slot._prepare_handle_by_key(key, payload)
            return await self._execute_with_cache(command, resolved)

    async def handle_operation_cache(self, operation_id: int | str) -> Any:
        async with self._operation():
            self._ensure_cache_initialized()
            command, resolved = await self._slot._prepare_handle_operation(
                operation_id,
                self._execution_cache.span,
            )
            return await self._execute_with_cache(command, resolved)

    async def compensate_saga(
        self,
        saga_id: str,
        *,
        trace: TraceT | None = None,
    ) -> None:
        async with self._operation():
            await self._finish_execution_cache()
            journal = self._slot.saga_journal
            if journal is None:
                raise RuntimeError("SagaJournal is not configured.")
            span = await self._start_span(
                trace=trace,
                name=f"{self._slot.execution_name}.saga.compensate {saga_id}",
                attributes={"saga.id": saga_id},
            )
            self._execution_cache.span = span
            record = await journal.load(
                saga_id,
                self._slot.resource_holder,
                span,
            )
            for entry in reversed(record.entries):
                await self._slot._compensate_entry(entry, saga_id, span)

    async def commit(self) -> None:
        self._begin_operation()
        try:
            await self._slot.commit(self._execution_cache.span)
            self._state = SlotLeaseState.COMMITTED
        finally:
            self._busy = False

    async def rollback(self) -> None:
        self._begin_operation()
        try:
            await self._slot.rollback()
        finally:
            self._busy = False

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[SlotLease[InputT, TraceT]]:
        self._ensure_executable()
        try:
            yield self
        except BaseException:
            if (
                self._state is SlotLeaseState.ACTIVE
                and not self._slot.resource_holder.is_finalized
            ):
                await self.rollback()
            raise
        else:
            if (
                self._state is SlotLeaseState.ACTIVE
                and not self._slot.resource_holder.is_finalized
            ):
                await self.commit()

    async def release(self) -> None:
        if self._released:
            return
        self._validate_current()
        if self._busy:
            raise ConcurrentSlotLeaseUseError(
                "Cannot release a SlotLease while an operation is running."
            )
        if not self._slot.resource_holder.is_finalized:
            await self._slot.rollback()
        await self._finish_execution_cache()
        await self._release_callback(self._slot)
        self._released = True

    async def __aenter__(self) -> SlotLease[InputT, TraceT]:
        self._ensure_executable()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        await self.release()
        return False

    async def _execute_with_new_cache(
        self,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
        *,
        input: InputT | None,
        trace: TraceT | None,
    ) -> Any:
        await self._finish_execution_cache()
        span = await self._start_operation_span(
            command=command,
            resolved=resolved,
            trace=trace,
        )
        lifecycle_context = await self._slot._create_lifecycle_context(
            resolved,
            input,
            span,
        )
        self._execution_cache.lifecycle_context = lifecycle_context
        self._execution_cache.span = span
        self._execution_cache.is_initialized = True
        async with self._slot._use_case_execution(lifecycle_context):
            return await self._invoke_use_case(
                command,
                resolved,
                lifecycle_context=lifecycle_context,
                span=span,
            )

    async def _execute_operation_with_new_cache(
        self,
        operation_id: int | str,
        *,
        input: InputT | None,
        trace: TraceT | None,
    ) -> Any:
        await self._finish_execution_cache()
        span = await self._start_span(
            trace=trace,
            name=(
                f"{self._slot.execution_name}.use_case.handle_operation {operation_id}"
            ),
            attributes={"operation.id": operation_id},
        )
        self._execution_cache.span = span
        command, resolved = await self._slot._prepare_handle_operation(
            operation_id,
            span,
        )
        lifecycle_context = await self._slot._create_lifecycle_context(
            resolved,
            input,
            span,
        )
        self._execution_cache.lifecycle_context = lifecycle_context
        self._execution_cache.is_initialized = True
        async with self._slot._use_case_execution(lifecycle_context):
            return await self._invoke_use_case(
                command,
                resolved,
                lifecycle_context=lifecycle_context,
                span=span,
            )

    async def _execute_with_cache(
        self,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
    ) -> Any:
        lifecycle_context = self._execution_cache.lifecycle_context
        async with self._slot._use_case_execution(lifecycle_context):
            return await self._invoke_use_case(
                command,
                resolved,
                lifecycle_context=lifecycle_context,
                span=self._execution_cache.span,
            )

    async def _invoke_use_case(
        self,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
        *,
        lifecycle_context: object | None,
        span: Span | None,
    ) -> Any:
        result = await resolved.handler.handle(
            command,
            UseCaseHandlerContext(
                uow=self._slot._get_use_case_uow(resolved),
                queue=self._slot.event_queue,
                lifecycle_context=lifecycle_context,
                span=span,
            ),
        )
        result = self._slot._collect_use_case_result(
            result,
            resolved.registration,
        )
        await self._slot._drain_events(
            span,
            resolved.registration.event_draining_mode,
        )
        return result

    @asynccontextmanager
    async def _operation(self) -> AsyncGenerator[None]:
        self._begin_operation()
        try:
            yield
        finally:
            self._busy = False

    def _ensure_cache_initialized(self) -> None:
        if not self._execution_cache.is_initialized:
            raise SlotLeaseStateError(
                "Cached execution requires handle, handle_by_key, or "
                "handle_operation to initialize lifecycle and span state."
            )

    async def _finish_execution_cache(self) -> None:
        span = self._execution_cache.span
        self._execution_cache.lifecycle_context = None
        self._execution_cache.span = None
        self._execution_cache.is_initialized = False
        if span is not None:
            await span.__aexit__(None, None, None)

    async def _start_operation_span(
        self,
        *,
        command: UseCaseCommand,
        resolved: ResolvedUseCase,
        trace: TraceT | None,
    ) -> Span | None:
        return await self._start_span(
            trace=trace,
            name=self._slot._span_name(
                f"{self._slot.execution_name}.use_case.handle",
                command,
            ),
            attributes=self._slot._span_attributes(command, resolved),
        )

    async def _start_span(
        self,
        *,
        trace: TraceT | None,
        name: str,
        attributes: Mapping[str, Any],
    ) -> Span | None:
        span_factory = self._slot.span_factory
        if span_factory is None:
            return None
        span = span_factory.create_span(
            trace=trace,
            name=name,
            attributes=attributes,
        )
        await span.__aenter__()
        return span

    def _begin_operation(self) -> None:
        self._ensure_executable()
        if self._busy:
            raise ConcurrentSlotLeaseUseError(
                "One SlotLease cannot be used concurrently; acquire separate slots."
            )
        self._busy = True

    def _ensure_executable(self) -> None:
        self._validate_current()
        if self._state is not SlotLeaseState.ACTIVE:
            raise SlotLeaseStateError(
                f"Cannot execute with lease in state {self._state.value}."
            )
        if self._slot.resource_holder.is_finalized:
            raise SlotLeaseStateError("SlotLease transaction is already finalized.")

    def _validate_current(self) -> None:
        if self._released:
            raise SlotLeaseStateError("SlotLease has been released.")
        if self._generation != self._slot.generation or not self._slot.is_in_use:
            raise StaleSlotLeaseError(
                "SlotLease no longer owns the physical execution slot."
            )
