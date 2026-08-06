from __future__ import annotations

from typing import Any

from direttore.application.modular_monolith.config import (
    ModularMonolithDirettoreContext,
    ModularMonolithSlotCreatorConfig,
)
from direttore.application.modular_monolith.execution_slot import (
    ModularMonolithExecutionSlot,
)
from direttore.application.slot_provider import SlotCreator
from direttore.core.contracts.lifecycle import Lifecycle
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
from direttore.core.modular_monolith_support.uow_routing_registries.use_case_uow_routing_registry import (
    UseCaseUowRoutingRegistry,
)
from direttore.core.primitives.container import Container
from direttore.core.primitives.event_queue import EventQueue
from direttore.core.registries.event_handler_registry import EventHandlerRegistry
from direttore.core.registries.use_case_handler_registry import UseCaseHandlerRegistry
from direttore.core.resolvers.event_handler_resolver import EventHandlerResolver
from direttore.core.resolvers.use_case_handler_resolver import UseCaseHandlerResolver


class ModularMonolithSlotCreator[InputT, TraceT](
    SlotCreator[ModularMonolithExecutionSlot[InputT, TraceT], InputT, TraceT]
):
    """Builds shared routing plus each modular-monolith execution slot."""

    def __init__(
        self,
        *,
        config: ModularMonolithSlotCreatorConfig[InputT, TraceT],
        container: Container,
        execution_dependencies_registry: (
            ModularMonolithExecutionDependencyRegistry | None
        ) = None,
    ) -> None:
        self.config = config
        self.container = container
        self.execution_dependencies_registry = execution_dependencies_registry
        dependency_types = (
            execution_dependencies_registry.registered_dependency_types()
            if execution_dependencies_registry is not None
            else set()
        )
        self.use_case_registry: UseCaseHandlerRegistry[
            Lifecycle[InputT | None, Any]
        ] = UseCaseHandlerRegistry.merge_many(
            [context.use_case_registry for context in config.contexts],
            source_name="modular_monolith",
        )
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
        self.use_case_resolver: UseCaseHandlerResolver[
            Lifecycle[InputT | None, Any]
        ] = UseCaseHandlerResolver(
            registry=self.use_case_registry,
            container=container,
            execution_dependency_types=dependency_types,
        )
        self.event_dispatcher = self._build_event_dispatcher(
            config.contexts, dependency_types
        )

    def create_slot(self) -> ModularMonolithExecutionSlot[InputT, TraceT]:
        holder = self.config.slot.resource_holder_factory()
        coordinator = self.config.slot.coordinator_factory(holder)
        event_queue = EventQueue()
        runtime = ModularMonolithExecutionRuntime(
            coordinator=coordinator,
            event_queue=event_queue,
            use_case_resolver=self.use_case_resolver,
            use_case_uow_routing=self.use_case_uow_routing,
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
            event_dispatcher=self.event_dispatcher,
            resource_holder=holder,
            coordinator=coordinator,
            runtime=runtime,
            event_queue=event_queue,
            use_case_payload_loader=self.config.use_case_execution.operation_loader,
            span_factory=self.config.span_factory,
            saga_journal=self.config.saga_journal,
            max_processed_events=self.config.use_case_execution.max_processed_events,
        )

    def validate(self) -> None:
        self.use_case_resolver.validate()
        if self.event_dispatcher is not None:
            self.event_dispatcher.validate_event_handlers()

    @staticmethod
    def _merge_event_registries(
        contexts: list[ModularMonolithDirettoreContext[InputT]],
    ) -> EventHandlerRegistry | None:
        registries = [
            context.event_registry for context in contexts if context.event_registry
        ]
        return (
            EventHandlerRegistry.merge_many(registries, source_name="modular_monolith")
            if registries
            else None
        )

    def _build_event_dispatcher(
        self,
        contexts: list[ModularMonolithDirettoreContext[InputT]],
        dependency_types: set[type[Any]],
    ) -> ModularMonolithEventDispatcher | None:
        if self.event_registry is None:
            return None
        routing = EventUowRoutingRegistry.from_registry_items(
            [
                UowRoutingRegistryItem(
                    registry=context.event_registry,
                    root_uow_type=context.use_case_root_uow_type,
                )
                for context in contexts
                if context.event_registry is not None
            ]
        )
        return ModularMonolithEventDispatcher(
            resolver=EventHandlerResolver(
                registry=self.event_registry,
                container=self.container,
                execution_dependency_types=dependency_types,
            ),
            event_uow_routing=routing,
        )
