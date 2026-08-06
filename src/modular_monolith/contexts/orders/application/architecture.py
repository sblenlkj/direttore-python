from direttore import (
    EventHandlerContext,
    EventHandlerRegistry,
    UseCaseHandlerContext,
    UseCaseHandlerRegistry,
)
from direttore.core.tracing import Span
from modular_monolith.contexts.orders.application.ports.unit_of_work import (
    OrdersUnitOfWork,
)
from modular_monolith.shared.lifecycle import RequestContext, RequestLifecycle

type OrdersHandlerContext = UseCaseHandlerContext[
    OrdersUnitOfWork,
    RequestContext,
    Span,
]
type OrdersEventContext = EventHandlerContext[OrdersUnitOfWork, Span]

use_case_registry = UseCaseHandlerRegistry[RequestLifecycle](
    source_name="orders",
    default_lifecycle=RequestLifecycle(),
)
event_registry = EventHandlerRegistry(source_name="orders")

