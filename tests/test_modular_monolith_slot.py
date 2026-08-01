import asyncio
from dataclasses import dataclass
from typing import ClassVar

from direttore.application.modular_monolith import (
    ModularMonolithDirettoreApplication,
    ModularMonolithDirettoreConfig,
    ModularMonolithDirettoreContext,
    ModularMonolithSlotConfig,
)
from direttore.application.slot_provider import FactoryExecutionSlotProvider
from direttore.core.contracts.handlers import QueryHandler, UseCaseHandler
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.modular_monolith_support import (
    ModularMonolithExecutionDependencyRegistry,
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modular_monolith_support.lifecycle import (
    ModularQueryLifecycle,
    ModularUseCaseLifecycle,
)
from direttore.core.primitives import BaseUnitOfWork, Container, ResourceHolder
from direttore.core.registries import QueryHandlerRegistry, UseCaseHandlerRegistry


@dataclass
class Inner(UseCaseCommand):
    value: int


@dataclass
class Outer(UseCaseCommand):
    value: int


@dataclass
class Read(Query):
    value: int


class Uow(BaseUnitOfWork):
    pass


class Coordinator(ModularUnitOfWorkCoordinator):
    def register(self):
        self.register_use_case_uow(Uow(self.resource_holder))
        self.register_query_uow(Uow(self.resource_holder))


class Lifecycle(ModularUseCaseLifecycle):
    async def create_context(self, input, config, coordinator):
        return {"request": input}


class QueryLifecycle(ModularQueryLifecycle):
    async def create_context(self, input, config, coordinator):
        return {"request": input}


class RuntimeClient:
    async def invoke(self, command):
        raise NotImplementedError


class Client(RuntimeClient):
    def __init__(self, runtime):
        self.runtime = runtime

    async def invoke(self, command):
        return await self.runtime.invoke(command)


class InnerHandler(UseCaseHandler):
    contexts: ClassVar[list[object]] = []

    async def handle(self, command, context):
        self.contexts.append(context.lifecycle_context)
        session = await context.uow.write_session()
        session.values.append(command.value)
        return command.value


class OuterHandler(UseCaseHandler):
    def __init__(self, client: RuntimeClient):
        self.client = client

    async def handle(self, command, context):
        return await self.client.invoke(Inner(command.value + 1))


class ReadHandler(QueryHandler):
    async def handle(self, query, context):
        session = await context.uow.read_session()
        return query.value + len(session.values)


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


def build(factory=False):
    log = []
    use_cases = UseCaseHandlerRegistry(default_lifecycle=Lifecycle())
    use_cases.register(Inner, InnerHandler, key="inner")
    use_cases.register(Outer, OuterHandler, key="outer")
    queries = QueryHandlerRegistry(default_lifecycle=QueryLifecycle())
    queries.register(Read, ReadHandler, key="read")
    dependencies = ModularMonolithExecutionDependencyRegistry()
    dependencies.register(
        dependency_type=RuntimeClient,
        factory=lambda context: Client(context.runtime),
    )

    def holder_factory():
        return ResourceHolder({"primary": lambda: Session(log)})

    provider_factory = (
        (lambda slot_factory: FactoryExecutionSlotProvider(slot_factory=slot_factory))
        if factory
        else None
    )
    app = ModularMonolithDirettoreApplication(
        config=ModularMonolithDirettoreConfig(
            slot=ModularMonolithSlotConfig(
                resource_holder_factory=holder_factory,
                coordinator_factory=lambda holder: Coordinator(resource_holder=holder),
            ),
            contexts=[
                ModularMonolithDirettoreContext(
                    use_case_registry=use_cases,
                    use_case_root_uow_type=Uow,
                    query_registry=queries,
                    query_root_uow_type=Uow,
                )
            ],
        ),
        container=Container(),
        execution_dependencies_registry=dependencies,
        slot_provider_factory=provider_factory,
        initial_slot_count=1,
        max_slot_count=1,
    )
    return app, log


def run(coro):
    return asyncio.run(coro)


def test_modular_runtime_keeps_lifecycle_for_nested_invocation_and_clears_it():
    InnerHandler.contexts.clear()
    app, log = build()

    async def scenario():
        assert await app.handle(Outer(4), input="request") == 5
        assert await app.handle_query(Read(2), input="query") == 2

    run(scenario())
    assert InnerHandler.contexts == [{"request": "request"}]
    assert log == ["commit", "close", "rollback", "close"]


def test_modular_factory_provider_supports_explicit_transactional_island():
    app, log = build(factory=True)

    async def scenario():
        async with app.slot() as lease:
            async with lease.transaction():
                await lease.handle(Inner(1), input=None)
                await lease.handle(Inner(2), input=None)

    run(scenario())
    assert log == ["commit", "close"]
