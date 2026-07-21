from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from direttore.core.engines.config import UseCaseEngineConfig
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.modules.auth import (
    ModularMonolithAuthConfig,
    ModularMonolithSessionAuthConfig,
)
from direttore.core.tracing import (
    TraceResolver,
    Tracer,
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


@dataclass(frozen=True)
class ModularMonolithDirettoreContext:
    use_case_registry: UseCaseHandlerRegistry
    use_case_root_uow_type: type[BaseUnitOfWork]
    query_registry: QueryHandlerRegistry | None = None
    query_root_uow_type: type[BaseUnitOfWork] | None = None
    event_registry: EventHandlerRegistry | None = None

    def __post_init__(self) -> None:
        if not issubclass(self.use_case_root_uow_type, BaseUnitOfWork):
            raise InvalidModularMonolithContextError(
                "root_uow_type must inherit from BaseUnitOfWork."
            )

        if self.query_registry is not None and self.query_root_uow_type is None:
            raise InvalidModularMonolithContextError(
                "query_registry was provided, but query_root_uow_type is not "
                "configured."
            )

        if self.query_registry is None and self.query_root_uow_type is not None:
            raise InvalidModularMonolithContextError(
                "query_root_uow_type was provided, but query_registry is not "
                "configured."
            )

        if (
            self.query_root_uow_type is not None
            and not issubclass(self.query_root_uow_type, BaseUnitOfWork)
        ):
            raise InvalidModularMonolithContextError(
                "query_root_uow_type must inherit from BaseUnitOfWork."
            )

@dataclass(frozen=True)
class ModularMonolithTracingConfig[TraceInputT, TraceT]:
    trace_resolver: TraceResolver[TraceInputT, TraceT] | None = None
    tracer: Tracer[TraceT] | None = None


@dataclass(frozen=True)
class ModularMonolithSlotConfig:
    use_case_resource_holder_factory: UseCaseResourceHolderFactory
    coordinator_factory: ModularUnitOfWorkCoordinatorFactory
    query_resource_holder_factory: QueryResourceHolderFactory | None = None

    @property
    def has_query(self) -> bool:
        return self.query_resource_holder_factory is not None


@dataclass(frozen=True)
class ModularMonolithDirettoreConfig[
    AuthInputT,
    AuthT,
    TraceInputT,
    TraceT,
]:
    slot: ModularMonolithSlotConfig
    contexts: list[ModularMonolithDirettoreContext]
    auth: ModularMonolithAuthConfig[AuthInputT, AuthT] | ModularMonolithSessionAuthConfig[AuthInputT, AuthT] | None = None
    tracing: ModularMonolithTracingConfig[TraceInputT, TraceT] | None = None
    use_case_engine: UseCaseEngineConfig = UseCaseEngineConfig()

    def __post_init__(self) -> None:
        if not self.contexts:
            raise InvalidModularMonolithContextError(
                "Modular monolith application requires at least one context."
            )

        has_query_context = any(
            context.query_registry is not None for context in self.contexts
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