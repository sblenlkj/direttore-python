from direttore.core.contracts.handlers.use_case_handler import UseCaseHandlerConfig
from direttore.core.primitives.resource_holder import ResourceHolder
from direttore.core.tracing import Span


class Lifecycle[InputT, LifecycleContextT]:
    async def create_context(
        self,
        input: InputT,
        config: UseCaseHandlerConfig,
        resource: ResourceHolder,
        span: Span | None,
    ) -> LifecycleContextT:
        raise NotImplementedError
