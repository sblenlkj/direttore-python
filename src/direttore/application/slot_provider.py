from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.application.slot_lease import SlotLease


@dataclass(frozen=True, slots=True)
class ExecutionSlotProviderStats:
    total_slots: int
    free_slots: int
    acquired_slots: int
    max_slots: int | None


class ExecutionSlotProvider[SlotT: BaseExecutionSlot](ABC):
    @abstractmethod
    async def acquire(self, *, saga_id: str | None = None) -> SlotLease:
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> ExecutionSlotProviderStats:
        raise NotImplementedError


class PoolExecutionSlotProvider[SlotT: BaseExecutionSlot](ExecutionSlotProvider[SlotT]):
    """Bounded provider that reuses cleaned physical slots."""

    def __init__(
        self,
        *,
        slot_factory: Callable[[], SlotT],
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        if initial_slot_count < 1 or max_slot_count < initial_slot_count:
            raise ValueError("Invalid execution slot pool size.")
        self._slot_factory = slot_factory
        self._max_slots = max_slot_count
        self._slots: dict[int, SlotT] = {}
        self._free_ids: list[int] = []
        self._condition = asyncio.Condition()
        for _ in range(initial_slot_count):
            slot = self._create_slot()
            self._free_ids.append(id(slot))

    async def acquire(self, *, saga_id: str | None = None) -> SlotLease:
        slot = await self._acquire_physical()
        try:
            generation = await slot.start_lease(saga_id=saga_id)
        except BaseException:
            await self._return_physical(slot)
            raise
        return SlotLease(
            slot=slot,
            generation=generation,
            release_callback=self._release,
        )

    def stats(self) -> ExecutionSlotProviderStats:
        return ExecutionSlotProviderStats(
            total_slots=len(self._slots),
            free_slots=len(self._free_ids),
            acquired_slots=len(self._slots) - len(self._free_ids),
            max_slots=self._max_slots,
        )

    async def _acquire_physical(self) -> SlotT:
        async with self._condition:
            while True:
                if self._free_ids:
                    return self._slots[self._free_ids.pop()]
                if len(self._slots) < self._max_slots:
                    return self._create_slot()
                await self._condition.wait()

    async def _release(self, slot: BaseExecutionSlot) -> None:
        await slot.finish_lease()
        await self._return_physical(slot)

    async def _return_physical(self, slot: BaseExecutionSlot) -> None:
        async with self._condition:
            slot_id = id(slot)
            if slot_id not in self._slots:
                raise RuntimeError("Cannot return an unknown execution slot.")
            if slot_id in self._free_ids:
                raise RuntimeError("Cannot return an execution slot twice.")
            self._free_ids.append(slot_id)
            self._condition.notify(1)

    def _create_slot(self) -> SlotT:
        slot = self._slot_factory()
        if id(slot) in self._slots:
            raise RuntimeError("Slot factory returned an already-owned slot.")
        self._slots[id(slot)] = slot
        return slot


class FactoryExecutionSlotProvider[SlotT: BaseExecutionSlot](
    ExecutionSlotProvider[SlotT]
):
    """Provider that creates and disposes a physical slot per acquisition."""

    def __init__(self, *, slot_factory: Callable[[], SlotT]) -> None:
        self._slot_factory = slot_factory
        self._active = 0
        self._created = 0

    async def acquire(self, *, saga_id: str | None = None) -> SlotLease:
        slot = self._slot_factory()
        generation = await slot.start_lease(saga_id=saga_id)
        self._active += 1
        self._created += 1
        return SlotLease(
            slot=slot,
            generation=generation,
            release_callback=self._release,
        )

    def stats(self) -> ExecutionSlotProviderStats:
        return ExecutionSlotProviderStats(
            total_slots=self._created,
            free_slots=0,
            acquired_slots=self._active,
            max_slots=None,
        )

    async def _release(self, slot: BaseExecutionSlot) -> None:
        try:
            await slot.finish_lease()
        finally:
            self._active -= 1
