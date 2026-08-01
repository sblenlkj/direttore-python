from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from direttore.core.engines.modular_monolith.modular_monolith_config import (
    ModularMonolithUseCaseEngineConfig,
    ModularMonolithQueryEngineConfig,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.primitives.resource_holder import (
    AbstractUseCaseResourceHolder,
    QueryResourceHolder,
)
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.event_handler_registry import (
    EventHandlerRegistry,
)
from direttore.core.registries.query_handler_registry import (
    QueryHandlerRegistry,
)
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.tracing import SpanFactory


type UseCaseResourceHolderFactory = Callable[
    [],
    AbstractUseCaseResourceHolder,
]

type QueryResourceHolderFactory = Callable[
    [],
    QueryResourceHolder,
]

type ModularUnitOfWorkCoordinatorFactory = Callable[
    [AbstractUseCaseResourceHolder, QueryResourceHolder | None],
    ModularUnitOfWorkCoordinator,
]


class ModularMonolithConfigError(Exception):
    pass


class InvalidModularMonolithContextError(ModularMonolithConfigError):
    pass


class InvalidModularMonolithSlotConfigError(ModularMonolithConfigError):
    pass


@dataclass(frozen=True, slots=True)
class ModularMonolithDirettoreContext:
    use_case_registry: UseCaseHandlerRegistry
    use_case_root_uow_type: type[BaseUnitOfWork]
    query_registry: QueryHandlerRegistry | None = None
    query_root_uow_type: type[BaseUnitOfWork] | None = None
    event_registry: EventHandlerRegistry | None = None

    def __post_init__(self) -> None:
        if not issubclass(
            self.use_case_root_uow_type,
            BaseUnitOfWork,
        ):
            raise InvalidModularMonolithContextError(
                "use_case_root_uow_type must inherit from BaseUnitOfWork."
            )

        has_query_registry = self.query_registry is not None
        has_query_root_uow_type = self.query_root_uow_type is not None

        if has_query_registry != has_query_root_uow_type:
            raise InvalidModularMonolithContextError(
                "Query context configuration is incomplete. "
                "Both query_registry and query_root_uow_type must be "
                "provided together."
            )

        if (
            self.query_root_uow_type is not None
            and not issubclass(
                self.query_root_uow_type,
                BaseUnitOfWork,
            )
        ):
            raise InvalidModularMonolithContextError(
                "query_root_uow_type must inherit from BaseUnitOfWork."
            )


@dataclass(frozen=True, slots=True)
class ModularMonolithSlotConfig:
    use_case_resource_holder_factory: UseCaseResourceHolderFactory
    coordinator_factory: ModularUnitOfWorkCoordinatorFactory
    query_resource_holder_factory: QueryResourceHolderFactory | None = None

    @property
    def has_query(self) -> bool:
        return self.query_resource_holder_factory is not None


@dataclass(frozen=True, slots=True)
class ModularMonolithDirettoreConfig:
    slot: ModularMonolithSlotConfig
    contexts: list[ModularMonolithDirettoreContext]
    span_factory: SpanFactory[object] | None = None
    use_case_engine: ModularMonolithUseCaseEngineConfig = field(
        default_factory=ModularMonolithUseCaseEngineConfig,
    )
    query_engine: ModularMonolithQueryEngineConfig = field(
        default_factory=ModularMonolithQueryEngineConfig,
    )

    def __post_init__(self) -> None:
        if not self.contexts:
            raise InvalidModularMonolithContextError(
                "Modular monolith application requires at least one context."
            )

        has_query_context = any(
            context.query_registry is not None
            for context in self.contexts
        )

        if has_query_context and not self.slot.has_query:
            raise InvalidModularMonolithSlotConfigError(
                "At least one context has query_registry, but "
                "query_resource_holder_factory is not configured."
            )

        if self.slot.has_query and not has_query_context:
            raise InvalidModularMonolithSlotConfigError(
                "query_resource_holder_factory is configured, but no context "
                "has query_registry."
            )
