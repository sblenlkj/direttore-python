from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from direttore.core.contracts.operation_loader import SimpleServiceOperationLoader
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.event_handler_registry import EventHandlerRegistry
from direttore.core.registries.query_handler_registry import QueryHandlerRegistry
from direttore.core.registries.use_case_handler_registry import (
    UseCaseHandlerRegistry,
)
from direttore.core.saga import SagaJournal
from direttore.core.tracing import SpanFactory

type ResourceHolderFactory = Callable[[], ResourceHolder]
type UnitOfWorkFactory = Callable[[ResourceHolder], BaseUnitOfWork]


@dataclass(frozen=True, slots=True)
class SimpleServiceUseCaseExecutionConfig:
    operation_loader: SimpleServiceOperationLoader | None = None
    max_processed_events: int = 100


@dataclass(frozen=True, slots=True)
class SimpleServiceQueryExecutionConfig:
    operation_loader: SimpleServiceOperationLoader | None = None


@dataclass(frozen=True, slots=True)
class SimpleServiceSlotConfig:
    resource_holder_factory: ResourceHolderFactory
    uow_factory: UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class SimpleServiceHandlerConfig:
    use_case_registry: UseCaseHandlerRegistry
    query_registry: QueryHandlerRegistry | None = None
    event_registry: EventHandlerRegistry | None = None


@dataclass(frozen=True, slots=True)
class SimpleServiceDirettoreConfig:
    slot: SimpleServiceSlotConfig
    handlers: SimpleServiceHandlerConfig
    span_factory: SpanFactory[object] | None = None
    saga_journal: SagaJournal | None = None
    use_case_execution: SimpleServiceUseCaseExecutionConfig = field(
        default_factory=SimpleServiceUseCaseExecutionConfig,
    )
    query_execution: SimpleServiceQueryExecutionConfig = field(
        default_factory=SimpleServiceQueryExecutionConfig,
    )
