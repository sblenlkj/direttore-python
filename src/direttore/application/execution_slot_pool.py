from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from direttore.application.base_execution_slot import BaseExecutionSlot


@dataclass(frozen=True, slots=True)
class ExecutionSlotPoolStats:
    total_slots: int
    free_slots: int
    acquired_slots: int
    max_slots: int


class ExecutionSlotPool[SlotT: BaseExecutionSlot]:
    """Async reusable execution slot pool.

    The pool owns a bounded set of execution slots.

    It creates ``initial_slot_count`` slots during initialization. If all slots
    are busy and the pool has not reached ``max_slot_count``, it creates a new
    slot. If the pool is already at maximum size, acquisition waits until
    another task releases a slot.

    Usage:

        async with pool.acquire() as slot:
            await slot.handle(...)

    The slot is reset and returned to the pool when the context exits,
    including when execution raises an exception.
    """

    def __init__(
        self,
        *,
        slot_factory: Callable[[], SlotT],
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self._validate_config(
            initial_slot_count=initial_slot_count,
            max_slot_count=max_slot_count,
        )

        self._slot_factory = slot_factory
        self._max_slot_count = max_slot_count

        self._slots: dict[int, SlotT] = {}
        self._free_slot_ids: set[int] = set()

        self._condition = asyncio.Condition()

        for _ in range(initial_slot_count):
            slot = self._create_slot()
            self._free_slot_ids.add(id(slot))

    @property
    def total_slot_count(self) -> int:
        return len(self._slots)

    @property
    def free_slot_count(self) -> int:
        return len(self._free_slot_ids)

    @property
    def acquired_slot_count(self) -> int:
        return len(self._slots) - len(self._free_slot_ids)

    @property
    def max_slot_count(self) -> int:
        return self._max_slot_count

    def stats(self) -> ExecutionSlotPoolStats:
        return ExecutionSlotPoolStats(
            total_slots=self.total_slot_count,
            free_slots=self.free_slot_count,
            acquired_slots=self.acquired_slot_count,
            max_slots=self.max_slot_count,
        )

    @asynccontextmanager
    async def acquire(
        self,
    ) -> AsyncGenerator[SlotT]:
        slot = await self._acquire_slot()

        try:
            yield slot
        finally:
            await self._release_slot(slot)

    async def _acquire_slot(self) -> SlotT:
        async with self._condition:
            while True:
                if self._free_slot_ids:
                    slot_id = self._free_slot_ids.pop()
                    return self._slots[slot_id]

                if len(self._slots) < self._max_slot_count:
                    return self._create_slot()

                await self._condition.wait()

    async def _release_slot(
        self,
        slot: SlotT,
    ) -> None:
        slot_id = id(slot)

        async with self._condition:
            if slot_id not in self._slots:
                raise RuntimeError(
                    "Cannot release unknown execution slot."
                )

            if slot_id in self._free_slot_ids:
                raise RuntimeError(
                    "Cannot release execution slot twice."
                )

        slot.reset()

        async with self._condition:
            self._free_slot_ids.add(slot_id)
            self._condition.notify()

    def _create_slot(self) -> SlotT:
        slot = self._slot_factory()
        slot_id = id(slot)

        if slot_id in self._slots:
            raise RuntimeError(
                "Execution slot factory returned an already owned slot."
            )

        self._slots[slot_id] = slot

        return slot

    def _validate_config(
        self,
        *,
        initial_slot_count: int,
        max_slot_count: int,
    ) -> None:
        if initial_slot_count < 1:
            raise ValueError(
                "initial_slot_count must be greater than or equal to 1."
            )

        if max_slot_count < 1:
            raise ValueError(
                "max_slot_count must be greater than or equal to 1."
            )

        if initial_slot_count > max_slot_count:
            raise ValueError(
                "initial_slot_count must be less than or equal to "
                "max_slot_count."
            )
