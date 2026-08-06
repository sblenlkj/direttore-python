import asyncio
from dataclasses import dataclass
from typing import ClassVar

from direttore.application.modular_monolith import (
    ModularMonolithDirettoreApplication,
    ModularMonolithDirettoreContext,
    ModularMonolithSlotConfig,
    ModularMonolithSlotCreator,
    ModularMonolithSlotCreatorConfig,
    ModularMonolithUseCaseExecutionConfig,
)
from direttore.application.slot_provider import (
    FactoryExecutionSlotProvider,
    PoolExecutionSlotProvider,
)
from direttore.core.contracts.handlers import UseCaseHandler
from direttore.core.contracts.lifecycle import Lifecycle as UseCaseLifecycle
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.contracts.operation_loader import KeyPayloadPair, OperationLoader
from direttore.core.modular_monolith_support import (
    ModularMonolithExecutionDependencyRegistry,
    ModularUnitOfWorkCoordinator,
)
from direttore.core.primitives import BaseUnitOfWork, Container
from direttore.core.registries import UseCaseHandlerRegistry
from tests.helpers import SessionResourceHolder


@dataclass
class Inner(UseCaseCommand):
    value: int


@dataclass
class Outer(UseCaseCommand):
    value: int


class Uow(BaseUnitOfWork):
    pass


class Coordinator(ModularUnitOfWorkCoordinator):
    def register(self):
        self.register_use_case_uow(Uow(self.resource_holder))


class Lifecycle(UseCaseLifecycle):
    inputs: ClassVar[list[object]] = []

    async def create_context(self, input, config, resource, span):
        assert isinstance(resource, SessionResourceHolder)
        self.inputs.append(input)
        return {"request": input}


class Loader(OperationLoader):
    def __init__(self) -> None:
        self.calls = 0

    async def get_key_payload_pair(self, operation_id, resource, span):
        self.calls += 1
        assert isinstance(resource, SessionResourceHolder)
        await resource.get_session()
        return KeyPayloadPair(key="inner", payload={"value": int(operation_id)})


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
    operation_loader = Loader()
    use_cases = UseCaseHandlerRegistry[UseCaseLifecycle](default_lifecycle=Lifecycle())
    use_cases.register(Inner, InnerHandler, key="inner")
    use_cases.register(Outer, OuterHandler, key="outer")
    dependencies = ModularMonolithExecutionDependencyRegistry()
    dependencies.register(
        dependency_type=RuntimeClient,
        factory=lambda context: Client(context.runtime),
    )

    def holder_factory():
        return SessionResourceHolder({"primary": lambda: Session(log)})

    slot_creator = ModularMonolithSlotCreator(
        config=ModularMonolithSlotCreatorConfig(
            slot=ModularMonolithSlotConfig(
                resource_holder_factory=holder_factory,
                coordinator_factory=lambda holder: Coordinator(resource_holder=holder),
            ),
            contexts=[
                ModularMonolithDirettoreContext(
                    use_case_registry=use_cases,
                    use_case_root_uow_type=Uow,
                )
            ],
            use_case_execution=ModularMonolithUseCaseExecutionConfig(
                operation_loader=operation_loader,
            ),
        ),
        container=Container(),
        execution_dependencies_registry=dependencies,
    )
    slot_provider = (
        FactoryExecutionSlotProvider(slot_creator=slot_creator)
        if factory
        else PoolExecutionSlotProvider(
            slot_creator=slot_creator,
            initial_slot_count=1,
            max_slot_count=1,
        )
    )
    app = ModularMonolithDirettoreApplication(
        slot_provider=slot_provider,
    )
    return app, log, operation_loader


def run(coro):
    return asyncio.run(coro)


def test_modular_runtime_keeps_lifecycle_for_nested_invocation_and_clears_it():
    InnerHandler.contexts.clear()
    app, log, _ = build()

    async def scenario():
        assert await app.handle(Outer(4), input="request") == 5

    run(scenario())
    assert InnerHandler.contexts == [{"request": "request"}]
    assert log == ["commit", "close"]


def test_modular_factory_provider_supports_explicit_transactional_island():
    app, log, _ = build(factory=True)

    async def scenario():
        async with app.slot() as lease:
            async with lease.transaction():
                await lease.handle(Inner(1), input=None)
                await lease.handle(Inner(2), input=None)

    run(scenario())
    assert log == ["commit", "close"]


def test_modular_lease_cache_reuses_first_lifecycle_context() -> None:
    Lifecycle.inputs.clear()
    InnerHandler.contexts.clear()
    app, log, _ = build(factory=True)

    async def scenario():
        async with app.slot() as lease:
            async with lease.transaction():
                await lease.handle(Inner(1), input="first")
                await lease.handle_by_key_cache("inner", {"value": 2})

    run(scenario())
    assert Lifecycle.inputs == ["first"]
    assert InnerHandler.contexts == [
        {"request": "first"},
        {"request": "first"},
    ]
    assert log == ["commit", "close"]


def test_modular_application_accepts_omitted_input() -> None:
    Lifecycle.inputs.clear()
    app, log, _ = build(factory=True)

    async def scenario():
        assert await app.handle(Inner(1)) == 1

    run(scenario())
    assert Lifecycle.inputs == [None]
    assert log == ["commit", "close"]


def test_modular_operation_loader_receives_resource_holder() -> None:
    app, log, operation_loader = build(factory=True)

    async def scenario():
        assert await app.handle_operation("3") == 3

    run(scenario())
    assert operation_loader.calls == 1
    assert log == ["commit", "close"]
