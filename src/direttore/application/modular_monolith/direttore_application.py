from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from direttore.application.modular_monolith.config import (
    ModularMonolithDirettoreConfig,
)
from direttore.application.modular_monolith.execution_slot import (
    ModularMonolithExecutionSlot,
)
from direttore.application.slot_lease import SlotLease
from direttore.application.slot_provider import (
    ExecutionSlotProvider,
    ExecutionSlotProviderStats,
    PoolExecutionSlotProvider,
)
from direttore.core.event_dispatchers.modular_monolith_event_dispatcher import (
    ModularMonolithEventDispatcher,
)
from direttore.core.modular_monolith_support.execution_dependencies import (
    ModularMonolithExecutionDependencyContext,
    ModularMonolithExecutionDependencyRegistry,
)
from direttore.core.modular_monolith_support.execution_runtime import (
    ModularMonolithExecutionRuntime,
)
from direttore.core.modular_monolith_support.uow_routing_registries.base_uow_routing_registry import (
    UowRoutingRegistryItem,
)
from direttore.core.modular_monolith_support.uow_routing_registries.event_uow_routing_registry import (
    EventUowRoutingRegistry,
)
from direttore.core.modular_monolith_support.uow_routing_registries.query_uow_routing_registry import (
    QueryUowRoutingRegistry,
)
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.primitives.container import Container
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.registries.event_handler_registry import EventHandlerRegistry
from direttore.core.registries.query_handler_registry import QueryHandlerRegistry
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.resolvers.event_handler_resolver import EventHandlerResolver
from direttore.core.resolvers.query_handler_resolver import QueryHandlerResolver
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)

type ModularSlotProviderFactory = Callable[
    [Callable[[], ModularMonolithExecutionSlot]],
    ExecutionSlotProvider[ModularMonolithExecutionSlot],
]


