from dataclasses import dataclass

from direttore import ResourceHolder, UseCaseHandlerConfig
from direttore.core.contracts import Lifecycle
from direttore.core.tracing import Span


@dataclass(frozen=True, slots=True)
class RequestInput:
    actor_id: str
    correlation_id: str


@dataclass(frozen=True, slots=True)
class RequestContext:
    actor_id: str | None
    correlation_id: str | None


class RequestLifecycle(Lifecycle[RequestInput | None, RequestContext]):
    async def create_context(
        self,
        input: RequestInput | None,
        config: UseCaseHandlerConfig,
        resource: ResourceHolder,
        span: Span | None,
    ) -> RequestContext:
        return RequestContext(
            actor_id=input.actor_id if input is not None else None,
            correlation_id=input.correlation_id if input is not None else None,
        )

