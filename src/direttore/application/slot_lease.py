from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.core.contracts.messages import Query, UseCaseCommand


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
    ROLLED_BACK = "rolled_back"
    ROLLBACK_ONLY = "rollback_only"
    FAILED = "failed"
    RELEASED = "released"


type SlotReleaseCallback = Callable[[BaseExecutionSlot], Awaitable[None]]


class SlotLease:
    """Generation-checked, sequential ownership of a physical slot."""

    def __init__(
        self,
        *,
        slot: BaseExecutionSlot,
        generation: int,
        release_callback: SlotReleaseCallback,
    ) -> None:
        self._slot = slot
        self._generation = generation
        self._release_callback = release_callback
        self._state = SlotLeaseState.ACTIVE
        self._busy = False

    @property
    def state(self) -> SlotLeaseState:
        return self._state

    @property
    def saga_id(self) -> str | None:
        return self._slot.saga_id

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle(command=command, input=input, trace=trace)  # type: ignore[attr-defined]
        )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle_by_key(  # type: ignore[attr-defined]
                key=key, payload=payload, input=input, trace=trace
            )
        )

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle_operation(  # type: ignore[attr-defined]
                operation_id=operation_id, input=input, trace=trace
            )
        )

    async def handle_query(
        self,
        query: Query,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle_query(query=query, input=input, trace=trace)  # type: ignore[attr-defined]
        )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle_query_by_key(  # type: ignore[attr-defined]
                key=key, payload=payload, input=input, trace=trace
            )
        )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> Any:
        return await self._execute(
            self._slot.handle_query_operation(  # type: ignore[attr-defined]
                operation_id=operation_id, input=input, trace=trace
            )
        )

    async def compensate_saga(
        self,
        saga_id: str,
        *,
        input: object = None,
        trace: object | None = None,
    ) -> None:
        await self._execute(
            self._slot.compensate_saga(  # type: ignore[attr-defined]
                saga_id=saga_id, input=input, trace=trace
            )
        )

    async def commit(self) -> None:
        self._begin_operation()
        try:
            await self._slot.commit()
        except BaseException:
            self._state = SlotLeaseState.FAILED
            raise
        else:
            self._state = SlotLeaseState.COMMITTED
        finally:
            self._busy = False

    async def rollback(self) -> None:
        self._validate_current()
        if self._state in (
            SlotLeaseState.COMMITTED,
            SlotLeaseState.ROLLED_BACK,
        ):
            raise SlotLeaseStateError(
                f"Cannot rollback lease in state {self._state.value}."
            )
        if self._state is SlotLeaseState.RELEASED:
            raise SlotLeaseStateError("Cannot rollback a released lease.")
        if self._busy:
            raise ConcurrentSlotLeaseUseError(
                "One SlotLease cannot be used concurrently."
            )
        self._busy = True
        try:
            await self._slot.rollback()
            self._state = SlotLeaseState.ROLLED_BACK
        finally:
            self._busy = False

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[SlotLease]:
        self._ensure_executable()
        try:
            yield self
        except BaseException:
            if self._state not in (
                SlotLeaseState.COMMITTED,
                SlotLeaseState.ROLLED_BACK,
            ):
                await self.rollback()
            raise
        else:
            if self._state is SlotLeaseState.ACTIVE:
                await self.commit()
            elif self._state in (
                SlotLeaseState.ROLLBACK_ONLY,
                SlotLeaseState.FAILED,
            ):
                await self.rollback()
                raise SlotLeaseStateError(
                    "Transaction was rolled back after an execution failure."
                )

    async def release(self) -> None:
        if self._state is SlotLeaseState.RELEASED:
            return
        self._validate_current()
        if self._busy:
            raise ConcurrentSlotLeaseUseError(
                "Cannot release a SlotLease while an operation is running."
            )
        cleanup = asyncio.create_task(self._release_impl())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise

    async def __aenter__(self) -> SlotLease:
        self._ensure_executable()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        await self.release()
        return False

    async def _execute(self, awaitable: Awaitable[Any]) -> Any:
        try:
            self._begin_operation()
        except BaseException:
            if hasattr(awaitable, "close"):
                awaitable.close()  # type: ignore[union-attr]
            raise
        try:
            return await awaitable
        except BaseException:
            self._state = SlotLeaseState.ROLLBACK_ONLY
            raise
        finally:
            self._busy = False

    async def _release_impl(self) -> None:
        try:
            if self._state in (
                SlotLeaseState.ACTIVE,
                SlotLeaseState.ROLLBACK_ONLY,
                SlotLeaseState.FAILED,
            ):
                await self._slot.rollback()
        finally:
            try:
                await self._release_callback(self._slot)
            finally:
                self._state = SlotLeaseState.RELEASED

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

    def _validate_current(self) -> None:
        if self._state is SlotLeaseState.RELEASED:
            raise SlotLeaseStateError("SlotLease has been released.")
        if self._generation != self._slot.generation or not self._slot.is_leased:
            raise StaleSlotLeaseError(
                "SlotLease no longer owns the physical execution slot."
            )