class ModularMonolithDirettoreApplication:
    def __init__(
        self,
        *,
        config: ModularMonolithDirettoreConfig,
        container: Container,
        execution_dependencies_registry: (
            ModularMonolithExecutionDependencyRegistry | None
        ) = None,
        slot_provider_factory: ModularSlotProviderFactory | None = None,
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self.config = config
        self.container = container
        self.execution_dependencies_registry = execution_dependencies_registry
        dependency_types = (
            execution_dependencies_registry.registered_dependency_types()
            if execution_dependencies_registry is not None
            else set()
        )
        self.use_case_registry = UseCaseHandlerRegistry.merge_many(
            [context.use_case_registry for context in config.contexts],
            source_name="modular_monolith",
        )
        self.query_registry = self._merge_query_registries(config.contexts)
        self.event_registry = self._merge_event_registries(config.contexts)
        self.use_case_uow_routing = UseCaseUowRoutingRegistry.from_registry_items(
            [
                UowRoutingRegistryItem(
                    registry=context.use_case_registry,
                    root_uow_type=context.use_case_root_uow_type,
                )
                for context in config.contexts
            ]
        )
        self.query_uow_routing = self._build_query_routing(config.contexts)
        self.use_case_resolver = UseCaseHandlerResolver(
            registry=self.use_case_registry,
            container=container,
            execution_dependency_types=dependency_types,
        )
        self.query_resolver = (
            QueryHandlerResolver(
                registry=self.query_registry,
                container=container,
                execution_dependency_types=dependency_types,
            )
            if self.query_registry is not None
            else None
        )
        self.event_dispatcher = self._build_event_dispatcher(
            config.contexts, dependency_types
        )
        if slot_provider_factory is None:
            self.slot_provider = PoolExecutionSlotProvider(
                slot_factory=self._create_slot,
                initial_slot_count=initial_slot_count,
                max_slot_count=max_slot_count,
            )
        else:
            self.slot_provider = slot_provider_factory(self._create_slot)

    async def acquire_slot(self, *, saga_id: str | None = None) -> SlotLease:
        return await self.slot_provider.acquire(saga_id=saga_id)

    @asynccontextmanager
    async def slot(self, *, saga_id: str | None = None) -> AsyncGenerator[SlotLease]:
        lease = await self.acquire_slot(saga_id=saga_id)
        try:
            yield lease
        finally:
            await lease.release()

    async def handle(self, command, *, input, trace=None, saga_id=None):
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle(command, input=input, trace=trace)

    async def handle_by_key(self, key, payload, *, input, trace=None, saga_id=None):
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle_by_key(key, payload, input=input, trace=trace)

    async def handle_operation(self, operation_id, *, input, trace=None, saga_id=None):
        async with self.slot(saga_id=saga_id) as lease:
            async with lease.transaction():
                return await lease.handle_operation(
                    operation_id, input=input, trace=trace
                )

    async def handle_query(self, query, *, input, trace=None):
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query(query, input=input, trace=trace)

    async def handle_query_by_key(self, key, payload, *, input, trace=None):
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query_by_key(
                    key, payload, input=input, trace=trace
                )

    async def handle_query_operation(self, operation_id, *, input, trace=None):
        async with self.slot() as lease:
            async with lease.transaction():
                return await lease.handle_query_operation(
                    operation_id, input=input, trace=trace
                )

    async def compensate_saga(self, saga_id, *, input=None, trace=None):
        async with self.slot() as lease:
            async with lease.transaction():
                await lease.compensate_saga(saga_id, input=input, trace=trace)

    def validate(self) -> None:
        self.use_case_resolver.validate()
        if self.query_resolver is not None:
            self.query_resolver.validate()
        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_provider_stats(self) -> ExecutionSlotProviderStats:
        return self.slot_provider.stats()

    def slot_pool_stats(self) -> ExecutionSlotProviderStats:
        return self.slot_provider_stats()

    def _create_slot(self) -> ModularMonolithExecutionSlot:
        holder = self.config.slot.resource_holder_factory()
        coordinator = self.config.slot.coordinator_factory(holder)
        event_queue = EventQueue()
        runtime = ModularMonolithExecutionRuntime(
            coordinator=coordinator,
            event_queue=event_queue,
            use_case_resolver=self.use_case_resolver,
            use_case_uow_routing=self.use_case_uow_routing,
            query_resolver=self.query_resolver,
            query_uow_routing=self.query_uow_routing,
        )
        if self.execution_dependencies_registry is not None:
            runtime._set_dependency_overrides(
                self.execution_dependencies_registry.build_overrides(
                    context=ModularMonolithExecutionDependencyContext(runtime=runtime)
                )
            )
        return ModularMonolithExecutionSlot(
            use_case_resolver=self.use_case_resolver,
            use_case_uow_routing=self.use_case_uow_routing,
            query_resolver=self.query_resolver,
            query_uow_routing=self.query_uow_routing,
            event_dispatcher=self.event_dispatcher,
            resource_holder=holder,
            coordinator=coordinator,
            runtime=runtime,
            event_queue=event_queue,
            use_case_payload_loader=self.config.use_case_execution.operation_loader,
            query_payload_loader=self.config.query_execution.operation_loader,
            span_factory=self.config.span_factory,
            saga_journal=self.config.saga_journal,
            max_processed_events=self.config.use_case_execution.max_processed_events,
        )

    @staticmethod
    def _merge_query_registries(contexts):
        registries = [c.query_registry for c in contexts if c.query_registry]
        return (
            QueryHandlerRegistry.merge_many(registries, source_name="modular_monolith")
            if registries
            else None
        )

    @staticmethod
    def _merge_event_registries(contexts):
        registries = [c.event_registry for c in contexts if c.event_registry]
        return (
            EventHandlerRegistry.merge_many(registries, source_name="modular_monolith")
            if registries
            else None
        )

    @staticmethod
    def _build_query_routing(contexts):
        items = [
            UowRoutingRegistryItem(
                registry=c.query_registry,
                root_uow_type=c.query_root_uow_type,
            )
            for c in contexts
            if c.query_registry is not None and c.query_root_uow_type is not None
        ]
        return QueryUowRoutingRegistry.from_registry_items(items) if items else None

    def _build_event_dispatcher(self, contexts, dependency_types):
        if self.event_registry is None:
            return None
        items = [
            UowRoutingRegistryItem(
                registry=c.event_registry,
                root_uow_type=c.use_case_root_uow_type,
            )
            for c in contexts
            if c.event_registry is not None
        ]
        routing = EventUowRoutingRegistry.from_registry_items(items)
        return ModularMonolithEventDispatcher(
            resolver=EventHandlerResolver(
                registry=self.event_registry,
                container=self.container,
                execution_dependency_types=dependency_types,
            ),
            event_uow_routing=routing,
        )
