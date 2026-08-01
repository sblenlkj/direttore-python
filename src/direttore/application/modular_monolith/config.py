from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from direttore.core.contracts.operation_loader import (
    ModularMonolithOperationLoader,
)
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
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
type ModularUnitOfWorkCoordinatorFactory = Callable[
    [ResourceHolder], ModularUnitOfWorkCoordinator
]


@dataclass(frozen=True, slots=True)
class ModularMonolithUseCaseExecutionConfig:
    operation_loader: ModularMonolithOperationLoader | None = None
    max_processed_events: int = 100


@dataclass(frozen=True, slots=True)
class ModularMonolithQueryExecutionConfig:
    operation_loader: ModularMonolithOperationLoader | None = None


@dataclass(frozen=True, slots=True)
class ModularMonolithDirettoreContext:
    use_case_registry: UseCaseHandlerRegistry
    use_case_root_uow_type: type[BaseUnitOfWork]
    query_registry: QueryHandlerRegistry | None = None
    query_root_uow_type: type[BaseUnitOfWork] | None = None
    event_registry: EventHandlerRegistry | None = None

    def __post_init__(self) -> None:
        if not issubclass(self.use_case_root_uow_type, BaseUnitOfWork):
            raise TypeError("use_case_root_uow_type must be a BaseUnitOfWork.")
        if (self.query_registry is None) != (self.query_root_uow_type is None):
            raise ValueError(
                "query_registry and query_root_uow_type must be configured together."
            )


@dataclass(frozen=True, slots=True)
class ModularMonolithSlotConfig:
    resource_holder_factory: ResourceHolderFactory
    coordinator_factory: ModularUnitOfWorkCoordinatorFactory


@dataclass(frozen=True, slots=True)
class ModularMonolithDirettoreConfig:
    slot: ModularMonolithSlotConfig
    contexts: list[ModularMonolithDirettoreContext]
    span_factory: SpanFactory[object] | None = None
    saga_journal: SagaJournal | None = None
    use_case_execution: ModularMonolithUseCaseExecutionConfig = field(
        default_factory=ModularMonolithUseCaseExecutionConfig,
    )
    query_execution: ModularMonolithQueryExecutionConfig = field(
        default_factory=ModularMonolithQueryExecutionConfig,
    )

    def __post_init__(self) -> None:
        if not self.contexts:
            raise ValueError("At least one modular context is required.")
