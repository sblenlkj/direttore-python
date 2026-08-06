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
    SlotCreator,
)
from direttore.core.contracts.handlers import UseCaseHandler, UseCaseHandlerConfig
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.primitives import BaseUnitOfWork
from direttore.core.registries.registrations import UseCaseHandlerRegistration
from direttore.core.resolvers.resolved_handlers import ResolvedHandler
from tests.helpers import SessionResourceHolder


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


class Handler(UseCaseHandler):
    def __init__(self, gate=None):
        self.gate = gate

    async def handle(self, command, context):
        await context.uow.write_session("primary")
        if self.gate is not None:
            await self.gate.wait()
        if command.value < 0:
            raise ValueError("failed")
        return command.value


class Slot(BaseExecutionSlot):
    def __init__(self, sessions: list[Session], gate=None):
        holder = SessionResourceHolder({"primary": lambda: self._new_session(sessions)})
        super().__init__(resource_holder=holder)
        self.sessions = sessions
        self.gate = gate
        self.reset_count = 0
        self.uow = BaseUnitOfWork(holder)
        self.resolved = ResolvedHandler(
            handler=Handler(gate),
            handler_type=Handler,
            registration=UseCaseHandlerRegistration(
                command_type=Command,
                handler_type=Handler,
                lifecycle=None,
                config=UseCaseHandlerConfig(),
            ),
        )

    @staticmethod
    def _new_session(sessions):
        session = Session()
        sessions.append(session)
        return session

    async def _prepare_handle(self, command):
        return command, self.resolved

    def _resolve_command(self, command_type):
        raise NotImplementedError

    def _resolve_by_key(self, key):
        raise NotImplementedError

    def _get_use_case_uow(self, resolved):
        return self.uow

    async def _drain_events(self, span, mode="sequential"):
        self.event_queue.clear()

    async def _compensate_entry(self, entry, saga_id, span):
        raise NotImplementedError

    async def _create_lifecycle_context(self, resolved, input, span):
        return None

    async def _start_operation_span(self, *, command, resolved, trace):
        return None

    def reset(self):
        self.reset_count += 1
        self.resource_holder.reset()


class TestSlotCreator(SlotCreator[Slot, object, object]):
    __test__ = False

    def __init__(self, factory):
        self.factory = factory

    def create_slot(self) -> Slot:
        return self.factory()


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
        slot_creator=TestSlotCreator(factory),
        initial_slot_count=1,
        max_slot_count=1,
    )

    async def scenario():
        lease = await provider.acquire_lease()
        assert await lease.handle(Command(1), input=None) == 1
        assert await lease.handle(Command(2), input=None) == 2
        await lease.commit()
        await lease.release()
        await lease.release()
        replacement = await provider.acquire_lease()
        await replacement.rollback()
        await replacement.release()

    run(scenario())
    assert len(slots) == 1
    assert sessions[0].calls == ["commit", "close"]
    assert slots[0].reset_count == 2


def test_provider_exposes_plain_slot_and_slot_lease() -> None:
    sessions: list[Session] = []
    provider = PoolExecutionSlotProvider(
        slot_creator=TestSlotCreator(lambda: Slot(sessions)),
        initial_slot_count=1,
        max_slot_count=1,
    )

    async def scenario():
        slot = await provider.acquire_slot()
        assert isinstance(slot, Slot)
        assert slot.is_in_use is True
        await slot.rollback()
        await provider.release_slot(slot)
        assert slot.is_in_use is False

        lease = await provider.acquire_lease()
        assert lease.state is SlotLeaseState.ACTIVE
        await lease.release()

    run(scenario())
    assert provider.stats().free_slots == 1


def test_execution_slot_requires_execution_model_hooks() -> None:
    class MissingHooksSlot(BaseExecutionSlot):
        def reset(self) -> None:
            pass

    with pytest.raises(TypeError):
        MissingHooksSlot(resource_holder=SessionResourceHolder())


def test_failure_keeps_lease_active_and_release_rolls_back() -> None:
    sessions: list[Session] = []
    provider = FactoryExecutionSlotProvider(
        slot_creator=TestSlotCreator(lambda: Slot(sessions))
    )

    async def scenario():
        lease = await provider.acquire_lease()
        with pytest.raises(ValueError):
            await lease.handle(Command(-1), input=None)
        assert lease.state is SlotLeaseState.ACTIVE
        assert await lease.handle(Command(1), input=None) == 1
        await lease.release()
        assert lease.state is SlotLeaseState.ACTIVE
        with pytest.raises(SlotLeaseStateError, match="released"):
            await lease.handle(Command(1), input=None)

    run(scenario())
    assert sessions[0].calls == ["rollback", "close"]


def test_concurrent_use_is_rejected() -> None:
    sessions: list[Session] = []

    async def scenario():
        gate = asyncio.Event()
        provider = FactoryExecutionSlotProvider(
            slot_creator=TestSlotCreator(lambda: Slot(sessions, gate))
        )
        lease = await provider.acquire_lease()
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
            slot_creator=TestSlotCreator(lambda: Slot(sessions, gate)),
            initial_slot_count=1,
            max_slot_count=1,
        )

        async def worker():
            async with await provider.acquire_lease() as lease:
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
