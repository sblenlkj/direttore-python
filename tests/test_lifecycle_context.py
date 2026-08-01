import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

from direttore.core.contracts.handlers import (
    UseCaseHandler,
    UseCaseHandlerConfig,
    UseCaseHandlerResult,
)
from direttore.core.contracts.lifecycle import UseCaseLifecycle
from direttore.core.contracts.messages import UseCaseCommand
from direttore.core.engines.simple_service.simple_service_use_case_engine import (
    SimpleServiceUseCaseEngine,
)
from direttore.core.primitives.container import Container
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)


@dataclass
class Command(UseCaseCommand):
    value: int


@dataclass
class OverrideCommand(UseCaseCommand):
    value: int


class ResourceHolder(AbstractUseCaseResourceHolder):
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class RecordingLifecycle(UseCaseLifecycle[Command, dict[str, object]]):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def create_context(self) -> dict[str, object]:
        self.events.append("create")
        return {}

    async def before_resource_holder_opened(
        self,
        input: Command,
        lifecycle_context: dict[str, object],
        config: UseCaseHandlerConfig,
    ) -> None:
        self.events.append("before")
        lifecycle_context["value"] = input.value

    async def after_resource_holder_opened(
        self,
        input: Command,
        lifecycle_context: dict[str, object],
        config: UseCaseHandlerConfig,
    ) -> None:
        self.events.append("after")
        lifecycle_context["resources_opened"] = True


class RecordingHandler(UseCaseHandler):
    contexts: ClassVar[list[dict[str, object]]] = []

    async def handle(
        self,
        command: UseCaseCommand,
        context: Any,
    ) -> UseCaseHandlerResult:
        RecordingHandler.contexts.append(context.lifecycle_context)
        return UseCaseHandlerResult()


def test_registration_uses_default_lifecycle_and_override() -> None:
    default_lifecycle = RecordingLifecycle()
    override_lifecycle = RecordingLifecycle()
    registry = UseCaseHandlerRegistry(default_lifecycle=default_lifecycle)

    registry.register(Command, RecordingHandler)
    registry.register(
        OverrideCommand,
        RecordingHandler,
        lifecycle=override_lifecycle,
    )

    assert registry.get_registration(Command).lifecycle is default_lifecycle
    assert registry.get_registration(OverrideCommand).lifecycle is override_lifecycle


def test_engine_passes_the_same_fresh_context_through_lifecycle_and_handler() -> None:
    async def run() -> None:
        RecordingHandler.contexts.clear()
        lifecycle = RecordingLifecycle()
        registry = UseCaseHandlerRegistry(default_lifecycle=lifecycle)
        registry.register(Command, RecordingHandler)
        engine: SimpleServiceUseCaseEngine[Any, Any, Any] = SimpleServiceUseCaseEngine(
            resolver=UseCaseHandlerResolver(
                registry=registry,
                container=Container(),
            ),
        )
        holder = ResourceHolder()
        uow = BaseUnitOfWork(holder)
        event_queue = EventQueue()

        await engine.handle(
            command=Command(value=1),
            resource_holder=holder,
            uow=uow,
            event_queue=event_queue,
        )
        await engine.handle(
            command=Command(value=2),
            resource_holder=holder,
            uow=uow,
            event_queue=event_queue,
        )

        assert lifecycle.events == [
            "create",
            "before",
            "after",
            "create",
            "before",
            "after",
        ]
        assert RecordingHandler.contexts == [
            {"value": 1, "resources_opened": True},
            {"value": 2, "resources_opened": True},
        ]
        assert RecordingHandler.contexts[0] is not RecordingHandler.contexts[1]

    asyncio.run(run())
