from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from direttore.application.simple_service.execution_slot import (
    SimpleServiceExecutionSlot,
)
from direttore.application.slot_lease import SlotLease
from direttore.application.slot_provider import (
    ExecutionSlotProvider,
    ExecutionSlotProviderStats,
)
from direttore.core.contracts.messages import UseCaseCommand


class SimpleServiceDirettoreApplication[InputT, TraceT]:
    """Simple-service facade backed by an already configured slot provider."""

    def __init__(
        self,
        *,
        slot_provider: ExecutionSlotProvider[
            SimpleServiceExecutionSlot[InputT, TraceT], InputT, TraceT
        ],
    ) -> None:
        self.slot_provider = slot_provider

    async def acquire_slot(
        self, *, saga_id: str | None = None
    ) -> SimpleServiceExecutionSlot[InputT, TraceT]:
        return await self.slot_provider.acquire_slot(saga_id=saga_id)

    async def acquire_lease(
        self, *, saga_id: str | None = None
    ) -> SlotLease[InputT, TraceT]:
        return await self.slot_provider.acquire_lease(saga_id=saga_id)

    @asynccontextmanager
    async def slot(
        self, *, saga_id: str | None = None
    ) -> AsyncGenerator[SlotLease[InputT, TraceT]]:
        lease = await self.acquire_lease(saga_id=saga_id)
        try:
            yield lease
        finally:
            await lease.release()

    @asynccontextmanager
    async def transactional_slot(
        self, *, saga_id: str | None = None
    ) -> AsyncGenerator[SimpleServiceExecutionSlot[InputT, TraceT]]:
        slot = await self.acquire_slot(saga_id=saga_id)
        try:
            yield slot
        except BaseException:
            if not slot.resource_holder.is_finalized:
                await slot.rollback()
            raise
        finally:
            await self.slot_provider.release_slot(slot)

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.transactional_slot(saga_id=saga_id) as slot:
            return await slot.handle(command=command, input=input, trace=trace)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.transactional_slot(saga_id=saga_id) as slot:
            return await slot.handle_by_key(key, payload, input=input, trace=trace)

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: InputT | None = None,
        trace: TraceT | None = None,
        saga_id: str | None = None,
    ) -> Any:
        async with self.transactional_slot(saga_id=saga_id) as slot:
            return await slot.handle_operation(operation_id, input=input, trace=trace)

    async def compensate_saga(
        self,
        saga_id: str,
        *,
        trace: TraceT | None = None,
    ) -> None:
        async with self.transactional_slot() as slot:
            await slot.compensate_saga(saga_id=saga_id, trace=trace)

    def validate(self) -> None:
        self.slot_provider.slot_creator.validate()

    def slot_provider_stats(self) -> ExecutionSlotProviderStats:
        return self.slot_provider.stats()

    def slot_pool_stats(self) -> ExecutionSlotProviderStats:
        """Deprecated name for metrics callers migrating to providers."""
        return self.slot_provider_stats()
