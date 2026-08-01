import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

from direttore.application.simple_service import (
    SimpleServiceDirettoreApplication,
    SimpleServiceDirettoreConfig,
    SimpleServiceHandlerConfig,
    SimpleServiceQueryExecutionConfig,
    SimpleServiceSlotConfig,
    SimpleServiceUseCaseExecutionConfig,
)
from direttore.application.slot_provider import FactoryExecutionSlotProvider
from direttore.core.contracts.handlers import (
    QueryHandler,
    UseCaseHandler,
)
from direttore.core.contracts.lifecycle import (
    QueryLifecycle,
    UseCaseLifecycle,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.contracts.operation_loader import (
    KeyPayloadPair,
    SimpleServiceOperationLoader,
)
from direttore.core.primitives import BaseUnitOfWork, Container, ResourceHolder
from direttore.core.registries import QueryHandlerRegistry, UseCaseHandlerRegistry
from direttore.core.saga import (
    InMemorySagaJournal,
    SagaHandlerResult,
)


@dataclass
class Command(UseCaseCommand):
    value: int


@dataclass
class GetValue(Query):
    value: int


@dataclass
class Compensation:
    value: int

    def to_payload(self):
        return {"value": self.value}

    @classmethod
    def from_payload(cls, payload):
        return cls(value=payload["value"])


class Lifecycle(UseCaseLifecycle):
    contexts: ClassVar[list[dict[str, Any]]] = []

    async def create_context(self, input, config, uow):
        context = {"input": input}
        self.contexts.append(context)
        return context


class ReadLifecycle(QueryLifecycle):
    async def create_context(self, input, config, uow):
        return {"input": input}


class Handler(UseCaseHandler):
    compensated: ClassVar[list[int]] = []

    async def handle(self, command, context):
        session = await context.uow.write_session()
        session.values.append(command.value)
        return SagaHandlerResult(
            result=command.value,
            compensation=Compensation(command.value),
        )

    async def compensate(self, compensation, context):
        await context.uow.write_session()
        self.compensated.append(compensation.value)


class QueryHandlerImpl(QueryHandler):
    async def handle(self, query, context):
        session = await context.uow.read_session()
        return query.value + len(session.values)


class Loader(SimpleServiceOperationLoader):
    def __init__(self, key):
        self.key = key
        self.calls = 0

    async def get_key_payload_pair(self, operation_id, uow):
        self.calls += 1
        await uow.read_session()
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
    use_cases = UseCaseHandlerRegistry(default_lifecycle=Lifecycle())
    use_cases.register(
        Command,
        Handler,
        key="command.v1",
        saga_key="command.saga.v1",
        compensation_type=Compensation,
    )
    queries = QueryHandlerRegistry(default_lifecycle=ReadLifecycle())
    queries.register(GetValue, QueryHandlerImpl, key="query.v1")
    command_loader = Loader("command.v1")
    query_loader = Loader("query.v1")
    journal = InMemorySagaJournal()

    def holder_factory():
        return ResourceHolder(
            {"primary": lambda: sessions.append(Session(log)) or sessions[-1]}
        )

    provider_factory = None
    if factory_provider:

        def provider_factory(slot_factory):
            return FactoryExecutionSlotProvider(slot_factory=slot_factory)

    application = SimpleServiceDirettoreApplication(
        config=SimpleServiceDirettoreConfig(
            slot=SimpleServiceSlotConfig(
                resource_holder_factory=holder_factory,
                uow_factory=BaseUnitOfWork,
            ),
            handlers=SimpleServiceHandlerConfig(
                use_case_registry=use_cases,
                query_registry=queries,
            ),
            saga_journal=journal,
            use_case_execution=SimpleServiceUseCaseExecutionConfig(
                operation_loader=command_loader
            ),
            query_execution=SimpleServiceQueryExecutionConfig(
                operation_loader=query_loader
            ),
        ),
        container=Container(),
        slot_provider_factory=provider_factory,
        initial_slot_count=1,
        max_slot_count=1,
    )
    return application, sessions, log, journal, command_loader, query_loader


def run(coro):
    return asyncio.run(coro)


def test_direct_key_operation_and_queries_share_one_slot_pipeline() -> None:
    app, sessions, log, _, command_loader, query_loader = build_application()

    async def scenario():
        assert await app.handle(Command(1), input="a") == 1
        assert await app.handle_by_key("command.v1", {"value": 2}, input="b") == 2
        assert await app.handle_operation("3", input="c") == 3
        assert await app.handle_query(GetValue(4), input="q") == 4
        assert await app.handle_query_by_key("query.v1", {"value": 5}, input="q") == 5
        assert await app.handle_query_operation("6", input="q") == 6

    run(scenario())
    assert command_loader.calls == 1
    assert query_loader.calls == 1
    assert len(Lifecycle.contexts) >= 3
    assert len({id(context) for context in Lifecycle.contexts[-3:]}) == 3
    assert log == [
        "commit",
        "close",
        "commit",
        "close",
        "commit",
        "close",
        "rollback",
        "close",
        "rollback",
        "close",
        "rollback",
        "close",
    ]


def test_explicit_lease_collects_one_saga_across_sequential_handles() -> None:
    Handler.compensated.clear()
    app, _, _, journal, _, _ = build_application(factory_provider=True)

    async def scenario():
        async with app.slot(saga_id="saga-1") as lease:
            async with lease.transaction():
                await lease.handle(Command(1), input=None)
                await lease.handle_by_key("command.v1", {"value": 2}, input=None)
        record = await journal.load("saga-1", object())
        assert [entry.payload["value"] for entry in record.entries] == [1, 2]
        await app.compensate_saga("saga-1")

    run(scenario())
    assert Handler.compensated == [2, 1]
