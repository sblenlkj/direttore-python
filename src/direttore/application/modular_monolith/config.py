from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from direttore.core.contracts.lifecycle import Lifecycle
from direttore.core.contracts.operation_loader import OperationLoader
from direttore.core.modular_monolith_support.coordinator import (
    ModularUnitOfWorkCoordinator,
)
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.primitives.uow import BaseUnitOfWork
from direttore.core.registries.event_handler_registry import EventHandlerRegistry
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
    operation_loader: OperationLoader | None = None
    max_processed_events: int = 100


@dataclass(frozen=True, slots=True)
class ModularMonolithDirettoreContext[InputT]:
    use_case_registry: UseCaseHandlerRegistry[Lifecycle[InputT | None, Any]]
    use_case_root_uow_type: type[BaseUnitOfWork]
    event_registry: EventHandlerRegistry | None = None

    def __post_init__(self) -> None:
        if not issubclass(self.use_case_root_uow_type, BaseUnitOfWork):
            raise TypeError("use_case_root_uow_type must be a BaseUnitOfWork.")


@dataclass(frozen=True, slots=True)
class ModularMonolithSlotConfig:
    resource_holder_factory: ResourceHolderFactory
    coordinator_factory: ModularUnitOfWorkCoordinatorFactory


@dataclass(frozen=True, slots=True)
class ModularMonolithSlotCreatorConfig[InputT, TraceT]:
    slot: ModularMonolithSlotConfig
    contexts: list[ModularMonolithDirettoreContext[InputT]]
    span_factory: SpanFactory[TraceT] | None = None
    saga_journal: SagaJournal | None = None
    use_case_execution: ModularMonolithUseCaseExecutionConfig = field(
        default_factory=ModularMonolithUseCaseExecutionConfig,
    )

    def __post_init__(self) -> None:
        if not self.contexts:
            raise ValueError("At least one modular context is required.")
