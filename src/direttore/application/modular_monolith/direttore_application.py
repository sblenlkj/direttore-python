from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from direttore.application.execution_slot_pool import (
    ExecutionSlotPool,
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
from direttore.core.contracts.messages import (
    Query,
    UseCaseCommand,
)
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
    ModularMonolithExecutionDependencyRegistry,
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
from direttore.core.tracing import Tracer
from direttore.core.primitives.container import Container
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


class ModularMonolithDirettoreApplication[
    AuthInputT,
    AuthT,
    TraceInputT,
    TraceT,
]:
    def __init__(
        self,
        *,
        config: ModularMonolithDirettoreConfig[
            AuthInputT,
            AuthT,
            TraceInputT,
            TraceT,
        ],
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

        execution_dependency_types: set[type[Any]] = set()
        if execution_dependencies_registry is not None:
            execution_dependency_types = (
                execution_dependencies_registry.registered_dependency_types()
            )

        use_case_registry = self._build_use_case_registry(
            contexts=self.config.contexts,
        )
        use_case_uow_routing = self._build_use_case_uow_routing(
            contexts=self.config.contexts,
        )

        use_case_resolver = UseCaseHandlerResolver(
            registry=use_case_registry,
            container=self.container,
            execution_dependency_types=execution_dependency_types,
        )

        self.event_dispatcher = self._build_event_dispatcher(
            contexts=self.config.contexts,
            execution_dependency_types=execution_dependency_types,
        )

        self.use_case_engine = ModularMonolithUseCaseEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ](
            resolver=use_case_resolver,
            use_case_uow_routing=use_case_uow_routing,
            event_dispatcher=self.event_dispatcher,
            config=self.config.use_case_engine,
        )

        self.query_engine = self._build_query_engine(
            contexts=self.config.contexts,
            execution_dependency_types=execution_dependency_types,
        )

        self.slot_pool = ExecutionSlotPool[
            ModularMonolithExecutionSlot[AuthInputT, AuthT, TraceT]
        ](
            slot_factory=self._create_slot,
            initial_slot_count=initial_slot_count,
            max_slot_count=max_slot_count,
        )

    async def handle(
        self,
        command: UseCaseCommand,
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> UseCaseHandlerResult:
        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle(
                command=command,
                auth_config=self.config.auth,
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> UseCaseHandlerResult:
        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_by_key(
                key=key,
                payload=payload,
                auth_config=self.config.auth,
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_query(
        self,
        query: Query,
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_query(
                query=query,
                auth_config=self.config.auth,
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    async def handle_query_by_key(
        self,
        key: str,
        payload: Mapping[str, Any],
        *,
        auth_input: AuthInputT | None = None,
        trace_input: TraceInputT | None = None,
    ) -> QueryHandlerResult:
        if self.query_engine is None:
            raise RuntimeError(
                "Modular monolith query execution is not configured."
            )

        slot = await self.slot_pool.acquire()

        try:
            trace = self._resolve_trace(trace_input)

            return await slot.handle_query_by_key(
                key=key,
                payload=payload,
                auth_config=self.config.auth,
                auth_input=auth_input,
                trace=trace,
                tracer=self._get_tracer(),
            )
        finally:
            await self.slot_pool.release(slot)

    def validate(self) -> None:
        self.use_case_engine.resolver.validate()

        if self.query_engine is not None:
            self.query_engine.resolver.validate()

        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    def slot_pool_stats(self):
        return self.slot_pool.stats()

    def _create_slot(
        self,
    ) -> ModularMonolithExecutionSlot[AuthInputT, AuthT, TraceT]:
        return ModularMonolithExecutionSlot(
            slot_config=self.config.slot,
            use_case_engine=self.use_case_engine,
            query_engine=self.query_engine,
            auth_config=self.config.auth,
            tracer=self._get_tracer(),
            dependency_registry=self.execution_dependencies_registry,
        )

    def _build_use_case_registry(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
    ) -> UseCaseHandlerRegistry:
        return UseCaseHandlerRegistry.merge_many(
            registries=[
                context.use_case_registry for context in contexts
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

        return QueryUowRoutingRegistry.from_registry_items(items)

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

        return EventUowRoutingRegistry.from_registry_items(items)

    def _build_query_engine(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
        execution_dependency_types: set[type[Any]] | None = None,
    ) -> ModularMonolithQueryEngine[AuthInputT, AuthT, TraceT] | None:
        query_registry = self._build_query_registry(
            contexts=contexts,
        )

        if query_registry is None:
            return None

        query_uow_routing = self._build_query_uow_routing(
            contexts=contexts,
        )

        if query_uow_routing is None:
            raise RuntimeError(
                "Query registry is configured, but query UoW routing could "
                "not be built."
            )

        query_resolver = QueryHandlerResolver(
            registry=query_registry,
            container=self.container,
            execution_dependency_types=execution_dependency_types,
        )

        return ModularMonolithQueryEngine[
            AuthInputT,
            AuthT,
            TraceT,
        ](
            resolver=query_resolver,
            query_uow_routing=query_uow_routing,
        )

    def _build_event_dispatcher(
        self,
        *,
        contexts: list[ModularMonolithDirettoreContext],
        execution_dependency_types: set[type[Any]] | None = None,
    ) -> ModularMonolithEventDispatcher[TraceT] | None:
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

        return ModularMonolithEventDispatcher[TraceT](
            resolver=event_resolver,
            event_uow_routing=event_uow_routing,
        )

    def _resolve_trace(
        self,
        trace_input: TraceInputT | None,
    ) -> TraceT | None:
        if self.config.tracing is None:
            return None

        if self.config.tracing.trace_resolver is None:
            return None

        return self.config.tracing.trace_resolver.resolve_trace(
            trace_input,
        )

    def _get_tracer(self) -> Tracer[TraceT] | None:
        if self.config.tracing is None:
            return None

        return self.config.tracing.tracer