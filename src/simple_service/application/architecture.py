from direttore import (
    EventHandlerContext,
    EventHandlerRegistry,
    SagaCompensationContext,
    UseCaseHandlerContext,
    UseCaseHandlerRegistry,
)
from direttore.core.tracing import Span
from simple_service.application.ports.unit_of_work import ApplicationUnitOfWork
from simple_service.shared.lifecycle import RequestContext, RequestLifecycle

type ApplicationHandlerContext = UseCaseHandlerContext[
    ApplicationUnitOfWork,
    RequestContext,
    Span,
]
type ApplicationEventContext = EventHandlerContext[ApplicationUnitOfWork, Span]
type ApplicationSagaContext = SagaCompensationContext[ApplicationUnitOfWork, Span]

use_case_registry = UseCaseHandlerRegistry[RequestLifecycle](
    source_name="simple_service",
    default_lifecycle=RequestLifecycle(),
)
event_registry = EventHandlerRegistry(source_name="simple_service")

