from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.application.slot_lease import SlotLease


@dataclass(frozen=True, slots=True)
class ExecutionSlotProviderStats:
    total_slots: int
    free_slots: int
    acquired_slots: int
    max_slots: int | None


class SlotCreator[SlotT: BaseExecutionSlot[Any, Any], InputT, TraceT](ABC):
    @abstractmethod
    def create_slot(self) -> SlotT:
        raise NotImplementedError

    def validate(self) -> None:
        """Validate dependencies shared by every slot created by this object."""


class ExecutionSlotProvider[SlotT: BaseExecutionSlot[Any, Any], InputT, TraceT](ABC):
    def __init__(self, *, slot_creator: SlotCreator[SlotT, InputT, TraceT]) -> None:
        self.slot_creator = slot_creator

    @abstractmethod
    async def acquire_slot(self, *, saga_id: str | None = None) -> SlotT:
        raise NotImplementedError

    @abstractmethod
    async def release_slot(self, slot: BaseExecutionSlot[InputT, TraceT]) -> None:
        raise NotImplementedError

    async def acquire_lease(
        self, *, saga_id: str | None = None
    ) -> SlotLease[InputT, TraceT]:
        """Acquire the stateful lease used for multi-operation transactions."""
        slot = await self.acquire_slot(saga_id=saga_id)
        return SlotLease(
            slot=slot,
            generation=slot.generation,
            release_callback=self.release_slot,
        )

    @abstractmethod
    def stats(self) -> ExecutionSlotProviderStats:
        raise NotImplementedError


class PoolExecutionSlotProvider[SlotT: BaseExecutionSlot[Any, Any], InputT, TraceT](
    ExecutionSlotProvider[SlotT, InputT, TraceT]
):
    """Bounded provider that reuses cleaned physical slots."""

    def __init__(
        self,
        *,
        slot_creator: SlotCreator[SlotT, InputT, TraceT],
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        if initial_slot_count < 1 or max_slot_count < initial_slot_count:
            raise ValueError("Invalid execution slot pool size.")

        super().__init__(slot_creator=slot_creator)

        self._max_slots = max_slot_count
        self._slots: dict[int, SlotT] = {}
        self._free_ids: list[int] = []
        self._condition = asyncio.Condition()

        for _ in range(initial_slot_count):
            slot = self._create_slot()
            self._free_ids.append(id(slot))

    async def acquire_slot(self, *, saga_id: str | None = None) -> SlotT:
        slot = await self._acquire_physical()
        try:
            await slot.prepare_slot(saga_id=saga_id)
        except BaseException:
            await self._return_physical(slot)
            raise
        return slot

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

    async def release_slot(self, slot: BaseExecutionSlot[InputT, TraceT]) -> None:
        slot_id = id(slot)
        if slot_id not in self._slots:
            raise RuntimeError("Cannot release an unknown execution slot.")
        if slot_id in self._free_ids:
            raise RuntimeError("Cannot release an execution slot twice.")
        await slot.finish_slot()
        await self._return_physical(slot)

    async def _return_physical(
        self,
        slot: BaseExecutionSlot[InputT, TraceT],
    ) -> None:
        async with self._condition:
            slot_id = id(slot)
            if slot_id not in self._slots:
                raise RuntimeError("Cannot return an unknown execution slot.")
            if slot_id in self._free_ids:
                raise RuntimeError("Cannot return an execution slot twice.")
            self._free_ids.append(slot_id)
            self._condition.notify(1)

    def _create_slot(self) -> SlotT:
        slot = self.slot_creator.create_slot()
        if id(slot) in self._slots:
            raise RuntimeError("Slot creator returned an already-owned slot.")
        self._slots[id(slot)] = slot
        return slot


class FactoryExecutionSlotProvider[SlotT: BaseExecutionSlot[Any, Any], InputT, TraceT](
    ExecutionSlotProvider[SlotT, InputT, TraceT]
):
    """Provider that creates and disposes a physical slot per acquisition."""

    def __init__(self, *, slot_creator: SlotCreator[SlotT, InputT, TraceT]) -> None:
        super().__init__(slot_creator=slot_creator)
        self._active_slot_ids: set[int] = set()
        self._created = 0

    async def acquire_slot(self, *, saga_id: str | None = None) -> SlotT:
        slot = self.slot_creator.create_slot()
        await slot.prepare_slot(saga_id=saga_id)
        slot_id = id(slot)
        if slot_id in self._active_slot_ids:
            await slot.finish_slot()
            raise RuntimeError("Slot creator returned an already-active slot.")
        self._active_slot_ids.add(slot_id)
        self._created += 1
        return slot

    def stats(self) -> ExecutionSlotProviderStats:
        return ExecutionSlotProviderStats(
            total_slots=self._created,
            free_slots=0,
            acquired_slots=len(self._active_slot_ids),
            max_slots=None,
        )

    async def release_slot(self, slot: BaseExecutionSlot[InputT, TraceT]) -> None:
        slot_id = id(slot)
        if slot_id not in self._active_slot_ids:
            raise RuntimeError("Cannot release an unknown execution slot.")
        try:
            await slot.finish_slot()
        finally:
            self._active_slot_ids.remove(slot_id)
