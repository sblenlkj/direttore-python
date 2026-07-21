from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from direttore.core.engines.config import UseCaseEngineConfig
from direttore.core.modules.auth import (
    SimpleServiceAuthConfig,
    SimpleServiceSessionAuthConfig,
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

type UseCaseUnitOfWorkFactory = Callable[
    [AbstractUseCaseResourceHolder],
    BaseUnitOfWork,
]

type QueryUnitOfWorkFactory = Callable[
    [QueryResourceHolder],
    BaseUnitOfWork,
]


class SimpleServiceConfigError(Exception):
    pass


class InvalidSimpleServiceSlotConfigError(SimpleServiceConfigError):
    pass


class InvalidSimpleServiceHandlerConfigError(SimpleServiceConfigError):
    pass


@dataclass(frozen=True)
class SimpleServiceTracingConfig[TraceInputT, TraceT]:
    trace_resolver: TraceResolver[TraceInputT, TraceT] | None = None
    tracer: Tracer[TraceT] | None = None


@dataclass(frozen=True)
class SimpleServiceSlotConfig:
    use_case_resource_holder_factory: UseCaseResourceHolderFactory
    use_case_uow_factory: UseCaseUnitOfWorkFactory
    query_resource_holder_factory: QueryResourceHolderFactory | None = None
    query_uow_factory: QueryUnitOfWorkFactory | None = None

    def __post_init__(self) -> None:
        has_query_resource_holder_factory = (
            self.query_resource_holder_factory is not None
        )
        has_query_uow_factory = self.query_uow_factory is not None

        if has_query_resource_holder_factory != has_query_uow_factory:
            raise InvalidSimpleServiceSlotConfigError(
                "Query slot configuration is incomplete. "
                "Both query_resource_holder_factory and query_uow_factory "
                "must be provided together."
            )

    @property
    def has_use_case(self) -> bool:
        return True

    @property
    def has_query(self) -> bool:
        return (
            self.query_resource_holder_factory is not None
            and self.query_uow_factory is not None
        )


@dataclass(frozen=True)
class SimpleServiceHandlerConfig:
    use_case_registry: UseCaseHandlerRegistry
    query_registry: QueryHandlerRegistry | None = None
    event_registry: EventHandlerRegistry | None = None


@dataclass(frozen=True)
class SimpleServiceDirettoreConfig[AuthInputT, AuthT, TraceInputT, TraceT]:
    slot: SimpleServiceSlotConfig
    handlers: SimpleServiceHandlerConfig
    auth: SimpleServiceAuthConfig[AuthInputT, AuthT] | SimpleServiceSessionAuthConfig[AuthInputT, AuthT] | None = None
    tracing: SimpleServiceTracingConfig[TraceInputT, TraceT] | None = None
    use_case_engine: UseCaseEngineConfig = field(
        default_factory=UseCaseEngineConfig,
    )

    def __post_init__(self) -> None:
        if self.slot.has_query and self.handlers.query_registry is None:
            raise InvalidSimpleServiceHandlerConfigError(
                "query_registry is required when query slot configuration is "
                "provided."
            )

        if not self.slot.has_query and self.handlers.query_registry is not None:
            raise InvalidSimpleServiceHandlerConfigError(
                "query_registry was provided, but query slot configuration is "
                "not configured."
            )

        if self.handlers.event_registry is not None and not self.slot.has_use_case:
            raise InvalidSimpleServiceHandlerConfigError(
                "event_registry requires use case slot configuration. "
                "Events are dispatched from use case execution."
            )