from direttore import (
    EventHandlerContext,
    EventHandlerRegistry,
    SagaCompensationContext,
    UseCaseHandlerContext,
    UseCaseHandlerRegistry,
)
from direttore.core.tracing import Span
from modular_monolith.contexts.warehouse.application.ports.unit_of_work import (
    WarehouseUnitOfWork,
)
from modular_monolith.shared.lifecycle import RequestContext, RequestLifecycle

type WarehouseHandlerContext = UseCaseHandlerContext[
    WarehouseUnitOfWork,
    RequestContext,
    Span,
]
type WarehouseEventContext = EventHandlerContext[WarehouseUnitOfWork, Span]
type WarehouseSagaContext = SagaCompensationContext[WarehouseUnitOfWork, Span]

use_case_registry = UseCaseHandlerRegistry[RequestLifecycle](
    source_name="warehouse",
    default_lifecycle=RequestLifecycle(),
)
event_registry = EventHandlerRegistry(source_name="warehouse")

