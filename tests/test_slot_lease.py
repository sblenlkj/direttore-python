import asyncio
from dataclasses import dataclass, field

import pytest

from direttore.application.base_execution_slot import BaseExecutionSlot
from direttore.application.slot_lease import (
    ConcurrentSlotLeaseUseError,
    SlotLeaseState,
    SlotLeaseStateError,
)
from direttore.application.slot_provider import (
    FactoryExecutionSlotProvider,
    PoolExecutionSlotProvider,
)
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.primitives import ResourceHolder


@dataclass
class Command(UseCaseCommand):
    value: int


@dataclass
class Session:
    calls: list[str] = field(default_factory=list)

    async def commit(self):
        self.calls.append("commit")

    async def rollback(self):
        self.calls.append("rollback")

    async def close(self):
        self.calls.append("close")


class Slot(BaseExecutionSlot):
    def __init__(self, sessions: list[Session], gate=None):
        holder = ResourceHolder({"primary": lambda: self._new_session(sessions)})
        super().__init__(resource_holder=holder)
        self.sessions = sessions
        self.gate = gate
        self.reset_count = 0

    @staticmethod
    def _new_session(sessions):
        session = Session()
        sessions.append(session)
        return session

    async def handle(self, *, command, input, trace=None):
        await self.resource_holder.get_session("primary", commit=True)
        if self.gate is not None:
            await self.gate.wait()
        if command.value < 0:
            raise ValueError("failed")
        return command.value

    def reset(self):
        self.reset_count += 1


def run(coro):
    return asyncio.run(coro)


def test_multiple_handles_commit_and_pool_reuse() -> None:
    sessions: list[Session] = []
    slots: list[Slot] = []

    def factory():
        slot = Slot(sessions)
        slots.append(slot)
        return slot

    provider = PoolExecutionSlotProvider(
        slot_factory=factory, initial_slot_count=1, max_slot_count=1
    )

    async def scenario():
        lease = await provider.acquire()
        assert await lease.handle(Command(1), input=None) == 1
        assert await lease.handle(Command(2), input=None) == 2
        await lease.commit()
        await lease.release()
        await lease.release()
        replacement = await provider.acquire()
        await replacement.rollback()
        await replacement.release()

    run(scenario())
    assert len(slots) == 1
    assert sessions[0].calls == ["commit", "close"]
    assert slots[0].reset_count == 2


def test_failure_is_rollback_only_and_release_rolls_back() -> None:
    sessions: list[Session] = []
    provider = FactoryExecutionSlotProvider(slot_factory=lambda: Slot(sessions))

    async def scenario():
        lease = await provider.acquire()
        with pytest.raises(ValueError):
            await lease.handle(Command(-1), input=None)
        assert lease.state is SlotLeaseState.ROLLBACK_ONLY
        with pytest.raises(SlotLeaseStateError):
            await lease.handle(Command(1), input=None)
        await lease.release()
        assert lease.state is SlotLeaseState.RELEASED

    run(scenario())
    assert sessions[0].calls == ["rollback", "close"]


def test_concurrent_use_is_rejected() -> None:
    sessions: list[Session] = []

    async def scenario():
        gate = asyncio.Event()
        provider = FactoryExecutionSlotProvider(
            slot_factory=lambda: Slot(sessions, gate)
        )
        lease = await provider.acquire()
        first = asyncio.create_task(lease.handle(Command(1), input=None))
        await asyncio.sleep(0)
        with pytest.raises(ConcurrentSlotLeaseUseError):
            await lease.handle(Command(2), input=None)
        gate.set()
        await first
        await lease.release()

    run(scenario())


def test_transaction_context_rolls_back_and_releases_on_cancellation() -> None:
    sessions: list[Session] = []

    async def scenario():
        gate = asyncio.Event()
        provider = PoolExecutionSlotProvider(
            slot_factory=lambda: Slot(sessions, gate),
            initial_slot_count=1,
            max_slot_count=1,
        )

        async def worker():
            async with await provider.acquire() as lease:
                async with lease.transaction():
                    await lease.handle(Command(1), input=None)

        task = asyncio.create_task(worker())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert provider.stats().free_slots == 1

    run(scenario())
    assert sessions[0].calls == ["rollback", "close"]
