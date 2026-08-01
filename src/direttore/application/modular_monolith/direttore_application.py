from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.execution_slot_pool import (
    ExecutionSlotPool,
    ExecutionSlotPoolStats,
)
from direttore.application.modular_monolith.config import (
    ModularMonolithDirettoreConfig,
    ModularMonolithDirettoreContext,
)
from direttore.application.modular_monolith.execution_slot import (
    ModularMonolithExecutionSlot,
)
from direttore.core.contracts.handlers import (
    QueryHandlerResult,
    UseCaseHandlerResult,
)
from direttore.core.contracts.messages import Query, UseCaseCommand
from direttore.core.engines.modular_monolith.modular_monolith_query_engine import (
    ModularMonolithQueryEngine,
)
from direttore.core.engines.modular_monolith.modular_monolith_use_case_engine import (
    ModularMonolithUseCaseEngine,
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
from direttore.core.registries.event_handler_registry import (
    EventHandlerRegistry,
)
from direttore.core.registries.query_handler_registry import (
    QueryHandlerRegistry,
)
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.resolvers.event_handler_resolver import (
    EventHandlerResolver,
)
from direttore.core.resolvers.query_handler_resolver import (
    QueryHandlerResolver,
)
from direttore.core.resolvers.use_case_handler_resolver import (
    UseCaseHandlerResolver,
)


class ModularMonolithDirettoreApplication:
    def __init__(
        self,
        *,
        config: ModularMonolithDirettoreConfig,
        container: Container,
        execution_dependencies_registry: (
            ModularMonolithExecutionDependencyRegistry | None
        ) = None,
        initial_slot_count: int = 5,
        max_slot_count: int = 20,
    ) -> None:
        self.config = config
        self.container = container
        self.execution_dependencies_registry = execution_dependencies_registry

        execution_dependency_types = self._get_execution_dependency_types()

        use_case_registry = self._build_use_case_registry(
            contexts=self.config.contexts,
        )
        query_registry = self._build_query_registry(
            contexts=self.config.contexts,
        )

        self.use_case_uow_routing = self._build_use_case_uow_routing(
            contexts=self.config.contexts,
        )
        self.query_uow_routing = self._build_query_uow_routing(
            contexts=self.config.contexts,
        )

        self.use_case_resolver = UseCaseHandlerResolver(
            registry=use_case_registry,
            container=self.container,
            execution_dependency_types=execution_dependency_types,
        )
        self.query_resolver = self._build_query_resolver(
            registry=query_registry,
            execution_dependency_types=execution_dependency_types,
        )

        self.event_dispatcher = self._build_event_dispatcher(
            contexts=self.config.contexts,
            execution_dependency_types=execution_dependency_types,
        )

        self.use_case_engine = ModularMonolithUseCaseEngine(
            resolver=self.use_case_resolver,
            use_case_uow_routing=self.use_case_uow_routing,
            event_dispatcher=self.event_dispatcher,
            span_factory=self.config.span_factory,
            config=self.config.use_case_engine,
        )
        self.query_engine = self._build_query_engine()

        self.slot_pool = ExecutionSlotPool[ModularMonolithExecutionSlot](
            slot_factory=self._create_slot,
            initial_slot_count=initial_slot_count,
            max_slot_count=max_slot_count,
        )

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle(
                command=command,
                input=input,
                trace=trace,
            )

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle_by_key(
                key=key,
                payload=payload,
                input=input,
                trace=trace,
            )

    async def handle_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> UseCaseHandlerResult:
        async with self.slot_pool.acquire() as slot:
            return await slot.handle_operation(
                operation_id=operation_id,
                input=input,
                trace=trace,
            )


    async def handle_query(
        self,
        query: Query,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query(
                query=query,
                input=input,
                trace=trace,
            )

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query_by_key(
                key=key,
                payload=payload,
                input=input,
                trace=trace,
            )

    async def handle_query_operation(
        self,
        operation_id: int | str,
        *,
        input: object,
        trace: object | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Simple service query execution is not configured."
            )

        async with self.slot_pool.acquire() as slot:
            return await slot.handle_query_operation(
                operation_id=operation_id,
                input=input,
                trace=trace,
            )


    def validate(self) -> None:
        self.use_case_engine.resolver.validate()

        if self.query_engine is not None:
            self.query_engine.resolver.validate()

        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_pool_stats(self) -> ExecutionSlotPoolStats:
        return self.slot_pool.stats()

    def _create_slot(
        self,
    ) -> ModularMonolithExecutionSlot:
        use_case_resource_holder = (
            self.config.slot.use_case_resource_holder_factory()
        )

        query_resource_holder = None
        if self.config.slot.query_resource_holder_factory is not None:
            query_resource_holder = (
                self.config.slot.query_resource_holder_factory()
            )

        coordinator = self.config.slot.coordinator_factory(
            use_case_resource_holder,
            query_resource_holder,
        )
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
            dependency_overrides = dict(
                self.execution_dependencies_registry.build_overrides(
                    context=ModularMonolithExecutionDependencyContext(
                        runtime=runtime,
                    ),
                )
            )
            runtime._set_dependency_overrides(
                dependency_overrides,
            )

        return ModularMonolithExecutionSlot(
            use_case_engine=self.use_case_engine,
            use_case_resource_holder=use_case_resource_holder,
            coordinator=coordinator,
            runtime=runtime,
            event_queue=event_queue,
            query_engine=self.query_engine,
            query_resource_holder=query_resource_holder,
        )

    def _get_execution_dependency_types(
        self,
    ) -> set[type[Any]]:
        if self.execution_dependencies_registry is None:
            return set()

        return (
            self.execution_dependencies_registry
            .registered_dependency_types()
        )

    def _build_use_case_registry(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> UseCaseHandlerRegistry:
        return UseCaseHandlerRegistry.merge_many(
            registries=[
                context.use_case_registry
                for context in contexts
            ],
            source_name="modular_monolith",
        )

    def _build_query_registry(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> QueryHandlerRegistry | None:
        query_registries = [
            context.query_registry
            for context in contexts
            if context.query_registry is not None
        ]

        if not query_registries:
            return None

        return QueryHandlerRegistry.merge_many(
            registries=query_registries,
            source_name="modular_monolith",
        )

    def _build_event_registry(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> EventHandlerRegistry | None:
        event_registries = [
            context.event_registry
            for context in contexts
            if context.event_registry is not None
        ]

        if not event_registries:
            return None

        return EventHandlerRegistry.merge_many(
            registries=event_registries,
            source_name="modular_monolith",
        )

    def _build_use_case_uow_routing(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> UseCaseUowRoutingRegistry:
        return UseCaseUowRoutingRegistry.from_registry_items(
            [
                UowRoutingRegistryItem(
                    registry=context.use_case_registry,
                    root_uow_type=context.use_case_root_uow_type,
                )
                for context in contexts
            ]
        )

    def _build_query_uow_routing(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> QueryUowRoutingRegistry | None:
        items = [
            UowRoutingRegistryItem(
                registry=context.query_registry,
                root_uow_type=context.query_root_uow_type,
            )
            for context in contexts
            if context.query_registry is not None
            and context.query_root_uow_type is not None
        ]

        if not items:
            return None

        return QueryUowRoutingRegistry.from_registry_items(
            items,
        )

    def _build_event_uow_routing(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> EventUowRoutingRegistry | None:
        items = [
            UowRoutingRegistryItem(
                registry=context.event_registry,
                root_uow_type=context.use_case_root_uow_type,
            )
            for context in contexts
            if context.event_registry is not None
        ]

        if not items:
            return None

        return EventUowRoutingRegistry.from_registry_items(
            items,
        )

    def _build_query_resolver(
        self,
        *,
        registry: QueryHandlerRegistry | None,
        execution_dependency_types: set[type[Any]],
    ) -> QueryHandlerResolver | None:
        if registry is None:
            return None

        return QueryHandlerResolver(
            registry=registry,
            container=self.container,
            execution_dependency_types=execution_dependency_types,
        )

    def _build_query_engine(
        self,
    ) -> ModularMonolithQueryEngine | None:
        if (
            self.query_resolver is None
            or self.query_uow_routing is None
        ):
            return None

        return ModularMonolithQueryEngine(
            resolver=self.query_resolver,
            query_uow_routing=self.query_uow_routing,
            span_factory=self.config.span_factory,
            config=self.config.query_engine,
        )

    def _build_event_dispatcher(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
        execution_dependency_types: set[type[Any]],
    ) -> ModularMonolithEventDispatcher | None:
        event_registry = self._build_event_registry(
            contexts=contexts,
        )

        if event_registry is None:
            return None

        event_uow_routing = self._build_event_uow_routing(
            contexts=contexts,
        )

        if event_uow_routing is None:
            raise RuntimeError(
                "Event registry is configured, but event UoW routing could "
                "not be built."
            )

        event_resolver = EventHandlerResolver(
            registry=event_registry,
            container=self.container,
            execution_dependency_types=execution_dependency_types,
        )

        return ModularMonolithEventDispatcher(
            resolver=event_resolver,
            event_uow_routing=event_uow_routing,
        )
