import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from direttore.application import SlotLeaseStateError
from direttore.application.simple_service import (
    SimpleServiceDirettoreApplication,
    SimpleServiceHandlerConfig,
    SimpleServiceSlotConfig,
    SimpleServiceSlotCreator,
    SimpleServiceSlotCreatorConfig,
    SimpleServiceUseCaseExecutionConfig,
)
from direttore.application.slot_provider import (
    FactoryExecutionSlotProvider,
    PoolExecutionSlotProvider,
)
from direttore.core.contracts.handlers import (
    SagaUseCaseHandlerResult,
    UseCaseHandler,
    UseCaseHandlerResult,
)
from direttore.core.contracts.lifecycle import Lifecycle as SimpleLifecycle
from direttore.core.contracts.messages import (
    UseCaseCommand,
    UseCaseCommandCompensation,
)
from direttore.core.contracts.operation_loader import (
    KeyPayloadPair,
    OperationLoader,
)
from direttore.core.primitives import BaseUnitOfWork, Container
from direttore.core.registries import UseCaseHandlerRegistry
from direttore.core.saga import InMemorySagaJournal
from direttore.core.tracing.recording_tracer import RecordingSpanFactory
from tests.helpers import SessionResourceHolder


@dataclass
class Command(UseCaseCommand):
    value: int


@dataclass(frozen=True)
class Result(UseCaseHandlerResult):
    value: int


@dataclass
class Compensation(UseCaseCommandCompensation):
    value: int

    def to_payload(self):
        return {"value": self.value}

    @classmethod
    def from_payload(cls, payload):
        return cls(value=payload["value"])


class Lifecycle(SimpleLifecycle):
    contexts: ClassVar[list[dict[str, Any]]] = []
    spans: ClassVar[list[object | None]] = []

    async def create_context(self, input, config, resource, span):
        assert isinstance(resource, SessionResourceHolder)
        self.spans.append(span)
        context = {"input": input}
        self.contexts.append(context)
        return context


class Handler(UseCaseHandler):
    compensated: ClassVar[list[int]] = []

    async def handle(self, command, context):
        session = await context.uow.write_session()
        session.values.append(command.value)
        if command.value < 0:
            raise RuntimeError("stop")
        return SagaUseCaseHandlerResult(
            result=Result(command.value),
            compensation=Compensation(command.value),
        )

    async def compensate(self, compensation, context):
        await context.uow.write_session()
        self.compensated.append(compensation.value)


class Loader(OperationLoader):
    def __init__(self, key):
        self.key = key
        self.calls = 0
        self.spans = []

    async def get_key_payload_pair(self, operation_id, resource, span):
        self.calls += 1
        self.spans.append(span)
        assert isinstance(resource, SessionResourceHolder)
        await resource.get_session()
        return KeyPayloadPair(key=self.key, payload={"value": int(operation_id)})


class Session:
    def __init__(self, log):
        self.log = log
        self.values = []

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")

    async def close(self):
        self.log.append("close")


def build_application(*, factory_provider=False):
    log: list[str] = []
    sessions: list[Session] = []
    use_cases = UseCaseHandlerRegistry[SimpleLifecycle](default_lifecycle=Lifecycle())
    use_cases.register(
        Command,
        Handler,
        key="command.v1",
        saga_key="command.saga.v1",
        compensation_type=Compensation,
    )
    command_loader = Loader("command.v1")
    journal = InMemorySagaJournal()

    def holder_factory():
        return SessionResourceHolder(
            {"primary": lambda: sessions.append(Session(log)) or sessions[-1]}
        )

    slot_creator = SimpleServiceSlotCreator(
        config=SimpleServiceSlotCreatorConfig(
            slot=SimpleServiceSlotConfig(
                resource_holder_factory=holder_factory,
                uow_factory=BaseUnitOfWork,
            ),
            handlers=SimpleServiceHandlerConfig(
                use_case_registry=use_cases,
            ),
            span_factory=RecordingSpanFactory(log_on_exit=False),
            saga_journal=journal,
            use_case_execution=SimpleServiceUseCaseExecutionConfig(
                operation_loader=command_loader
            ),
        ),
        container=Container(),
    )
    slot_provider = (
        FactoryExecutionSlotProvider(slot_creator=slot_creator)
        if factory_provider
        else PoolExecutionSlotProvider(
            slot_creator=slot_creator,
            initial_slot_count=1,
            max_slot_count=1,
        )
    )
    application = SimpleServiceDirettoreApplication(
        slot_provider=slot_provider,
    )
    return application, sessions, log, journal, command_loader


def run(coro):
    return asyncio.run(coro)


def test_direct_key_and_operation_use_plain_slots() -> None:
    app, sessions, log, _, command_loader = build_application()

    async def scenario():
        assert await app.handle(Command(1)) == Result(1)
        assert await app.handle_by_key("command.v1", {"value": 2}, input="b") == Result(
            2
        )
        assert await app.handle_operation("3", input="c") == Result(3)

    run(scenario())
    assert command_loader.calls == 1
    assert len(Lifecycle.contexts) >= 3
    assert len({id(context) for context in Lifecycle.contexts[-3:]}) == 3
    assert Lifecycle.contexts[-3]["input"] is None
    assert command_loader.spans[-1] is Lifecycle.spans[-1]
    assert command_loader.spans[-1] is not None
    assert log == [
        "commit",
        "close",
        "commit",
        "close",
        "commit",
        "close",
    ]


def test_explicit_lease_collects_one_saga_across_sequential_handles() -> None:
    Handler.compensated.clear()
    app, _, _, journal, _ = build_application(factory_provider=True)
    lifecycle_count = len(Lifecycle.contexts)

    async def scenario():
        async with app.slot(saga_id="saga-1") as lease:
            assert lease.saga_id == "saga-1"
            async with lease.transaction():
                await lease.handle(Command(1), input=None)
                await lease.handle_by_key("command.v1", {"value": 2}, input=None)
        assert lease.saga_id is None
        record = await journal.load("saga-1", object(), None)
        assert [entry.payload["value"] for entry in record.entries] == [1, 2]
        await app.compensate_saga("saga-1")

    run(scenario())
    assert Handler.compensated == [2, 1]
    assert len(Lifecycle.contexts) == lifecycle_count + 2


def test_lease_cache_reuses_first_lifecycle_context_for_all_handle_forms() -> None:
    app, _, log, _, command_loader = build_application(factory_provider=True)
    context_count = len(Lifecycle.contexts)

    async def scenario():
        async with app.slot() as lease:
            async with lease.transaction():
                assert await lease.handle(Command(1), input="first") == Result(1)
                assert await lease.handle_by_key_cache(
                    "command.v1", {"value": 2}
                ) == Result(2)
                assert await lease.handle_operation_cache("3") == Result(3)

    run(scenario())
    assert command_loader.calls == 1
    assert len(Lifecycle.contexts) == context_count + 1
    assert Lifecycle.contexts[-1] == {"input": "first"}
    assert log == ["commit", "close"]


def test_simple_transactional_slot_rolls_back_and_releases_on_failure() -> None:
    app, _, log, _, _ = build_application(factory_provider=True)

    async def scenario():
        with pytest.raises(RuntimeError, match="stop"):
            async with app.transactional_slot() as slot:
                await slot.handle(command=Command(-1), input=None)

    run(scenario())
    assert log == ["rollback", "close"]


def test_physical_slot_does_not_expose_lease_cache_methods() -> None:
    app, _, _, _, _ = build_application(factory_provider=True)

    async def scenario():
        async with app.transactional_slot() as slot:
            assert not hasattr(slot, "handle_cache")
            assert not hasattr(slot, "handle_by_key_cache")
            assert not hasattr(slot, "handle_operation_cache")
            assert not hasattr(slot, "_lease_span")

    run(scenario())


def test_lease_cache_requires_a_normal_handle_first() -> None:
    app, _, _, _, _ = build_application(factory_provider=True)

    async def scenario():
        async with app.slot() as lease:
            with pytest.raises(SlotLeaseStateError, match="requires handle"):
                await lease.handle_cache(Command(1))

    run(scenario())
